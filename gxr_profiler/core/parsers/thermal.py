"""Thermal service parsing."""

from __future__ import annotations

import re

THERM_TEMP_RE = re.compile(r"Temperature\{mValue=([\d.]+),\s*mType=(-?\d+),\s*mName=([^,]+),\s*mStatus=(-?\d+)\}")


def parse_thermalservice(text: str) -> dict[str, float]:
    """Extract thermal status and live HAL temperatures.

    Prefers the 'Current temperatures from HAL' block (live) over the cached
    block. Returns t_<NAME> temps plus sev_<NAME> throttling severities.
    """
    out: dict[str, float] = {}
    m = re.search(r"Thermal Status:\s*(\d+)", text)
    if m:
        out["thermal_status"] = float(m.group(1))

    block = text
    idx = text.find("Current temperatures from HAL:")
    if idx != -1:
        block = text[idx:]
        end = block.find("Current cooling devices")
        if end != -1:
            block = block[:end]
    for val, _typ, name, status in THERM_TEMP_RE.findall(block):
        name = name.strip()
        out[f"t_{name}"] = float(val)
        out[f"sev_{name}"] = float(status)
    return out
