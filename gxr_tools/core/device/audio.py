"""Audio capability snapshot."""

from __future__ import annotations

from ..adb import AdbClient
from ..parsers import parse_audio_policy


def audio_info(adb: AdbClient) -> dict:
    return parse_audio_policy(adb.shell("dumpsys media.audio_policy", timeout=15.0))
