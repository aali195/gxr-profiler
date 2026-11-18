"""User-facing device settings and their read/apply/revert commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

PRIVACY_ICONS_COMMAND = "cmd device_config get privacy camera_mic_icons_enabled"
CONFIG_SYNC_COMMAND = "cmd device_config get_sync_disabled_for_tests"

HIDE_ICONS_COMMANDS = (
    "cmd device_config put privacy camera_mic_icons_enabled false default",
    "cmd device_config set_sync_disabled_for_tests persistent",
)
SHOW_ICONS_COMMANDS = (
    "cmd device_config put privacy camera_mic_icons_enabled true default",
    "cmd device_config set_sync_disabled_for_tests none",
)

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


def _value(raw: str) -> str:
    lines = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _status(
    *,
    enabled: bool,
    state: str,
    icons: str,
    sync: str,
    warning: str = "",
    error: str = "",
) -> dict:
    return {
        "enabled": enabled,
        "state": state,
        "icons": icons,
        "sync": sync,
        "details": [
            {"label": "Privacy icons", "value": icons or "unknown"},
            {"label": "DeviceConfig sync", "value": sync or "unknown"},
        ],
        "warning": warning,
        "error": error,
    }


def _multi_status(
    *,
    enabled: bool,
    state: str,
    details: list[dict],
    warning: str = "",
    error: str = "",
    value: str | None = None,
) -> dict:
    result = {
        "enabled": enabled,
        "state": state,
        "details": details,
        "warning": warning,
        "error": error,
    }
    if value is not None:
        result["value"] = value
    return result


def parse_privacy_indicator_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    icons = _value(values.get("icons", "")).lower()
    sync = _value(values.get("sync", "")).lower()
    if error:
        return _status(enabled=False, state=STATUS_UNKNOWN, icons=icons, sync=sync, error=error)

    icons_known = icons in {"true", "false", "0", "1", "null", ""}
    sync_known = sync in {"none", "persistent", "until_reboot", "", "null"}
    if not icons_known or not sync_known:
        return _status(
            enabled=False,
            state=STATUS_UNKNOWN,
            icons=icons or "unknown",
            sync=sync or "unknown",
            warning="The headset returned an unexpected DeviceConfig response.",
        )

    hidden = icons in {"false", "0"}
    persistent = sync == "persistent"
    enabled = hidden
    if hidden and persistent:
        return _status(enabled=enabled, state=STATUS_ACTIVE, icons="hidden", sync="persistent")
    if not hidden and not persistent and sync in {"none", "", "null"}:
        return _status(enabled=enabled, state=STATUS_INACTIVE, icons="shown", sync="normal")
    if hidden:
        return _status(
            enabled=enabled,
            state=STATUS_PARTIAL,
            icons="hidden",
            sync=sync or "normal",
            warning="The indicator is hidden, but the setting may return after a reboot. Use Reapply to make it persistent.",
        )
    return _status(
        enabled=enabled,
        state=STATUS_PARTIAL,
        icons="shown",
        sync=sync or "normal",
        warning="DeviceConfig sync is disabled, but the indicator is still shown. Toggle the setting on to apply it fully, or off to restore defaults.",
    )


def _toggle_status(
    *,
    enabled: bool,
    state: str,
    label: str,
    value: str,
    warning: str = "",
    error: str = "",
) -> dict:
    return {
        "enabled": enabled,
        "state": state,
        "details": [{"label": label, "value": value}],
        "warning": warning,
        "error": error,
    }


def parse_toggle_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return _toggle_status(enabled=False, state=STATUS_UNKNOWN, label="Value", value="unknown", error=error)
    if raw in {"1", "true"}:
        return _toggle_status(enabled=True, state=STATUS_ACTIVE, label="Value", value="enabled")
    if raw in {"0", "false", "null", ""}:
        return _toggle_status(enabled=False, state=STATUS_INACTIVE, label="Value", value="disabled")
    return _toggle_status(
        enabled=False,
        state=STATUS_UNKNOWN,
        label="Value",
        value=raw or "unknown",
        warning="The headset returned an unexpected setting value.",
    )


def parse_disabled_property_status(
    values: dict[str, str],
    *,
    label: str = "Dynamic policy",
    unknown_warning: str = "The headset returned an unexpected dynamic-policy value.",
) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return _toggle_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            label=label,
            value="unknown",
            error=error,
        )
    if raw in {"false", "0"}:
        return _toggle_status(
            enabled=True,
            state=STATUS_ACTIVE,
            label=label,
            value="disabled",
        )
    if raw in {"true", "1"}:
        return _toggle_status(
            enabled=False,
            state=STATUS_INACTIVE,
            label=label,
            value="enabled",
        )
    return _toggle_status(
        enabled=False,
        state=STATUS_UNKNOWN,
        label=label,
        value=raw or "unknown",
        warning=unknown_warning,
    )


def parse_fixed_hsm_status(values: dict[str, str]) -> dict:
    return parse_disabled_property_status(
        values,
        label="Home Space rate",
        unknown_warning="The headset returned an unexpected fixed-HSM value.",
    )


def parse_heads_up_status(values: dict[str, str]) -> dict:
    return parse_disabled_property_status(
        values,
        label="Heads-up",
        unknown_warning="The headset returned an unexpected heads-up value.",
    )


def parse_stay_awake_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return _toggle_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            label="Stay awake",
            value="unknown",
            error=error,
        )
    if raw in {"", "null"}:
        raw = "0"
    try:
        enabled = int(raw) != 0
    except ValueError:
        return _toggle_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            label="Stay awake",
            value=raw or "unknown",
            warning="The headset returned an unexpected stay-awake value.",
        )
    return _toggle_status(
        enabled=enabled,
        state=STATUS_ACTIVE if enabled else STATUS_INACTIVE,
        label="Stay awake",
        value="charging" if enabled else "off",
    )


def parse_child_process_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return _toggle_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            label="Child-process limits",
            value="unknown",
            error=error,
        )
    if raw in {"", "null", "true", "1"}:
        return _toggle_status(
            enabled=False,
            state=STATUS_INACTIVE,
            label="Child-process limits",
            value="enabled",
        )
    if raw in {"false", "0"}:
        return _toggle_status(
            enabled=True,
            state=STATUS_ACTIVE,
            label="Child-process limits",
            value="disabled",
        )
    return _toggle_status(
        enabled=False,
        state=STATUS_UNKNOWN,
        label="Child-process limits",
        value=raw or "unknown",
        warning="The headset returned an unexpected child-process value.",
    )


def parse_choice_status(
    values: dict[str, str],
    options: tuple[SettingOption, ...],
    *,
    label: str = "Current",
    unknown_warning: str = "",
) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return {
            "enabled": False,
            "state": STATUS_UNKNOWN,
            "value": raw,
            "details": [{"label": label, "value": "unknown"}],
            "warning": "",
            "error": error,
        }
    labels = {option.value: option.label for option in options}
    if raw in labels:
        return {
            "enabled": False,
            "state": STATUS_ACTIVE,
            "value": raw,
            "details": [{"label": label, "value": labels[raw]}],
            "warning": "",
            "error": "",
        }
    return {
        "enabled": False,
        "state": STATUS_UNKNOWN,
        "value": raw,
        "details": [{"label": label, "value": raw or "not set"}],
        "warning": unknown_warning or "The headset returned an unexpected setting value.",
        "error": "",
    }


def parse_natural_input_status(
    values: dict[str, str],
    options: tuple[SettingOption, ...],
) -> dict:
    error = values.get("_error", "")
    mode = _value(values.get("value", "")).lower()
    pointer = _value(values.get("pointer", "")).lower()
    labels = {option.value: option.label for option in options}
    details = [
        {"label": "Aiming method", "value": labels.get(mode, mode or "unknown")},
        {"label": "Input pointer", "value": labels.get(pointer, pointer or "unknown")},
    ]
    if error:
        return _multi_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            details=details,
            error=error,
        )
    if mode not in labels or pointer not in labels:
        return _multi_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            value=mode,
            details=details,
            warning="The headset returned an unrecognized aiming or pointer value.",
        )
    if mode != pointer:
        return _multi_status(
            enabled=False,
            state=STATUS_PARTIAL,
            value=mode,
            details=details,
            warning="Aiming and input pointer values differ. Use Reapply or select a mode again.",
        )
    return _multi_status(
        enabled=False,
        state=STATUS_ACTIVE,
        value=mode,
        details=details,
    )


def _package_present(raw: str, package: str) -> bool:
    expected = f"package:{package}"
    return any(line.strip() == expected for line in (raw or "").splitlines())


def _package_reader(package: str) -> Callable[[dict[str, str]], dict]:
    def reader(values: dict[str, str]) -> dict:
        error = values.get("_error", "")
        if error:
            return _toggle_status(enabled=False, state=STATUS_UNKNOWN, label="Package", value="unknown", error=error)
        if not _package_present(values.get("installed", ""), package):
            return _toggle_status(
                enabled=False,
                state=STATUS_UNAVAILABLE,
                label="Package",
                value="not installed",
                warning="This package is not installed on this build.",
            )
        if _package_present(values.get("disabled", ""), package):
            return _toggle_status(enabled=True, state=STATUS_ACTIVE, label="Package", value="disabled")
        return _toggle_status(enabled=False, state=STATUS_INACTIVE, label="Package", value="enabled")

    return reader


def parse_ota_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return _toggle_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            label="Global setting",
            value="unknown",
            error=error,
        )
    if raw in {"1", "true"}:
        return _toggle_status(
            enabled=True,
            state=STATUS_ACTIVE,
            label="Global setting",
            value="automatic updates disabled",
        )
    if raw in {"0", "false", "null", ""}:
        return _toggle_status(
            enabled=False,
            state=STATUS_INACTIVE,
            label="Global setting",
            value="automatic updates enabled",
        )
    return _toggle_status(
        enabled=False,
        state=STATUS_UNKNOWN,
        label="Global setting",
        value=raw or "unknown",
        warning="The headset returned an unexpected OTA setting value.",
    )


def _animation_off(raw: str) -> tuple[bool | None, str]:
    text = _value(raw).lower()
    if text in {"", "null"}:
        return False, "default"
    try:
        return float(text) == 0.0, text
    except ValueError:
        return None, text


def parse_animation_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    keys = (
        ("window", "Window"),
        ("transition", "Transition"),
        ("animator", "Animator"),
    )
    details = []
    off_count = 0
    invalid = False
    for key, label in keys:
        off, shown = _animation_off(values.get(key, ""))
        if off is None:
            invalid = True
        elif off:
            off_count += 1
        details.append({"label": f"{label} scale", "value": shown})
    if error or invalid:
        return _multi_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            details=details,
            error=error,
            warning="" if error else "One or more animation scales returned an unexpected value.",
        )
    if off_count == len(keys):
        return _multi_status(enabled=True, state=STATUS_ACTIVE, details=details)
    if off_count == 0:
        return _multi_status(enabled=False, state=STATUS_INACTIVE, details=details)
    return _multi_status(
        enabled=False,
        state=STATUS_PARTIAL,
        details=details,
        warning="Only some animation scales are disabled. Use Reapply to set all three.",
    )


def _boolean_on(raw: str) -> bool | None:
    text = _value(raw).lower()
    if text in {"1", "true"}:
        return True
    if text in {"0", "false", "null", ""}:
        return False
    return None


def parse_transparency_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    keys = (
        ("transparency", "Reduce transparency"),
        ("blur", "Window blur"),
    )
    details = []
    on_count = 0
    invalid = False
    for key, label in keys:
        on = _boolean_on(values.get(key, ""))
        if on is None:
            invalid = True
        elif on:
            on_count += 1
        details.append({"label": label, "value": "enabled" if on else "disabled" if on is False else "unknown"})
    if error or invalid:
        return _multi_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            details=details,
            error=error,
            warning="" if error else "One or more transparency keys returned an unexpected value.",
        )
    if on_count == len(keys):
        return _multi_status(enabled=True, state=STATUS_ACTIVE, details=details)
    if on_count == 0:
        return _multi_status(enabled=False, state=STATUS_INACTIVE, details=details)
    return _multi_status(
        enabled=True,
        state=STATUS_PARTIAL,
        details=details,
        warning="Only part of the transparency/blur change is applied. Use Reapply.",
    )


def parse_scan_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    keys = (
        ("wifi", "Wi-Fi always scanning"),
        ("ble", "BLE always scanning"),
    )
    details = []
    disabled_count = 0
    invalid = False
    for key, label in keys:
        raw = _value(values.get(key, "")).lower()
        if raw in {"0", "false"}:
            disabled = True
        elif raw in {"1", "true", "null", ""}:
            disabled = False
        else:
            disabled = None
        if disabled is None:
            invalid = True
        elif disabled:
            disabled_count += 1
        details.append(
            {
                "label": label,
                "value": "disabled" if disabled else "enabled" if disabled is False else "unknown",
            }
        )
    if error or invalid:
        return _multi_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            details=details,
            error=error,
            warning="" if error else "One or more scan keys returned an unexpected value.",
        )
    if disabled_count == len(keys):
        return _multi_status(enabled=True, state=STATUS_ACTIVE, details=details)
    if disabled_count == 0:
        return _multi_status(enabled=False, state=STATUS_INACTIVE, details=details)
    return _multi_status(
        enabled=True,
        state=STATUS_PARTIAL,
        details=details,
        warning="Only one scan type is disabled. Use Reapply to disable both.",
    )


UPDATE_SECTION_ID = "updates"
UPDATE_SECTION_TITLE = "Software updates"
UPDATE_SECTION_DESCRIPTION = (
    "Samsung updates may replace the current build or patch the root exploit. These controls reduce "
    "automatic update paths, but they also stop security updates and do not remove an update that is "
    "already downloaded or prepared."
)
UPDATE_WARNING = (
    "Disabling this can remove Software Update functionality and stop firmware/security updates. "
    "It may not cancel an update that is already downloaded or prepared."
)


def _package_setting(
    *,
    setting_id: str,
    package: str,
    label: str,
    description: str,
    warning: str,
    section: str = UPDATE_SECTION_ID,
    section_title: str = UPDATE_SECTION_TITLE,
    section_description: str = UPDATE_SECTION_DESCRIPTION,
    persistence_note: str = "Survives reboots; package state may be restored by an update.",
) -> SettingDefinition:
    return SettingDefinition(
        id=setting_id,
        section=section,
        section_title=section_title,
        section_description=section_description,
        label=label,
        description=description,
        warning=warning,
        read_commands=(
            ("installed", f"pm list packages {package}"),
            ("disabled", f"pm list packages -d {package}"),
        ),
        apply_commands=(f"pm disable-user --user 0 {package}",),
        revert_commands=(f"pm enable --user 0 {package}",),
        reader=_package_reader(package),
        persistence_note=persistence_note,
        default_label="Off",
    )


UPDATE_CLIENT = _package_setting(
    setting_id="disable_update_client",
    package="com.wssyncmldm",
    label="Disable Samsung update client (com.wssyncmldm)",
    description=(
        "Samsung's firmware-over-the-air update client. It checks for and downloads update packages. "
        "Samsung does not document the exact split from the update agent."
    ),
    warning=UPDATE_WARNING,
)

UPDATE_AGENT = _package_setting(
    setting_id="disable_update_agent",
    package="com.sec.android.soagent",
    label="Disable Samsung update agent (com.sec.android.soagent)",
    description=(
        "Samsung's Software update agent behind Settings > Software update. It coordinates update "
        "checks, downloads and scheduling."
    ),
    warning=UPDATE_WARNING,
)

OTA_AUTOMATIC_UPDATE = SettingDefinition(
    id="disable_automatic_ota",
    section=UPDATE_SECTION_ID,
    section_title=UPDATE_SECTION_TITLE,
    section_description=UPDATE_SECTION_DESCRIPTION,
    label="Disable automatic OTA scheduling",
    description=(
        "Android Developer Options setting that prevents system updates from being automatically "
        "scheduled. Manual checks, notifications or an already prepared update may still apply."
    ),
    warning=(
        "This only disables automatic scheduling. It does not disable the update packages or remove "
        "an update that is already downloaded."
    ),
    read_commands=(("value", "settings get global ota_disable_automatic_update"),),
    apply_commands=("settings put global ota_disable_automatic_update 1",),
    revert_commands=("settings delete global ota_disable_automatic_update",),
    reader=parse_ota_status,
    default_label="Off",
)


XR_PERF_METRICS = SettingDefinition(
    id="xr_perf_metrics",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Enable Android XR performance metrics",
    description=(
        "Shows Android XR's on-device performance metrics overlay. Useful while profiling a run, "
        "but it is a static HUD over the display."
    ),
    warning=(
        "Turn this off when finished. Static overlay elements can cause OLED burn-in on the headset "
        "if left on for long periods."
    ),
    read_commands=(("value", "settings --user 0 get system toggle_xr_perf_metrics"),),
    apply_commands=("settings --user 0 put system toggle_xr_perf_metrics 1",),
    revert_commands=("settings --user 0 put system toggle_xr_perf_metrics 0",),
    reader=parse_toggle_status,
    persistence_note="Survives reboots; the overlay remains enabled until turned off.",
    default_label="Off",
)


HANDS_BREAKTHROUGH = SettingDefinition(
    id="hands_breakthrough",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Enable hands breakthrough",
    description=(
        "Shows your hands through content instead of only their outlines. The feature adds a small "
        "GPU cost while it is active."
    ),
    warning="Adds a small GPU cost.",
    read_commands=(("value", "settings --user 0 get system toggle_hands_breakthrough"),),
    apply_commands=("settings --user 0 put system toggle_hands_breakthrough 1",),
    revert_commands=("settings --user 0 put system toggle_hands_breakthrough 0",),
    reader=parse_toggle_status,
    persistence_note="Survives reboots.",
    default_label="Off",
)


TOUCH_ON_EVERYTHING = SettingDefinition(
    id="touch_on_everything",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Enable touch on everything",
    description=("Enables direct hand touch/poke interaction with elements instead of requiring a gesture."),
    warning="",
    read_commands=(("value", "settings --user 0 get system enable_touch_on_everything"),),
    apply_commands=("settings --user 0 put system enable_touch_on_everything 1",),
    revert_commands=("settings --user 0 put system enable_touch_on_everything 0",),
    reader=parse_toggle_status,
    persistence_note="Survives reboots.",
    default_enabled=True,
    default_label="On",
)


GUARDIAN_BOUNDARY = SettingDefinition(
    id="guardian_boundary",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Guardian safety boundary",
    description=(
        "Turns the Android XR safety boundary on or off. The boundary warns you when you leave "
        "the play area and is enabled by default."
    ),
    warning=(
        "Turning this off disables the safety boundary. Only do this in a clear, safe space with "
        "someone nearby if needed."
    ),
    read_commands=(("value", "settings --user 0 get system toggle_guardian"),),
    apply_commands=("settings --user 0 put system toggle_guardian 1",),
    revert_commands=("settings --user 0 put system toggle_guardian 0",),
    reader=parse_toggle_status,
    persistence_note="Survives reboots; Android may re-enable the boundary after setup.",
    default_enabled=True,
    default_label="On",
    confirm_on_disable=True,
)


GUARDIAN_RADIUS_OPTIONS = (
    SettingOption("0", "Small", ("settings --user 0 put system guardian_radius 0",)),
    SettingOption("1", "Large", ("settings --user 0 put system guardian_radius 1",)),
)

GUARDIAN_RADIUS = SettingDefinition(
    id="guardian_radius",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Boundary size",
    description="Chooses the size of the circular safety boundary: Small or Large.",
    warning="Boundary changes affect safety. Numeric values are inferred from the firmware and are untested.",
    read_commands=(("value", "settings --user 0 get system guardian_radius"),),
    apply_commands=(),
    revert_commands=(),
    reader=lambda values: parse_choice_status(
        values,
        GUARDIAN_RADIUS_OPTIONS,
        label="Boundary size",
        unknown_warning="The headset returned an unexpected boundary-size value.",
    ),
    persistence_note="Survives reboots; value mapping is untested.",
    kind=SETTING_KIND_CHOICE,
    options=GUARDIAN_RADIUS_OPTIONS,
    default_label="Unknown",
)


def parse_auto_spatialization_status(values: dict[str, str]) -> dict:
    error = values.get("_error", "")
    raw = _value(values.get("value", "")).lower()
    if error:
        return _toggle_status(
            enabled=False,
            state=STATUS_UNKNOWN,
            label="Labs preference",
            value="unknown",
            error=error,
        )
    if raw in {"1", "true"}:
        return _toggle_status(enabled=True, state=STATUS_ACTIVE, label="Labs preference", value="enabled")
    if raw in {"0", "false", "null", ""}:
        return _toggle_status(enabled=False, state=STATUS_INACTIVE, label="Labs preference", value="disabled")
    return _toggle_status(
        enabled=False,
        state=STATUS_UNKNOWN,
        label="Labs preference",
        value=raw or "unknown",
        warning="The headset returned an unexpected auto-spatialization value.",
    )


AUTO_SPATIALIZATION = SettingDefinition(
    id="auto_spatialization_default",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Enable auto-spatialization preference",
    description=(
        "Turns on the saved Labs auto-spatialization preference. It does not force every window "
        "into 3D, change per-window choices, or bypass content and thermal restrictions."
    ),
    warning=(
        "If the KernelSU auto-spatialization module is installed, it will set this back to 1 at "
        "boot. Disable or remove that module before using this toggle."
    ),
    read_commands=(("value", "settings --user 0 get system auto_spatialization_settings"),),
    apply_commands=("settings --user 0 put system auto_spatialization_settings 1",),
    revert_commands=("settings --user 0 put system auto_spatialization_settings 0",),
    reader=parse_auto_spatialization_status,
    persistence_note="Survives reboots; Android may reset the Labs preference.",
    default_label="Off",
)


ANIMATIONS = SettingDefinition(
    id="disable_animations",
    section=TESTING_SECTION_ID,
    section_title=TESTING_SECTION_TITLE,
    section_description=TESTING_SECTION_DESCRIPTION,
    label="Disable UI animations",
    description=(
        "Sets the window, transition and animator duration scales to 0. Reverting deletes the keys "
        "so Android restores its configured defaults."
    ),
    warning="Untested; this may have no visible effect on this build.",
    read_commands=(
        ("window", "settings --user 0 get global window_animation_scale"),
        ("transition", "settings --user 0 get global transition_animation_scale"),
        ("animator", "settings --user 0 get global animator_duration_scale"),
    ),
    apply_commands=(
        "settings --user 0 put global window_animation_scale 0",
        "settings --user 0 put global transition_animation_scale 0",
        "settings --user 0 put global animator_duration_scale 0",
    ),
    revert_commands=(
        "settings --user 0 delete global window_animation_scale",
        "settings --user 0 delete global transition_animation_scale",
        "settings --user 0 delete global animator_duration_scale",
    ),
    reader=parse_animation_status,
    persistence_note="Survives reboots; deleting restores Android defaults.",
    default_label="Off",
)


TRANSPARENCY = SettingDefinition(
    id="reduce_transparency",
    section=TESTING_SECTION_ID,
    section_title=TESTING_SECTION_TITLE,
    section_description=TESTING_SECTION_DESCRIPTION,
    label="Reduce transparency and window blur",
    description=(
        "Enables Android's reduced-transparency and disabled-window-blur preferences. This may "
        "slightly reduce GPU/UI overhead on builds that honor either key."
    ),
    warning="Untested; this may do nothing on this build.",
    read_commands=(
        ("transparency", "settings --user 0 get global accessibility_reduce_transparency"),
        ("blur", "settings --user 0 get global disable_window_blurs"),
    ),
    apply_commands=(
        "settings --user 0 put global accessibility_reduce_transparency 1",
        "settings --user 0 put global disable_window_blurs 1",
    ),
    revert_commands=(
        "settings --user 0 delete global accessibility_reduce_transparency",
        "settings --user 0 delete global disable_window_blurs",
    ),
    reader=parse_transparency_status,
    persistence_note="Survives reboots; deleting restores defaults.",
    default_label="Off",
)


DISABLE_ALWAYS_ON_SCANNING = SettingDefinition(
    id="disable_always_on_scanning",
    section=ADVANCED_SECTION_ID,
    section_title=ADVANCED_SECTION_TITLE,
    section_description=ADVANCED_SECTION_DESCRIPTION,
    label="Disable always-on Wi-Fi/BLE scanning",
    description=(
        "Sets both Android always-on scan preferences to 0. Reverting deletes the keys so the "
        "platform can restore its defaults."
    ),
    warning="May reduce location accuracy and nearby-device features.",
    read_commands=(
        ("wifi", "settings --user 0 get global wifi_scan_always_enabled"),
        ("ble", "settings --user 0 get global ble_scan_always_enabled"),
    ),
    apply_commands=(
        "settings --user 0 put global wifi_scan_always_enabled 0",
        "settings --user 0 put global ble_scan_always_enabled 0",
    ),
    revert_commands=(
        "settings --user 0 delete global wifi_scan_always_enabled",
        "settings --user 0 delete global ble_scan_always_enabled",
    ),
    reader=parse_scan_status,
    persistence_note="Survives reboots; defaults may differ by build.",
    default_label="Unknown",
)


DISABLE_PERFORMANCE_OPTIMIZATION = SettingDefinition(
    id="disable_performance_optimization_policy",
    section=ADVANCED_SECTION_ID,
    section_title=ADVANCED_SECTION_TITLE,
    section_description=ADVANCED_SECTION_DESCRIPTION,
    label="Disable performance optimization policy",
    description=(
        "Turns off Android XR's SurfaceFlinger app dynamic policy. The policy watches for jank, limits "
        "how many apps stay open, and can background or close apps to recover performance. Disabling "
        "it removes that intervention. It is not a guaranteed FPS boost."
    ),
    warning=(
        "Requires root. May let apps run past the system limit, increasing resource pressure. Apply "
        "only while testing performance."
    ),
    read_commands=(
        (
            "value",
            "getprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy",
        ),
    ),
    apply_commands=(
        "su -c 'service call SurfaceFlinger 1044 i32 0'",
        "su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy false'",
    ),
    revert_commands=(
        "su -c 'service call SurfaceFlinger 1044 i32 1'",
        "su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy true'",
    ),
    reader=parse_disabled_property_status,
    persistence_note="Survives reboots; applied live through SurfaceFlinger.",
    root_required=True,
    default_label="Off",
)


DISABLE_CHILD_PROCESS_RESTRICTIONS = SettingDefinition(
    id="disable_child_process_restrictions",
    section=ADVANCED_SECTION_ID,
    section_title=ADVANCED_SECTION_TITLE,
    section_description=ADVANCED_SECTION_DESCRIPTION,
    label="Disable child-process restrictions",
    description=(
        "Sets Android's global settings_enable_monitor_phantom_procs to false. This disables the "
        "phantom-process monitor's restrictions on child processes, which can help apps that spawn many "
        "child processes such as Termux or emulators. It is not a general FPS tweak."
    ),
    warning=(
        "Global resource-limit change. Runaway child processes may increase CPU/memory use and battery "
        "drain. Re-enable when finished."
    ),
    read_commands=(("value", "settings --user 0 get global settings_enable_monitor_phantom_procs"),),
    apply_commands=("settings --user 0 put global settings_enable_monitor_phantom_procs false",),
    revert_commands=("settings --user 0 delete global settings_enable_monitor_phantom_procs",),
    reader=parse_child_process_status,
    persistence_note="Survives reboots; deleting restores Android's default monitoring.",
    default_label="Off",
)


STAY_AWAKE_WHILE_CHARGING = SettingDefinition(
    id="stay_awake_while_charging",
    section=ADVANCED_SECTION_ID,
    section_title=ADVANCED_SECTION_TITLE,
    section_description=ADVANCED_SECTION_DESCRIPTION,
    label="Stay awake while charging",
    description=(
        "Sets Android's keep-awake-while-plugged-in bitmask to 7 (AC, USB and wireless). This matches "
        "the Android XR Engine Hub stay-awake mode and keeps the headset awake between test runs, "
        "including when you take it off."
    ),
    warning="Increases heat and OLED burn-in risk if left on. Turn it off between sessions.",
    read_commands=(("value", "settings --user 0 get global stay_on_while_plugged_in"),),
    apply_commands=("settings --user 0 put global stay_on_while_plugged_in 7",),
    revert_commands=("settings --user 0 put global stay_on_while_plugged_in 0",),
    reader=parse_stay_awake_status,
    persistence_note="Survives reboots.",
    default_label="Off",
)


DISABLE_HEADS_UP_NOTIFICATIONS = SettingDefinition(
    id="disable_heads_up_notifications",
    section=ADVANCED_SECTION_ID,
    section_title=ADVANCED_SECTION_TITLE,
    section_description=ADVANCED_SECTION_DESCRIPTION,
    label="Disable heads-up notifications",
    description=(
        "Sets Android's global heads-up preference to 0. Notifications still appear in the "
        "notification shade, but they no longer pop up over the current app."
    ),
    warning="Important alerts will no longer appear as pop-ups.",
    read_commands=(("value", "settings --user 0 get global heads_up_notifications_enabled"),),
    apply_commands=("settings --user 0 put global heads_up_notifications_enabled 0",),
    revert_commands=("settings --user 0 put global heads_up_notifications_enabled 1",),
    reader=parse_heads_up_status,
    persistence_note="Survives reboots.",
    default_label="Off",
)


GAME_OPTIMIZING_SERVICE = _package_setting(
    setting_id="disable_game_optimizing_service",
    package="com.samsung.android.game.gos",
    label="Disable Samsung Game Optimizing Service (com.samsung.android.game.gos)",
    description=(
        "Samsung's Game Optimizing Service package. Disabling it may affect game and thermal "
        "management; its behavior on Galaxy XR is not verified."
    ),
    warning="This may change thermal or gaming behavior. It is reversible but unverified on this headset.",
    section=TESTING_SECTION_ID,
    section_title=TESTING_SECTION_TITLE,
    section_description=TESTING_SECTION_DESCRIPTION,
    persistence_note="Survives reboots; may be re-enabled by an update.",
)


DISABLE_FIXED_HSM_DISPLAY_RATE = SettingDefinition(
    id="disable_fixed_hsm_display_rate",
    section=TESTING_SECTION_ID,
    section_title=TESTING_SECTION_TITLE,
    section_description=TESTING_SECTION_DESCRIPTION,
    label="Disable fixed Home Space Mode display rate",
    description=(
        "Calls SurfaceFlinger transaction 1043 and clears the fixed_hsm_display_rate DeviceConfig "
        "flag. The firmware developer option is labelled 'Disable fixed Home Space Mode display rate'. "
        "It may let Home Space use a different refresh rate instead of the fixed rate."
    ),
    warning=("Requires root. Untested on this headset; may change refresh rate, frame pacing or power use."),
    read_commands=(
        (
            "value",
            "getprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate",
        ),
    ),
    apply_commands=(
        "su -c 'service call SurfaceFlinger 1043 i32 0'",
        ("su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate false'"),
    ),
    revert_commands=(
        "su -c 'service call SurfaceFlinger 1043 i32 1'",
        ("su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate true'"),
    ),
    reader=parse_fixed_hsm_status,
    persistence_note="Survives reboots; applied live through SurfaceFlinger.",
    root_required=True,
    default_label="Off",
)


NATURAL_INPUT_OPTIONS = (
    SettingOption(
        "6",
        "Hand and eye aiming",
        (
            "settings --user 0 put system natural_input_mode 6",
            "settings --user 0 put system input_pointer 6",
        ),
    ),
    SettingOption(
        "5",
        "Eye aiming only",
        (
            "settings --user 0 put system natural_input_mode 5",
            "settings --user 0 put system input_pointer 5",
        ),
    ),
    SettingOption(
        "1",
        "Hand aiming only",
        (
            "settings --user 0 put system natural_input_mode 1",
            "settings --user 0 put system input_pointer 1",
        ),
    ),
    SettingOption(
        "7",
        "Head direction + touchpad (no hands)",
        (
            "settings --user 0 put system natural_input_mode 7",
            "settings --user 0 put system input_pointer 7",
        ),
    ),
)

NATURAL_INPUT = SettingDefinition(
    id="natural_input_mode",
    section=XR_SECTION_ID,
    section_title=XR_SECTION_TITLE,
    section_description=XR_SECTION_DESCRIPTION,
    label="Aiming method",
    description=(
        "Android XR aiming method. The firmware UI exposes 6 = hand and eye aiming, 5 = eye aiming "
        "only, and 1 = hand aiming only. Hidden mode 7 is HMD fallback: head direction with touchpad "
        "click and no hand tracking. Enable it with Volume Down + Volume Up + the headset action "
        "button."
    ),
    warning="Changing this changes how you aim and select.",
    read_commands=(
        ("value", "settings --user 0 get system natural_input_mode"),
        ("pointer", "settings --user 0 get system input_pointer"),
    ),
    apply_commands=(),
    revert_commands=(),
    reader=lambda values: parse_natural_input_status(values, NATURAL_INPUT_OPTIONS),
    persistence_note="Survives reboots.",
    kind=SETTING_KIND_CHOICE,
    options=NATURAL_INPUT_OPTIONS,
    default_label="Hand and eye aiming",
)


PRIVACY_INDICATOR = SettingDefinition(
    id="hide_recording_indicator",
    section="privacy",
    section_title="Privacy indicators",
    section_description=(
        "Android shows a green dot when an app is using the microphone or camera. "
        "Hiding it is useful for PC VR, and the change can be reverted at any time."
    ),
    label="Hide recording indicator (green dot)",
    description=(
        "Hides the camera/microphone privacy indicator and keeps the change across reboots "
        "by disabling DeviceConfig syncing. Android updates may reset this setting."
    ),
    warning=(
        "This hides a privacy indicator. Make sure you understand which apps can use the "
        "microphone or camera while it is hidden."
    ),
    read_commands=(("icons", PRIVACY_ICONS_COMMAND), ("sync", CONFIG_SYNC_COMMAND)),
    apply_commands=HIDE_ICONS_COMMANDS,
    revert_commands=SHOW_ICONS_COMMANDS,
    reader=parse_privacy_indicator_status,
    persistence_note="Survives reboots; may reset after an Android update.",
    default_label="Off",
    recommended=True,
)


SETTING_DEFINITIONS = {
    definition.id: definition
    for definition in (
        PRIVACY_INDICATOR,
        UPDATE_CLIENT,
        UPDATE_AGENT,
        OTA_AUTOMATIC_UPDATE,
        XR_PERF_METRICS,
        HANDS_BREAKTHROUGH,
        TOUCH_ON_EVERYTHING,
        GUARDIAN_BOUNDARY,
        GUARDIAN_RADIUS,
        AUTO_SPATIALIZATION,
        ANIMATIONS,
        TRANSPARENCY,
        GAME_OPTIMIZING_SERVICE,
        DISABLE_ALWAYS_ON_SCANNING,
        DISABLE_PERFORMANCE_OPTIMIZATION,
        DISABLE_CHILD_PROCESS_RESTRICTIONS,
        STAY_AWAKE_WHILE_CHARGING,
        DISABLE_HEADS_UP_NOTIFICATIONS,
        DISABLE_FIXED_HSM_DISPLAY_RATE,
        NATURAL_INPUT,
    )
}
SETTING_SECTIONS = [
    {
        "id": XR_SECTION_ID,
        "title": XR_SECTION_TITLE,
        "description": XR_SECTION_DESCRIPTION,
        "settings": [
            XR_PERF_METRICS.id,
            NATURAL_INPUT.id,
            HANDS_BREAKTHROUGH.id,
            TOUCH_ON_EVERYTHING.id,
            GUARDIAN_BOUNDARY.id,
            GUARDIAN_RADIUS.id,
            AUTO_SPATIALIZATION.id,
        ],
        "test_only": False,
    },
    {
        "id": PRIVACY_INDICATOR.section,
        "title": PRIVACY_INDICATOR.section_title,
        "description": PRIVACY_INDICATOR.section_description,
        "settings": [PRIVACY_INDICATOR.id],
        "test_only": False,
    },
    {
        "id": UPDATE_SECTION_ID,
        "title": UPDATE_SECTION_TITLE,
        "description": UPDATE_SECTION_DESCRIPTION,
        "settings": [UPDATE_CLIENT.id, UPDATE_AGENT.id, OTA_AUTOMATIC_UPDATE.id],
        "test_only": False,
    },
    {
        "id": ADVANCED_SECTION_ID,
        "title": ADVANCED_SECTION_TITLE,
        "description": ADVANCED_SECTION_DESCRIPTION,
        "settings": [
            DISABLE_PERFORMANCE_OPTIMIZATION.id,
            DISABLE_CHILD_PROCESS_RESTRICTIONS.id,
            STAY_AWAKE_WHILE_CHARGING.id,
            DISABLE_HEADS_UP_NOTIFICATIONS.id,
            DISABLE_ALWAYS_ON_SCANNING.id,
        ],
        "test_only": False,
    },
    {
        "id": TESTING_SECTION_ID,
        "title": TESTING_SECTION_TITLE,
        "description": TESTING_SECTION_DESCRIPTION,
        "settings": [
            ANIMATIONS.id,
            TRANSPARENCY.id,
            GAME_OPTIMIZING_SERVICE.id,
            DISABLE_FIXED_HSM_DISPLAY_RATE.id,
        ],
        "test_only": True,
    },
]


def get_setting_definition(setting_id: str) -> SettingDefinition:
    definition = SETTING_DEFINITIONS.get(setting_id)
    if definition is None:
        raise ValueError(f"unknown setting: {setting_id}")
    return definition


def public_setting(definition: SettingDefinition) -> dict:
    return {
        "id": definition.id,
        "section": definition.section,
        "label": definition.label,
        "description": definition.description,
        "warning": definition.warning,
        "persistence": definition.persistence,
        "persistence_note": definition.persistence_note,
        "root_required": definition.root_required,
        "default_enabled": definition.default_enabled,
        "default_label": definition.default_label,
        "kind": definition.kind,
        "options": [
            {"value": option.value, "label": option.label, "commands": list(option.commands)}
            for option in definition.options
        ],
        "confirm_on_disable": definition.confirm_on_disable,
        "recommended": definition.recommended,
        "commands": {
            "read": [command for _, command in definition.read_commands],
            "apply": list(definition.apply_commands),
            "revert": list(definition.revert_commands),
        },
    }
