"""Audio codec, flinger, policy and state parsing."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from .media import MAPP, MCODEC, MMIME

MTIME = re.compile(r"\((\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})\)")
MSAMPLE = re.compile(r"android\.media\.mediacodec\.(?:sampleRate|sample-rate)=(\d+)")
MCHANNELS = re.compile(r"android\.media\.mediacodec\.(?:channelCount|channel-count)=(\d+)")


def parse_media_audio(lines: list[str]) -> dict:
    """Return the most recent audio codec session from media.metrics lines."""
    out: dict = {}
    for line in lines:
        if "mode=audio" not in line:
            continue
        m = MCODEC.search(line)
        if not m:
            continue
        out = {"audio_codec": m.group(1)}
        tm = MTIME.search(line)
        if tm:
            mo, d, h, mi, s, ms = (int(x) for x in tm.groups())
            try:
                stamp = datetime(2000, mo, d, h, mi, s, ms * 1000, tzinfo=UTC)
            except ValueError:
                stamp = None
            if stamp is not None:
                out["audio_codec_ts"] = (stamp - datetime(2000, 1, 1, tzinfo=UTC)).total_seconds()
        ma = MAPP.search(line)
        if ma:
            out["audio_codec_app"] = ma.group(1)
        mm = MMIME.search(line)
        if mm:
            out["audio_codec_mime"] = mm.group(1)
        rate = MSAMPLE.search(line)
        if rate:
            out["audio_codec_rate"] = float(rate.group(1))
        ch = MCHANNELS.search(line)
        if ch:
            out["audio_codec_channels"] = float(ch.group(1))
    return out


def audio_format_bits(fmt: str | None) -> float | None:
    if not fmt:
        return None
    if "FLOAT" in fmt:
        return 32.0
    m = re.search(r"(\d+)_BIT", fmt)
    return float(m.group(1)) if m else None


def _audio_thread(block: str) -> dict:
    d: dict = {}
    m = re.search(r"Standby:\s*(yes|no)", block)
    if m:
        d["standby"] = m.group(1)
    m = re.search(r"Sample rate:\s*(\d+)\s*Hz", block)
    if m:
        d["rate"] = float(m.group(1))
    m = re.search(r"HAL format:\s*0x[0-9a-f]+ \(([A-Z0-9_]+)\)", block)
    if m:
        d["format"] = m.group(1).removeprefix("AUDIO_FORMAT_")
    m = re.search(r"Channel count:\s*(\d+)", block)
    if m:
        d["channels"] = float(m.group(1))
    m = re.search(r"Output devices:\s*[^(]*\(([^)]+)\)", block)
    if m:
        d["out_device"] = m.group(1)
    m = re.search(r"Input device:\s*[^(]*\(([^)]+)\)", block)
    if m:
        d["in_device"] = m.group(1)
    m = re.search(r"Audio source:\s*\d+ \(([^)]+)\)", block)
    if m:
        d["source"] = m.group(1)
    m = re.search(r"Master mute:\s*(on|off)", block)
    if m:
        d["master_mute"] = m.group(1) == "on"
    m = re.search(r"Normal mixer raw underrun counters: partial=(\d+) empty=(\d+)", block)
    if m:
        d["underruns"] = float(int(m.group(1)) + int(m.group(2)))
    m = re.search(r"Threadloop write latency stats: ave=([\d.]+)", block)
    if m:
        d["write_ms"] = float(m.group(1))
    m = re.search(r"(\d+) Tracks of which (\d+) are active", block)
    if m:
        d["tracks"] = int(m.group(1))
        d["active_tracks"] = int(m.group(2))
    return d


def _clean_device(name: str) -> str:
    return name.replace("AUDIO_DEVICE_OUT_", "").replace("AUDIO_DEVICE_IN_", "").replace("AUDIO_DEVICE_", "")


def parse_audio_flinger(text: str) -> dict:
    """Active output/input thread state from media.audio_flinger."""
    blocks = re.split(r"(?m)^(?=(?:Output|Input) thread )", text)
    outs: list[dict] = []
    ins: list[dict] = []
    for block in blocks:
        if block.startswith("Output thread"):
            outs.append(_audio_thread(block))
        elif block.startswith("Input thread"):
            ins.append(_audio_thread(block))

    out: dict = {}
    active_out = [o for o in outs if o.get("standby") == "no" and o.get("active_tracks", 0) > 0]
    active_out.sort(key=lambda o: o.get("active_tracks", 0), reverse=True)
    if active_out:
        o = active_out[0]
        out["audio_out_active"] = 1.0
        for key, col in (
            ("out_device", "audio_out_device"),
            ("format", "audio_out_format"),
            ("rate", "audio_out_rate"),
            ("channels", "audio_out_channels"),
            ("underruns", "audio_out_underruns"),
            ("write_ms", "audio_out_write_ms"),
        ):
            if key in o:
                out[col] = o[key]
        bits = audio_format_bits(o.get("format"))
        if bits is not None:
            out["audio_out_bits"] = bits
        if "master_mute" in o:
            out["audio_out_mute"] = 1.0 if o["master_mute"] else 0.0
        if "out_device" in o:
            out["audio_out_device"] = _clean_device(o["out_device"])
    else:
        out["audio_out_active"] = 0.0

    active_in = [i for i in ins if i.get("standby") == "no" and i.get("active_tracks", 0) > 0]
    active_in.sort(key=lambda i: i.get("active_tracks", 0), reverse=True)
    if active_in:
        i = active_in[0]
        out["audio_in_active"] = 1.0
        for key, col in (
            ("in_device", "audio_in_device"),
            ("format", "audio_in_format"),
            ("rate", "audio_in_rate"),
            ("channels", "audio_in_channels"),
            ("source", "audio_in_source"),
        ):
            if key in i:
                out[col] = i[key]
        bits = audio_format_bits(i.get("format"))
        if bits is not None:
            out["audio_in_bits"] = bits
        if "in_device" in i:
            out["audio_in_device"] = _clean_device(i["in_device"])
        if "source" in i:
            out["audio_in_source"] = i["source"].replace("AUDIO_SOURCE_", "")
    else:
        out["audio_in_active"] = 0.0
    return out


def parse_audio_state(text: str) -> dict:
    """Audio focus, active playback count, music volume and mic mute."""
    out: dict = {}
    m = re.search(r"Audio Focus stack entries[^\n]*\n(.*?)(?=\n[^\s]|\Z)", text, re.DOTALL)
    if m:
        packs = re.findall(r"pack:\s*([\w.]+)", m.group(1))
        if packs:
            out["audio_app"] = packs[-1]

    m = re.search(r"players:\n(.*?)\n\s*ducked players", text, re.DOTALL)
    if m:
        states = re.findall(r"AudioPlaybackConfiguration .*?state:(\w+)", m.group(1))
        out["audio_players"] = float(states.count("started"))

    m = re.search(r"mic mute FromSwitch=(\w+) FromRestrictions=(\w+) FromApi=(\w+) from system=(\w+)", text)
    if m:
        out["audio_mic_mute"] = 1.0 if any(x == "true" for x in m.groups()) else 0.0

    m = re.search(r"- STREAM_MUSIC:\n(.*?)(?=\n- STREAM_|\Z)", text, re.DOTALL)
    if m:
        block = m.group(1)
        muted = re.search(r"Muted:\s*(true|false)", block)
        maxv = re.search(r"Max:\s*(\d+)", block)
        vol = re.search(r"streamVolume:(\d+)", block)
        if muted:
            out["audio_out_mute"] = 1.0 if muted.group(1) == "true" else 0.0
        if maxv and vol:
            mx = int(maxv.group(1))
            if mx:
                out["audio_out_volume_pct"] = round(100.0 * int(vol.group(1)) / mx, 1)
    return out


def _audio_devices(block: str) -> list[dict]:
    devices: list[dict] = []
    for m in re.finditer(r'Port ID: \d+; "([^"]+)"; \{([^}]+)\}(.*?)(?=Port ID: \d+;|\Z)', block, re.DOTALL):
        name, body = m.group(1), m.group(3)
        formats = re.findall(r"AUDIO_FORMAT_([A-Z0-9_]+) \(0x[0-9a-fA-F]+\)", body)
        rates: list[int] = []
        for rm in re.finditer(r"sampling rates: ([^\n]+)", body):
            rates.extend(int(x) for x in re.findall(r"\d+", rm.group(1)))
        if name and formats:
            devices.append({"name": name, "formats": sorted(set(formats)), "rates_hz": sorted(set(rates))})
    return devices


def parse_audio_policy(text: str) -> dict:
    """Supported output/input devices, formats and sample rates."""
    if "Available output devices" not in text:
        return {}
    if "Available input devices" in text:
        head, rest = text.split("Available input devices", 1)
        rest = rest.split("Hardware modules", 1)[0]
    else:
        head, rest = text, ""
    return {"outputs": _audio_devices(head), "inputs": _audio_devices(rest)}
