"""Run listing, detail, edit and delete endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...core.adb import RunNotFound
from ...core.naming import base_label
from ...report.data import downsample, process_series_for, procs_for
from ...report.data import series as build_series
from ..deps import ManagerDep, StoreDep
from ..models import RunEdit

router = APIRouter()


@router.get("/api/runs")
def list_runs(store: StoreDep):
    return [r.to_dict() for r in store.list()]


@router.get("/api/runs/{label}")
def run_detail(label: str, store: StoreDep):
    try:
        meta, df = store.load(label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=404, detail=f"run not found: {label}")
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid run data: {exc}")
    import pandas as pd

    if "elapsed_s" in df.columns:
        elapsed_values = pd.to_numeric(df["elapsed_s"], errors="coerce").ffill().fillna(0.0)
        elapsed = [float(x) for x in elapsed_values.tolist()]
    else:
        elapsed = []
    elapsed, series = downsample(elapsed, build_series(df))
    return {"label": label, "meta": meta, "elapsed": elapsed, "series": series}


@router.get("/api/runs/{label}/procs/series")
def run_proc_series(label: str, store: StoreDep):
    try:
        if not store.exists(label):
            raise HTTPException(status_code=404, detail=f"run not found: {label}")
        return process_series_for(store, label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (KeyError, TypeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid process data: {exc}")


@router.get("/api/runs/{label}/procs")
def run_procs(label: str, store: StoreDep):
    try:
        if not store.exists(label):
            raise HTTPException(status_code=404, detail=f"run not found: {label}")
        return procs_for(store, label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (KeyError, TypeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid process data: {exc}")


def _same_run(a: str, b: str) -> bool:
    try:
        return base_label(a).casefold() == base_label(b).casefold()
    except ValueError:
        return False


@router.patch("/api/runs/{label}")
def edit_run(label: str, body: RunEdit, store: StoreDep, manager: ManagerDep):
    if manager.status == "recording" and _same_run(manager.label, label):
        raise HTTPException(status_code=409, detail="cannot edit a run while it is recording")
    try:
        new_label = store.update(label, name=body.name, notes=body.notes)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"run not found: {label}")
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, TypeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"label": new_label, "notes": store.read_meta(new_label).get("notes", "")}


@router.delete("/api/runs/{label}")
def delete_run(label: str, store: StoreDep, manager: ManagerDep):
    if manager.status == "recording" and _same_run(manager.label, label):
        raise HTTPException(status_code=409, detail="cannot delete a run while it is recording")
    try:
        store.delete(label)
    except RunNotFound:
        raise HTTPException(status_code=404, detail=f"run not found: {label}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"could not delete run: {exc}")
    return {"ok": True}
