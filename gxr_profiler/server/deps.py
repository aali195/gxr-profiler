"""FastAPI dependencies backed by application state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..runs.store import RunStore
from .debug import DebugManager
from .recording import RecordManager


def get_store(request: Request) -> RunStore:
    return request.app.state.store


def get_manager(request: Request) -> RecordManager:
    return request.app.state.manager


def get_debug_manager(request: Request) -> DebugManager:
    return request.app.state.debug


StoreDep = Annotated[RunStore, Depends(get_store)]
ManagerDep = Annotated[RecordManager, Depends(get_manager)]
DebugDep = Annotated[DebugManager, Depends(get_debug_manager)]
