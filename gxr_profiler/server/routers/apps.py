"""Installed package listing, details and confirmed package actions."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from ...core.adb import AdbError
from ..deps import AppsDep, ManagerDep
from ..models import AppActionRequest, AppPerformanceRequest, InstallPreviewRequest, InstallRequest

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/apps")
def list_apps(apps: AppsDep):
    try:
        return apps.list_packages()
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not list packages")
        raise HTTPException(status_code=500, detail="could not list packages") from exc


@router.get("/api/apps/{package}")
def app_detail(package: str, apps: AppsDep, root: bool = False):
    try:
        return apps.detail(package, root=root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not read package details for %s", package)
        raise HTTPException(status_code=500, detail="could not read package details") from exc


@router.post("/api/apps/{package}/action")
def app_action(package: str, body: AppActionRequest, apps: AppsDep, manager: ManagerDep):
    if manager.state().get("status") == "recording":
        raise HTTPException(status_code=409, detail="cannot change packages while a recording is in progress")
    try:
        return apps.run_action(package, body.action, confirm=body.confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("package action failed for %s", package)
        raise HTTPException(status_code=500, detail="package action failed") from exc


@router.post("/api/apps/{package}/performance")
def app_performance(
    package: str,
    body: AppPerformanceRequest,
    apps: AppsDep,
    manager: ManagerDep,
):
    if manager.state().get("status") == "recording":
        raise HTTPException(
            status_code=409,
            detail="cannot change packages while a recording is in progress",
        )
    try:
        return apps.set_game_override(package, body.fps, body.downscale, confirm=body.confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("package performance override failed for %s", package)
        raise HTTPException(status_code=500, detail="package performance override failed") from exc


@router.post("/api/apps/install/stage")
async def stage_install_file(
    request: Request,
    apps: AppsDep,
    name: str = Query(..., min_length=1, max_length=255),
    path: str = Query("", max_length=1024),
):
    manager = apps.install
    try:
        size_hint = int(request.headers.get("content-length") or 0)
    except ValueError:
        size_hint = 0
    try:
        manager.validate_upload(name, size_hint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    temp_path: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(
            dir=str(manager.upload_dir),
            prefix="upload-",
            suffix=".part",
        )
        temp_path = Path(raw_path)
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "wb") as handle:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > manager.max_upload_bytes:
                    raise ValueError("file is larger than the 32 GB upload limit")
                digest.update(chunk)
                handle.write(chunk)
        return await run_in_threadpool(
            manager.accept_upload,
            temp_path,
            name,
            path,
            digest.hexdigest(),
            size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="the archive is not a valid XAPK") from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not stage install file %s", name)
        raise HTTPException(status_code=500, detail="could not stage the install file") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                log.debug("could not remove temporary upload", exc_info=True)


@router.delete("/api/apps/install/stage")
def clear_staged_install_files(apps: AppsDep):
    try:
        return apps.install.clear()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not clear staged install files")
        raise HTTPException(status_code=500, detail="could not clear the staged files") from exc


@router.delete("/api/apps/install/stage/{stage_id}")
def discard_install_file(stage_id: str, apps: AppsDep):
    try:
        return apps.install.discard(stage_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not discard staged install file")
        raise HTTPException(status_code=500, detail="could not discard the staged file") from exc


@router.post("/api/apps/install/preview")
def preview_install(body: InstallPreviewRequest, apps: AppsDep):
    try:
        return apps.install.preview(
            body.items,
            body.obb_packages,
            body.options.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not preview install")
        raise HTTPException(status_code=500, detail="could not preview the install") from exc


@router.post("/api/apps/install")
def start_install(body: InstallRequest, apps: AppsDep, manager: ManagerDep):
    if manager.state().get("status") == "recording":
        raise HTTPException(
            status_code=409,
            detail="cannot install packages while a recording is in progress",
        )
    try:
        return apps.install.start(
            body.items,
            body.obb_packages,
            body.options.model_dump(),
            confirm=body.confirm,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("could not start install")
        raise HTTPException(status_code=500, detail="could not start the install") from exc


@router.get("/api/apps/install/state")
def install_state(apps: AppsDep):
    return apps.install.state()


@router.get("/api/apps/install/{job_id}")
def install_status(job_id: str, apps: AppsDep):
    try:
        return apps.install.status(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
