"""Media codec, SurfaceFlinger and display parsing."""

from __future__ import annotations

import re

MCODEC = re.compile(r"android\.media\.mediacodec\.codec=([^,}\s]+)")
MMIME = re.compile(r"android\.media\.mediacodec\.mime=([^,}\s]+)")
MAPP = re.compile(r"\(([A-Za-z][A-Za-z0-9_.]*),\s*-?\d+,\s*-?\d+\)")
MID = re.compile(r"android\.media\.mediacodec\.id=(-?\d+)")
MPROFILE = re.compile(r"android\.media\.mediacodec\.profile=(\d+)")
MHDR = re.compile(r"android\.media\.mediacodec\.hdr-format=(-?\d+)")
MW = re.compile(r"android\.media\.mediacodec\.width=(\d+)")
MH = re.compile(r"android\.media\.mediacodec\.height=(\d+)")
RESOURCE_PID = re.compile(r"^Pid: (-?\d+)$")
RESOURCE_MEDIA_INFO = re.compile(
    r"addMediaInfo\(pid (-?\d+), clientId (-?\d+), resources (\d+)x(\d+) "
    r"\(fps:([\d.]+)\).*?sw codec : (yes|no).*?encoder : (yes|no).*?componentName = (\S+).*?bitrate = (\d+)"
)

HDR_MARKERS = ("BT2020", "PQ", "HLG", "ST2084", "HDR")


def parse_media_video(lines: list[str]) -> dict:
    """Return the most recent video codec session from media.metrics lines."""
    out: dict = {}
    for line in lines:
        if "mode=video" not in line:
            continue
        m = MCODEC.search(line)
        if not m:
            continue
        out = {"media_codec": m.group(1)}
        ma = MAPP.search(line)
        if ma:
            out["media_app"] = ma.group(1)
        mm = MMIME.search(line)
        if mm:
            out["media_mime"] = mm.group(1)
        mid = MID.search(line)
        if mid:
            out["media_id"] = float(mid.group(1))
        prof = MPROFILE.search(line)
        if prof:
            out["media_profile"] = float(prof.group(1))
        hdr = MHDR.search(line)
        if hdr:
            out["media_hdr_format"] = float(hdr.group(1))
        w = MW.search(line)
        h = MH.search(line)
        if w:
            out["media_w"] = float(w.group(1))
        if h:
            out["media_h"] = float(h.group(1))
    bd = media_bit_depth(out.get("media_mime"), out.get("media_profile"))
    if bd is not None:
        out["media_bit_depth"] = bd
    return out


def _resource_client_info(lines: list[str]) -> dict[int, dict]:
    """Return the latest addMediaInfo/getMediaResourceInfo data by client id."""
    add = re.compile(
        r"addMediaInfo\(pid (-?\d+), clientId (-?\d+), resources (\d+)x(\d+) "
        r"\(fps:([\d.]+)\).*?sw codec : (yes|no).*?encoder : (yes|no).*?componentName = (\S+)"
    )
    get = re.compile(
        r"getMediaResourceInfo\(PID : (-?\d+), clientID : (-?\d+), "
        r".*?resources (\d+)x(\d+) \(fps:([\d.]+)\).*?sw codec : (yes|no).*?encoder : (yes|no)"
    )
    out: dict[int, dict] = {}
    order = 0
    for line in lines:
        m = add.search(line) or get.search(line)
        if not m:
            continue
        cid, w, h, sw, enc = int(m.group(2)), m.group(3), m.group(4), m.group(6), m.group(7)
        if cid not in out:
            out[cid] = {
                "media_w": float(w),
                "media_h": float(h),
                "media_hw_dec": 1.0 if sw == "no" and enc == "no" else 0.0,
                "media_sw_dec": 1.0 if sw == "yes" else 0.0,
                "media_encoder": enc == "yes",
                "order": order,
            }
            order += 1
    return out


def parse_media_resources(lines: list[str]) -> dict:
    """Parse the live video decoder allocation from media.resource_manager.

    This is an allocation view, not a frame-decoding counter.  It deliberately
    ignores encoder clients and accepts any positive video resource count.
    """
    clients: list[dict] = []
    current_pid: int | None = None
    current: dict | None = None
    for line in lines:
        if line.startswith(("Process Pid override", "Events logs")):
            break
        m = RESOURCE_PID.fullmatch(line)
        if m:
            current_pid = int(m.group(1))
            continue
        if line == "Client:":
            current = {"pid": current_pid, "id": None, "name": None, "video": False}
            clients.append(current)
            continue
        if current is None:
            continue
        if line.startswith("Id: "):
            try:
                current["id"] = int(line[4:].strip())
            except ValueError:
                pass
        elif line.startswith("Name: "):
            current["name"] = line[6:].strip()
        elif "video-codec" in line:
            try:
                count = int(line.rsplit(":", 1)[1].strip())
            except (IndexError, ValueError):
                count = 0
            if count > 0:
                current["video"] = True

    candidates = [c for c in clients if c["video"] and c["name"]]
    if not candidates:
        return {}

    info_by_id = _resource_client_info(lines)
    # addMediaInfo/getMediaResourceInfo history is newest-first.  Pick the
    # newest non-encoder video client; fall back to the first decoder-looking
    # candidate if no media-info event is available.
    candidates = [c for c in candidates if not info_by_id.get(c["id"], {}).get("media_encoder", False)]
    candidates = [c for c in candidates if ".encoder" not in (c["name"] or "").lower()]
    if candidates:
        candidates.sort(key=lambda c: info_by_id.get(c["id"], {}).get("order", 1_000_000))
    active = candidates[0] if candidates else None
    if active is None:
        return {}

    out = {"media_active": 1.0, "media_codec": active["name"]}
    info = info_by_id.get(active["id"])
    if info:
        out.update({k: v for k, v in info.items() if k not in ("media_encoder", "order")})
    else:
        name = active["name"]
        out["media_hw_dec"] = 1.0 if is_hw_codec(name) else 0.0
        out["media_sw_dec"] = 1.0 if is_sw_codec(name) else 0.0
    return out


def media_bit_depth(mime: str | None, profile: float | None) -> float | None:
    """Infer decoded bit depth from the codec profile (Android constants)."""
    if profile is None:
        return None
    p = int(profile)
    if mime in ("video/hevc", "video/av01"):
        return 10.0 if p in (2, 4096, 8192) else 8.0
    if mime in ("video/x-vnd.on2.vp9", "video/vp9"):
        return 10.0 if p in (4, 8, 4096, 8192, 16384, 32768) else 8.0
    if mime == "video/avc":
        return 10.0 if p in (16,) else 8.0
    return None


def visible_sf_lines(lines: list[str]) -> list[str]:
    """Keep dataspaces/formats from visible compositor layers.

    `sort -u` used to mix hidden, cached and active layers, which can make an
    inactive HDR layer look like current output.  Layer blocks precede their
    composition type, so retain a line only after seeing a non-INVALID layer.
    """
    out: list[str] = []
    visible: bool | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("* Layer"):
            visible = None
        elif "composition type=" in stripped:
            visible = "INVALID" not in stripped.upper()
        elif (
            stripped.startswith("Current color mode:")
            or visible is not False
            and stripped.startswith(("dataspace=", "format:"))
        ):
            out.append(stripped)
    return out


def bit_depth_from_formats(lines: list[str]) -> float | None:
    """Active composer bit depth from SurfaceFlinger layer formats."""
    text = " ".join(lines).upper()
    if any(tag in text for tag in ("1010102", "P010", "P210", "Y210", "10_BIT", "RGBA_10")):
        return 10.0
    if "8888" in text:
        return 8.0
    return None


def color_mode_from_lines(lines: list[str]) -> str | None:
    for line in lines:
        m = re.search(r"Current color mode:\s*ColorMode::([A-Z0-9_]+)", line)
        if m:
            return m.group(1)
    return None


def is_hw_codec(name: str) -> bool:
    return name.startswith(("c2.qti.", "OMX.qcom.", "OMX.qti."))


def is_sw_codec(name: str) -> bool:
    return name.startswith(("c2.android.", "OMX.google."))


def parse_display_props(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    m = re.search(r"Display Brightness=([\d.]+)", text)
    if m:
        out["disp_brightness"] = float(m.group(1))
    else:
        m = re.search(r"mBrightnessState=([\d.]+)", text)
        if m:
            out["disp_brightness"] = float(m.group(1))
    m = re.search(r"Display SdrBrightness=([\d.]+)", text)
    if m:
        out["disp_sdr_brightness"] = float(m.group(1))
    return out


def hdr_from_dataspaces(lines: list[str]) -> bool:
    for line in lines:
        token = line.upper()
        if any(marker in token for marker in HDR_MARKERS):
            return True
    return False
