"""Typed configuration and value objects shared by CLI and server."""

from __future__ import annotations

from dataclasses import dataclass, field

from .columns import TEMP_SENSORS
from .paths import default_runs_dir


@dataclass
class RunConfig:
    """Everything needed to record one run."""

    name: str
    out_dir: str = field(default_factory=default_runs_dir)
    duration: float = 0.0
    interval: float = 1.0

    cooldown_below: float | None = None
    cooldown_sensor: str = "AP"
    cooldown_max_wait: float = 0.0

    notes: str = ""

    logcat: bool = True
    root: bool = False  # fan RPM/PWM + active panel (read-only su -c)
    sensors: bool = False
    sensors_interval: float = 10.0
    processes: bool = True
    processes_interval: float = 10.0
    processes_top: int = 0
    processes_kernel: bool = False
    process_io: bool = False

    media_interval: float = 30.0
    state_interval: float = 5.0
    radio_interval: float = 30.0
    profile: str = "standard"

    def __post_init__(self) -> None:
        if self.cooldown_sensor not in TEMP_SENSORS:
            raise ValueError(f"unknown cooldown sensor: {self.cooldown_sensor}")
        if self.cooldown_max_wait < 0:
            raise ValueError("cooldown max wait cannot be negative")
        if self.interval <= 0:
            raise ValueError("interval must be greater than zero")
        if self.duration < 0:
            raise ValueError("duration cannot be negative")
        if self.cooldown_below is not None and self.cooldown_below < 0:
            raise ValueError("cooldown target cannot be negative")
        if self.processes_top < 0:
            raise ValueError("processes_top cannot be negative")
        for name, value in (
            ("sensors_interval", self.sensors_interval),
            ("processes_interval", self.processes_interval),
            ("media_interval", self.media_interval),
            ("state_interval", self.state_interval),
            ("radio_interval", self.radio_interval),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if self.process_io and not self.root:
            raise ValueError("process I/O requires root")

    def features(self) -> dict:
        return {
            "logcat": self.logcat,
            "root_fan": self.root,
            "sensors": self.sensors,
            "sensors_interval_s": self.sensors_interval,
            "processes": self.processes,
            "processes_interval_s": self.processes_interval,
            "processes_top": self.processes_top,
            "processes_kernel": self.processes_kernel,
            "process_io": self.root and self.processes and self.process_io,
            "media_interval_s": self.media_interval,
            "state_interval_s": self.state_interval,
            "radio_interval_s": self.radio_interval,
            "profile": self.profile,
        }


@dataclass
class SampleEvent:
    """One 1 Hz snapshot emitted to listeners (TUI / SSE)."""

    elapsed_s: float
    row: dict = field(default_factory=dict)


CAPTURE_PROFILES: dict[str, dict] = {
    "standard": {
        "processes": True,
        "processes_interval": 10.0,
        "processes_kernel": False,
        "process_io": False,
        "sensors": False,
        "sensors_interval": 10.0,
        "media_interval": 30.0,
        "state_interval": 5.0,
        "radio_interval": 30.0,
        "root": False,
    },
    "detailed": {
        "processes": True,
        "processes_interval": 5.0,
        "processes_kernel": False,
        "process_io": False,
        "sensors": True,
        "sensors_interval": 10.0,
        "media_interval": 10.0,
        "state_interval": 5.0,
        "radio_interval": 30.0,
        "root": False,
    },
    "everything": {
        "processes": True,
        "processes_interval": 5.0,
        "processes_kernel": True,
        "process_io": True,
        "sensors": True,
        "sensors_interval": 5.0,
        "media_interval": 10.0,
        "state_interval": 1.0,
        "radio_interval": 5.0,
        "root": True,
    },
}


def apply_profile(config: RunConfig, name: str) -> RunConfig:
    """Apply a named capture profile to a config, leaving unknown names alone."""
    values = CAPTURE_PROFILES.get(name)
    if values:
        for key, value in values.items():
            setattr(config, key, value)
    config.profile = name
    return config
