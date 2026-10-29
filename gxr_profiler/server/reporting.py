"""Shared report selection, naming and HTML building."""

from __future__ import annotations

from urllib.parse import quote

from ..core.adb import RunNotFound
from ..core.naming import safe_filename
from ..report.static import MAX_COMPARE_RUNS, build
from ..runs.store import RunStore


def dedupe_labels(labels) -> list[str]:
    if isinstance(labels, str):
        labels = [labels]
    return list(dict.fromkeys(str(x) for x in (labels or [])))


def missing_labels(store: RunStore, labels: list[str]) -> list[str]:
    known = {r.label for r in store.list()}
    return [label for label in labels if label not in known]


def report_filename(labels: list[str]) -> str:
    return f"gxr-profiler_{safe_filename('_vs_'.join(labels))}.html"


def content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode() or "gxr-profiler_run.html"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def validate_selection(labels: list[str]) -> None:
    if len(labels) > MAX_COMPARE_RUNS:
        raise ValueError(f"too many runs selected (maximum {MAX_COMPARE_RUNS})")


def build_report(store: RunStore, labels: list[str], pins=None) -> str:
    try:
        return build(labels, runs_dir=store.runs_dir, pins=pins)
    except RunNotFound as exc:
        raise RunNotFound("one or more runs not found") from exc
