"""Installed package discovery, metadata parsing and package actions.

The profiler's recording path remains read-only. This module exists for the
explicit GXR Manager > Apps workflow: listing packages and building the small
set of package manager commands that the user can confirm manually.
"""

from __future__ import annotations

import re
import shlex
from typing import TypedDict

from gxr_core.parsers.process import (
    oom_class,
    parse_cpuinfo,
    parse_gpu_mem,
    parse_oom_scores,
    parse_proc_stats,
    parse_ps,
)
from gxr_core.process_snapshot import PROCESS_SNAPSHOT_SCRIPT

PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")
PACKAGE_LINE_RE = re.compile(r"^package:(.+)$")
DETAIL_USER_RE = re.compile(r"^\s*User (\d+):\s*(.*)$", re.MULTILINE)


class AppRow(TypedDict, total=False):
    package: str
    uid: int | None
    version_code: int | None
    apk_path: str
    size_kb: int | None
    installer: str
    kind: str
    system: bool
    state: str
    running: bool
    proc_count: int
    cpu_pct: float | None
    rss_kb: float | None
    gpu_mem_kb: float | None
    threads: int | None
    oom_adj: int | None
    oom_class: str
    proc_names: list[str]
    critical: bool
    actions: list[str]


PACKAGE_LIST_SCRIPT = """echo '###PACKAGES'; pm list packages -U --show-versioncode --user 0
echo '###SYSTEM'; pm list packages -s -u --user 0
echo '###THIRD'; pm list packages -3 -u --user 0
echo '###DISABLED'; pm list packages -d --user 0
echo '###ENABLED'; pm list packages -e --user 0
echo '###ALL'; pm list packages -u --user 0
echo '###PATH'; pm list packages -f -u --user 0
echo '###INSTALLER'; pm list packages -i -u --user 0
"""

APP_LIST_SCRIPT = PACKAGE_LIST_SCRIPT + PROCESS_SNAPSHOT_SCRIPT

PACKAGE_FALLBACK_SCRIPT = "pm list packages -U --user 0"

APP_ACTION_SPECS = {
    "disable": {
        "label": "Disable",
        "title": "Disable package",
        "confirm": "Disable package",
        "description": (
            "The package will be disabled for user 0 and its components will stop running. "
            "You can enable it again from this tool."
        ),
        "command": "pm disable-user --user {user} {package}",
        "destructive": True,
        "data_loss": False,
    },
    "enable": {
        "label": "Enable",
        "title": "Enable package",
        "confirm": "Enable package",
        "description": "The package will be enabled for user 0 and its normal components can run again.",
        "command": "pm enable --user {user} {package}",
        "destructive": False,
        "data_loss": False,
    },
    "remove_user": {
        "label": "Remove for user 0",
        "title": "Remove package for user 0",
        "confirm": "Remove for user 0",
        "description": (
            "This removes the package for user 0 only. The stock APK remains in the system image "
            "and can be restored with Restore. App data for user 0 may be deleted."
        ),
        "command": "pm uninstall --user {user} {package}",
        "destructive": True,
        "data_loss": True,
    },
    "restore": {
        "label": "Restore",
        "title": "Restore package",
        "confirm": "Restore package",
        "description": ("Reinstalls the existing system package for user 0. App data removed earlier is not restored."),
        "command": "cmd package install-existing --user {user} {package}",
        "destructive": False,
        "data_loss": False,
    },
    "uninstall": {
        "label": "Uninstall",
        "title": "Uninstall user app",
        "confirm": "Uninstall permanently",
        "description": (
            "Permanently uninstalls this user-installed app and its data. It cannot be restored "
            "from this tool; reinstall it from the original source."
        ),
        "command": "pm uninstall {package}",
        "destructive": True,
        "data_loss": True,
    },
}

APP_ACTIONS = tuple(APP_ACTION_SPECS)
APP_DESTRUCTIVE_ACTIONS = frozenset(name for name, spec in APP_ACTION_SPECS.items() if spec["destructive"])

GAME_FPS_VALUES = ("30", "45", "60", "90", "disable")
GAME_DOWNSCALE_VALUES = ("0.5", "0.6", "0.7", "0.8", "0.9", "disable")

OBB_NAME_RE = re.compile(
    r"^(main|patch)\.(\d+)\.([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)\.obb$",
    re.IGNORECASE,
)
OBB_FILE_RE = re.compile(r"^[^/\\<>:\"|?*\x00-\x1f]+\.obb$", re.IGNORECASE)

GAME_MODE_RE = re.compile(r"current mode:\s*([A-Za-z]+),\s*available game modes:\s*\[([^\]]*)\]")
GAME_SCALING_RE = re.compile(r"Scaling:\s*([0-9.]+)")
GAME_FPS_RE = re.compile(r"Fps:\s*([0-9]+)")

CRITICAL_EXACT = frozenset(
    {
        "android",
        "com.android.systemui",
        "com.android.openxr.broker",
        "com.android.xranchormanager",
        "com.google.android.gms",
        "com.google.android.gsf",
        "com.android.webview",
        "com.google.android.webview",
        "com.google.xr.perception.inputserver",
        "com.google.xr.facetracking.calibration",
        "com.samsung.fitting.eyetracking.calibration",
        "com.samsung.android.app.xr.home",
        "com.samsung.android.app.xr.vstcontrollerui",
        "com.samsung.android.vst.batterysavingsettings",
        "com.samsung.android.networkstack",
    }
)
CRITICAL_PREFIXES = ("vendor.", "com.qualcomm.", "com.samsung.android.wifi.")

SYSTEM_PATH_PREFIXES = (
    "/system",
    "/system_ext",
    "/product",
    "/vendor",
    "/odm",
    "/apex",
)

_ACTION_SUCCESS_MARKERS = (
    "success",
    "new state:",
    "installed for user",
    "installed for all users",
)
_ACTION_FAILURE_MARKERS = (
    "failure",
    "error:",
    "exception",
    "not installed",
    "unknown package",
    "permission denied",
    "security exception",
    "delete_failed",
    "does not exist",
    "not found",
    "unable to find",
)


def validate_package_name(package: str) -> str:
    """Return a safe Android package name or raise ValueError."""
    name = (package or "").strip()
    if not name or len(name) > 255 or not PACKAGE_RE.match(name):
        raise ValueError("invalid package name")
    return name


def validate_game_fps(value: str) -> str:
    if value not in GAME_FPS_VALUES:
        raise ValueError(f"invalid game FPS value: {value}")
    return value


def validate_game_downscale(value: str) -> str:
    if value not in GAME_DOWNSCALE_VALUES:
        raise ValueError(f"invalid game downscale value: {value}")
    return value


def parse_obb_name(name: str) -> dict:
    """Parse the standard ``main|patch.<version>.<package>.obb`` file name."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    match = OBB_NAME_RE.match(base)
    if not match:
        return {"kind": "", "version_code": None, "package": ""}
    return {
        "kind": match.group(1).lower(),
        "version_code": int(match.group(2)),
        "package": match.group(3),
    }


def validate_obb_filename(name: str) -> str:
    base = (name or "").strip()
    if not base or len(base) > 255 or base != base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]:
        raise ValueError("invalid OBB file name")
    if not OBB_FILE_RE.match(base):
        raise ValueError("invalid OBB file name")
    return base


def obb_remote_path(package: str, name: str) -> str:
    package = validate_package_name(package)
    name = validate_obb_filename(name)
    return f"/sdcard/Android/obb/{package}/{name}"


def build_install_args(
    paths: list[str],
    *,
    replace: bool = True,
    allow_downgrade: bool = False,
    grant_permissions: bool = False,
    user: int = 0,
    split: bool = False,
) -> list[str]:
    """Build adb install arguments for one APK or one split-APK set."""
    if not paths:
        raise ValueError("at least one APK is required")
    args = ["install-multiple" if split or len(paths) > 1 else "install"]
    if replace:
        args.append("-r")
    if allow_downgrade:
        args.append("-d")
    if grant_permissions:
        args.append("-g")
    args.extend(["--user", str(int(user))])
    args.extend(str(path) for path in paths)
    return args


def _display_arg(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(ch in text for ch in " \t"):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def format_adb_command(args: list[str]) -> str:
    return "adb " + " ".join(_display_arg(item) for item in args)


def build_game_override_command(package: str, fps: str, downscale: str) -> str:
    package = validate_package_name(package)
    fps = validate_game_fps(fps)
    downscale = validate_game_downscale(downscale)
    args = []
    if fps != "disable":
        args.extend(["--fps", fps])
    if downscale != "disable":
        args.extend(["--downscale", downscale])
    elif fps != "disable":
        # The game command preserves the previous scale when the flag is omitted.
        args.extend(["--downscale", "disable"])
    if not args:
        return f"cmd game reset {shlex.quote(package)}"
    return f"cmd game set {' '.join(args)} {shlex.quote(package)}"


def parse_game_info(modes_text: str, configs_text: str = "") -> dict:
    raw = " ".join((modes_text or "").split())
    match = GAME_MODE_RE.search(raw)
    if not match:
        return {
            "supported": False,
            "current_mode": "",
            "available_modes": [],
            "fps": "disable",
            "downscale": "disable",
            "interventions": "No custom intervention",
        }
    current_mode = match.group(1).lower()
    available_modes = [item.strip().lower() for item in match.group(2).split(",") if item.strip()]
    fps_match = GAME_FPS_RE.search(configs_text or "")
    scale_match = GAME_SCALING_RE.search(configs_text or "")
    fps = fps_match.group(1) if fps_match else "disable"
    downscale = "disable"
    if scale_match:
        try:
            downscale = f"{float(scale_match.group(1)):g}"
        except ValueError:
            downscale = scale_match.group(1)
    parts = []
    if fps != "disable":
        parts.append(f"FPS {fps}")
    if downscale != "disable":
        try:
            parts.append(f"render scale {float(downscale) * 100:g}%")
        except ValueError:
            parts.append(f"render scale {downscale}")
    return {
        "supported": "custom" in available_modes,
        "current_mode": current_mode,
        "available_modes": available_modes,
        "fps": fps,
        "downscale": downscale,
        "interventions": ", ".join(parts) or "No custom intervention",
    }


def is_critical_package(package: str) -> bool:
    return package in CRITICAL_EXACT or package.startswith(CRITICAL_PREFIXES)


def _package_set(lines: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line.startswith("package:"):
            continue
        name = line[8:].strip().split()[0] if line[8:].strip() else ""
        if name and PACKAGE_RE.match(name):
            out.add(name)
    return out


def parse_package_lines(text: str) -> dict[str, dict]:
    """Parse pm list packages variants (uid/version/path/installer tokens)."""
    out: dict[str, dict] = {}
    for raw in text.splitlines():
        m = PACKAGE_LINE_RE.match(raw.strip())
        if not m:
            continue
        body = m.group(1).strip()
        if not body:
            continue
        if body.startswith("/") and "=" in body:
            path, package = body.rsplit("=", 1)
            package = package.strip()
            if not PACKAGE_RE.match(package or ""):
                continue
            out.setdefault(package, {})["apk_path"] = path.strip()
            continue
        tokens = body.split()
        if not tokens:
            continue
        package = tokens[0]
        if not PACKAGE_RE.match(package):
            continue
        rec = out.setdefault(package, {})
        for token in tokens[1:]:
            if token.startswith("uid:") and token[4:].isdigit():
                rec["uid"] = int(token[4:])
            elif token.startswith("versionCode:") and token[12:].isdigit():
                rec["version_code"] = int(token[12:])
            elif token.startswith("installer="):
                installer = token[10:].strip()
                if installer and installer != "null":
                    rec["installer"] = installer
    return out


def parse_process_usage(
    cpuinfo_text: str,
    ps_text: str,
    stat_text: str = "",
    oom_text: str = "",
    gpu_text: str = "",
) -> dict[str, dict]:
    """Aggregate the current process snapshot by package-style process name."""
    cpu = parse_cpuinfo(cpuinfo_text)
    ps = parse_ps(ps_text)
    stats = parse_proc_stats(stat_text)
    oom = parse_oom_scores(oom_text)
    gpu = parse_gpu_mem(gpu_text)
    usage: dict[str, dict] = {}
    for pid in set(cpu) | set(ps) | set(stats) | set(gpu):
        rec = ps.get(pid) or {}
        cpu_rec = cpu.get(pid) or {}
        stat_rec = stats.get(pid) or {}
        name = rec.get("name") or cpu_rec.get("name") or stat_rec.get("comm") or ""
        if not name:
            continue
        package = name.split(":", 1)[0]
        if not package:
            continue
        entry = usage.setdefault(
            package,
            {
                "proc_count": 0,
                "cpu_pct": 0.0,
                "rss_kb": 0.0,
                "gpu_mem_kb": 0.0,
                "threads": 0,
                "oom_adj": None,
                "proc_names": [],
            },
        )
        entry["proc_count"] += 1
        entry["cpu_pct"] += float(cpu_rec.get("cpu_pct") or 0.0)
        entry["rss_kb"] += float(rec.get("rss_kb") or 0.0)
        entry["gpu_mem_kb"] += float(gpu.get(pid) or 0.0)
        entry["threads"] += int(stat_rec.get("threads") or 0)
        adj = oom.get(pid)
        if adj is not None:
            entry["oom_adj"] = adj if entry["oom_adj"] is None else min(entry["oom_adj"], adj)
        if name not in entry["proc_names"]:
            entry["proc_names"].append(name)
    for entry in usage.values():
        entry["cpu_pct"] = round(entry["cpu_pct"], 1)
        entry["rss_kb"] = round(entry["rss_kb"])
        entry["gpu_mem_kb"] = round(entry["gpu_mem_kb"])
        entry["threads"] = int(entry["threads"])
        entry["oom_class"] = oom_class(entry["oom_adj"]) if entry["oom_adj"] is not None else ""
        entry["proc_names"].sort()
    return usage


def _section_text(sections: dict[str, list[str]], name: str) -> str:
    return "\n".join(sections.get(name, []))


def _path_looks_system(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in SYSTEM_PATH_PREFIXES)


def _kind(package: str, system: bool, apk_path: str) -> str:
    if system:
        return "system-updated" if apk_path.startswith("/data/app") else "system"
    return "user"


def _state(package: str, installed: set[str], disabled: set[str], all_packages: set[str]) -> str:
    if package in all_packages and package not in installed and package not in disabled:
        return "removed"
    if package in disabled:
        return "disabled"
    return "enabled"


def _actions(kind: str, state: str) -> list[str]:
    if state == "removed":
        return ["restore"] if kind != "user" else []
    actions: list[str] = []
    if state == "enabled":
        actions.append("disable")
    elif state == "disabled":
        actions.append("enable")
    if kind == "user":
        actions.append("uninstall")
    else:
        actions.append("remove_user")
    return actions


def build_app_rows(sections: dict[str, list[str]]) -> list[AppRow]:
    packages = parse_package_lines(_section_text(sections, "PACKAGES"))
    paths = parse_package_lines(_section_text(sections, "PATH"))
    installers = parse_package_lines(_section_text(sections, "INSTALLER"))
    system = _package_set(sections.get("SYSTEM", []))
    third = _package_set(sections.get("THIRD", []))
    disabled = _package_set(sections.get("DISABLED", []))
    enabled = _package_set(sections.get("ENABLED", []))
    all_packages = _package_set(sections.get("ALL", []))
    process_usage = parse_process_usage(
        _section_text(sections, "CPUINFO"),
        _section_text(sections, "PS"),
        _section_text(sections, "STAT"),
        _section_text(sections, "OOM"),
        _section_text(sections, "GPUMEM"),
    )

    installed = set(packages) | disabled | enabled
    names = installed | all_packages | set(paths) | set(installers)
    rows: list[dict] = []
    for package in names:
        base = dict(packages.get(package) or {})
        base.update({k: v for k, v in (paths.get(package) or {}).items() if v not in (None, "")})
        base.update({k: v for k, v in (installers.get(package) or {}).items() if v not in (None, "")})
        apk_path = base.get("apk_path", "")
        is_system = package in system or (package not in third and (not apk_path or _path_looks_system(apk_path)))
        kind = _kind(package, is_system, apk_path)
        state = _state(package, installed, disabled, all_packages)
        critical = is_critical_package(package)
        actions = _actions(kind, state)
        if critical:
            actions = [action for action in actions if action not in APP_DESTRUCTIVE_ACTIONS]
        usage = process_usage.get(package, {})
        proc_count = int(usage.get("proc_count") or 0)
        rows.append(
            {
                "package": package,
                "uid": base.get("uid"),
                "version_code": base.get("version_code"),
                "apk_path": apk_path,
                "size_kb": None,
                "installer": base.get("installer", ""),
                "kind": kind,
                "system": is_system,
                "state": state,
                "running": proc_count > 0,
                "proc_count": proc_count,
                "cpu_pct": usage.get("cpu_pct", 0.0) if proc_count else None,
                "rss_kb": usage.get("rss_kb", 0) if proc_count else None,
                "gpu_mem_kb": usage.get("gpu_mem_kb", 0) if proc_count else None,
                "threads": usage.get("threads", 0) if proc_count else None,
                "oom_adj": usage.get("oom_adj") if proc_count else None,
                "oom_class": usage.get("oom_class", "") if proc_count else "",
                "proc_names": usage.get("proc_names", []) if proc_count else [],
                "critical": critical,
                "actions": actions,
            }
        )
    rows.sort(key=lambda row: row["package"].casefold())
    return rows


def summarize(rows: list[AppRow]) -> dict:
    def total(key: str) -> float:
        return sum(float(row.get(key) or 0) for row in rows)

    return {
        "total": len(rows),
        "system": sum(1 for row in rows if row["kind"] != "user"),
        "user": sum(1 for row in rows if row["kind"] == "user"),
        "enabled": sum(1 for row in rows if row["state"] == "enabled"),
        "disabled": sum(1 for row in rows if row["state"] == "disabled"),
        "removed": sum(1 for row in rows if row["state"] == "removed"),
        "running": sum(1 for row in rows if row.get("running")),
        "cpu_pct": round(total("cpu_pct"), 1),
        "rss_kb": round(total("rss_kb")),
        "gpu_mem_kb": round(total("gpu_mem_kb")),
        "size_kb": round(total("size_kb")),
    }


def size_targets_for_rows(rows: list[AppRow]) -> dict[str, list[AppRow]]:
    targets: dict[str, list[dict]] = {}
    for row in rows:
        path = row.get("apk_path") or ""
        if not path:
            continue
        target = path.rsplit("/", 1)[0] if path.startswith("/data/app/") else path
        targets.setdefault(target, []).append(row)
    return targets


def merge_package_fallback(sections: dict[str, list[str]], fallback_text: str) -> None:
    """Merge a plain ``pm list packages -U`` result into an existing section set."""
    current = sections.get("PACKAGES") or []
    if parse_package_lines("\n".join(current)):
        return
    sections["PACKAGES"] = fallback_text.splitlines()


def parse_package_paths(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            path = line[8:].strip()
            if path and path not in out:
                out.append(path)
    return out


def _field(text: str, name: str) -> str:
    m = re.search(rf"^\s*{re.escape(name)}=(.*)$", text, re.MULTILINE)
    value = m.group(1).strip() if m else ""
    return "" if value == "null" else value


def _int_field(text: str, name: str) -> int | None:
    m = re.search(rf"\b{re.escape(name)}=(\d+)", text)
    return int(m.group(1)) if m else None


def _flags(text: str, name: str) -> list[str]:
    m = re.search(rf"^\s*{re.escape(name)}=\[(.*?)\]", text, re.MULTILINE)
    return m.group(1).split() if m else []


def _permission_count(text: str) -> int | None:
    marker = re.search(r"^\s*requested permissions:\s*$", text, re.MULTILINE)
    if not marker:
        return None
    count = 0
    lines = text[marker.end() :].splitlines()
    if lines and not lines[0].strip():
        lines = lines[1:]
    for raw in lines:
        line = raw.strip()
        if not line:
            break
        if line.endswith(":") and "permission" in line.lower():
            break
        if re.match(r"^[A-Za-z0-9_.]+$", line):
            count += 1
    return count


def _user_states(text: str) -> list[dict]:
    out: list[dict] = []
    for m in DETAIL_USER_RE.finditer(text):
        body = m.group(2)
        entry = {"user": int(m.group(1))}
        for key in ("installed", "hidden", "suspended", "stopped", "notLaunched"):
            value = re.search(rf"\b{key}=(\w+)", body)
            if value:
                entry[key] = value.group(1) == "true"
        enabled = re.search(r"\benabled=(\d+)", body)
        if enabled:
            entry["enabled"] = int(enabled.group(1))
        out.append(entry)
    return out


def parse_package_detail(text: str, apk_paths: list[str] | None = None) -> dict:
    version_code = _int_field(text, "versionCode")
    min_sdk = _int_field(text, "minSdk")
    target_sdk = _int_field(text, "targetSdk")
    detail = {
        "version_name": _field(text, "versionName"),
        "version_code": version_code,
        "min_sdk": min_sdk,
        "target_sdk": target_sdk,
        "code_path": _field(text, "codePath"),
        "data_dir": _field(text, "dataDir"),
        "primary_cpu_abi": _field(text, "primaryCpuAbi"),
        "installer": _field(text, "installerPackageName"),
        "first_install_time": _field(text, "firstInstallTime"),
        "last_update_time": _field(text, "lastUpdateTime"),
        "flags": _flags(text, "flags"),
        "requested_permissions_count": _permission_count(text),
        "user_states": _user_states(text),
        "apk_paths": list(apk_paths or []),
    }
    return detail


def parse_du(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw in text.splitlines():
        parts = raw.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        out[parts[1].strip()] = int(parts[0])
    return out


def build_action_command(package: str, action: str, user: int = 0) -> str:
    spec = APP_ACTION_SPECS.get(action)
    if spec is None:
        raise ValueError(f"unknown app action: {action}")
    package = validate_package_name(package)
    return spec["command"].format(user=int(user), package=shlex.quote(package))


def interpret_action_result(output: str, returncode: int = 0) -> tuple[bool, str]:
    text = (output or "").strip()
    low = text.lower()
    if returncode != 0:
        return False, text or f"adb exited with code {returncode}"
    if any(marker in low for marker in _ACTION_FAILURE_MARKERS):
        return False, text or "the package manager rejected the action"
    if not low:
        return True, ""
    if any(marker in low for marker in _ACTION_SUCCESS_MARKERS):
        return True, text
    return False, text
