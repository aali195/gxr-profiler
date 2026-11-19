"""Background recorder manager and SSE fan-out state."""

from __future__ import annotations

import logging
import threading
from collections import deque

from gxr_core.adb import CONNECT_POLL_S, CONNECT_WAIT_S, AdbError, RealAdb, resolve_serial
from gxr_core.naming import validate_run_name
from gxr_core.recording_state import RecordingMarker

from ..capture.recorder import Recorder
from ..core.models import RunConfig

log = logging.getLogger(__name__)


class RecordManager:
    """Runs a Recorder on a background thread and fans events out to SSE clients."""

    def __init__(self, runs_dir: str, serial: str | None = None) -> None:
        self.runs_dir = runs_dir
        self.serial = serial
        self.lock = threading.Lock()
        self._lifecycle = threading.Lock()
        self.events: deque[dict] = deque(maxlen=2000)
        self.next_seq = 0
        self.row_count = 0
        self.elapsed = 0.0
        self.status = "idle"
        self.label = ""
        self.duration = 0.0
        self.profile = ""
        self.recorder: Recorder | None = None
        self.thread: threading.Thread | None = None
        self.recording = RecordingMarker()

    def _on_sample(self, event) -> None:
        with self.lock:
            self.next_seq += 1
            self.row_count += 1
            self.elapsed = float(event.elapsed_s)
            self.events.append(
                {"seq": self.next_seq, "rows": self.row_count, "elapsed": event.elapsed_s, "row": event.row}
            )

    def start(self, cfg: RunConfig) -> None:
        with self._lifecycle:
            self._start_locked(cfg)

    def _start_locked(self, cfg: RunConfig) -> None:
        validate_run_name(cfg.name)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("a recording is already running")
        try:
            serial = resolve_serial(self.serial, wait_seconds=CONNECT_WAIT_S, poll_seconds=CONNECT_POLL_S)
        except AdbError as exc:
            with self.lock:
                self.status = "error"
            raise RuntimeError(str(exc)) from exc

        adb = RealAdb(serial=serial)
        recorder = Recorder(adb, cfg, on_sample=self._on_sample)
        with self.lock:
            self.events.clear()
            self.next_seq = 0
            self.row_count = 0
            self.elapsed = 0.0
            self.status = "recording"
            self.label = cfg.name
            self.duration = cfg.duration
            self.profile = cfg.profile
            self.recorder = recorder

        self.recording.start(cfg.name)

        def _run() -> None:
            status = "error"
            try:
                recorder.run()
                status = "done"
            except Exception:
                log.exception("recording failed")
            finally:
                with self.lock:
                    self.elapsed = max(self.elapsed, float(getattr(recorder, "recording_elapsed_s", 0.0) or 0.0))
                    self.status = status
                self.recording.stop(status=status)

        try:
            self.thread = threading.Thread(target=_run, name="recorder", daemon=True)
            self.thread.start()
        except Exception:
            self.recording.stop(status="error", error="could not start recording thread")
            with self.lock:
                self.status = "error"
            raise

    def stop(self) -> None:
        if self.recorder:
            self.recorder.stop()

    def shutdown(self, timeout: float = 30.0) -> None:
        self.stop()
        thread = self.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self.recording.stop(status="shutdown")

    def state(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "label": self.label,
                "rows": self.row_count,
                "elapsed": self.elapsed,
                "duration": self.duration,
                "profile": self.profile,
                "running": self.thread is not None and self.thread.is_alive(),
            }
