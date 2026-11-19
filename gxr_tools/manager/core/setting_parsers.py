"""Parsers that turn raw Android setting output into UI status objects."""

from __future__ import annotations

from collections.abc import Callable

from .setting_types import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_PARTIAL,
    STATUS_UNAVAILABLE,
    STATUS_UNKNOWN,
    SettingOption,
)


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


def package_reader(package: str) -> Callable[[dict[str, str]], dict]:
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
