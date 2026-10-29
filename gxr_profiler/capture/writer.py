"""Run file writer: wide CSV + events + procs + meta.json."""

from __future__ import annotations

import csv
import logging
import os
import shutil
import threading

from ..core.fs import atomic_write_json
from ..core.naming import validate_run_name
from ..core.paths import (
    RUN_DATA_FILE,
    RUN_EVENTS_FILE,
    RUN_META_FILE,
    RUN_PROCS_FILE,
    ensure_writable_dir,
)
from .columns import EVENT_COLUMNS, PROC_COLUMNS, REPORT_COLUMNS

log = logging.getLogger(__name__)


class RunWriter:
    def __init__(self, out_dir: str, name: str) -> None:
        name = validate_run_name(name)
        out_dir = ensure_writable_dir(out_dir)
        self.root = out_dir
        self.dir = os.path.join(out_dir, name)
        self.name = name
        self.csv_path = os.path.join(self.dir, RUN_DATA_FILE)
        self.events_path = os.path.join(self.dir, RUN_EVENTS_FILE)
        self.procs_path = os.path.join(self.dir, RUN_PROCS_FILE)
        self.meta_path = os.path.join(self.dir, RUN_META_FILE)
        if os.path.exists(self.dir):
            raise FileExistsError(f"run already exists: {name} in {out_dir}")
        self._csv = None
        self._csv_w = None
        self._events = None
        self._events_w = None
        self._procs = None
        self._procs_w = None
        self.opened = False
        self._keys_checked = False
        self._closed = False
        self._lock = threading.Lock()

    def open(self, with_procs: bool = False) -> None:
        self._closed = False
        created_dir = False
        try:
            os.makedirs(self.dir, exist_ok=False)
            created_dir = True
            self._csv = open(self.csv_path, "w", newline="", encoding="utf-8")
            self._csv_w = csv.DictWriter(self._csv, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
            self._csv_w.writeheader()
            self._events = open(self.events_path, "w", newline="", encoding="utf-8")
            self._events_w = csv.DictWriter(self._events, fieldnames=EVENT_COLUMNS)
            self._events_w.writeheader()
            if with_procs:
                self._procs = open(self.procs_path, "w", newline="", encoding="utf-8")
                self._procs_w = csv.DictWriter(self._procs, fieldnames=PROC_COLUMNS)
                self._procs_w.writeheader()
        except Exception:
            self._closed = True
            for f in (self._csv, self._events, self._procs):
                try:
                    if f:
                        f.close()
                except Exception:
                    pass
            if created_dir:
                shutil.rmtree(self.dir, ignore_errors=True)
            raise
        self.opened = True

    def write_row(self, row: dict) -> None:
        with self._lock:
            if self._closed:
                return
            if self._csv_w:
                if not self._keys_checked:
                    unknown = set(row) - set(self._csv_w.fieldnames or [])
                    if unknown:
                        log.warning("ignoring unknown columns: %s", ", ".join(sorted(unknown)))
                    self._keys_checked = True
                self._csv_w.writerow(row)
                self._csv.flush()

    def write_event(self, ts_host: float, ts_dev: str, tag: str, name: str, key: str, value) -> None:
        with self._lock:
            if self._closed:
                return
            if self._events_w:
                self._events_w.writerow(
                    {
                        "ts_host": f"{ts_host:.3f}",
                        "ts_dev": ts_dev,
                        "tag": tag,
                        "name": name,
                        "key": key,
                        "value": value,
                    }
                )
                self._events.flush()

    def write_proc(self, row: dict) -> None:
        with self._lock:
            if self._closed:
                return
            if self._procs_w:
                self._procs_w.writerow(row)

    @property
    def procs_writer(self) -> csv.DictWriter | None:
        return self._procs_w

    def flush_procs(self) -> None:
        with self._lock:
            if not self._closed and self._procs:
                self._procs.flush()

    def write_meta(self, meta: dict) -> None:
        atomic_write_json(self.meta_path, meta)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for f in (self._csv, self._events, self._procs):
                try:
                    if f:
                        f.close()
                except Exception:
                    pass
