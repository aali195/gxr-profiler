"""FastAPI dependencies backed by manager application state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from gxr_tools.core.recording_state import read_state

from .apps import AppsService
from .debug import DebugManager
from .files import FilesService
from .settings import SettingsService


def get_apps_service(request: Request) -> AppsService:
    return request.app.state.apps


def get_settings_service(request: Request) -> SettingsService:
    return request.app.state.settings


def get_debug_manager(request: Request) -> DebugManager:
    return request.app.state.debug


def get_files_service(request: Request) -> FilesService:
    return request.app.state.files


def require_token(request: Request) -> None:
    if request.headers.get("x-gxr-profiler-token") != request.app.state.token:
        raise HTTPException(status_code=403, detail="missing local API token")


def require_idle() -> None:
    state = read_state()
    if state.get("active"):
        label = state.get("label") or "a run"
        raise HTTPException(
            status_code=409,
            detail=f"the profiler is recording {label}; device changes are blocked",
        )


AppsDep = Annotated[AppsService, Depends(get_apps_service)]
SettingsDep = Annotated[SettingsService, Depends(get_settings_service)]
DebugDep = Annotated[DebugManager, Depends(get_debug_manager)]
FilesDep = Annotated[FilesService, Depends(get_files_service)]
TokenDep = Annotated[None, Depends(require_token)]
IdleDep = Annotated[None, Depends(require_idle)]
