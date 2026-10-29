"""XR perception heartbeats and raw camera stream state."""

from __future__ import annotations

import re

XRB_HEAD_RE = re.compile(r"\[HeadTracking\].*?received from CIB\[[^\]]+\]=\d+\(([\d.]+)fps\)")
XRB_HAND_RE = re.compile(r"\[HandTracking[^\]]*\].*?ImageBundlesReceived=\d+\(([\d.]+)fps\)")
XRB_EYE_RE = re.compile(r"\[EyeTracking[^\]]*\].*?Frames enqueued for tracking=\d+\(([\d.]+)fps\)")
IRLED_FPS_RE = re.compile(r"fps:\s*([\d.]+)")
CIB_RE = re.compile(r"\[CIB\]\s*'([^']+)':\s*\(([\d.]+)\s*FPS\s*@\s*([\d.]+)Hz\)")


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


def cib_key(name: str) -> str:
    return "cib_" + re.sub(r"[^a-z0-9]", "", name.lower())


def parse_cib(msg: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, fps, hz in CIB_RE.findall(msg):
        key = cib_key(name)
        out[key + "_fps"] = float(fps)
        out[key + "_hz"] = float(hz)
    return out
