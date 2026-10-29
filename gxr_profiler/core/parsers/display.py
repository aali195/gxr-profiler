"""Display capability parsing from dumpsys display."""

from __future__ import annotations

import re

HDR_TYPES = {1: "Dolby Vision", 2: "HDR10", 3: "HLG", 4: "HDR10+", 5: "Technicolor"}
COLOR_MODES = {
    0: "NATIVE",
    1: "STANDARD",
    2: "WIDE_COLOR_GAMUT",
    3: "DYNAMIC",
    7: "SRGB",
    9: "DISPLAY_P3",
}


def parse_display_info(text: str) -> dict:
    """Parse the active mode, HDR capabilities and brightness range."""
    out: dict = {}
    m = re.search(
        r"mActiveSfDisplayMode=DisplayMode\{[^}]*?width=(\d+),\s*height=(\d+),[^}]*?refreshRate=([\d.]+)",
        text,
    )
    if not m:
        m = re.search(r"width=(\d+),\s*height=(\d+).*?refreshRate=([\d.]+)", text)
    if m:
        out["width"] = int(m.group(1))
        out["height"] = int(m.group(2))
        out["refresh_hz"] = round(float(m.group(3)), 2)

    m = re.search(r"mSupportedHdrTypes=\[([\d,\s]*)\]", text)
    if m:
        codes = [int(x) for x in re.findall(r"\d+", m.group(1))]
        out["hdr_types"] = [HDR_TYPES.get(c, str(c)) for c in codes]
        if codes:
            out["bit_depth"] = 10
    for key, pat in (
        ("max_luminance_nits", r"mMaxLuminance=([\d.]+)"),
        ("max_average_luminance_nits", r"mMaxAverageLuminance=([\d.]+)"),
        ("min_luminance_nits", r"mMinLuminance=([\d.]+)"),
    ):
        m = re.search(pat, text)
        if m:
            out[key] = float(m.group(1))
    m = re.search(
        r"brightnessMinimum ([\d.]+), brightnessMaximum ([\d.]+), brightnessDefault ([\d.]+)",
        text,
    )
    if m:
        out["brightness"] = {
            "min": float(m.group(1)),
            "max": float(m.group(2)),
            "default": float(m.group(3)),
        }
    m = re.search(r"supportedColorModes \[([\d,\s]*)\]", text)
    if m:
        codes = [int(x) for x in re.findall(r"\d+", m.group(1))]
        out["color_modes"] = [COLOR_MODES.get(c, str(c)) for c in codes]
    m = re.search(r"allmSupported (true|false)", text)
    if m:
        out["allm"] = m.group(1) == "true"
    m = re.search(r"gameContentTypeSupported (true|false)", text)
    if m:
        out["game_mode"] = m.group(1) == "true"
    return out
