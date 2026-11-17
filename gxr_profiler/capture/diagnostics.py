"""Read-only diagnostics snapshot: crash logs, boot state, dropbox, thermal.

The diagnostics tab is a one-click snapshot, not a recording.  Every command
here is a read: ``logcat -d``, ``getprop``, ``dumpsys`` and optional ``su -c``
reads.  Nothing is cleared, written or persisted on the device.
"""

from __future__ import annotations

import re
import shlex
import time
from datetime import UTC, datetime

from ..core.adb import AdbClient
from ..core.device.props import all_props
from ..core.parsers.crash import (
    parse_crashes,
    parse_dropbox,
    parse_events,
    parse_exit_info,
    parse_tombstone_text,
)
from .poller import Poller

BOOT_PROP_KEYS = (
    "sys.boot.reason",
    "sys.boot.reason.last",
    "ro.boot.bootreason",
    "sys.rescue_boot_count",
    "sys.rescue_boot_start",
    "sys.boot_mitigation_count",
    "sys.boot_mitigation_start",
    "sys.max_rescue_level_attempted",
    "sys.attempting_reboot",
    "sys.attempting_factory_reset",
    "persist.sys.last_factory_reset",
)

DEVICE_PROP_KEYS = {
    "model": "ro.product.model",
    "device": "ro.product.device",
    "product": "ro.product.name",
    "soc": "ro.soc.model",
    "android": "ro.build.version.release",
    "sdk": "ro.build.version.sdk",
    "build_id": "ro.build.id",
    "build_display_id": "ro.build.display.id",
    "build_fingerprint": "ro.build.fingerprint",
    "build_type": "ro.build.type",
    "build_tags": "ro.build.tags",
    "security_patch": "ro.build.version.security_patch",
}

THERMAL_KEYS = (
    "thermal_status",
    "thermal_max_sev",
    "t_AP",
    "t_WIFI",
    "t_LRP",
    "t_BAT",
    "fan_step",
    "batt_temp",
    "batt_level",
    "ddr_temp",
    "g_clock",
    "g_busy",
    "psm",
    "disp_hz",
)

_PROP_RE = re.compile(r"^\[([^\]]+)\]: \[(.*)\]$")
_LIST_NAME_RE = re.compile(r"\s(\S+)$")


class DiagnosticsCollector:
    def __init__(
        self,
        adb: AdbClient,
        root: bool = False,
        include_tombstones: bool = False,
        include_dmesg: bool = False,
        log_lines: int = 1500,
    ) -> None:
        self.adb = adb
        self.root = bool(root or include_tombstones or include_dmesg)
        self.include_tombstones = bool(include_tombstones)
        self.include_dmesg = bool(include_dmesg)
        self.log_lines = max(100, min(int(log_lines), 5000))
        self.errors: list[str] = []

    def collect(self) -> dict:
        started = time.monotonic()
        props = self._props()
        crash_text = self._logcat("crash")
        events_text = self._events_log()
        system_text = self._logcat("system")
        main_text = self._logcat("main", min(self.log_lines, 1200))
        dropbox_text = self._shell("dumpsys dropbox --print", timeout=15.0)
        exit_text = self._shell("dumpsys activity exit-info", timeout=25.0)

        events = parse_events(events_text)
        crashes = parse_crashes(crash_text)
        dropbox = parse_dropbox(dropbox_text)
        crashes = _merge_dropbox_crashes(crashes, dropbox)
        exit_info = parse_exit_info(exit_text)
        thermal = self._thermal()
        root = self._root()
        tombstone_crashes = self._tombstone_crashes(root)
        boot = {
            "props": {key: props.get(key) for key in BOOT_PROP_KEYS},
            "uptime_s": self._uptime(),
            "rescue_notes": events.get("rescue_notes", []),
            "boot_progress": events.get("boot_progress", []),
        }
        report = {
            "collected_at": datetime.now(UTC).isoformat(),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "device": {label: props.get(key) for label, key in DEVICE_PROP_KEYS.items()},
            "options": {
                "root": self.root,
                "include_tombstones": self.include_tombstones,
                "include_dmesg": self.include_dmesg,
                "log_lines": self.log_lines,
            },
            "boot": boot,
            "events": events,
            "crashes": crashes,
            "tombstone_crashes": tombstone_crashes,
            "dropbox": dropbox,
            "exit_info": exit_info,
            "thermal": thermal,
            "root": root,
            "errors": list(self.errors),
            "sections": {
                "crash": _cap(crash_text),
                "events": _cap(events_text),
                "system": _cap(system_text),
                "main": _cap(main_text),
                "dropbox": _cap(dropbox_text),
                "exit_info": _cap(exit_text),
            },
        }
        return report

    # -- collectors ------------------------------------------------------
    def _props(self) -> dict[str, str]:
        try:
            props = all_props(self.adb)
        except Exception as exc:
            self.errors.append(f"getprop failed: {exc}")
            props = {}
        if not props:
            text = self._shell("getprop", timeout=15.0)
            props = {m.group(1): m.group(2) for m in _PROP_RE.finditer(text)}
        return props

    def _logcat(self, buffer: str, lines: int | None = None) -> str:
        count = lines if lines is not None else self.log_lines
        return self._shell(f"logcat -d -b {buffer} -v time -t {count} 2>/dev/null", timeout=12.0)

    def _events_log(self) -> str:
        # The events buffer is high-volume; keep the boot/crash/ANR subset even
        # when the user's line cap is small. This is still an on-device read.
        count = max(self.log_lines, 3000)
        script = (
            f"logcat -d -b events -v time -t {count} 2>/dev/null | "
            "grep -E 'rescue_note|boot_progress|am_crash|am_anr|am_proc_died'"
        )
        return self._shell(script, timeout=12.0)

    def _uptime(self) -> float | None:
        text = self._shell("cat /proc/uptime", timeout=6.0)
        try:
            return float(text.split()[0])
        except (IndexError, ValueError):
            return None

    def _thermal(self) -> dict:
        try:
            raw = Poller(self.adb, use_root=self.root).poll_preview()
        except Exception as exc:
            self.errors.append(f"thermal preview failed: {exc}")
            return {}
        return {key: raw.get(key) for key in THERMAL_KEYS if key in raw}

    def _shell(self, script: str, timeout: float = 15.0) -> str:
        try:
            return self.adb.shell(script, timeout=timeout)
        except Exception as exc:
            self.errors.append(f"{script.splitlines()[0][:60]}: {exc}")
            return ""

    # -- root ------------------------------------------------------------
    def _root(self) -> dict:
        info = {
            "requested": self.root,
            "available": False,
            "tombstone_list": "",
            "tombstones": [],
            "dropbox_list": "",
            "dropbox_files": [],
            "anr_list": "",
            "anr_files": [],
            "dmesg": "",
            "last_kmsg": "",
            "pstore": "",
            "watchdog": "",
            "package_watchdog": "",
            "errors": [],
        }
        if not self.root:
            return info
        who = self._shell("su -c id", timeout=8.0)
        if "uid=0" not in who:
            info["errors"].append(who.strip() or "su did not return uid=0")
            return info
        info["available"] = True

        def root_read(command: str, timeout: float = 15.0) -> str:
            text = self._shell(f"su -c '{command}'", timeout=timeout)
            low = text.lower()
            if "permission denied" in low or "operation not permitted" in low:
                info["errors"].append(command)
            return text

        info["tombstone_list"] = root_read("ls -lt /data/tombstones 2>&1 | head -n 10")
        info["dropbox_list"] = root_read("ls -lt /data/system/dropbox 2>&1 | head -n 10")
        info["anr_list"] = root_read("ls -lt /data/anr 2>&1 | head -n 10")
        if self.include_tombstones:
            command = (
                "for f in $(ls -1t /data/tombstones/tombstone_[0-9][0-9] 2>/dev/null | head -n 20); do "
                'echo "@@TOMBSTONE $(basename "$f")"; head -c 30000 "$f"; done'
            )
            text = self._shell("su -c " + shlex.quote(command), timeout=30.0)
            if "permission denied" in text.lower():
                info["errors"].append("tombstones")
            for chunk in text.split("@@TOMBSTONE ")[1:]:
                name, _, content = chunk.partition("\n")
                name = name.strip()
                if name:
                    info["tombstones"].append({"name": name, "content": _cap(content, 30000)})
            for name in _names(info["dropbox_list"], 2):
                info["dropbox_files"].append(
                    {"name": name, "content": _cap(root_read(f"cat /data/system/dropbox/{name} 2>&1", 20.0), 60000)}
                )
            for name in _names(info["anr_list"], 1):
                info["anr_files"].append(
                    {"name": name, "content": _cap(root_read(f"cat /data/anr/{name} 2>&1", 20.0), 60000)}
                )
        if self.include_dmesg:
            info["dmesg"] = _cap(root_read("dmesg 2>&1 | tail -n 500", 20.0), 80000)
            info["last_kmsg"] = _cap(root_read("cat /proc/last_kmsg 2>&1 | tail -c 40000", 15.0), 40000)
            info["pstore"] = _cap(root_read("ls -lt /sys/fs/pstore 2>&1 | head -n 20", 10.0), 10000)
        info["watchdog"] = _cap(root_read("cat /metadata/watchdog/mitigation_count.txt 2>&1", 8.0), 2000)
        info["package_watchdog"] = _cap(
            root_read("cat /data/system/package-watchdog.xml 2>&1 | head -c 40000", 12.0), 40000
        )
        return info

    def _tombstone_crashes(self, root: dict) -> list[dict]:
        crashes: list[dict] = []
        for entry in root.get("tombstones") or []:
            for crash in parse_tombstone_text(entry.get("content") or ""):
                crash["source"] = "tombstone"
                crash["tombstone"] = entry.get("name")
                crashes.append(crash)
        return crashes


def _merge_dropbox_crashes(crashes: list[dict], dropbox: list[dict]) -> list[dict]:
    """Recover tombstone bodies from Dropbox when the logcat crash buffer rotated."""
    for entry in dropbox:
        if entry.get("tag") != "SYSTEM_TOMBSTONE":
            continue
        for crash in parse_tombstone_text(entry.get("body") or ""):
            if not any(_same_crash(crash, existing) for existing in crashes):
                crashes.append(crash)
    return crashes


def _same_crash(left: dict, right: dict) -> bool:
    if left.get("process") != right.get("process"):
        return False
    if left.get("signal") != right.get("signal"):
        return False
    if left.get("abort") and right.get("abort") and left["abort"] != right["abort"]:
        return False
    return _top_symbol(left) == _top_symbol(right)


def _top_symbol(crash: dict) -> str:
    frames = crash.get("frames") or []
    if not frames:
        return ""
    first = frames[0]
    return (first.get("symbol") if isinstance(first, dict) else str(first)) or ""


def _names(listing: str, limit: int) -> list[str]:
    names: list[str] = []
    for line in listing.splitlines():
        low = line.lower()
        if line.startswith("total ") or not line.strip():
            continue
        if "permission denied" in low or "no such file" in low or "not found" in low:
            continue
        m = _LIST_NAME_RE.search(line)
        if not m:
            continue
        name = m.group(1).strip()
        if name in {".", ".."} or name.startswith("Permission"):
            continue
        if name in names:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return names


def _cap(text: str, limit: int = 200000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"
