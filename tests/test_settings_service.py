import json
from types import SimpleNamespace

import pytest

from gxr_manager.server.settings import SettingsService


class FakeSettingsAdb:
    def __init__(self, icons="true", sync="none", invalid_reads=False):
        self.icons = icons
        self.sync = sync
        self.run_calls = []
        self.fail_command = ""
        self.invalid_reads = invalid_reads
        self.installed = {"com.wssyncmldm", "com.sec.android.soagent", "com.samsung.android.game.gos"}
        self.disabled = set()
        self.system = {
            "auto_spatialization_settings": "0",
            "toggle_xr_perf_metrics": "0",
            "toggle_hands_breakthrough": "0",
            "enable_touch_on_everything": "1",
            "toggle_guardian": "0",
            "guardian_radius": "1",
            "natural_input_mode": "1",
            "input_pointer": "1",
        }
        self.global_ = {
            "ota_disable_automatic_update": "0",
            "window_animation_scale": "1.0",
            "transition_animation_scale": "1.0",
            "animator_duration_scale": "1.0",
            "wifi_scan_always_enabled": "0",
            "ble_scan_always_enabled": "0",
            "stay_on_while_plugged_in": "0",
            "heads_up_notifications_enabled": "1",
        }
        self.secure = {"xr_restore_previous_workspace": "0"}
        self.dynamic_policy = "true"
        self.fixed_hsm = "true"

    def _settings(self, command):
        parts = command.split()
        index = 1
        if len(parts) > 1 and parts[1] == "--user":
            index = 3
        if index + 2 >= len(parts):
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        action, namespace, key = parts[index : index + 3]
        state = {"system": self.system, "global": self.global_, "secure": self.secure}[namespace]
        if action == "get":
            return SimpleNamespace(stdout=state.get(key, "null") + "\n", stderr="", returncode=0)
        if action == "put" and index + 3 < len(parts):
            state[key] = parts[index + 3]
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if action == "delete":
            state.pop(key, None)
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    def run(self, args, timeout=25.0):
        command = args[-1]
        self.run_calls.append(command)
        if command.startswith(
            "getprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate"
        ):
            return SimpleNamespace(stdout=self.fixed_hsm + "\n", stderr="", returncode=0)
        if command.startswith("su -c 'service call SurfaceFlinger 1043 i32 "):
            self.fixed_hsm = "false" if " i32 0" in command else "true"
            return SimpleNamespace(stdout="Result: Parcel(NULL)\n", stderr="", returncode=0)
        if command.startswith(
            "su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate "
        ):
            self.fixed_hsm = "false" if " false'" in command else "true"
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if command.startswith(
            "getprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy"
        ):
            return SimpleNamespace(stdout=self.dynamic_policy + "\n", stderr="", returncode=0)
        if command.startswith("su -c 'service call SurfaceFlinger 1044 i32 "):
            self.dynamic_policy = "false" if " i32 0" in command else "true"
            return SimpleNamespace(stdout="Result: Parcel(NULL)\n", stderr="", returncode=0)
        if command.startswith(
            "su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy "
        ):
            self.dynamic_policy = "false" if " false'" in command else "true"
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if command.startswith("cmd device_config get privacy camera_mic_icons_enabled"):
            if self.invalid_reads:
                return SimpleNamespace(stdout="garbage\n", stderr="", returncode=0)
            return SimpleNamespace(stdout=self.icons + "\n", stderr="", returncode=0)
        if command.startswith("cmd device_config get_sync_disabled_for_tests"):
            return SimpleNamespace(stdout=self.sync + "\n", stderr="", returncode=0)
        if command.startswith("settings "):
            if command == self.fail_command:
                return SimpleNamespace(stdout="", stderr="Error: denied", returncode=1)
            return self._settings(command)
        if command.startswith("pm list packages -d "):
            package = command.rsplit(" ", 1)[-1]
            return SimpleNamespace(
                stdout=(f"package:{package}\n" if package in self.disabled else ""), stderr="", returncode=0
            )
        if command.startswith("pm list packages "):
            package = command.rsplit(" ", 1)[-1]
            return SimpleNamespace(
                stdout=(f"package:{package}\n" if package in self.installed else ""), stderr="", returncode=0
            )
        if command == self.fail_command:
            return SimpleNamespace(stdout="", stderr="Error: denied", returncode=1)
        if "camera_mic_icons_enabled false" in command:
            self.icons = "false"
        elif "camera_mic_icons_enabled true" in command:
            self.icons = "true"
        elif "set_sync_disabled_for_tests persistent" in command:
            self.sync = "persistent"
        elif "set_sync_disabled_for_tests none" in command:
            self.sync = "none"
        elif command.startswith("pm disable-user --user 0 "):
            self.disabled.add(command.rsplit(" ", 1)[-1])
        elif command.startswith("pm enable --user 0 "):
            self.disabled.discard(command.rsplit(" ", 1)[-1])
        return SimpleNamespace(stdout="", stderr="", returncode=0)


def _service(tmp_path, adb):
    return SettingsService(serial="fake", reports_dir=str(tmp_path / "reports"), adb_factory=lambda serial=None: adb)


def _setting(snapshot, setting_id):
    for section in snapshot["sections"]:
        for item in section["settings"]:
            if item["id"] == setting_id:
                return item
    raise AssertionError(f"setting not found: {setting_id}")


def _log_entries(tmp_path):
    path = tmp_path / "reports" / "setting-actions.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_settings_snapshot_and_toggle_apply_revert(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    snapshot = service.snapshot()
    item = _setting(snapshot, "hide_recording_indicator")
    assert item["state"] == "inactive"
    assert item["enabled"] is False

    result = service.set_enabled("hide_recording_indicator", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    assert adb.run_calls[-4:-2] == [
        "cmd device_config put privacy camera_mic_icons_enabled false default",
        "cmd device_config set_sync_disabled_for_tests persistent",
    ]

    result = service.set_enabled("hide_recording_indicator", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"

    entries = _log_entries(tmp_path)
    assert entries[-1]["setting_id"] == "hide_recording_indicator"
    assert entries[-1]["enabled"] is False


def test_settings_snapshot_reports_partial_and_unknown(tmp_path):
    partial = _service(tmp_path, FakeSettingsAdb(icons="false", sync="none"))
    assert _setting(partial.snapshot(), "hide_recording_indicator")["state"] == "partial"

    unknown = _service(tmp_path, FakeSettingsAdb(invalid_reads=True))
    assert _setting(unknown.snapshot(), "hide_recording_indicator")["state"] == "unknown"


def test_settings_toggle_reports_failure(tmp_path):
    adb = FakeSettingsAdb()
    adb.fail_command = "cmd device_config put privacy camera_mic_icons_enabled false default"
    service = _service(tmp_path, adb)
    result = service.set_enabled("hide_recording_indicator", True)
    assert result["ok"] is False
    assert "denied" in result["output"]
    assert result["state"]["state"] == "inactive"


def test_settings_reject_unknown_setting_and_wrong_kind(tmp_path):
    service = _service(tmp_path, FakeSettingsAdb())
    with pytest.raises(ValueError):
        service.set_enabled("missing", True)
    with pytest.raises(ValueError):
        service.set_enabled("guardian_radius", True)
    with pytest.raises(ValueError):
        service.set_value("xr_perf_metrics", "1")
    with pytest.raises(ValueError):
        service.set_value("guardian_radius", "9")


def test_update_settings_snapshot_and_toggles(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    snapshot = service.snapshot()

    for setting_id in ("disable_update_client", "disable_update_agent", "disable_automatic_ota"):
        item = _setting(snapshot, setting_id)
        assert item["state"] == "inactive"
        assert item["enabled"] is False

    result = service.set_enabled("disable_update_client", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    assert result["commands"] == ["pm disable-user --user 0 com.wssyncmldm"]

    result = service.set_enabled("disable_update_agent", True)
    assert result["ok"] is True
    assert result["commands"] == ["pm disable-user --user 0 com.sec.android.soagent"]

    result = service.set_enabled("disable_automatic_ota", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    assert result["commands"] == ["settings put global ota_disable_automatic_update 1"]

    result = service.set_enabled("disable_automatic_ota", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"
    assert result["commands"] == ["settings delete global ota_disable_automatic_update"]


def test_update_package_missing_and_ota_active(tmp_path):
    adb = FakeSettingsAdb()
    adb.installed.remove("com.wssyncmldm")
    adb.global_["ota_disable_automatic_update"] = "1"
    snapshot = _service(tmp_path, adb).snapshot()
    assert _setting(snapshot, "disable_update_client")["state"] == "unavailable"
    assert _setting(snapshot, "disable_automatic_ota")["state"] == "active"


def test_auto_spatialization_toggle_and_persistence(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    item = _setting(service.snapshot(), "auto_spatialization_default")
    assert item["state"] == "inactive"
    assert item["persistence"] == "persistent"
    assert item["root_required"] is False
    assert item["default_label"] == "Off"

    result = service.set_enabled("auto_spatialization_default", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    assert result["commands"] == ["settings --user 0 put system auto_spatialization_settings 1"]

    result = service.set_enabled("auto_spatialization_default", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"
    assert result["commands"] == ["settings --user 0 put system auto_spatialization_settings 0"]


def test_xr_controls_snapshot_and_toggles(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    snapshot = service.snapshot()

    for setting_id in ("xr_perf_metrics", "hands_breakthrough", "guardian_boundary"):
        item = _setting(snapshot, setting_id)
        assert item["state"] == "inactive"
        assert item["enabled"] is False
    assert _setting(snapshot, "touch_on_everything")["enabled"] is True
    assert _setting(snapshot, "guardian_radius")["value"] == "1"
    assert _setting(snapshot, "guardian_radius")["details"][0]["value"] == "Large"

    result = service.set_enabled("xr_perf_metrics", True)
    assert result["ok"] is True
    assert result["commands"] == ["settings --user 0 put system toggle_xr_perf_metrics 1"]
    assert "OLED burn-in" in _setting(service.snapshot(), "xr_perf_metrics")["warning"]

    result = service.set_enabled("hands_breakthrough", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"

    result = service.set_enabled("guardian_boundary", True)
    assert result["ok"] is True
    assert result["commands"] == ["settings --user 0 put system toggle_guardian 1"]

    result = service.set_value("guardian_radius", "0")
    assert result["ok"] is True
    assert result["value"] == "0"
    assert result["label"] == "Small"
    assert _setting(service.snapshot(), "guardian_radius")["value"] == "0"

    entry = _log_entries(tmp_path)[-1]
    assert entry["setting_id"] == "guardian_radius"
    assert entry["value"] == "0"
    assert entry["label"] == "Small"


def test_display_and_advanced_toggles(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    snapshot = service.snapshot()

    animations = _setting(snapshot, "disable_animations")
    assert animations["state"] == "inactive"
    result = service.set_enabled("disable_animations", True)
    assert result["ok"] is True
    assert result["commands"] == [
        "settings --user 0 put global window_animation_scale 0",
        "settings --user 0 put global transition_animation_scale 0",
        "settings --user 0 put global animator_duration_scale 0",
    ]
    assert result["state"]["state"] == "active"
    result = service.set_enabled("disable_animations", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"

    transparency = _setting(snapshot, "reduce_transparency")
    assert transparency["state"] == "inactive"
    result = service.set_enabled("reduce_transparency", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    result = service.set_enabled("reduce_transparency", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"

    scanning = _setting(snapshot, "disable_always_on_scanning")
    assert scanning["state"] == "active"
    result = service.set_enabled("disable_always_on_scanning", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"
    result = service.set_enabled("disable_always_on_scanning", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"

    gos = _setting(snapshot, "disable_game_optimizing_service")
    assert gos["state"] == "inactive"
    result = service.set_enabled("disable_game_optimizing_service", True)
    assert result["ok"] is True
    assert result["commands"] == ["pm disable-user --user 0 com.samsung.android.game.gos"]
    assert result["state"]["state"] == "active"


def test_stay_awake_and_heads_up_toggles(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    snapshot = service.snapshot()
    assert _setting(snapshot, "stay_awake_while_charging")["state"] == "inactive"
    assert _setting(snapshot, "disable_heads_up_notifications")["state"] == "inactive"

    result = service.set_enabled("stay_awake_while_charging", True)
    assert result["ok"] is True
    assert result["commands"] == ["settings --user 0 put global stay_on_while_plugged_in 7"]
    assert result["state"]["state"] == "active"
    assert adb.global_["stay_on_while_plugged_in"] == "7"

    result = service.set_enabled("stay_awake_while_charging", False)
    assert result["ok"] is True
    assert adb.global_["stay_on_while_plugged_in"] == "0"
    assert result["state"]["state"] == "inactive"

    result = service.set_enabled("disable_heads_up_notifications", True)
    assert result["ok"] is True
    assert result["commands"] == ["settings --user 0 put global heads_up_notifications_enabled 0"]
    assert result["state"]["state"] == "active"
    assert adb.global_["heads_up_notifications_enabled"] == "0"

    result = service.set_enabled("disable_heads_up_notifications", False)
    assert result["ok"] is True
    assert adb.global_["heads_up_notifications_enabled"] == "1"
    assert result["state"]["state"] == "inactive"


def test_child_process_restrictions_toggle(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    item = _setting(service.snapshot(), "disable_child_process_restrictions")
    assert item["state"] == "inactive"

    result = service.set_enabled("disable_child_process_restrictions", True)
    assert result["ok"] is True
    assert result["commands"] == ["settings --user 0 put global settings_enable_monitor_phantom_procs false"]
    assert result["state"]["state"] == "active"
    assert adb.global_["settings_enable_monitor_phantom_procs"] == "false"

    result = service.set_enabled("disable_child_process_restrictions", False)
    assert result["ok"] is True
    assert result["commands"] == ["settings --user 0 delete global settings_enable_monitor_phantom_procs"]
    assert result["state"]["state"] == "inactive"
    assert "settings_enable_monitor_phantom_procs" not in adb.global_


def test_performance_optimization_policy_toggle(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    item = _setting(service.snapshot(), "disable_performance_optimization_policy")
    assert item["state"] == "inactive"
    assert item["root_required"] is True

    result = service.set_enabled("disable_performance_optimization_policy", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    assert result["commands"] == [
        "su -c 'service call SurfaceFlinger 1044 i32 0'",
        "su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy false'",
    ]
    assert adb.dynamic_policy == "false"

    result = service.set_enabled("disable_performance_optimization_policy", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"
    assert adb.dynamic_policy == "true"


def test_fixed_hsm_display_rate_toggle(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    item = _setting(service.snapshot(), "disable_fixed_hsm_display_rate")
    assert item["state"] == "inactive"
    assert item["root_required"] is True

    result = service.set_enabled("disable_fixed_hsm_display_rate", True)
    assert result["ok"] is True
    assert result["state"]["state"] == "active"
    assert result["commands"] == [
        "su -c 'service call SurfaceFlinger 1043 i32 0'",
        "su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate false'",
    ]
    assert adb.fixed_hsm == "false"

    result = service.set_enabled("disable_fixed_hsm_display_rate", False)
    assert result["ok"] is True
    assert result["state"]["state"] == "inactive"
    assert adb.fixed_hsm == "true"


def test_natural_input_and_hidden_mode(tmp_path):
    adb = FakeSettingsAdb()
    service = _service(tmp_path, adb)
    snapshot = service.snapshot()

    natural = _setting(snapshot, "natural_input_mode")
    assert natural["state"] == "active"
    assert natural["value"] == "1"
    assert natural["details"][0]["value"] == "Hand aiming only"
    result = service.set_value("natural_input_mode", "6")
    assert result["ok"] is True
    assert result["label"] == "Hand and eye aiming"
    assert _setting(service.snapshot(), "natural_input_mode")["value"] == "6"

    with pytest.raises(ValueError):
        service.set_value("natural_input_mode", "3")

    result = service.set_value("natural_input_mode", "7")
    assert result["ok"] is True
    assert result["label"] == "Head direction + touchpad (no hands)"
    assert result["commands"] == [
        "settings --user 0 put system natural_input_mode 7",
        "settings --user 0 put system input_pointer 7",
    ]
    assert _setting(service.snapshot(), "natural_input_mode")["value"] == "7"
