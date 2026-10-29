"""Android sensor service summary parsing."""

from __future__ import annotations

import re

SENS_TOTAL_RE = re.compile(r"Total\s+(\d+)\s+h/w sensors,\s*(\d+)\s+running\s+(\d+)\s+disabled clients")
SENS_SAMPLING_RE = re.compile(r"sampling_period\(ms\) = \{[^}]*\},\s*selected = ([\d.]+) ms")
SENS_CONN_RE = re.compile(r"(\d+) active connections")
SENS_ACTIVE_ENTRY_RE = re.compile(r"\(handle=0x[0-9a-fA-F]+,\s*connections=\d+\)")


def parse_sensors(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    m = SENS_TOTAL_RE.search(text)
    if m:
        out["sensors_total"] = float(m.group(1))
        out["sensors_running"] = float(m.group(2))
        out["sensors_disabled_clients"] = float(m.group(3))
    rates = [float(x) for x in SENS_SAMPLING_RE.findall(text)]
    if rates:
        out["sensor_rate_min_ms"] = min(rates)
        out["sensor_rate_max_ms"] = max(rates)
        if min(rates) > 0:
            out["sensor_max_hz"] = 1000.0 / min(rates)
    conns = [int(x) for x in SENS_CONN_RE.findall(text)]
    if conns:
        out["sensor_conns"] = float(sum(conns))
    out["sensors_active"] = float(len(SENS_ACTIVE_ENTRY_RE.findall(text)))
    return out
