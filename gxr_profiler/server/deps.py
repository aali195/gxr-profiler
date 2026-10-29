"""FastAPI dependencies backed by application state."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..runs.store import RunStore
from .recording import RecordManager


def get_store(request: Request) -> RunStore:
    return request.app.state.store


def get_manager(request: Request) -> RecordManager:
    return request.app.state.manager


StoreDep = Annotated[RunStore, Depends(get_store)]
ManagerDep = Annotated[RecordManager, Depends(get_manager)]
