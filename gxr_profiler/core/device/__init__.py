"""Device snapshot collection (props, display, audio, Wi-Fi, root, panel)."""

from __future__ import annotations

from ..parsers.display import parse_display_info
from .info import collect_device_info

__all__ = ["collect_device_info", "parse_display_info"]
