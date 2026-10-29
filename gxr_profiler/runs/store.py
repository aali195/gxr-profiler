"""Run storage: list/load runs and their derived data.

Runs live in ``runs/<label>/`` (data.csv, events.csv, procs.csv, meta.json).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Any

from ..core.adb import RunNotFound
from ..core.fs import atomic_write_json
from ..core.naming import base_label, validate_run_name
from ..core.paths import (
    RUN_DATA_FILE,
    RUN_EVENTS_FILE,
    RUN_META_FILE,
    RUN_PROCS_FILE,
    default_runs_dir,
)

log = logging.getLogger(__name__)
RunMeta = dict[str, Any]

_FILE_NAMES = {
    "csv": RUN_DATA_FILE,
    "events.csv": RUN_EVENTS_FILE,
    "procs.csv": RUN_PROCS_FILE,
    "meta.json": RUN_META_FILE,
}


@dataclass
class RunSummary:
    label: str
    started: str = ""
    recording_started: str = ""
    ended: str = ""
    rows: int = 0
    duration_s: float | None = None
    duration_actual_s: float | None = None
    device_model: str = ""
    build: str = ""
    panel: str = ""
    power_saving: bool | None = None
    hand_tracking: bool | None = None
    controllers: bool | None = None
    passthrough: bool | None = None
    has_procs: bool = False
    profile: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class RunStore:
    def __init__(self, runs_dir: str | None = None) -> None:
        self.runs_dir = runs_dir or default_runs_dir()

    # -- paths -----------------------------------------------------------
    def _base(self, label: str) -> str:
        return base_label(label)

    def _run_dir(self, base: str) -> str:
        return os.path.join(self.runs_dir, base)

    def _new_path(self, base: str, kind: str) -> str:
        return os.path.join(self._run_dir(base), _FILE_NAMES[kind])

    def path(self, label: str, kind: str = "csv") -> str:
        return self._new_path(self._base(label), kind)

    def exists(self, label: str) -> bool:
        return os.path.exists(self.path(label, "csv"))

    # -- read ------------------------------------------------------------
    def read_meta(self, label: str) -> RunMeta:
        p = self._new_path(self._base(label), "meta.json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise TypeError(f"invalid run metadata: {p}")
        return data

    def load(self, label: str):
        import pandas as pd

        base = self._base(label)
        csv = self._new_path(base, "csv")
        if not os.path.exists(csv):
            raise RunNotFound(f"run not found: {label}")
        return self.read_meta(base), pd.read_csv(csv)

    def load_procs(self, label: str):
        import pandas as pd

        p = self._new_path(self._base(label), "procs.csv")
        if not os.path.exists(p):
            return None
        try:
            return pd.read_csv(p)
        except Exception:
            log.warning("could not read %s", p, exc_info=True)
            return None

    # -- edit ------------------------------------------------------------
    @staticmethod
    def _sanitize(name: str) -> str:
        return validate_run_name(name)

    def update(self, label: str, name: str | None = None, notes: str | None = None) -> str:
        """Rename a run and/or update its notes. Returns the (possibly new) label."""
        base = self._base(label)
        meta = self.read_meta(base)
        if not meta or not self.exists(base):
            raise RunNotFound(f"run not found: {label}")

        new_base = self._sanitize(name) if name is not None else base
        old_dir = self._run_dir(base)
        new_dir = self._run_dir(new_base)
        if name is not None and new_base != base:
            if os.path.exists(new_dir):
                raise FileExistsError(f"a run named '{new_base}' already exists")
            os.replace(old_dir, new_dir)

        meta["label"] = new_base
        if notes is not None:
            meta["notes"] = notes
        atomic_write_json(self._new_path(new_base, "meta.json"), meta)
        return new_base

    def delete(self, label: str) -> None:
        """Remove a run's directory."""
        base = self._base(label)
        if not self.exists(base):
            raise RunNotFound(f"run not found: {label}")
        shutil.rmtree(self._run_dir(base))

    # -- list ------------------------------------------------------------
    def _summary(self, label: str, meta: dict) -> RunSummary:
        di = meta.get("device_info") or {}
        if not isinstance(di, dict):
            di = {}
        start_state = meta.get("start_state") or {}
        end_state = meta.get("end_state") or {}
        features = meta.get("features") or {}
        if not isinstance(features, dict):
            features = {}
        if not isinstance(start_state, dict):
            start_state = {}
        if not isinstance(end_state, dict):
            end_state = {}
        panel = di.get("panel") or {}
        if not isinstance(panel, dict):
            panel = {}
        return RunSummary(
            label=label,
            started=meta.get("started") or "",
            recording_started=meta.get("recording_started") or "",
            ended=meta.get("ended") or "",
            rows=meta.get("rows") or 0,
            duration_s=meta.get("duration_s"),
            duration_actual_s=meta.get("duration_actual_s"),
            device_model=di.get("model") or meta.get("device_model", ""),
            build=di.get("build_display_id", ""),
            panel=panel.get("active", ""),
            power_saving=bool(start_state.get("psm", 0))
            if "psm" in start_state
            else (bool(start_state.get("low_power", 0)) if "low_power" in start_state else None),
            hand_tracking=start_state.get("hand_tracking_active"),
            controllers=start_state.get("controllers_active", end_state.get("controllers_active")),
            passthrough=start_state.get("passthrough", end_state.get("passthrough")),
            has_procs=os.path.exists(self._new_path(label, "procs.csv")),
            profile=features.get("profile") or "",
            notes=meta.get("notes") or "",
        )

    def list(self) -> list[RunSummary]:
        out: list[RunSummary] = []
        if not os.path.isdir(self.runs_dir):
            return out
        seen: set[str] = set()
        for entry in sorted(os.scandir(self.runs_dir), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            try:
                label = validate_run_name(entry.name)
            except ValueError:
                continue
            if not os.path.exists(os.path.join(entry.path, RUN_DATA_FILE)):
                continue
            if label in seen:
                continue
            seen.add(label)
            try:
                meta = self.read_meta(label)
                out.append(self._summary(label, meta))
            except (ValueError, OSError, TypeError, AttributeError):
                log.warning("skipping malformed run %s", label, exc_info=True)
        return out
