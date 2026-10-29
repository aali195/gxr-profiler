"""Guardian/boundary status from Android system settings (read-only)."""

from __future__ import annotations

import logging

from ..adb import AdbClient

log = logging.getLogger(__name__)


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return None


def _number(value: str | None, cast):
    if value is None or not value.strip():
        return None
    try:
        return cast(value.strip())
    except (TypeError, ValueError):
        return None


def parse_boundary_settings(lines: list[str]) -> dict:
    raw: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if sep:
            raw[key.strip()] = value.strip()
    out = {
        "consent_granted": _bool(raw.get("guardian_consent_granted")),
        "toggle_guardian": _bool(raw.get("toggle_guardian")),
        "radius_m": _number(raw.get("guardian_radius"), float),
        "placement_mode": _number(raw.get("guardian_boundary_placement_mode"), int),
        "position_setup_available": _bool(raw.get("guardian_position_setup_available")),
        "toggle_radius_available": _bool(raw.get("guardian_toggle_radius_available")),
        "floor_setup_mode": _number(raw.get("guardian_floor_height_setup_mode"), int),
        "floor_offset_m": _number(raw.get("guardian_floor_y_offset_from_head"), float),
    }
    return {k: v for k, v in out.items() if v is not None}


def boundary_info(adb: AdbClient) -> dict:
    try:
        text = adb.shell(
            "echo @@SECURE; settings list secure | grep '^guardian_'; "
            "echo @@SYSTEM; settings list system | grep -E '^guardian_|^toggle_guardian'",
            timeout=8.0,
        )
        return parse_boundary_settings(text.splitlines())
    except Exception:
        log.debug("could not read boundary settings", exc_info=True)
        return {}
