"""XR perception heartbeats and raw camera stream state."""

from __future__ import annotations

import re

XRB_HEAD_RE = re.compile(r"\[HeadTracking\].*?received from CIB\[[^\]]+\]=\d+\(([\d.]+)fps\)")
XRB_HAND_RE = re.compile(r"\[HandTracking[^\]]*\].*?ImageBundlesReceived=\d+\(([\d.]+)fps\)")
XRB_EYE_RE = re.compile(r"\[EyeTracking[^\]]*\].*?Frames enqueued for tracking=\d+\(([\d.]+)fps\)")
IRLED_FPS_RE = re.compile(r"fps:\s*([\d.]+)")
IRLED_STATUS_RE = re.compile(
    r"fps:\s*([\d.]+).*?lastIrLedBrightness=(\d+).*?flickerSensorLux:\s*(-?\d+(?:\.\d+)?)"
)
IRLED_WRITER_RE = re.compile(r"QVRIRLedWriter::(start|stop)")
CIB_RE = re.compile(r"\[CIB\]\s*'([^']+)':\s*\(([\d.]+)\s*FPS\s*@\s*[\d.]+Hz\)")


def parse_xr_heartbeat(msg: str) -> dict[str, float]:
    out: dict[str, float] = {}
    m = XRB_HEAD_RE.search(msg)
    if m:
        out["cam_head_fps"] = float(m.group(1))
    m = XRB_HAND_RE.search(msg)
    if m:
        out["cam_hand_fps"] = float(m.group(1))
    m = XRB_EYE_RE.search(msg)
    if m:
        out["cam_eye_fps"] = float(m.group(1))
    return out


def parse_irled_fps(msg: str) -> float | None:
    m = IRLED_FPS_RE.search(msg)
    return float(m.group(1)) if m else None


def parse_irled_status(msg: str) -> dict[str, float] | None:
    """Parse the IRLedController loop line: rate, brightness setpoint, ALS lux."""
    m = IRLED_STATUS_RE.search(msg)
    if not m:
        return None
    return {
        "irled_fps": float(m.group(1)),
        "irled_brightness": float(m.group(2)),
        "irled_lux": float(m.group(3)),
    }


def parse_irled_writer(msg: str) -> float | None:
    """Track whether QVRIRLedWriter is emitting (1) or stopped (0)."""
    m = IRLED_WRITER_RE.search(msg)
    if not m:
        return None
    return 1.0 if m.group(1) == "start" else 0.0


def parse_irled_state(msg: str) -> float | None:
    """Track the IRLedController perception service state (1 = active, 0 = suspended)."""
    if "mName: IRLedController" in msg:
        if "handleResume" in msg:
            return 1.0
        if "handleSuspend" in msg:
            return 0.0
    if "resumePerceptionPlugin, resumed" in msg or "Already RESUMED" in msg or "loop, started" in msg:
        return 1.0
    if "suspendPerceptionPlugin, suspended" in msg or "Already SUSPENDED" in msg or "running=false" in msg:
        return 0.0
    return None


def cib_key(name: str) -> str:
    return "cib_" + re.sub(r"[^a-z0-9]", "", name.lower())


def parse_cib(msg: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, fps in CIB_RE.findall(msg):
        key = cib_key(name)
        out[key + "_fps"] = float(fps)
    return out
