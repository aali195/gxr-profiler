"""Shared types and status constants for device settings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_PARTIAL = "partial"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNKNOWN = "unknown"

PERSISTENT = "persistent"
UNTIL_REBOOT = "until_reboot"
MODULE_REQUIRED = "module"

SETTING_KIND_TOGGLE = "toggle"
SETTING_KIND_CHOICE = "choice"

XR_SECTION_ID = "xr"
XR_SECTION_TITLE = "XR controls"
XR_SECTION_DESCRIPTION = (
    "XR-specific Android settings. Several are experimental or change safety behavior; each row "
    "shows its own warning and persistence."
)

ADVANCED_SECTION_ID = "advanced"
ADVANCED_SECTION_TITLE = "Advanced"
ADVANCED_SECTION_DESCRIPTION = "Less common changes with a larger side effect. Expand only when you need one of these."

TESTING_SECTION_ID = "testing"
TESTING_SECTION_TITLE = "Testing — untested"
TESTING_SECTION_DESCRIPTION = (
    "Keys reverse-engineered from the installed firmware and exposed for local testing. "
    "Their behavior or numeric value mapping is not fully verified."
)


@dataclass(frozen=True)
class SettingOption:
    value: str
    label: str
    commands: tuple[str, ...]


@dataclass(frozen=True)
class SettingDefinition:
    id: str
    section: str
    section_title: str
    section_description: str
    label: str
    description: str
    warning: str
    read_commands: tuple[tuple[str, str], ...]
    apply_commands: tuple[str, ...]
    revert_commands: tuple[str, ...]
    reader: Callable[[dict[str, str]], dict]
    persistence: str = PERSISTENT
    persistence_note: str = ""
    root_required: bool = False
    default_enabled: bool = False
    default_label: str | None = None
    kind: str = SETTING_KIND_TOGGLE
    options: tuple[SettingOption, ...] = ()
    confirm_on_disable: bool = False
    recommended: bool = False
