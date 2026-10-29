"""Bluetooth and location state parsing."""

from __future__ import annotations

import re

LOCATION_MODES = {0: "off", 1: "device only", 2: "battery saving", 3: "high accuracy"}


def parse_radios(bt_lines: list[str], loc_lines: list[str]) -> dict:
    """Bluetooth adapter state and location services mode/providers."""
    out: dict = {}
    bt_text = "\n".join(bt_lines)
    for line in bt_lines:
        s = line.strip()
        if s in ("0", "1"):
            out["bt_on"] = float(s)
            break
    m = re.search(r"enabled:\s*(true|false)", bt_text)
    if m and "bt_on" not in out:
        out["bt_on"] = 1.0 if m.group(1) == "true" else 0.0
    m = re.search(r"state:\s*([A-Z_]+)", bt_text)
    if m:
        out["bt_state"] = m.group(1)

    loc_text = "\n".join(loc_lines)
    mode: float | None = None
    for line in loc_lines:
        s = line.strip()
        if s in ("0", "1", "2", "3"):
            mode = float(s)
            break
    if mode is not None:
        out["loc_mode"] = mode
        out["loc_enabled"] = 1.0 if mode > 0 else 0.0
        out["loc_mode_name"] = LOCATION_MODES[int(mode)]
    m = re.search(r"^(true|false)$", loc_text, re.MULTILINE)
    if m:
        out["loc_enabled"] = 1.0 if m.group(1) == "true" else 0.0
    for line in loc_lines:
        s = line.strip()
        if s and s not in ("0", "1", "2", "3", "true", "false") and s.lower() not in ("null", "unknown"):
            out["loc_providers"] = s
            break
    return out
