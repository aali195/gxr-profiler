"""Recording start/stop/status and live SSE stream."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from ...capture.poller import Poller
from ...core.adb import AdbError, RealAdb, resolve_serial
from ..deps import ManagerDep
from ..models import RecordRequest

router = APIRouter()


@router.get("/api/preview")
def preview(manager: ManagerDep):
    """Return a lightweight, unsaved view of the current headset state."""
    if manager.state().get("status") == "recording":
        raise HTTPException(status_code=409, detail="recording in progress")
    try:
        adb = RealAdb(serial=resolve_serial(manager.serial))
        data = Poller(adb).poll_preview()
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"preview unavailable: {exc}") from exc
    severities = [v for k, v in data.items() if k.startswith("sev_") and isinstance(v, (int, float))]
    data["thermal_max_sev"] = max(severities) if severities else None
    return data


@router.post("/api/record")
def record_start(body: RecordRequest, manager: ManagerDep):
    try:
        manager.start(body.to_config(manager.runs_dir))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@router.post("/api/record/stop")
def record_stop(manager: ManagerDep):
    manager.stop()
    return {"ok": True}


@router.get("/api/record/status")
def record_status(manager: ManagerDep):
    return manager.state()


@router.get("/api/record/stream")
async def stream(manager: ManagerDep, last_event_id: str | None = Header(default=None, alias="Last-Event-ID")):
    try:
        last_seq = int(last_event_id or 0)
    except ValueError:
        last_seq = 0

    async def gen():
        nonlocal last_seq
        while True:
            with manager.lock:
                pending = [ev for ev in manager.events if int(ev.get("seq", 0)) > last_seq]
                status = manager.status
                total_rows = manager.row_count
            for ev in pending:
                last_seq = max(last_seq, int(ev.get("seq", 0)))
                yield f"id: {last_seq}\ndata: {json.dumps(ev)}\n\n"
            if not pending:
                yield f"event: status\ndata: {json.dumps({'status': status, 'rows': total_rows})}\n\n"
            if status in ("done", "error") and not pending:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
