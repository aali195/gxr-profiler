"""Logcat header and event parsing."""

from __future__ import annotations

import re

LOG_RE = re.compile(
    r"^(?P<date>\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(?P<prio>[VDIWEFS])/(?P<tag>.+?)\(\s*(?P<pid>\d+)\):\s?(?P<msg>.*)$"
)
THERM_CHANGED_RE = re.compile(
    r"^\[(?P<name>[^,]+),(?P<type>-?\d+),(?P<value>-?[0-9.]+),(?P<sev>-?\d+),(?P<hot>-?\d+)\]"
)
KV_COLON_RE = re.compile(r"([A-Za-z0-9_]+)\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)")
KV_EQ_RE = re.compile(r"([A-Za-z0-9_]+)\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)")
FAN_RE = re.compile(r"step\s*=\s*(\d+)")
DCVSH_RE = re.compile(r"cluster:\s*(-?\d+),\s*scaling limit:\s*(\d+),\s*max possible:\s*(\d+)")

DYNPOL_FIELDS = {
    "thermal_status": re.compile(r'"Thermal status":\s*(\d+)'),
    "xr_fps": re.compile(r'"FrameRate":\s*([0-9.]+)'),
    "xr_target": re.compile(r'"ExpectedFrameRate":\s*([0-9.]+)'),
    "xr_drops": re.compile(r'"frame drops/sec":\s*([0-9.]+)'),
    "xr_cpu": re.compile(r'"CPU":\s*([0-9.]+)'),
    "xr_gpu": re.compile(r'"GPU":\s*([0-9.]+)'),
    "xr_ram": re.compile(r'"RAM":\s*([0-9.]+)'),
    "disp_hz": re.compile(r'"Refresh rate: "\s*:\s*([0-9.]+)'),
}
PSM_RE = re.compile(r'"Power save mode":\s*(true|false)')

SSRM_SIOP_SENSORS = {"CHG", "SUBBAT", "BAT", "USB", "WIFI", "AP", "LRP"}
SSRM_S_SENSORS = {"AP", "LRP", "USB", "BAT"}


def parse_header(line: str) -> dict | None:
    m = LOG_RE.match(line)
    if not m:
        return None
    d = m.groupdict()
    d["tag"] = d["tag"].strip()
    return d


def parse_thermal_changed(msg: str) -> dict | None:
    m = THERM_CHANGED_RE.match(msg.strip())
    if not m:
        return None
    return {
        "name": m.group("name").strip(),
        "type": int(m.group("type")),
        "value": float(m.group("value")),
        "sev": int(m.group("sev")),
        "hot": int(m.group("hot")),
    }


def parse_kv_colon(msg: str) -> dict[str, float]:
    return {k: float(v) for k, v in KV_COLON_RE.findall(msg)}


def parse_kv_eq(msg: str) -> dict[str, float]:
    return {k: float(v) for k, v in KV_EQ_RE.findall(msg)}


def parse_fan_step(msg: str) -> int | None:
    m = FAN_RE.search(msg)
    return int(m.group(1)) if m else None


def parse_dcvsh(msg: str) -> dict | None:
    m = DCVSH_RE.search(msg)
    if not m:
        return None
    return {"cluster": int(m.group(1)), "limit": int(m.group(2)), "max": int(m.group(3))}


def parse_dynpol(msg: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, rx in DYNPOL_FIELDS.items():
        m = rx.search(msg)
        if m:
            out[key] = float(m.group(1))
    m = PSM_RE.search(msg)
    if m:
        out["psm"] = 1.0 if m.group(1) == "true" else 0.0
    return out
