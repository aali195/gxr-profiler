"""Chart/column specification."""

from __future__ import annotations

from fastapi import APIRouter

from ...core.columns import temp_sensor_options
from ...core.models import CAPTURE_PROFILES
from ...report import charts

router = APIRouter()


@router.get("/api/spec")
def spec():
    return {
        **charts.spec(),
        "capture_profiles": CAPTURE_PROFILES,
        "cooldown_sensors": temp_sensor_options(),
    }
