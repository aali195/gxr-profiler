"""Installed package discovery, metadata parsing and package actions.

The recording path remains read-only.  This module exists for the explicit
Tools > Apps workflow: listing packages and building the small set of package
manager commands that the user can confirm manually.
"""

from __future__ import annotations

import re
import shlex

from .parsers.process import (
    oom_class,
    parse_cpuinfo,
    parse_gpu_mem,
    parse_oom_scores,
    parse_proc_stats,
    parse_ps,
)
from .parsers.util import split_sections

PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")
PACKAGE_LINE_RE = re.compile(r"^package:(.+)$")
USER_RE = re.compile(r"UserInfo\{(\d+):")
DETAIL_USER_RE = re.compile(r"^\s*User (\d+):\s*(.*)$", re.MULTILINE)

APP_LIST_SCRIPT = """echo '###USERS'; pm list users
echo '###PACKAGES'; pm list packages -U --show-versioncode --user 0
echo '###SYSTEM'; pm list packages -s -u --user 0
echo '###THIRD'; pm list packages -3 -u --user 0
echo '###DISABLED'; pm list packages -d --user 0
echo '###ENABLED'; pm list packages -e --user 0
echo '###ALL'; pm list packages -u --user 0
echo '###PATH'; pm list packages -f -u --user 0
echo '###INSTALLER'; pm list packages -i -u --user 0
echo '###CPUINFO'; dumpsys cpuinfo
echo '###PS'; ps -A -o PID,UID,RSS,NAME
echo '###STAT'; grep -H '' /proc/[0-9]*/stat 2>/dev/null
echo '###OOM'; grep -H '' /proc/[0-9]*/oom_score_adj 2>/dev/null
echo '###GPUMEM'; dumpsys gpu | sed -n '/Memory snapshot for GPU/,/driverPackageName/p'
"""

PACKAGE_FALLBACK_SCRIPT = "pm list packages -U --user 0"

APP_ACTIONS = ("disable", "enable", "remove_user", "restore", "uninstall")
APP_DESTRUCTIVE_ACTIONS = frozenset({"disable", "remove_user", "uninstall"})

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


def parse_users(text: str) -> list[int]:
    return sorted({int(m.group(1)) for m in USER_RE.finditer(text)})


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


def build_app_rows(sections: dict[str, list[str]]) -> list[dict]:
    packages = parse_package_lines("\n".join(sections.get("PACKAGES", [])))
    paths = parse_package_lines("\n".join(sections.get("PATH", [])))
    installers = parse_package_lines("\n".join(sections.get("INSTALLER", [])))
    system = _package_set(sections.get("SYSTEM", []))
    third = _package_set(sections.get("THIRD", []))
    disabled = _package_set(sections.get("DISABLED", []))
    enabled = _package_set(sections.get("ENABLED", []))
    all_packages = _package_set(sections.get("ALL", []))
    process_usage = parse_process_usage(
        "\n".join(sections.get("CPUINFO", [])),
        "\n".join(sections.get("PS", [])),
        "\n".join(sections.get("STAT", [])),
        "\n".join(sections.get("OOM", [])),
        "\n".join(sections.get("GPUMEM", [])),
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
                "stock": is_system,
                "state": state,
                "installed": package in installed,
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


def summarize(rows: list[dict]) -> dict:
    def total(key: str) -> float:
        return sum(float(row.get(key) or 0) for row in rows)

    return {
        "total": len(rows),
        "system": sum(1 for row in rows if row["kind"] != "user"),
        "user": sum(1 for row in rows if row["kind"] == "user"),
        "updated_system": sum(1 for row in rows if row["kind"] == "system-updated"),
        "enabled": sum(1 for row in rows if row["state"] == "enabled"),
        "disabled": sum(1 for row in rows if row["state"] == "disabled"),
        "removed": sum(1 for row in rows if row["state"] == "removed"),
        "running": sum(1 for row in rows if row.get("running")),
        "cpu_pct": round(total("cpu_pct"), 1),
        "rss_kb": round(total("rss_kb")),
        "gpu_mem_kb": round(total("gpu_mem_kb")),
        "size_kb": round(total("size_kb")),
    }


def parse_app_list(text: str) -> tuple[list[dict], list[int]]:
    sections = split_sections(text)
    return build_app_rows(sections), parse_users("\n".join(sections.get("USERS", [])))


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
        "resource_path": _field(text, "resourcePath"),
        "data_dir": _field(text, "dataDir"),
        "primary_cpu_abi": _field(text, "primaryCpuAbi"),
        "installer": _field(text, "installerPackageName"),
        "first_install_time": _field(text, "firstInstallTime"),
        "last_update_time": _field(text, "lastUpdateTime"),
        "install_time": _field(text, "installTime"),
        "update_time": _field(text, "updateTime"),
        "flags": _flags(text, "flags"),
        "private_flags": _flags(text, "privateFlags"),
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
    package = validate_package_name(package)
    quoted = shlex.quote(package)
    if action == "disable":
        return f"pm disable-user --user {int(user)} {quoted}"
    if action == "enable":
        return f"pm enable --user {int(user)} {quoted}"
    if action == "remove_user":
        return f"pm uninstall --user {int(user)} {quoted}"
    if action == "restore":
        return f"cmd package install-existing --user {int(user)} {quoted}"
    if action == "uninstall":
        return f"pm uninstall {quoted}"
    raise ValueError(f"unknown app action: {action}")


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
