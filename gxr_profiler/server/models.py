"""Request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from ..core.apps import APP_ACTIONS, GAME_DOWNSCALE_VALUES, GAME_FPS_VALUES
from ..core.models import CAPTURE_PROFILES, RunConfig, apply_profile


class RunEdit(BaseModel):
    name: str | None = None
    notes: str | None = None


class RecordRequest(BaseModel):
    name: str = "run"
    duration: float = Field(default=0.0, ge=0)
    interval: float = Field(default=1.0, gt=0)
    cooldown: float | None = Field(default=None, ge=0)
    sensor: str = "AP"
    cooldown_max_wait: float | None = Field(default=None, ge=0)
    notes: str = ""
    root: bool | None = None
    sensors: bool | None = None
    sensors_interval: float | None = Field(default=None, gt=0)
    processes: bool | None = None
    processes_interval: float | None = Field(default=None, gt=0)
    processes_top: int | None = Field(default=None, ge=0)
    processes_kernel: bool | None = None
    process_io: bool | None = None
    media_interval: float | None = Field(default=None, gt=0)
    state_interval: float | None = Field(default=None, gt=0)
    radio_interval: float | None = Field(default=None, gt=0)
    profile: str = "standard"

    def to_config(self, runs_dir: str) -> RunConfig:
        if self.profile not in {*CAPTURE_PROFILES, "custom"}:
            raise ValueError(f"unknown capture profile: {self.profile}")
        cfg = RunConfig(
            name=self.name,
            out_dir=runs_dir,
            duration=self.duration,
            interval=self.interval,
            cooldown_below=(self.cooldown if self.cooldown is not None else None),
            cooldown_sensor=self.sensor or "AP",
            cooldown_max_wait=self.cooldown_max_wait or 0.0,
            notes=self.notes,
        )
        apply_profile(cfg, self.profile)
        overrides = {
            "root": self.root,
            "sensors": self.sensors,
            "sensors_interval": self.sensors_interval,
            "processes": self.processes,
            "processes_interval": self.processes_interval,
            "processes_top": self.processes_top,
            "processes_kernel": self.processes_kernel,
            "process_io": self.process_io,
            "media_interval": self.media_interval,
            "state_interval": self.state_interval,
            "radio_interval": self.radio_interval,
        }
        for key, value in overrides.items():
            if value is not None:
                setattr(cfg, key, value)
        if cfg.process_io and not cfg.root:
            raise ValueError("--process-io requires root extras")
        if cfg.process_io and not cfg.processes:
            raise ValueError("--process-io requires process sampling")
        return cfg


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


class RecordStatus(BaseModel):
    status: str
    label: str
    rows: int
    running: bool
