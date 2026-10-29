"""Thread-safe metric state (last-known value per event-derived metric)."""

from __future__ import annotations

import threading


class MetricState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {}

    def update(self, items: dict) -> None:
        if items:
            with self._lock:
                self._data.update(items)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
