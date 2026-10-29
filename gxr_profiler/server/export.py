"""Offline report export service (HTTP + pywebview save dialog)."""

from __future__ import annotations

import os
from pathlib import Path

from ..core.fs import atomic_write_text
from ..core.paths import default_reports_dir
from ..runs.store import RunStore
from .reporting import build_report, dedupe_labels, missing_labels, report_filename, validate_selection


class ExportService:
    def __init__(self, runs_dir: str) -> None:
        self.runs_dir = runs_dir

    def _checked_labels(self, labels) -> tuple[list[str], str | None]:
        labels = dedupe_labels(labels)
        if not labels:
            return [], "select at least one run"
        try:
            validate_selection(labels)
        except ValueError as exc:
            return [], str(exc)
        missing = missing_labels(RunStore(self.runs_dir), labels)
        if missing:
            return [], "run not found: " + ", ".join(missing)
        return labels, None

    def save_report(self, labels, window, webview_module, pins=None) -> dict:
        labels, error = self._checked_labels(labels)
        if error:
            return {"ok": False, "error": error}
        filename = report_filename(labels)
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.is_dir() else Path(default_reports_dir())

        if window is None or webview_module is None:
            return {"ok": False, "error": "save dialog unavailable"}
        try:
            dialog_type = getattr(getattr(webview_module, "FileDialog", None), "SAVE", None)
            if dialog_type is None:
                dialog_type = webview_module.SAVE_DIALOG
            path = window.create_file_dialog(
                dialog_type,
                directory=str(default_dir),
                save_filename=filename,
            )
        except Exception as exc:
            return {"ok": False, "error": f"save dialog failed: {exc}"}
        if not path:
            return {"ok": False, "cancelled": True}
        if isinstance(path, (list, tuple)):
            path = path[0]
        path = str(path)
        if not path.lower().endswith(".html"):
            path += ".html"
        try:
            html = build_report(RunStore(self.runs_dir), labels, pins=pins)
            atomic_write_text(path, html)
        except Exception as exc:
            return {"ok": False, "error": f"could not save: {exc}"}
        return {"ok": True, "path": os.path.abspath(path)}


def make_js_api(service: ExportService, window_provider, webview_module):
    """Return a pywebview JS API with no non-serializable instance attributes."""

    class ExportApi:
        def save_report(self, labels, pins=None):
            return service.save_report(labels, window_provider(), webview_module, pins=pins)

    return ExportApi()
