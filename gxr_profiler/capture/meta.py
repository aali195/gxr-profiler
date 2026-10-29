"""Run manifest construction."""

from __future__ import annotations

from .. import __version__
from ..core import schema
from ..core.models import RunConfig
from .columns import REPORT_COLUMNS


def build_meta(
    config: RunConfig,
    *,
    started: str | None,
    recording_started: str | None = None,
    ended: str | None = None,
    duration_actual_s: float | None,
    rows: int,
    device_info: dict,
    start_state: dict,
    end_state: dict,
) -> dict:
    di = device_info
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "tool_version": __version__,
        "label": config.name,
        "started": started,
        "recording_started": recording_started,
        "ended": ended,
        "interval_s": config.interval,
        "duration_s": config.duration,
        "duration_actual_s": round(duration_actual_s, 3) if duration_actual_s else None,
        "rows": rows,
        "columns": len(REPORT_COLUMNS),
        "features": config.features(),
        "notes": config.notes,
        "device_model": di.get("model", ""),
        "android": di.get("android", ""),
        "platform": di.get("board", ""),
        "wifi_ssid": (di.get("wifi") or {}).get("ssid", ""),
        "device_info": di,
        "cooldown_sensor": config.cooldown_sensor,
        "cooldown_below": config.cooldown_below,
        "cooldown_max_wait": config.cooldown_max_wait,
        "start_state": start_state,
        "end_state": end_state,
        "columns_meta": schema.columns_meta(REPORT_COLUMNS),
    }
