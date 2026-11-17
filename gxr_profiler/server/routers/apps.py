"""Installed package listing, details and confirmed package actions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...core.adb import AdbError
from ..deps import AppsDep, ManagerDep
from ..models import AppActionRequest

router = APIRouter()


@router.get("/api/apps")
def list_apps(apps: AppsDep):
    try:
        return apps.list_packages()
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"could not list packages: {exc}") from exc


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
        raise HTTPException(status_code=503, detail=f"could not read package details: {exc}") from exc


@router.post("/api/apps/{package}/action")
def app_action(package: str, body: AppActionRequest, apps: AppsDep, manager: ManagerDep):
    if manager.state().get("status") == "recording":
        raise HTTPException(status_code=409, detail="cannot change packages while a recording is in progress")
    try:
        return apps.run_action(package, body.action, confirm=body.confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AdbError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"package action failed: {exc}") from exc
