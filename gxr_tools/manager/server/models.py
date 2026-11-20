"""Request/response models for the manager HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.apps import APP_ACTIONS, GAME_DOWNSCALE_VALUES, GAME_FPS_VALUES


class DebugRequest(BaseModel):
    root: bool = False
    include_tombstones: bool = False
    include_dmesg: bool = False
    log_lines: int = Field(default=1500, ge=100, le=5000)


class AppActionRequest(BaseModel):
    action: str
    confirm: bool = False

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in APP_ACTIONS:
            raise ValueError(f"unknown app action: {value}")
        return value


class AppPerformanceRequest(BaseModel):
    fps: str = "disable"
    downscale: str = "disable"
    confirm: bool = False

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, value: str) -> str:
        if value not in GAME_FPS_VALUES:
            raise ValueError(f"invalid game FPS value: {value}")
        return value

    @field_validator("downscale")
    @classmethod
    def validate_downscale(cls, value: str) -> str:
        if value not in GAME_DOWNSCALE_VALUES:
            raise ValueError(f"invalid game downscale value: {value}")
        return value


class InstallOptions(BaseModel):
    replace: bool = True
    allow_downgrade: bool = False
    grant_permissions: bool = False


class InstallPreviewRequest(BaseModel):
    items: list[str] = Field(min_length=1)
    obb_packages: dict[str, str] = Field(default_factory=dict)
    options: InstallOptions = Field(default_factory=InstallOptions)


class InstallRequest(InstallPreviewRequest):
    confirm: bool = False


class SettingUpdate(BaseModel):
    enabled: bool | None = None
    value: str | None = None

    @model_validator(mode="after")
    def validate_one_value(self):
        if (self.enabled is None) == (self.value is None):
            raise ValueError("provide exactly one of enabled or value")
        return self


class FileRootRequest(BaseModel):
    enabled: bool


class FileMkdirRequest(BaseModel):
    path: str
    name: str


class FileRenameRequest(BaseModel):
    path: str
    name: str


class FileMoveRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    destination: str
    overwrite: bool = False


class FileDeleteRequest(BaseModel):
    paths: list[str] = Field(min_length=1)
    recursive: bool = False
    confirm: str = ""


class FileDownloadTicketRequest(BaseModel):
    path: str
