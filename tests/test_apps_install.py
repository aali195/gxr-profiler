import hashlib
import json
import time
import uuid
import zipfile

import pytest

from gxr_profiler.core.apps import format_adb_command
from gxr_profiler.server.app_install import InstallManager

from .install_fixtures import FakeInstallAdb, build_apk, build_xapk


def _manager(tmp_path, adb, busy_check=None):
    return InstallManager(
        serial="fake",
        reports_dir=str(tmp_path / "reports"),
        staging_dir=str(tmp_path / "staging"),
        busy_check=busy_check,
        adb_factory=lambda serial=None: adb,
    )


def _stage(manager, name, data, relative=""):
    source = manager.upload_dir / (uuid.uuid4().hex + ".part")
    source.write_bytes(data)
    result = manager.accept_upload(
        source,
        name,
        relative,
        hashlib.sha256(data).hexdigest(),
        len(data),
    )
    return result["files"]


def _wait(manager, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.status(job_id)
        if job["status"] != "running":
            return job
        time.sleep(0.01)
    raise AssertionError("install job did not finish")


def test_install_command_display_quotes_windows_paths():
    command = format_adb_command(["install", "-r", "--user", "0", r"C:\Path With Space\base.apk"])
    assert command == r'adb install -r --user 0 "C:\Path With Space\base.apk"'
    assert (
        format_adb_command(["shell", "mkdir", "-p", "/sdcard/Android/obb/com.example"])
        == "adb shell mkdir -p /sdcard/Android/obb/com.example"
    )


def test_preview_and_install_apk_with_obb(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    apk_file = _stage(manager, "base.apk", apk, "base.apk")[0]
    obb_name = "main.123.com.example.game.obb"
    obb_file = _stage(
        manager,
        obb_name,
        b"OBB!",
        f"Android/obb/com.example.game/{obb_name}",
    )[0]

    plan = manager.preview([apk_file["id"], obb_file["id"]], {}, {})
    assert plan["ok"] is True
    assert plan["errors"] == []
    assert plan["groups"][0]["package"] == "com.example.game"
    assert plan["groups"][0]["command"].startswith("adb install -r --user 0")
    assert plan["obb"][0]["remote_path"] == f"/sdcard/Android/obb/com.example.game/{obb_name}"
    assert plan["obb"][0]["mkdir_command"].startswith("adb shell mkdir -p")

    job = manager.start([apk_file["id"], obb_file["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "done"
    assert result["result"]["packages"] == ["com.example.game"]
    assert result["result"]["obb_count"] == 1
    assert any(call[0] == "install" for call in adb.calls)
    assert any(call[0] == "push" for call in adb.calls)
    assert manager.list_staged() == []

    log_path = tmp_path / "reports" / "app-actions.jsonl"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["action"] == "install"
    assert entry["ok"] is True
    assert entry["package"] == "com.example.game"
    assert len(entry["files"]) == 2


def test_split_apks_use_install_multiple(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    base = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    split = build_apk(
        tmp_path / "split.apk",
        "com.example.game",
        version_code=123,
        split="config.arm64_v8a",
    ).read_bytes()
    base_file = _stage(manager, "base.apk", base)[0]
    split_file = _stage(manager, "split_config.arm64_v8a.apk", split)[0]

    plan = manager.preview([base_file["id"], split_file["id"]], {}, {})
    assert plan["ok"] is True
    group = plan["groups"][0]
    assert group["apk_count"] == 2
    assert group["split"] is True
    assert group["command"].startswith("adb install-multiple -r --user 0")


def test_install_options_change_flags(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game").read_bytes()
    item = _stage(manager, "base.apk", apk)[0]

    plan = manager.preview(
        [item["id"]],
        {},
        {"replace": False, "allow_downgrade": True, "grant_permissions": True},
    )
    command = plan["groups"][0]["command"]
    assert " -r " not in command
    assert " -d " in command
    assert " -g " in command


def test_obb_package_can_be_supplied_for_nonstandard_name(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    item = _stage(manager, "game.obb", b"OBB!")[0]
    assert item["package"] == ""
    assert item["warnings"]

    plan = manager.preview([item["id"]], {}, {})
    assert plan["ok"] is False
    assert any("choose the target package" in error for error in plan["errors"])

    plan = manager.preview([item["id"]], {item["id"]: "com.example.game"}, {})
    assert plan["ok"] is True
    assert plan["obb"][0]["package"] == "com.example.game"


def test_obb_requires_the_package_to_be_installed(tmp_path):
    adb = FakeInstallAdb(installed=False)
    manager = _manager(tmp_path, adb)
    item = _stage(
        manager,
        "main.123.com.example.game.obb",
        b"OBB!",
        "Android/obb/com.example.game/main.123.com.example.game.obb",
    )[0]
    plan = manager.preview([item["id"]], {}, {})
    assert plan["ok"] is False
    assert any("is not installed" in error for error in plan["errors"])


def test_critical_package_install_is_blocked(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "systemui.apk", "com.android.systemui").read_bytes()
    item = _stage(manager, "systemui.apk", apk)[0]
    plan = manager.preview([item["id"]], {}, {})
    assert plan["ok"] is False
    assert any("critical system package" in error for error in plan["errors"])


def test_unreadable_apk_is_blocked(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    item = _stage(manager, "broken.apk", b"not a zip")[0]
    assert item["readable"] is False
    plan = manager.preview([item["id"]], {}, {})
    assert plan["ok"] is False
    assert any("not a readable APK" in error for error in plan["errors"])


def test_xapk_stages_bundle_and_obb(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    obb_name = "main.123.com.example.game.obb"
    path = build_xapk(
        tmp_path / "game.xapk",
        "com.example.game",
        version_code=123,
        obb_name=obb_name,
    )
    result = _stage(manager, "game.xapk", path.read_bytes())
    assert len(result) == 3
    assert {item["kind"] for item in result} == {"apk", "obb"}
    assert len({item["bundle_id"] for item in result}) == 1
    assert all(item["bundle_name"] == "game.xapk" for item in result)
    assert all(item["package"] == "com.example.game" for item in result)

    plan = manager.preview([item["id"] for item in result], {}, {})
    assert plan["ok"] is True
    assert plan["groups"][0]["apk_count"] == 2
    assert plan["obb"][0]["name"] == obb_name

    manager.discard(result[0]["id"])
    assert manager.list_staged() == []


def test_xapk_rejects_zip_slip(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    path = tmp_path / "evil.xapk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("../evil.apk", b"not an apk")
    with pytest.raises(ValueError, match="unsafe path"):
        _stage(manager, "evil.xapk", path.read_bytes())
    assert manager.list_staged() == []


def test_failed_install_keeps_staged_files(tmp_path):
    adb = FakeInstallAdb(fail_install=True)
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game").read_bytes()
    item = _stage(manager, "base.apk", apk)[0]

    job = manager.start([item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "INSTALL_FAILED" in result["error"]
    assert len(manager.list_staged()) == 1

    log_path = tmp_path / "reports" / "app-actions.jsonl"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["action"] == "install"
    assert entry["ok"] is False


def test_install_detects_error_output_with_zero_returncode(tmp_path):
    adb = FakeInstallAdb(install_output="Error: package manager rejected the install\n", install_returncode=0)
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    item = _stage(manager, "base.apk", apk)[0]
    job = manager.start([item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "package manager rejected" in result["error"]


def test_install_verifies_the_installed_version(tmp_path):
    adb = FakeInstallAdb(reported_version=999)
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    item = _stage(manager, "base.apk", apk)[0]
    job = manager.start([item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "versionCode 999" in result["error"]
    assert "expected 123" in result["error"]
    assert len(manager.list_staged()) == 1


def test_install_fails_when_version_cannot_be_verified(tmp_path):
    adb = FakeInstallAdb(dumpsys_output="")
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    item = _stage(manager, "base.apk", apk)[0]
    job = manager.start([item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "could not verify versionCode 123" in result["error"]


def test_obb_push_failure_keeps_staged_files(tmp_path):
    adb = FakeInstallAdb(fail_push=True)
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    apk_item = _stage(manager, "base.apk", apk)[0]
    obb_name = "main.123.com.example.game.obb"
    obb_item = _stage(manager, obb_name, b"OBB!", f"Android/obb/com.example.game/{obb_name}")[0]
    job = manager.start([apk_item["id"], obb_item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "failed to copy" in result["error"]
    assert len(manager.list_staged()) == 2


def test_obb_size_mismatch_fails_the_install(tmp_path):
    adb = FakeInstallAdb(stat_size=999)
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    apk_item = _stage(manager, "base.apk", apk)[0]
    obb_name = "main.123.com.example.game.obb"
    obb_item = _stage(manager, obb_name, b"OBB!", f"Android/obb/com.example.game/{obb_name}")[0]
    job = manager.start([apk_item["id"], obb_item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "device has 999 bytes" in result["error"]
    assert len(manager.list_staged()) == 2


def test_obb_unverifiable_size_fails_the_install(tmp_path):
    adb = FakeInstallAdb(stat_output="stat: unknown option\n")
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    apk_item = _stage(manager, "base.apk", apk)[0]
    obb_name = "main.123.com.example.game.obb"
    obb_item = _stage(manager, obb_name, b"OBB!", f"Android/obb/com.example.game/{obb_name}")[0]
    job = manager.start([apk_item["id"], obb_item["id"]], {}, {}, confirm=True)
    result = _wait(manager, job["id"])
    assert result["status"] == "error"
    assert "could not verify the remote file" in result["error"]
    assert len(manager.list_staged()) == 2


def test_preview_enforces_the_file_limit(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    with pytest.raises(ValueError, match="limit is 64"):
        manager.preview([str(index) for index in range(65)], {}, {})


def test_staged_files_cannot_be_removed_during_an_install(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    apk = build_apk(tmp_path / "base.apk", "com.example.game", version_code=123).read_bytes()
    item = _stage(manager, "base.apk", apk)[0]
    manager._job = {"id": "running-job", "status": "running"}
    with pytest.raises(RuntimeError, match="install is running"):
        manager.discard(item["id"])
    with pytest.raises(RuntimeError, match="install is running"):
        manager.clear()


def test_recording_and_confirmation_block_install(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb, busy_check=lambda: True)
    apk = build_apk(tmp_path / "base.apk", "com.example.game").read_bytes()
    item = _stage(manager, "base.apk", apk)[0]
    with pytest.raises(ValueError, match="confirmation"):
        manager.start([item["id"]], {}, {}, confirm=False)
    with pytest.raises(PermissionError, match="recording"):
        manager.start([item["id"]], {}, {}, confirm=True)


def test_upload_name_validation(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    with pytest.raises(ValueError):
        manager.validate_upload("setup.exe")
    with pytest.raises(ValueError):
        manager.validate_upload("../evil.apk")
    with pytest.raises(ValueError):
        manager.validate_upload("evil.apk.exe")
    assert manager.validate_upload("game.apk") == "game.apk"


def test_expired_staged_files_are_rejected(tmp_path):
    adb = FakeInstallAdb()
    manager = _manager(tmp_path, adb)
    with pytest.raises(ValueError, match="expired"):
        manager.preview(["missing"], {}, {})
