"""Recording status endpoint consumed by the manager UI."""

from __future__ import annotations

from fastapi import APIRouter

from gxr_tools.core.recording_state import read_state

router = APIRouter()


@router.get("/api/recording")
def recording_status():
    return read_state()
