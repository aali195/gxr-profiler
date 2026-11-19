"""Thermal service parsing."""

from __future__ import annotations

import re

from ..columns import THERMAL_ZONE_KEYS

THERM_TEMP_RE = re.compile(r"Temperature\{mValue=([\d.]+),\s*mType=(-?\d+),\s*mName=([^,]+),\s*mStatus=(-?\d+)\}")
MAX34427_RE = re.compile(r"(-?[\d.]+)A,\s*(-?[\d.]+)W,\s*(-?[\d.]+)V")


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


def parse_thermal_zones(lines: list[str]) -> dict[str, float]:
    """Parse ``<zone type> <millidegrees>`` lines from the raw thermal zones."""
    out: dict[str, float] = {}
    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            continue
        zone, raw = parts
        col = THERMAL_ZONE_KEYS.get(zone)
        if col is None:
            continue
        try:
            value = float(raw) / 1000.0
        except ValueError:
            continue
        if -40.0 <= value <= 150.0:
            out[col] = value
    return out


def parse_max34427(lines: list[str]) -> dict[str, float]:
    """Parse the active MAX34427 ``ch1 <current>A, <power>W, <voltage>V`` line."""
    out: dict[str, float] = {}
    for line in lines:
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[0] != "ch1":
            continue
        match = MAX34427_RE.search(parts[1])
        if not match:
            continue
        current, power, voltage = (float(value) for value in match.groups())
        out["max_ch1_current"] = current
        out["max_ch1_power"] = power
        out["max_ch1_voltage"] = voltage
    return out
