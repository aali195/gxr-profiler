import json
from types import SimpleNamespace

import pytest

from gxr_tools.manager.core.apps import PACKAGE_FALLBACK_SCRIPT
from gxr_tools.manager.server.apps import AppsService
from tests.apps_fixtures import APP_LIST, DETAIL


class FakeAppsAdb:
    def __init__(self, list_text=APP_LIST, detail_text=DETAIL, fail_action=False, root_available=True):
        self.list_text = list_text
        self.detail_text = detail_text
        self.fail_action = fail_action
        self.root_available = root_available
        self.shell_calls = []
        self.run_calls = []
        self.game_modes = "com.example.app current mode: standard, available game modes: [standard,custom]"
        self.game_configs = "No intervention found for package com.example.app"

    def shell(self, script, timeout=25.0):
        self.shell_calls.append(script)
        if "###PACKAGES" in script:
            return self.list_text
        if script == PACKAGE_FALLBACK_SCRIPT:
            return "package:com.example.app uid:10123\n"
        if script.startswith("du -sk"):
            return "1024 /data/app/~~abc/com.example.app-1\n512 /system/priv-app/SystemUI/SystemUI.apk\n"
        if script.startswith("dumpsys package"):
            return self.detail_text
        if script.startswith("cmd game list-modes "):
            return self.game_modes
        if script.startswith("cmd game list-configs "):
            return self.game_configs
        if script.startswith("pm path"):
            return "package:/data/app/~~abc/com.example.app-1/base.apk\n"
        if script == "su -c id":
            if not self.root_available:
                return "uid=2000(shell) gid=2000(shell)\n"
            return "uid=0(root) gid=0(root) context=u:r:ksu:s0\n"
        if script.startswith("su -c") and "du -sk" in script:
            return "100 /data/user/0/com.example.app\n8 /data/user/0/com.example.app/cache\n"
        return ""

    def run(self, args, timeout=25.0):
        self.run_calls.append(args)
        command = args[-1]
        if command.startswith("cmd game set "):
            parts = command.split()
            fps = parts[parts.index("--fps") + 1] if "--fps" in parts else "disable"
            downscale = parts[parts.index("--downscale") + 1] if "--downscale" in parts else "disable"
            scaling = downscale if downscale != "disable" else "-1.0"
            fps_text = fps if fps != "disable" else ""
            self.game_modes = "com.example.app current mode: custom, available game modes: [standard,custom]"
            self.game_configs = (
                "com.example.app interventions: \n"
                "[Name:com.example.app Modes: {4=[Game Mode:4,Scaling:"
                + scaling
                + ",Use Angle:false,Fps:"
                + fps_text
                + ",Loading Boost Duration:-1]}]"
            )
            return SimpleNamespace(stdout="Set custom mode intervention config for game\n", stderr="", returncode=0)
        if command.startswith("cmd game reset "):
            self.game_modes = "com.example.app current mode: standard, available game modes: [standard,custom]"
            self.game_configs = "No intervention found for package com.example.app"
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if self.fail_action:
            return SimpleNamespace(stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]", stderr="", returncode=1)
        return SimpleNamespace(stdout="Success", stderr="", returncode=0)


def _service(tmp_path, adb):
    return AppsService(serial="fake", reports_dir=str(tmp_path / "reports"), adb_factory=lambda serial=None: adb)


def test_apps_service_lists_and_reads_detail(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    data = service.list_packages()
    assert data["summary"]["total"] == 4
    assert data["summary"]["size_kb"] == 1536
    assert data["action_specs"]["disable"]["command"] == "pm disable-user --user 0 {package}"

    row = next(item for item in data["packages"] if item["package"] == "com.example.app")
    assert row["kind"] == "user"
    assert row["actions"] == ["disable", "uninstall"]
    assert row["proc_count"] == 1
    assert row["cpu_pct"] == 12.5
    assert row["rss_kb"] == 2048
    assert row["gpu_mem_kb"] == 1024
    assert row["size_kb"] == 1024
    assert row["threads"] == 12
    assert row["oom_class"] == "cached"

    detail = service.detail("com.example.app", root=True)
    assert detail["detail"]["version_name"] == "1.2.3"
    assert detail["detail"]["apk_paths"] == ["/data/app/~~abc/com.example.app-1/base.apk"]
    assert detail["root"]["available"] is True
    assert detail["root"]["data_kb"] == 100
    assert detail["root"]["cache_kb"] == 8


def test_apps_service_root_denied_keeps_base_detail(tmp_path):
    service = _service(tmp_path, FakeAppsAdb(root_available=False))
    detail = service.detail("com.example.app", root=True)
    assert detail["detail"]["version_name"] == "1.2.3"
    assert detail["root"]["available"] is False
    assert detail["root"]["errors"]


def test_apps_service_action_validates_and_logs(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    result = service.run_action("com.example.app", "disable", confirm=True)
    assert result["ok"] is True
    assert result["command"] == "pm disable-user --user 0 com.example.app"
    assert adb.run_calls[-1][-1] == "pm disable-user --user 0 com.example.app"
    log_path = tmp_path / "reports" / "app-actions.jsonl"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["package"] == "com.example.app"
    assert entry["action"] == "disable"


def test_apps_service_rejects_unavailable_and_critical_actions(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    with pytest.raises(ValueError):
        service.run_action("com.example.app", "enable", confirm=True)

    with pytest.raises(PermissionError, match="cannot be disabled or removed"):
        service.run_action("com.android.systemui", "disable", confirm=True)

    with pytest.raises(ValueError):
        service.run_action("com.example.app", "disable", confirm=False)


def test_apps_service_action_does_not_read_sizes(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    service.run_action("com.example.app", "disable", confirm=True)
    assert not any(script.startswith("du -sk") for script in adb.shell_calls)


def test_apps_service_batches_size_reads(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    rows = [{"apk_path": f"/system/app/App{i}/App{i}.apk"} for i in range(130)]
    service._add_sizes(adb, rows)
    commands = [script for script in adb.shell_calls if script.startswith("du -sk")]
    assert len(commands) == 3


def test_apps_service_game_override(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    detail = service.detail("com.example.app")
    assert detail["game"]["supported"] is True
    assert detail["game"]["fps"] == "disable"

    result = service.set_game_override("com.example.app", "90", "0.8", confirm=True)
    assert result["ok"] is True
    assert result["command"] == "cmd game set --fps 90 --downscale 0.8 com.example.app"
    assert result["game"]["fps"] == "90"
    assert result["game"]["downscale"] == "0.8"
    log_path = tmp_path / "reports" / "app-actions.jsonl"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["action"] == "performance"
    assert entry["fps"] == "90"
    assert entry["downscale"] == "0.8"

    result = service.set_game_override("com.example.app", "disable", "0.8", confirm=True)
    assert result["ok"] is True
    assert result["command"] == "cmd game set --downscale 0.8 com.example.app"
    assert result["game"]["fps"] == "disable"
    assert result["game"]["downscale"] == "0.8"

    result = service.set_game_override("com.example.app", "90", "disable", confirm=True)
    assert result["ok"] is True
    assert result["command"] == "cmd game set --fps 90 --downscale disable com.example.app"
    assert result["game"]["fps"] == "90"
    assert result["game"]["downscale"] == "disable"

    result = service.set_game_override("com.example.app", "disable", "disable", confirm=True)
    assert result["ok"] is True
    assert result["command"] == "cmd game reset com.example.app"
    assert result["game"]["fps"] == "disable"

    with pytest.raises(ValueError):
        service.set_game_override("com.example.app", "90", "0.8", confirm=False)
    with pytest.raises(ValueError):
        service.set_game_override("com.example.app", "72", "0.8", confirm=True)
    with pytest.raises(ValueError):
        service.set_game_override("com.example.app", "90", "0.55", confirm=True)
    with pytest.raises(PermissionError):
        service.set_game_override("com.android.systemui", "90", "0.8", confirm=True)


def test_apps_service_game_override_unsupported(tmp_path):
    adb = FakeAppsAdb()
    adb.game_modes = "com.example.app current mode: unsupported, available game modes: []"
    service = _service(tmp_path, adb)
    with pytest.raises(ValueError, match="not supported"):
        service.set_game_override("com.example.app", "90", "0.8", confirm=True)


def test_apps_service_rejects_invalid_package_names(tmp_path):
    service = _service(tmp_path, FakeAppsAdb())
    with pytest.raises(ValueError):
        service.detail("../evil")
    with pytest.raises(ValueError):
        service.run_action("../evil", "disable", confirm=True)


def test_apps_service_failure_result_and_fallback(tmp_path):
    adb = FakeAppsAdb(list_text="###PACKAGES\nError: Unknown option\n", fail_action=True)
    service = _service(tmp_path, adb)
    data = service.list_packages()
    assert data["packages"][0]["package"] == "com.example.app"
    result = service.run_action("com.example.app", "disable", confirm=True)
    assert result["ok"] is False
    assert "Failure" in result["output"]
