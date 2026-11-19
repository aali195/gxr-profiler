"""Background diagnostics snapshot manager and saved report files."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from gxr_tools.core.adb import AdbClient, AdbError, RealAdb, resolve_serial
from gxr_tools.core.fs import atomic_write_text
from gxr_tools.core.paths import ensure_writable_dir

from ..core.collector import DiagnosticsCollector
from ..core.diagnostics import analyze_report, format_markdown

log = logging.getLogger(__name__)


class DebugManager:
    """Collect one diagnostics snapshot at a time and retain the latest result."""

    def __init__(
        self,
        serial: str | None = None,
        reports_dir: str | None = None,
        adb_factory: Callable[..., AdbClient] = RealAdb,
    ) -> None:
        self.serial = serial
        self.reports_dir = reports_dir
        self.adb_factory = adb_factory
        self.lock = threading.Lock()
        self._lifecycle = threading.Lock()
        self.thread: threading.Thread | None = None
        self.status = "idle"
        self.error = ""
        self.started = ""
        self.finished = ""
        self.report: dict | None = None

    def start(self, options: dict) -> None:
        with self._lifecycle:
            with self.lock:
                if self.thread and self.thread.is_alive():
                    raise RuntimeError("a diagnostics snapshot is already running")
            try:
                serial = resolve_serial(self.serial)
            except AdbError as exc:
                with self.lock:
                    self.status = "error"
                    self.error = str(exc)
                raise RuntimeError(str(exc)) from exc
            with self.lock:
                self.status = "running"
                self.error = ""
                self.started = datetime.now(UTC).isoformat()
                self.finished = ""
                self.report = None
            self.thread = threading.Thread(
                target=self._run,
                args=(serial, dict(options)),
                name="diagnostics",
                daemon=True,
            )
            self.thread.start()

    def _run(self, serial: str, options: dict) -> None:
        try:
            adb = self.adb_factory(serial=serial)
            report = DiagnosticsCollector(adb, **options).collect()
            report["issues"] = analyze_report(report)
            report["saved"] = self._save(report)
            with self.lock:
                self.report = report
                self.status = "done"
                self.finished = datetime.now(UTC).isoformat()
        except Exception as exc:
            log.exception("diagnostics snapshot failed")
            with self.lock:
                self.status = "error"
                self.error = str(exc)
                self.finished = datetime.now(UTC).isoformat()

    def _save(self, report: dict) -> dict:
        if not self.reports_dir:
            return {}
        try:
            ensure_writable_dir(self.reports_dir)
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")[:-3]
            folder = Path(self.reports_dir)
            json_path = folder / f"diagnostics-{stamp}.json"
            md_path = folder / f"diagnostics-{stamp}.md"
            saved = {"json": str(json_path.resolve()), "markdown": str(md_path.resolve())}
            report["saved"] = saved
            atomic_write_text(json_path, json.dumps(report, indent=2, ensure_ascii=False))
            atomic_write_text(md_path, format_markdown(report))
            return saved
        except Exception as exc:
            log.warning("could not save diagnostics snapshot", exc_info=True)
            return {"error": str(exc)}

    def state(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "started": self.started,
                "finished": self.finished,
                "error": self.error,
                "running": bool(self.thread and self.thread.is_alive()),
                "collected_at": (self.report or {}).get("collected_at"),
                "saved": (self.report or {}).get("saved") or {},
            }

    def latest(self) -> dict | None:
        with self.lock:
            return self.report

    def shutdown(self, timeout: float = 30.0) -> None:
        thread = self.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
