from gxr_tools.manager.core.settings import (
    SETTING_DEFINITIONS,
    SETTING_SECTIONS,
    get_setting_definition,
    parse_animation_status,
    parse_choice_status,
    parse_privacy_indicator_status,
    parse_scan_status,
    parse_toggle_status,
    parse_transparency_status,
    public_setting,
)


def test_privacy_status_active_and_inactive():
    active = parse_privacy_indicator_status({"icons": "false\n", "sync": "persistent\n"})
    assert active["enabled"] is True
    assert active["state"] == "active"
    assert active["warning"] == ""

    inactive = parse_privacy_indicator_status({"icons": "true", "sync": "none"})
    assert inactive["enabled"] is False
    assert inactive["state"] == "inactive"


def test_privacy_status_partial_states():
    hidden_not_persistent = parse_privacy_indicator_status({"icons": "false", "sync": "none"})
    assert hidden_not_persistent["enabled"] is True
    assert hidden_not_persistent["state"] == "partial"

    persistent_but_visible = parse_privacy_indicator_status({"icons": "true", "sync": "persistent"})
    assert persistent_but_visible["enabled"] is False
    assert persistent_but_visible["state"] == "partial"

    until_reboot = parse_privacy_indicator_status({"icons": "false", "sync": "until_reboot"})
    assert until_reboot["state"] == "partial"


def test_privacy_status_unknown_and_errors():
    unknown = parse_privacy_indicator_status({"icons": "garbage", "sync": "none"})
    assert unknown["state"] == "unknown"

    failed = parse_privacy_indicator_status({"icons": "", "sync": "", "_error": "permission denied"})
    assert failed["state"] == "unknown"
    assert "permission denied" in failed["error"]


def test_toggle_and_choice_status_parsers():
    assert parse_toggle_status({"value": "1"})["state"] == "active"
    assert parse_toggle_status({"value": "true"})["state"] == "active"
    assert parse_toggle_status({"value": "0"})["state"] == "inactive"
    assert parse_toggle_status({"value": "null"})["state"] == "inactive"
    assert parse_toggle_status({"value": "garbage"})["state"] == "unknown"

    definition = get_setting_definition("guardian_radius")
    active = parse_choice_status({"value": "1"}, definition.options)
    assert active["state"] == "active"
    assert active["value"] == "1"
    assert active["details"][0]["value"] == "Large"
    assert parse_choice_status({"value": "9"}, definition.options)["state"] == "unknown"


def test_multi_key_status_parsers():
    active = parse_animation_status({"window": "0", "transition": "0.0", "animator": "0"})
    assert active["state"] == "active"
    assert active["enabled"] is True

    partial = parse_animation_status({"window": "0", "transition": "1.0", "animator": "1.0"})
    assert partial["state"] == "partial"

    inactive = parse_animation_status({"window": "null", "transition": "1.0", "animator": "1.0"})
    assert inactive["state"] == "inactive"

    assert parse_transparency_status({"transparency": "1", "blur": "1"})["state"] == "active"
    assert parse_transparency_status({"transparency": "1", "blur": "0"})["state"] == "partial"
    assert parse_transparency_status({"transparency": "null", "blur": "null"})["state"] == "inactive"
    assert parse_scan_status({"wifi": "0", "ble": "0"})["state"] == "active"
    assert parse_scan_status({"wifi": "0", "ble": "1"})["state"] == "partial"
    assert parse_scan_status({"wifi": "null", "ble": "null"})["state"] == "inactive"


def test_setting_metadata_and_commands():
    definition = get_setting_definition("hide_recording_indicator")
    public = public_setting(definition)
    assert public["section"] == "privacy"
    assert any("camera_mic_icons_enabled false" in command for command in public["commands"]["apply"])
    assert any("set_sync_disabled_for_tests persistent" in command for command in public["commands"]["apply"])
    assert any("camera_mic_icons_enabled true" in command for command in public["commands"]["revert"])
    assert public["recommended"] is True
    assert SETTING_SECTIONS[0]["id"] == "xr"
    assert SETTING_SECTIONS[0]["settings"][0] == "xr_perf_metrics"


def test_package_update_setting_status():
    reader = get_setting_definition("disable_update_client").reader
    inactive = reader(
        {
            "installed": "package:com.wssyncmldm\n",
            "disabled": "",
        }
    )
    assert inactive["state"] == "inactive"

    active = reader(
        {
            "installed": "package:com.wssyncmldm\n",
            "disabled": "package:com.wssyncmldm\n",
        }
    )
    assert active["state"] == "active"

    missing = reader({"installed": "", "disabled": ""})
    assert missing["state"] == "unavailable"


def test_ota_status_parser():
    reader = get_setting_definition("disable_automatic_ota").reader
    assert reader({"value": "1"})["state"] == "active"
    assert reader({"value": "0"})["state"] == "inactive"
    assert reader({"value": "null"})["state"] == "inactive"
    assert reader({"value": "garbage"})["state"] == "unknown"


def test_update_section_is_registered():
    section = next(item for item in SETTING_SECTIONS if item["id"] == "updates")
    assert section["settings"] == ["disable_update_client", "disable_update_agent", "disable_automatic_ota"]


def test_sections_and_new_setting_metadata():
    ids = [section["id"] for section in SETTING_SECTIONS]
    assert ids == ["xr", "privacy", "updates", "advanced", "testing"]
    advanced = next(item for item in SETTING_SECTIONS if item["id"] == "advanced")
    testing = next(item for item in SETTING_SECTIONS if item["id"] == "testing")
    assert "collapsed" not in advanced
    assert "collapsed" not in testing
    assert advanced["settings"] == [
        "disable_child_process_restrictions",
        "stay_awake_while_charging",
        "disable_heads_up_notifications",
        "disable_always_on_scanning",
    ]
    assert testing["test_only"] is True
    assert testing["settings"] == [
        "disable_performance_optimization_policy",
        "disable_animations",
        "reduce_transparency",
        "disable_game_optimizing_service",
        "disable_fixed_hsm_display_rate",
    ]

    perf = public_setting(get_setting_definition("xr_perf_metrics"))
    assert "OLED burn-in" in perf["warning"]
    assert perf["default_label"] == "Off"

    guardian = public_setting(get_setting_definition("guardian_boundary"))
    assert guardian["confirm_on_disable"] is True
    assert guardian["default_enabled"] is True

    radius = public_setting(get_setting_definition("guardian_radius"))
    assert radius["kind"] == "choice"
    assert [option["label"] for option in radius["options"]] == ["Small", "Large"]

    natural = public_setting(get_setting_definition("natural_input_mode"))
    assert natural["kind"] == "choice"
    assert natural["section"] == "xr"
    assert [option["value"] for option in natural["options"]] == ["6", "5", "1", "7"]
    assert [option["label"] for option in natural["options"]] == [
        "Hand and eye aiming",
        "Eye aiming only",
        "Hand aiming only",
        "Head direction + touchpad (no hands)",
    ]
    assert len(natural["commands"]["read"]) == 2
    assert natural["persistence_note"] == "Survives reboots."
    xr = next(item for item in SETTING_SECTIONS if item["id"] == "xr")
    assert xr["settings"][:2] == ["xr_perf_metrics", "natural_input_mode"]


def test_auto_spatialization_status_and_persistence_metadata():
    reader = get_setting_definition("auto_spatialization_default").reader
    assert reader({"value": "1"})["state"] == "active"
    assert reader({"value": "0"})["state"] == "inactive"
    assert reader({"value": "null"})["state"] == "inactive"
    assert reader({"value": "garbage"})["state"] == "unknown"

    public = public_setting(get_setting_definition("auto_spatialization_default"))
    assert public["persistence"] == "persistent"
    assert public["root_required"] is False
    assert public["persistence_note"]

    privacy = public_setting(get_setting_definition("hide_recording_indicator"))
    assert privacy["persistence"] == "persistent"
    assert "Android update" in privacy["persistence_note"]


def test_performance_optimization_parser_and_metadata():
    reader = get_setting_definition("disable_performance_optimization_policy").reader
    assert reader({"value": "false"})["state"] == "active"
    assert reader({"value": "true"})["state"] == "inactive"
    assert reader({"value": "garbage"})["state"] == "unknown"
    error = reader({"_error": "Operation not permitted", "value": ""})
    assert error["state"] == "unknown"
    assert "Operation not permitted" in error["error"]

    public = public_setting(get_setting_definition("disable_performance_optimization_policy"))
    assert public["section"] == "testing"
    assert public["root_required"] is True
    assert public["default_label"] == "Off"
    assert "Requires root" in public["warning"]


def test_stay_awake_and_heads_up_parsers():
    stay = get_setting_definition("stay_awake_while_charging").reader
    assert stay({"value": "0"})["state"] == "inactive"
    assert stay({"value": "null"})["state"] == "inactive"
    assert stay({"value": "7"})["state"] == "active"
    assert stay({"value": "4"})["state"] == "active"
    assert stay({"value": "garbage"})["state"] == "unknown"
    assert stay({"_error": "denied", "value": ""})["state"] == "unknown"

    heads_up = get_setting_definition("disable_heads_up_notifications").reader
    assert heads_up({"value": "0"})["state"] == "active"
    assert heads_up({"value": "1"})["state"] == "inactive"
    assert heads_up({"value": "garbage"})["state"] == "unknown"


def test_fixed_hsm_parser_and_metadata():
    reader = get_setting_definition("disable_fixed_hsm_display_rate").reader
    assert reader({"value": "false"})["state"] == "active"
    assert reader({"value": "true"})["state"] == "inactive"
    assert reader({"value": "garbage"})["state"] == "unknown"

    public = public_setting(get_setting_definition("disable_fixed_hsm_display_rate"))
    assert public["section"] == "testing"
    assert public["root_required"] is True
    assert public["default_label"] == "Off"
    assert "Requires root" in public["warning"]


def test_child_process_parser_and_metadata():
    reader = get_setting_definition("disable_child_process_restrictions").reader
    assert reader({"value": "null"})["state"] == "inactive"
    assert reader({"value": "true"})["state"] == "inactive"
    assert reader({"value": "1"})["state"] == "inactive"
    assert reader({"value": "false"})["state"] == "active"
    assert reader({"value": "0"})["state"] == "active"
    assert reader({"value": "garbage"})["state"] == "unknown"
    assert reader({"_error": "denied", "value": ""})["state"] == "unknown"

    public = public_setting(get_setting_definition("disable_child_process_restrictions"))
    assert public["section"] == "advanced"
    assert public["root_required"] is False


def test_all_definitions_are_public_and_have_commands():
    for definition in SETTING_DEFINITIONS.values():
        public = public_setting(definition)
        assert public["commands"]["read"]
        if definition.kind == "choice":
            assert public["options"]
            assert all(option["commands"] for option in public["options"])
        else:
            assert public["commands"]["apply"]
            assert public["commands"]["revert"]
