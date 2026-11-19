"""Cross-process recording state shared by the profiler and manager.

The profiler owns the marker; the manager only reads it.  The marker is a
heartbeat file so a crashed profiler cannot block device management forever.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from .fs import atomic_write_json
from .paths import runtime_dir

log = logging.getLogger(__name__)

STATE_FILENAME = "recording.json"
HEARTBEAT_S = 3.0
STALE_AFTER_S = 12.0


class RecordingState(TypedDict):
    active: bool
    stale: bool
    label: str
    status: str
    error: str
    pid: int | None
    token: str
    started_at: str
    updated_at: str


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def state_dir(path: str | os.PathLike[str] | None = None) -> Path:
    root = Path(path) if path is not None else Path(os.environ.get("GXR_STATE_DIR") or runtime_dir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def state_path(path: str | os.PathLike[str] | None = None) -> Path:
    return state_dir(path) / STATE_FILENAME


def write_state(
    active: bool,
    *,
    label: str = "",
    status: str = "",
    error: str = "",
    pid: int | None = None,
    started_at: str | None = None,
    updated_at: str | None = None,
    token: str = "",
    path: str | os.PathLike[str] | None = None,
) -> None:
    payload = {
        "active": bool(active),
        "label": label,
        "status": status,
        "error": error,
        "pid": os.getpid() if pid is None else pid,
        "token": token,
        "started_at": started_at or _iso_now(),
        "updated_at": updated_at or _iso_now(),
    }
    try:
        atomic_write_json(state_path(path), payload)
    except OSError:
        log.warning("could not write recording state", exc_info=True)


def read_state(path: str | os.PathLike[str] | None = None, *, now: datetime | None = None) -> RecordingState:
    try:
        data = json.loads(state_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {
            "active": False,
            "stale": False,
            "label": "",
            "status": "",
            "error": "",
            "pid": None,
            "token": "",
            "started_at": "",
            "updated_at": "",
        }
    if not isinstance(data, dict):
        data = {}
    active = bool(data.get("active"))
    stale = False
    if active:
        try:
            updated = datetime.fromisoformat(str(data.get("updated_at") or ""))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            current = now or datetime.now(UTC)
            stale = current - updated > timedelta(seconds=STALE_AFTER_S)
        except (ValueError, TypeError):
            stale = True
    return {
        "active": active and not stale,
        "stale": stale,
        "label": str(data.get("label") or ""),
        "status": str(data.get("status") or ""),
        "error": str(data.get("error") or ""),
        "pid": data.get("pid"),
        "token": str(data.get("token") or ""),
        "started_at": str(data.get("started_at") or ""),
        "updated_at": str(data.get("updated_at") or ""),
    }


def is_recording(path: str | os.PathLike[str] | None = None) -> bool:
    return bool(read_state(path).get("active"))


class RecordingMarker:
    """Heartbeat marker written by the profiler while a recording is active."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = path
        self.label = ""
        self.started_at = ""
        self._token = ""
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self, label: str) -> None:
        with self._lock:
            if self._stop is not None:
                self._stop.set()
            self.label = label
            self.started_at = _iso_now()
            self._token = uuid.uuid4().hex
            self._stop = threading.Event()
            self._write(True, status="recording")
            self._thread = threading.Thread(target=self._heartbeat, name="gxr-recording-state", daemon=True)
            self._thread.start()

    def _heartbeat(self) -> None:
        stop = self._stop
        if stop is None:
            return
        while not stop.wait(HEARTBEAT_S):
            with self._lock:
                if stop.is_set():
                    return
                self._write(True, status="recording")

    def _write(self, active: bool, *, status: str, error: str = "") -> None:
        write_state(
            active,
            label=self.label,
            status=status,
            error=error,
            started_at=self.started_at,
            token=self._token,
            path=self.path,
        )

    def stop(self, status: str = "idle", error: str = "") -> None:
        with self._lock:
            stop = self._stop
            thread = self._thread
            token = self._token
            self._stop = None
            self._thread = None
            self._token = ""
            if stop is not None:
                stop.set()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        # Do not clear another profiler instance's active recording.
        current = read_state(self.path)
        current_token = current.get("token") or ""
        if current.get("active") and current_token and current_token != token:
            return
        with self._lock:
            self._write(False, status=status, error=error)


def clear_state(path: str | os.PathLike[str] | None = None) -> None:
    try:
        state_path(path).unlink(missing_ok=True)
    except OSError:
        log.debug("could not remove recording state", exc_info=True)
