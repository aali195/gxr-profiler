"""One-click diagnostics snapshot and saved report access."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import DebugDep
from ..models import DebugRequest

router = APIRouter()


@router.post("/api/debug/collect")
def debug_collect(body: DebugRequest, debug: DebugDep):
    try:
        debug.start(body.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/api/debug/status")
def debug_status(debug: DebugDep):
    return debug.state()


@router.get("/api/debug/report")
def debug_report(debug: DebugDep):
    report = debug.latest()
    if report is None:
        raise HTTPException(status_code=404, detail="no diagnostics snapshot has been collected yet")
    return report
