"""Device settings snapshot and reversible toggles."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from gxr_tools.core.adb import AdbError

from ..deps import IdleDep, SettingsDep
from ..models import SettingUpdate

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/settings")
def list_settings(settings: SettingsDep):
    try:
        return settings.snapshot()
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not read settings")
        raise HTTPException(status_code=500, detail="could not read settings") from exc


@router.post("/api/settings/{setting_id}")
def update_setting(setting_id: str, body: SettingUpdate, settings: SettingsDep, _idle: IdleDep):
    try:
        if body.value is not None:
            return settings.set_value(setting_id, body.value)
        return settings.set_enabled(setting_id, bool(body.enabled))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("setting update failed for %s", setting_id)
        raise HTTPException(status_code=500, detail="setting update failed") from exc
