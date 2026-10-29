"""Self-contained HTML report export."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ...core.adb import RunNotFound
from ..deps import StoreDep
from ..reporting import (
    build_report,
    content_disposition,
    dedupe_labels,
    missing_labels,
    report_filename,
    validate_selection,
)

router = APIRouter()


def _parse_pins(raw: str | None):
    if not raw:
        return None
    try:
        pins = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid pins payload") from exc
    if not isinstance(pins, dict):
        raise HTTPException(status_code=400, detail="invalid pins payload")
    return pins


@router.get("/api/report")
def export_report(
    store: StoreDep,
    labels: list[str] | None = Query(default=None),
    pins: str | None = Query(default=None),
):
    labels = dedupe_labels(labels)
    if not labels:
        raise HTTPException(status_code=400, detail="select at least one run")
    pins_payload = _parse_pins(pins)
    try:
        validate_selection(labels)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    missing = missing_labels(store, labels)
    if missing:
        raise HTTPException(status_code=404, detail="run not found: " + ", ".join(missing))
    try:
        html = build_report(store, labels, pins=pins_payload)
    except RunNotFound:
        raise HTTPException(status_code=404, detail="one or more runs not found")
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": content_disposition(report_filename(labels))},
    )
