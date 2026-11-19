"""Package listing and confirmed package-management actions."""

from __future__ import annotations

import logging
import shlex
import threading
from collections.abc import Callable
from pathlib import Path

from gxr_core.adb import AdbClient, AdbError, RealAdb, resolve_serial
from gxr_core.parsers.util import split_sections
from gxr_core.paths import default_reports_dir

from ..core.apps import (
    APP_ACTION_SPECS,
    APP_ACTIONS,
    APP_DESTRUCTIVE_ACTIONS,
    APP_LIST_SCRIPT,
    PACKAGE_FALLBACK_SCRIPT,
    build_action_command,
    build_app_rows,
    build_game_override_command,
    interpret_action_result,
    is_critical_package,
    merge_package_fallback,
    parse_du,
    parse_game_info,
    parse_package_detail,
    parse_package_lines,
    parse_package_paths,
    size_targets_for_rows,
    summarize,
    validate_game_downscale,
    validate_game_fps,
    validate_package_name,
)
from .action_log import append_action_log
from .app_install import InstallManager

log = logging.getLogger(__name__)

SIZE_BATCH_SIZE = 64

_GAME_FAILURE_MARKERS = (
    "error",
    "exception",
    "failure",
    "failed",
    "invalid",
    "not supported",
    "unsupported",
    "not found",
)


class AppsService:
    """Read package state and execute one explicitly confirmed action at a time."""

    def __init__(
        self,
        serial: str | None = None,
        reports_dir: str | None = None,
        user: int = 0,
        adb_factory: Callable[..., AdbClient] = RealAdb,
        staging_dir: str | None = None,
        busy_check: Callable[[], bool] | None = None,
    ) -> None:
        self.serial = serial
        self.user = user
        self.reports_dir = reports_dir or str(Path(default_reports_dir()) / "apps")
        self.adb_factory = adb_factory
        self.busy_check = busy_check
        self.lock = threading.Lock()
        self.device_lock = threading.Lock()
        self.install = InstallManager(
            serial=serial,
            reports_dir=self.reports_dir,
            user=user,
            staging_dir=staging_dir,
            busy_check=busy_check,
            adb_factory=adb_factory,
            device_lock=self.device_lock,
        )

    def _adb(self) -> AdbClient:
        return self.adb_factory(serial=resolve_serial(self.serial))

    def _action_specs(self) -> dict:
        specs = {}
        for name, spec in APP_ACTION_SPECS.items():
            specs[name] = {
                "label": spec["label"],
                "title": spec["title"],
                "confirm": spec["confirm"],
                "description": spec["description"],
                "command": spec["command"].format(user=self.user, package="{package}"),
                "destructive": spec["destructive"],
                "data_loss": spec["data_loss"],
            }
        return specs

    def _read_snapshot(self, adb: AdbClient, include_sizes: bool = True) -> dict:
        text = adb.shell(APP_LIST_SCRIPT, timeout=25.0)
        sections = split_sections(text)
        if not parse_package_lines("\n".join(sections.get("PACKAGES", []))):
            fallback = adb.shell(PACKAGE_FALLBACK_SCRIPT, timeout=15.0)
            merge_package_fallback(sections, fallback)
        rows = build_app_rows(sections)
        if not rows:
            raise AdbError("the device returned no installed packages")
        if include_sizes:
            self._add_sizes(adb, rows)
        return {"packages": rows, "summary": summarize(rows), "action_specs": self._action_specs()}

    def _add_sizes(self, adb: AdbClient, rows: list[dict]) -> None:
        targets = size_targets_for_rows(rows)
        sizes: dict[str, int] = {}
        items = list(targets)
        for start in range(0, len(items), SIZE_BATCH_SIZE):
            batch = items[start : start + SIZE_BATCH_SIZE]
            command = "du -sk " + " ".join(shlex.quote(target) for target in batch) + " 2>/dev/null"
            try:
                sizes.update(parse_du(adb.shell(command, timeout=20.0)))
            except Exception:
                log.debug("package size read failed", exc_info=True)
        for target, target_rows in targets.items():
            size_kb = sizes.get(target)
            if size_kb is None:
                continue
            for row in target_rows:
                row["size_kb"] = size_kb

    def list_packages(self) -> dict:
        with self.lock:
            return self._read_snapshot(self._adb())

    def detail(self, package: str, root: bool = False) -> dict:
        package = validate_package_name(package)
        with self.lock:
            adb = self._adb()
            text = adb.shell("dumpsys package " + shlex.quote(package), timeout=25.0)
            if "unable to find package" in text.lower() or "unknown package" in text.lower():
                raise LookupError(f"package not found: {package}")
            try:
                paths = parse_package_paths(adb.shell("pm path " + shlex.quote(package), timeout=10.0))
            except Exception:
                log.debug("package path read failed", exc_info=True)
                paths = []
            result = {
                "package": package,
                "detail": parse_package_detail(text, paths),
                "critical": is_critical_package(package),
                "game": self._game_detail(adb, package),
            }
            if root:
                result["root"] = self._root_detail(adb, package)
            return result

    def _game_detail(self, adb, package: str) -> dict:
        try:
            modes_text = adb.shell("cmd game list-modes " + shlex.quote(package), timeout=10.0)
            configs_text = adb.shell("cmd game list-configs " + shlex.quote(package), timeout=10.0)
        except Exception as exc:
            log.debug("game mode read failed for %s", package, exc_info=True)
            return {
                "supported": False,
                "current_mode": "",
                "available_modes": [],
                "fps": "disable",
                "downscale": "disable",
                "interventions": "No custom intervention",
                "error": str(exc),
            }
        return parse_game_info(modes_text, configs_text)

    def _root_detail(self, adb, package: str) -> dict:
        info = {
            "requested": True,
            "available": False,
            "data_kb": None,
            "cache_kb": None,
            "sizes_kb": {},
            "errors": [],
        }
        try:
            who = adb.shell("su -c id", timeout=8.0)
        except Exception as exc:
            info["errors"].append(f"root check failed: {exc}")
            return info
        if "uid=0" not in who:
            info["errors"].append(who.strip() or "su did not return uid=0")
            return info
        info["available"] = True
        paths = [f"/data/user/0/{package}", f"/data/user_de/0/{package}", f"/data/user/0/{package}/cache"]
        command = "du -sk " + " ".join(paths) + " 2>/dev/null"
        try:
            text = adb.shell("su -c " + shlex.quote(command), timeout=20.0)
        except Exception as exc:
            info["errors"].append(f"root size read failed: {exc}")
            return info
        if "permission denied" in text.lower():
            info["errors"].append("SELinux denied access to the app data directory")
        sizes = parse_du(text)
        info["sizes_kb"] = sizes
        data_kb = sizes.get(f"/data/user/0/{package}")
        if data_kb is None:
            data_kb = sizes.get(f"/data/data/{package}")
        cache_kb = sizes.get(f"/data/user/0/{package}/cache")
        if cache_kb is None:
            cache_kb = sizes.get(f"/data/data/{package}/cache")
        info["data_kb"] = data_kb
        info["cache_kb"] = cache_kb
        return info

    def run_action(self, package: str, action: str, confirm: bool = False) -> dict:
        package = validate_package_name(package)
        if action not in APP_ACTIONS:
            raise ValueError(f"unknown app action: {action}")
        if not confirm:
            raise ValueError("confirmation is required")
        if self.busy_check and self.busy_check():
            raise RuntimeError("the profiler is recording; device changes are blocked")
        if self.install.active():
            raise RuntimeError("an install is running; wait for it to finish")
        if not self.device_lock.acquire(blocking=False):
            raise RuntimeError("another device operation is running")
        try:
            if self.install.active():
                raise RuntimeError("an install is running; wait for it to finish")
            with self.lock:
                adb = self._adb()
                current = self._read_snapshot(adb, include_sizes=False)
                row = next((item for item in current["packages"] if item["package"] == package), None)
                if row is None:
                    raise LookupError(f"package not found: {package}")
                if is_critical_package(package) and action in APP_DESTRUCTIVE_ACTIONS:
                    raise PermissionError("critical system packages cannot be disabled or removed")
                if action not in row["actions"]:
                    raise ValueError(f"{action} is not available for this package in its current state")
                command = build_action_command(package, action, self.user)
                proc = adb.run(["shell", command], timeout=20.0)
                output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                ok, message = interpret_action_result(output, proc.returncode)
                result = {
                    "ok": ok,
                    "package": package,
                    "action": action,
                    "command": command,
                    "output": message,
                    "returncode": proc.returncode,
                    "kind": row["kind"],
                    "state_before": row["state"],
                }
                self._log_action(result)
                return result
        finally:
            self.device_lock.release()

    def set_game_override(self, package: str, fps: str, downscale: str, confirm: bool = False) -> dict:
        package = validate_package_name(package)
        fps = validate_game_fps(fps)
        downscale = validate_game_downscale(downscale)
        if not confirm:
            raise ValueError("confirmation is required")
        if is_critical_package(package):
            raise PermissionError("critical system packages cannot be performance-tuned")
        if self.busy_check and self.busy_check():
            raise RuntimeError("the profiler is recording; device changes are blocked")
        if self.install.active():
            raise RuntimeError("an install is running; wait for it to finish")
        if not self.device_lock.acquire(blocking=False):
            raise RuntimeError("another device operation is running")
        try:
            if self.install.active():
                raise RuntimeError("an install is running; wait for it to finish")
            with self.lock:
                adb = self._adb()
                game = self._game_detail(adb, package)
                if not game.get("supported"):
                    raise ValueError("custom game mode interventions are not supported for this package")
                command = build_game_override_command(package, fps, downscale)
                proc = adb.run(["shell", command], timeout=20.0)
                output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                output = output.strip()
                failed = proc.returncode != 0 or any(marker in output.lower() for marker in _GAME_FAILURE_MARKERS)
                after = self._game_detail(adb, package)
                ok = not failed and after.get("fps") == fps and after.get("downscale") == downscale
                if not ok and not output:
                    output = "The device did not apply the requested game mode."
                result = {
                    "ok": ok,
                    "package": package,
                    "action": "performance",
                    "command": command,
                    "output": output,
                    "fps": fps,
                    "downscale": downscale,
                    "game": after,
                }
                self._log_action(result)
                return result
        finally:
            self.device_lock.release()

    def _log_action(self, result: dict) -> None:
        keys = (
            "ok",
            "package",
            "action",
            "command",
            "output",
            "kind",
            "state_before",
            "fps",
            "downscale",
        )
        append_action_log(
            self.reports_dir,
            "app-actions.jsonl",
            {key: result.get(key) for key in keys},
        )
