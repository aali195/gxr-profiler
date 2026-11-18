"""FastAPI dependencies backed by application state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..runs.store import RunStore
from .apps import AppsService
from .debug import DebugManager
from .recording import RecordManager
from .settings import SettingsService


def get_store(request: Request) -> RunStore:
    return request.app.state.store


def get_manager(request: Request) -> RecordManager:
    return request.app.state.manager


def get_debug_manager(request: Request) -> DebugManager:
    return request.app.state.debug


def get_apps_service(request: Request) -> AppsService:
    return request.app.state.apps


def get_settings_service(request: Request) -> SettingsService:
    return request.app.state.settings


StoreDep = Annotated[RunStore, Depends(get_store)]
ManagerDep = Annotated[RecordManager, Depends(get_manager)]
DebugDep = Annotated[DebugManager, Depends(get_debug_manager)]
AppsDep = Annotated[AppsService, Depends(get_apps_service)]
SettingsDep = Annotated[SettingsService, Depends(get_settings_service)]
