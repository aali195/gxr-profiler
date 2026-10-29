"""Background recorder manager and SSE fan-out state."""

from __future__ import annotations

import logging
import threading
from collections import deque

from ..capture.recorder import Recorder
from ..core.adb import AdbError, RealAdb, resolve_serial
from ..core.models import RunConfig
from ..core.naming import validate_run_name

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
        self.status = "idle"
        self.label = ""
        self.duration = 0.0
        self.profile = ""
        self.recorder: Recorder | None = None
        self.thread: threading.Thread | None = None

    def _on_sample(self, event) -> None:
        with self.lock:
            self.next_seq += 1
            self.row_count += 1
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
            serial = resolve_serial(self.serial)
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
            self.status = "recording"
            self.label = cfg.name
            self.duration = cfg.duration
            self.profile = cfg.profile
            self.recorder = recorder

        def _run() -> None:
            try:
                recorder.run()
                with self.lock:
                    self.status = "done"
            except Exception:
                log.exception("recording failed")
                with self.lock:
                    self.status = "error"

        self.thread = threading.Thread(target=_run, name="recorder", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.recorder:
            self.recorder.stop()

    def shutdown(self, timeout: float = 30.0) -> None:
        self.stop()
        thread = self.thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def state(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "label": self.label,
                "rows": self.row_count,
                "duration": self.duration,
                "profile": self.profile,
                "running": self.thread is not None and self.thread.is_alive(),
            }
