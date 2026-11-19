"""Passthrough state from XrSystemUI and the CPM controller."""

from __future__ import annotations

import re

PASSTHROUGH_STATE_RE = re.compile(r"New requested state:\s*([A-Za-z]+)(?:\(([^)]*)\))?")
PASSTHROUGH_RUNNING_RE = re.compile(r"passthroughRunning:\s*(\d)")


def parse_passthrough(text: str) -> dict[str, float | str]:
    out: dict[str, float | str] = {}
    for line in text.splitlines():
        m = PASSTHROUGH_STATE_RE.search(line)
        if m:
            mode, args = m.group(1), m.group(2) or ""
            enabled = "requestEnabled=true" in args or ("enabled=true" in args and "requestEnabled=" not in args)
            out["passthrough"] = 1.0 if enabled else 0.0
            out["passthrough_mode"] = mode
            continue
        m = PASSTHROUGH_RUNNING_RE.search(line)
        if m:
            out["passthrough"] = float(m.group(1))
    return out
