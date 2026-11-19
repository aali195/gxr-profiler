"""Runtime data locations.

Frozen builds keep `runs/` and `reports/` next to the executable; source runs
keep the historical current-working-directory behaviour.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def default_runs_dir() -> str:
    return str(runtime_dir() / "runs")


def default_reports_dir() -> str:
    return str(runtime_dir() / "reports")


RUN_DATA_FILE = "data.csv"
RUN_EVENTS_FILE = "events.csv"
RUN_PROCS_FILE = "procs.csv"
RUN_META_FILE = "meta.json"


def ensure_writable_dir(path: str | os.PathLike[str]) -> str:
    """Create a directory and prove it is writable, with a clear error."""
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=p, prefix=".gxr-profiler-write-", delete=True):
            pass
    except OSError as exc:
        raise OSError(
            f"directory is not writable: {p}. Move gxr-profiler.exe to a writable folder or pass --runs-dir / --out."
        ) from exc
    return str(p)
