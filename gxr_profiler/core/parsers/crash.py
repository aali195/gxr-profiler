"""Crash, boot, dropbox and process-exit parsing.

The headset does not put every failure in one place:

* ``logcat -b crash`` holds native debuggerd blocks and Java crash output.
* ``logcat -b events`` holds ``rescue_note``, ``boot_progress_*`` and
  ``am_crash`` / ``am_anr`` / ``am_proc_died`` records.
* ``dumpsys dropbox --print`` holds persisted system/app crash entries.
* ``dumpsys activity exit-info`` holds the ActivityManager view of app exits.

The helpers here are deliberately tolerant: callers collect a snapshot and
show whatever was readable instead of failing the entire diagnostics run.
"""

from __future__ import annotations

import re

from .logcat import parse_header

_NATIVE_START_RE = re.compile(r"^\*\*\* \*\*\*")
_CMD_RE = re.compile(r"^Cmdline:\s*(.+?)\s*$")
_PID_RE = re.compile(
    r"^pid:\s*(\d+),\s*tid:\s*(\d+),\s*name:\s*(.*?)\s*>>>\s*(.*?)\s*<<<\s*$"
)
_SIGNAL_RE = re.compile(r"^signal\s+(\d+)\s+\(([^)]+)\)")
_ABORT_RE = re.compile(r"^Abort message:\s*(.*)$")
_CAUSE_RE = re.compile(r"^Cause:\s*(.*)$")
_UPTIME_RE = re.compile(r"^Process uptime:\s*(.*)$")
_TS_RE = re.compile(r"^Timestamp:\s*(.*)$")
_FRAME_RE = re.compile(r"^#(?P<num>\d+)\s+pc\s+(?P<pc>[0-9a-f]+)\s+(?P<path>\S+)\s*(?P<symbol>.*)$")
_JAVA_PROCESS_RE = re.compile(r"^Process:\s*(.+?),?\s*PID:\s*(\d+)")
_EVENT_ARRAY_RE = re.compile(r"^\[(.*)\]$")
_RESCUE_NOTE_RE = re.compile(r"^\[(\d+),(\d+),(\d+)\]$")
_DROPBOX_HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<tag>\S+)\s+\((?P<meta>[^)]*)\)\s*$"
)
_EXIT_PACKAGE_RE = re.compile(r"^\s*package:\s*(?P<package>\S+)\s*$")
_EXIT_START_RE = re.compile(r"^\s*ApplicationExitInfo\s+#(?P<index>\d+):\s*$")
_EXIT_FIELD_RE = re.compile(
    r"(?P<key>timestamp|pid|realUid|packageUid|definingUid|user|process|reason|subreason|status|"
    r"importance|pss|rss|description|state|trace)=(?P<value>.*?)(?=\s+\w+=|$)"
)
_EXIT_REASON_RE = re.compile(r"\((?P<reason>.*)\)$")


def parse_crashes(text: str) -> list[dict]:
    """Return native, Java and ANR crash records from a logcat snapshot."""
    crashes: list[dict] = []
    current: dict | None = None

    def finish() -> None:
        nonlocal current
        if not current:
            return
        if current["kind"] == "native":
            if current["frames"]:
                current["top_frame"] = current["frames"][0]
            # Ignore incomplete native blocks (a torn first line is common).
            if current["process"] or current["signal"] or current["abort"]:
                crashes.append(current)
        elif current["kind"] == "java":
            if current["process"] or current["error"]:
                crashes.append(current)
        elif current["kind"] == "anr":
            if current["process"]:
                crashes.append(current)
        current = None

    for line in text.splitlines():
        hdr = parse_header(line)
        if not hdr:
            continue
        tag = hdr["tag"]
        msg = hdr["msg"].strip()
        ts = f"{hdr['date']} {hdr['time']}"

        if _NATIVE_START_RE.match(msg):
            finish()
            current = {
                "kind": "native",
                "timestamp": ts,
                "process": None,
                "pid": hdr.get("pid"),
                "tid": None,
                "thread": None,
                "signal": None,
                "signal_num": None,
                "abort": None,
                "cause": None,
                "uptime": None,
                "timestamp_ns": None,
                "frames": [],
                "top_frame": None,
                "error": None,
                "raw": [msg],
            }
            continue

        if current and current["kind"] == "native":
            if tag not in {"DEBUG", "DEBUGGERD", "libc", "tombstoned"} and not msg.startswith("Fatal signal"):
                finish()
                # fall through so this line can start a Java/ANR block
            else:
                current["raw"].append(msg)
                if len(current["raw"]) > 140:
                    current["raw"] = current["raw"][-140:]
                m = _CMD_RE.match(msg)
                if m:
                    current["process"] = m.group(1).strip()
                m = _PID_RE.match(msg)
                if m:
                    current["pid"] = m.group(1)
                    current["tid"] = m.group(2)
                    current["thread"] = m.group(3).strip()
                    if m.group(4).strip():
                        current["process"] = m.group(4).strip()
                m = _SIGNAL_RE.match(msg)
                if m:
                    current["signal_num"] = int(m.group(1))
                    current["signal"] = m.group(2).strip()
                m = _ABORT_RE.match(msg)
                if m:
                    current["abort"] = m.group(1).strip().strip("'")
                m = _CAUSE_RE.match(msg)
                if m:
                    current["cause"] = m.group(1).strip()
                m = _UPTIME_RE.match(msg)
                if m:
                    current["uptime"] = m.group(1).strip()
                m = _TS_RE.match(msg)
                if m:
                    current["timestamp_ns"] = m.group(1).strip()
                m = _FRAME_RE.match(msg)
                if m:
                    path = m.group("path")
                    symbol = re.sub(r"\s*\(BuildId:[^)]*\)\s*$", "", m.group("symbol") or "").strip()
                    current["frames"].append(
                        {"num": int(m.group("num")), "path": path, "symbol": symbol}
                    )
                continue

        if "FATAL EXCEPTION" in msg:
            finish()
            current = {
                "kind": "java",
                "timestamp": ts,
                "process": None,
                "pid": hdr.get("pid"),
                "tid": None,
                "thread": None,
                "signal": "SIGABRT",
                "signal_num": 6,
                "abort": None,
                "cause": None,
                "uptime": None,
                "timestamp_ns": None,
                "frames": [],
                "top_frame": None,
                "error": msg,
                "raw": [msg],
            }
            continue

        if current and current["kind"] == "java" and tag == "AndroidRuntime":
            current["raw"].append(msg)
            if len(current["raw"]) > 140:
                current["raw"] = current["raw"][-140:]
            m = _JAVA_PROCESS_RE.match(msg)
            if m:
                current["process"] = m.group(1).strip()
                current["pid"] = m.group(2)
            elif msg.startswith(("at ", "\tat ")):
                current["frames"].append({"num": len(current["frames"]), "path": "", "symbol": msg.strip()})
            elif msg.startswith(("Caused by:", "java.", "android.", "com.")) and not current["cause"]:
                current["cause"] = msg
            continue

        if msg.startswith("ANR in "):
            finish()
            process = msg[len("ANR in "):].split("(", 1)[0].strip()
            current = {
                "kind": "anr",
                "timestamp": ts,
                "process": process,
                "pid": hdr.get("pid"),
                "tid": None,
                "thread": None,
                "signal": None,
                "signal_num": None,
                "abort": None,
                "cause": None,
                "uptime": None,
                "timestamp_ns": None,
                "frames": [],
                "top_frame": None,
                "error": msg,
                "raw": [msg],
            }
            continue

    finish()
    if not crashes:
        return []
    # Keep the newest-first order used by logcat snapshots, but drop exact repeats
    # that can appear when a `-b all` dump is restarted.
    seen: set[tuple] = set()
    out: list[dict] = []
    for crash in crashes:
        key = (
            crash.get("kind"),
            crash.get("timestamp"),
            crash.get("process"),
            crash.get("signal"),
            crash.get("abort"),
            crash.get("top_frame", {}).get("symbol") if crash.get("top_frame") else None,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(crash)
    return out


def parse_tombstone_text(text: str) -> list[dict]:
    """Parse a plain debuggerd tombstone body (e.g. Dropbox SYSTEM_TOMBSTONE)."""
    crashes: list[dict] = []
    current: dict | None = None

    def finish() -> None:
        nonlocal current
        if current and (current["process"] or current["signal"] or current["abort"]):
            if current["frames"]:
                current["top_frame"] = current["frames"][0]
            current["source"] = "dropbox"
            crashes.append(current)
        current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _NATIVE_START_RE.match(line):
            finish()
            current = {
                "kind": "native",
                "timestamp": None,
                "process": None,
                "pid": None,
                "tid": None,
                "thread": None,
                "signal": None,
                "signal_num": None,
                "abort": None,
                "cause": None,
                "uptime": None,
                "timestamp_ns": None,
                "frames": [],
                "top_frame": None,
                "error": None,
                "raw": [line],
            }
            continue
        if current is None:
            continue
        current["raw"].append(line)
        if len(current["raw"]) > 140:
            current["raw"] = current["raw"][-140:]
        m = _TS_RE.match(line)
        if m:
            current["timestamp"] = m.group(1).strip()
        m = _CMD_RE.match(line)
        if m:
            current["process"] = m.group(1).strip()
        m = _PID_RE.match(line)
        if m:
            current["pid"] = m.group(1)
            current["tid"] = m.group(2)
            current["thread"] = m.group(3).strip()
            if m.group(4).strip():
                current["process"] = m.group(4).strip()
        m = _SIGNAL_RE.match(line)
        if m:
            current["signal_num"] = int(m.group(1))
            current["signal"] = m.group(2).strip()
        m = _ABORT_RE.match(line)
        if m:
            current["abort"] = m.group(1).strip().strip("'")
        m = _CAUSE_RE.match(line)
        if m:
            current["cause"] = m.group(1).strip()
        m = _UPTIME_RE.match(line)
        if m:
            current["uptime"] = m.group(1).strip()
        m = _FRAME_RE.match(line)
        if m:
            path = m.group("path")
            symbol = re.sub(r"\s*\(BuildId:[^)]*\)\s*$", "", m.group("symbol") or "").strip()
            current["frames"].append({"num": int(m.group("num")), "path": path, "symbol": symbol})
    finish()
    return crashes


def parse_events(text: str) -> dict:
    """Parse the boot/rescue and ActivityManager subset of the events buffer."""
    out: dict[str, list[dict]] = {
        "rescue_notes": [],
        "boot_progress": [],
        "am_crashes": [],
        "am_anrs": [],
        "proc_died": [],
    }
    for line in text.splitlines():
        hdr = parse_header(line)
        if not hdr:
            continue
        tag = hdr["tag"]
        msg = hdr["msg"].strip()
        ts = f"{hdr['date']} {hdr['time']}"

        if tag.startswith("rescue_note"):
            m = _RESCUE_NOTE_RE.match(msg)
            if m:
                out["rescue_notes"].append(
                    {
                        "timestamp": ts,
                        "uid": int(m.group(1)),
                        "count": int(m.group(2)),
                        "window_ms": int(m.group(3)),
                    }
                )
            continue

        if tag.startswith("boot_progress"):
            out["boot_progress"].append({"timestamp": ts, "tag": tag, "message": msg})
            continue

        if tag in {"am_crash", "am_anr", "am_proc_died"}:
            values = _event_values(msg)
            record = {"timestamp": ts, "tag": tag, "values": values, "message": msg}
            if tag == "am_crash":
                record["process"] = values.get(2)
                out["am_crashes"].append(record)
            elif tag == "am_anr":
                record["process"] = values.get(2)
                out["am_anrs"].append(record)
            else:
                record["process"] = values.get(2)
                out["proc_died"].append(record)

    return out


def parse_dropbox(text: str) -> list[dict]:
    """Parse ``dumpsys dropbox --print`` into timestamp/tag/body entries."""
    entries: list[dict] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        m = _DROPBOX_HEADER_RE.match(line)
        if m:
            if current:
                _finish_dropbox(current, entries)
            current = {
                "timestamp": m.group("ts"),
                "tag": m.group("tag"),
                "meta": m.group("meta"),
                "body": [],
            }
            continue
        if current is not None:
            if line.startswith(("========================================", "Drop box contents:")):
                continue
            if line:
                current["body"].append(line)
    if current:
        _finish_dropbox(current, entries)
    return entries


def parse_exit_info(text: str) -> list[dict]:
    """Parse ``dumpsys activity exit-info`` records."""
    records: list[dict] = []
    package = None
    current: dict | None = None
    for line in text.splitlines():
        m = _EXIT_PACKAGE_RE.match(line)
        if m:
            package = m.group("package")
            continue
        m = _EXIT_START_RE.match(line)
        if m:
            if current:
                records.append(current)
            current = {
                "package": package,
                "index": int(m.group("index")),
                "timestamp": None,
                "pid": None,
                "process": None,
                "reason": None,
                "subreason": None,
                "status": None,
                "importance": None,
                "pss": None,
                "rss": None,
                "description": None,
            }
            continue
        if current is None:
            continue
        for fm in _EXIT_FIELD_RE.finditer(line.strip()):
            key, value = fm.group("key"), fm.group("value").strip()
            if key in {"timestamp", "pid", "process", "importance", "pss", "rss", "description"}:
                current[key] = value
            elif key in {"reason", "subreason"}:
                current[key] = value
                rm = _EXIT_REASON_RE.search(value)
                if rm:
                    current[f"{key}_text"] = rm.group("reason")
    if current:
        records.append(current)
    return records


def _event_values(message: str) -> dict[int, str]:
    m = _EVENT_ARRAY_RE.match(message.strip())
    if not m:
        return {}
    return {i: part.strip() for i, part in enumerate(m.group(1).split(","))}


def _finish_dropbox(current: dict, entries: list[dict]) -> None:
    body = "\n".join(current["body"]).strip()
    if len(body) > 12000:
        body = body[:12000] + "\n... (truncated)"
    entries.append(
        {
            "timestamp": current["timestamp"],
            "tag": current["tag"],
            "meta": current["meta"],
            "body": body,
        }
    )
