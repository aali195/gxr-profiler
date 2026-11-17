"""Package listing and confirmed package-management actions."""

from __future__ import annotations

import json
import logging
import shlex
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..core.adb import AdbError, RealAdb, resolve_serial
from ..core.apps import (
    APP_ACTIONS,
    APP_DESTRUCTIVE_ACTIONS,
    APP_LIST_SCRIPT,
    PACKAGE_FALLBACK_SCRIPT,
    build_action_command,
    build_app_rows,
    interpret_action_result,
    is_critical_package,
    merge_package_fallback,
    parse_du,
    parse_package_detail,
    parse_package_lines,
    parse_package_paths,
    parse_users,
    summarize,
    validate_package_name,
)
from ..core.parsers.util import split_sections
from ..core.paths import default_reports_dir, ensure_writable_dir

log = logging.getLogger(__name__)


class AppsService:
    """Read package state and execute one explicitly confirmed action at a time."""

    def __init__(
        self,
        serial: str | None = None,
        reports_dir: str | None = None,
        user: int = 0,
        adb_factory: Callable[..., object] = RealAdb,
    ) -> None:
        self.serial = serial
        self.user = user
        self.reports_dir = reports_dir or str(Path(default_reports_dir()) / "apps")
        self.adb_factory = adb_factory
        self.lock = threading.Lock()

    def _adb(self):
        return self.adb_factory(serial=resolve_serial(self.serial))

    def _list_locked(self, adb) -> dict:
        text = adb.shell(APP_LIST_SCRIPT, timeout=25.0)
        sections = split_sections(text)
        if not parse_package_lines("\n".join(sections.get("PACKAGES", []))):
            fallback = adb.shell(PACKAGE_FALLBACK_SCRIPT, timeout=15.0)
            merge_package_fallback(sections, fallback)
        rows = build_app_rows(sections)
        if not rows:
            raise AdbError("the device returned no installed packages")
        self._add_sizes(adb, rows)
        return {
            "packages": rows,
            "summary": summarize(rows),
            "users": parse_users("\n".join(sections.get("USERS", []))),
            "user": self.user,
        }

    def _add_sizes(self, adb, rows: list[dict]) -> None:
        targets: dict[str, list[dict]] = {}
        for row in rows:
            path = row.get("apk_path") or ""
            if not path:
                continue
            target = path.rsplit("/", 1)[0] if path.startswith("/data/app/") else path
            targets.setdefault(target, []).append(row)
        if not targets:
            return
        command = "du -sk " + " ".join(shlex.quote(target) for target in targets) + " 2>/dev/null"
        try:
            sizes = parse_du(adb.shell(command, timeout=20.0))
        except Exception:
            log.debug("package size read failed", exc_info=True)
            return
        for target, target_rows in targets.items():
            size_kb = sizes.get(target)
            if size_kb is None:
                continue
            for row in target_rows:
                row["size_kb"] = size_kb

    def list_packages(self) -> dict:
        with self.lock:
            return self._list_locked(self._adb())

    def detail(self, package: str, root: bool = False) -> dict:
        package = validate_package_name(package)
        with self.lock:
            adb = self._adb()
            text = adb.shell("dumpsys package " + shlex.quote(package), timeout=25.0)
            if "unable to find package" in text.lower() or "unknown package" in text.lower():
                raise LookupError(f"package not found: {package}")
            paths = parse_package_paths(adb.shell("pm path " + shlex.quote(package), timeout=10.0))
            result = {
                "package": package,
                "detail": parse_package_detail(text, paths),
                "critical": is_critical_package(package),
            }
            if root:
                result["root"] = self._root_detail(adb, package)
            return result

    def _root_detail(self, adb, package: str) -> dict:
        info = {
            "requested": True,
            "available": False,
            "data_kb": None,
            "cache_kb": None,
            "sizes_kb": {},
            "errors": [],
        }
        who = adb.shell("su -c id", timeout=8.0)
        if "uid=0" not in who:
            info["errors"].append(who.strip() or "su did not return uid=0")
            return info
        info["available"] = True
        paths = [f"/data/user/0/{package}", f"/data/user_de/0/{package}", f"/data/user/0/{package}/cache"]
        command = "du -sk " + " ".join(paths) + " 2>/dev/null"
        text = adb.shell("su -c " + shlex.quote(command), timeout=20.0)
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
        with self.lock:
            adb = self._adb()
            current = self._list_locked(adb)
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

    def _log_action(self, result: dict) -> None:
        try:
            ensure_writable_dir(self.reports_dir)
            path = Path(self.reports_dir) / "app-actions.jsonl"
            entry = {
                "at": datetime.now(UTC).isoformat(),
                **{
                    key: result.get(key)
                    for key in ("ok", "package", "action", "command", "output", "kind", "state_before")
                },
            }
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            log.warning("could not write app action log", exc_info=True)

    def state(self) -> dict:
        return {"user": self.user, "serial": self.serial}
