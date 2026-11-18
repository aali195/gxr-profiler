import pytest

from gxr_profiler.core.apps import (
    APP_ACTION_SPECS,
    APP_ACTIONS,
    GAME_DOWNSCALE_VALUES,
    GAME_FPS_VALUES,
    build_action_command,
    build_app_rows,
    build_game_override_command,
    interpret_action_result,
    is_critical_package,
    merge_package_fallback,
    parse_du,
    parse_game_info,
    parse_package_detail,
    parse_package_lines,
    parse_package_paths,
    parse_process_usage,
    size_targets_for_rows,
    summarize,
    validate_package_name,
)
from gxr_profiler.core.parsers.util import split_sections
from tests.apps_fixtures import APP_LIST, DETAIL


def test_parse_package_lines_variants():
    parsed = parse_package_lines(
        "package:com.foo uid:10000 versionCode:9\n"
        "package:/data/app/com.foo/base.apk=com.foo\n"
        "package:com.bar installer=com.android.vending\n"
    )
    assert parsed["com.foo"]["uid"] == 10000
    assert parsed["com.foo"]["version_code"] == 9
    assert parsed["com.foo"]["apk_path"] == "/data/app/com.foo/base.apk"
    assert parsed["com.bar"]["installer"] == "com.android.vending"


def test_build_rows_classifies_system_user_disabled_removed_and_running():
    rows = build_app_rows(split_sections(APP_LIST))
    by_name = {row["package"]: row for row in rows}
    assert by_name["com.example.app"]["kind"] == "user"
    assert by_name["com.example.app"]["state"] == "enabled"
    assert by_name["com.example.app"]["running"] is True
    assert by_name["com.example.app"]["proc_count"] == 1
    assert by_name["com.example.app"]["cpu_pct"] == 12.5
    assert by_name["com.example.app"]["rss_kb"] == 2048
    assert by_name["com.example.app"]["gpu_mem_kb"] == 1024
    assert by_name["com.example.app"]["threads"] == 12
    assert by_name["com.example.app"]["oom_class"] == "cached"
    assert by_name["com.example.app"]["proc_names"] == ["com.example.app"]
    assert by_name["com.example.app"]["actions"] == ["disable", "uninstall"]
    assert by_name["com.android.systemui"]["kind"] == "system"
    assert by_name["com.android.systemui"]["critical"] is True
    assert by_name["com.android.systemui"]["actions"] == []
    assert by_name["com.samsung.stock"]["state"] == "disabled"
    assert by_name["com.samsung.stock"]["running"] is True
    assert by_name["com.samsung.stock"]["actions"] == ["enable", "remove_user"]
    assert by_name["com.removed.system"]["state"] == "removed"
    assert by_name["com.removed.system"]["actions"] == ["restore"]
    summary = summarize(rows)
    assert summary["total"] == 4
    assert summary["system"] == 3
    assert summary["user"] == 1
    assert summary["removed"] == 1
    assert summary["cpu_pct"] == 15.5
    assert summary["rss_kb"] == 6144
    assert summary["gpu_mem_kb"] == 3072
    assert summary["size_kb"] == 0


def test_missing_path_and_type_defaults_to_system_for_safety():
    sections = split_sections("###PACKAGES\npackage:com.mystery uid:1000\n")
    row = build_app_rows(sections)[0]
    assert row["kind"] == "system"
    assert "uninstall" not in row["actions"]


def test_critical_packages_cannot_be_disabled_or_removed():
    sections = split_sections(
        "###PACKAGES\npackage:com.android.systemui uid:1000\n"
        "###SYSTEM\npackage:com.android.systemui\n"
        "###DISABLED\npackage:com.android.systemui\n"
        "###PATH\npackage:/system/priv-app/SystemUI/SystemUI.apk=com.android.systemui\n"
    )
    row = build_app_rows(sections)[0]
    assert row["critical"] is True
    assert row["actions"] == ["enable"]
    assert "disable" not in row["actions"]
    assert "remove_user" not in row["actions"]


def test_updated_system_package_is_distinguished():
    sections = split_sections(
        "###PACKAGES\npackage:com.android.systemui uid:1000\n"
        "###SYSTEM\npackage:com.android.systemui\n"
        "###PATH\npackage:/data/app/com.android.systemui/base.apk=com.android.systemui\n"
    )
    row = build_app_rows(sections)[0]
    assert row["kind"] == "system-updated"


def test_package_fallback_merges_only_when_primary_list_is_empty():
    sections = split_sections("###PACKAGES\nError: Unknown option\n")
    merge_package_fallback(sections, "package:com.foo uid:10000\n")
    assert parse_package_lines("\n".join(sections["PACKAGES"]))["com.foo"]["uid"] == 10000
    existing = split_sections("###PACKAGES\npackage:com.bar uid:1\n")
    merge_package_fallback(existing, "package:com.foo uid:10000\n")
    assert "com.foo" not in parse_package_lines("\n".join(existing["PACKAGES"]))


def test_size_targets_use_data_app_directory_and_system_file():
    rows = [
        {"apk_path": "/data/app/~~abc/com.foo-1/base.apk"},
        {"apk_path": "/system/app/Foo/Foo.apk"},
    ]
    targets = size_targets_for_rows(rows)
    assert set(targets) == {"/data/app/~~abc/com.foo-1", "/system/app/Foo/Foo.apk"}
    assert targets["/data/app/~~abc/com.foo-1"] == [rows[0]]
    assert targets["/system/app/Foo/Foo.apk"] == [rows[1]]


def test_parse_paths_process_usage_and_du():
    usage = parse_process_usage(
        "  12.5% 123/com.foo: 10% user + 2.5% kernel\n   1.5% 456/com.foo:worker: 1% user + 0.5% kernel\n",
        "PID UID RSS NAME\n123 10000 2048 com.foo\n456 10000 1024 com.foo:worker\n",
        "/proc/123/stat:123 (com.foo) S 1 0 0 0 0 0 0 0 0 0 200 90 0 0 20 0 12 0 1001 0 0\n"
        "/proc/456/stat:456 (com.foo:worker) S 1 0 0 0 0 0 0 0 0 0 300 60 0 0 20 0 8 0 1002 0 0\n",
        "/proc/123/oom_score_adj:-800\n/proc/456/oom_score_adj:100\n",
        "Proc 123 total: 1048576\nProc 456 total: 2097152\n",
    )
    assert usage["com.foo"]["proc_count"] == 2
    assert usage["com.foo"]["cpu_pct"] == 14.0
    assert usage["com.foo"]["rss_kb"] == 3072
    assert usage["com.foo"]["gpu_mem_kb"] == 3072
    assert usage["com.foo"]["threads"] == 20
    assert usage["com.foo"]["oom_class"] == "system"
    assert usage["com.foo"]["proc_names"] == ["com.foo", "com.foo:worker"]
    assert parse_package_paths("package:/a/base.apk\npackage:/a/split.apk\n") == ["/a/base.apk", "/a/split.apk"]
    assert parse_du("10 /data/user/0/com.foo\n4 /data/user/0/com.foo/cache\n") == {
        "/data/user/0/com.foo": 10,
        "/data/user/0/com.foo/cache": 4,
    }


def test_parse_package_detail():
    detail = parse_package_detail(DETAIL, ["/data/app/base.apk"])
    assert detail["version_name"] == "1.2.3"
    assert detail["version_code"] == 42
    assert detail["min_sdk"] == 30
    assert detail["target_sdk"] == 34
    assert detail["code_path"].startswith("/data/app/")
    assert detail["data_dir"] == "/data/user/0/com.example.app"
    assert detail["installer"] == "com.android.vending"
    assert detail["first_install_time"] == "2025-01-02 03:04:05"
    assert detail["last_update_time"] == "2025-02-03 04:05:06"
    assert detail["primary_cpu_abi"] == "arm64-v8a"
    assert detail["flags"] == ["HAS_CODE", "ALLOW_CLEAR_USER_DATA", "ALLOW_BACKUP"]
    assert detail["requested_permissions_count"] == 2
    assert detail["user_states"][0]["installed"] is True
    assert detail["user_states"][0]["enabled"] == 0
    assert detail["apk_paths"] == ["/data/app/base.apk"]


def test_parse_game_info_and_commands():
    info = parse_game_info(
        "com.foo current mode: custom, available game modes: [standard,custom]",
        "com.foo interventions: \n"
        "[Name:com.foo Modes: {4=[Game Mode:4,Scaling:0.8,Use Angle:false,Fps:90,"
        "Loading Boost Duration:-1]}]",
    )
    assert info["supported"] is True
    assert info["current_mode"] == "custom"
    assert info["available_modes"] == ["standard", "custom"]
    assert info["fps"] == "90"
    assert info["downscale"] == "0.8"
    assert "FPS 90" in info["interventions"]
    assert "80%" in info["interventions"]

    assert build_game_override_command("com.foo", "90", "0.8") == "cmd game set --fps 90 --downscale 0.8 com.foo"
    assert build_game_override_command("com.foo", "disable", "0.8") == "cmd game set --downscale 0.8 com.foo"
    assert (
        build_game_override_command("com.foo", "90", "disable") == "cmd game set --fps 90 --downscale disable com.foo"
    )
    assert build_game_override_command("com.foo", "disable", "disable") == "cmd game reset com.foo"

    unsupported = parse_game_info(
        "com.foo current mode: unsupported, available game modes: []",
        "No intervention found for package com.foo",
    )
    assert unsupported["supported"] is False
    assert unsupported["fps"] == "disable"
    assert unsupported["downscale"] == "disable"

    assert "disable" in GAME_FPS_VALUES
    assert "0.8" in GAME_DOWNSCALE_VALUES
    with pytest.raises(ValueError):
        build_game_override_command("com.foo", "72", "0.8")
    with pytest.raises(ValueError):
        build_game_override_command("com.foo", "90", "0.55")


def test_validate_package_name_and_critical_packages():
    assert validate_package_name("com.example.app") == "com.example.app"
    assert validate_package_name("android") == "android"
    for bad in ("", "../evil", "com.foo; rm -rf /", "com..foo", "com.foo/bar"):
        with pytest.raises(ValueError):
            validate_package_name(bad)
    assert is_critical_package("com.android.systemui")
    assert is_critical_package("vendor.samsung.hardware.secxrcontroller@1.0-service")
    assert not is_critical_package("com.example.app")


def test_action_commands_and_result_interpretation():
    assert build_action_command("com.foo", "disable") == "pm disable-user --user 0 com.foo"
    assert build_action_command("com.foo", "enable") == "pm enable --user 0 com.foo"
    assert build_action_command("com.foo", "remove_user") == "pm uninstall --user 0 com.foo"
    assert build_action_command("com.foo", "restore") == "cmd package install-existing --user 0 com.foo"
    assert build_action_command("com.foo", "uninstall") == "pm uninstall com.foo"
    assert interpret_action_result("Success") == (True, "Success")
    assert interpret_action_result("Package com.foo new state: disabled-user", 0)[0] is True
    assert interpret_action_result("Failure [DELETE_FAILED_INTERNAL_ERROR]", 0)[0] is False
    assert interpret_action_result("Unexpected output", 0)[0] is False
    assert interpret_action_result("", 1)[0] is False


def test_action_specs_cover_all_actions():
    assert tuple(APP_ACTION_SPECS) == APP_ACTIONS
    for name, spec in APP_ACTION_SPECS.items():
        assert "{package}" in spec["command"]
        assert build_action_command("com.foo", name).startswith(spec["command"].split("{", 1)[0])
