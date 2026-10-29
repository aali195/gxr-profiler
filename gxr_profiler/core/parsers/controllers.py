"""Controller connection/tracking events from Samsung XR services."""

from __future__ import annotations

import re

CONTROLLER_STATE_RE = re.compile(r"updateDeviceState\s+hand_controller_(left|right):\s+state=([^,]+),\s+battery=(\d+)")
CONTROLLER_TRACK_RE = re.compile(r"(start|stop) tracking for hand_controller_(left|right)")
CONTROLLER_POSE_RE = re.compile(r"Contr\[(\d)\].*?status:(\d+).*?quality:\s*(\d+)")


def parse_controller(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = CONTROLLER_STATE_RE.search(line)
        if m:
            side, state, battery = m.groups()
            disconnected = "disconnect" in state.lower()
            out[f"ctrl_{side}_connected"] = 0.0 if disconnected else 1.0
            out[f"ctrl_{side}_battery"] = float(battery)
            if disconnected:
                out[f"ctrl_{side}_track"] = 0.0
            continue
        m = CONTROLLER_TRACK_RE.search(line)
        if m:
            action, side = m.groups()
            out[f"ctrl_{side}_track"] = 1.0 if action == "start" else 0.0
            continue
        m = CONTROLLER_POSE_RE.search(line)
        if m:
            index, status, quality = (int(x) for x in m.groups())
            side = "left" if index == 0 else "right" if index == 1 else None
            if side:
                out[f"ctrl_{side}_track"] = 1.0 if status == 2 and quality > 0 else 0.0
    return out


def controller_active(events: dict[str, float]) -> float | None:
    track = [v for k, v in events.items() if k.startswith("ctrl_") and k.endswith("_track")]
    if track:
        return 1.0 if any(v > 0 for v in track) else 0.0
    connected = [v for k, v in events.items() if k.startswith("ctrl_") and k.endswith("_connected")]
    if connected:
        return 1.0 if any(v > 0 for v in connected) else 0.0
    return None


def parse_controller_log(text: str) -> dict[str, float]:
    out = parse_controller(text)
    active = controller_active(out)
    if active is not None:
        out["controllers_active"] = active
    return out
