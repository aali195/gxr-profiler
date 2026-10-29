"""Display capabilities and panel identification."""

from __future__ import annotations

import re

from ..adb import AdbClient
from ..parsers import parse_display_info


def display_info(text: str, props: dict[str, str]) -> dict:
    display = parse_display_info(text)
    for key, prop in (
        ("hdr_support", "ro.surface_flinger.has_HDR_display"),
        ("wide_color", "ro.surface_flinger.has_wide_color_display"),
        ("color_management", "ro.surface_flinger.use_color_management"),
    ):
        if props.get(prop) is not None:
            display[key] = props.get(prop) == "true"
    return display


def panel_info(adb: AdbClient, check_root: bool) -> dict:
    """Active panel (needs root) plus the shipped XR2 panel variants (no root)."""
    out: dict = {}
    try:
        listing = adb.shell("ls /vendor/etc/display", timeout=8.0)
        names = re.findall(r"qdcm_calib_data_(XR2_[A-Za-z0-9_]+)\.json", listing)
        variants = sorted({n.removesuffix("_SUB") for n in names})
        if variants:
            out["variants"] = variants
    except Exception:
        pass
    if not check_root:
        return out
    script = (
        "su -c 'echo @@TYPE; cat /sys/class/lcd/panel/lcd_type 2>/dev/null; "
        "echo @@CMD; grep -o dsi_display0=[^:]* /proc/cmdline 2>/dev/null; "
        "echo @@EDID; strings /sys/class/drm/card0-DSI-1/edid 2>/dev/null | grep XR2'"
    )
    try:
        txt = adb.shell(script, timeout=10.0)
    except Exception:
        txt = ""
    secs: dict[str, list[str]] = {}
    cur = None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("@@"):
            cur = s[2:]
            secs[cur] = []
        elif cur is not None and s:
            secs[cur].append(s)
    if secs.get("TYPE"):
        out["lcd_type"] = secs["TYPE"][0]
    if secs.get("CMD"):
        m = re.search(r"dsi_display0=(\S+)", secs["CMD"][0])
        if m:
            out["active"] = m.group(1)
    if secs.get("EDID"):
        out["edid"] = secs["EDID"][0]
    return out
