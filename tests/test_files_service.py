import json

import pytest

from gxr_tools.manager.core.file_errors import (
    ConfirmationRequired,
    DeviceBusy,
    FileConflict,
    FileMissing,
    FilesUnavailable,
    InvalidPath,
    PathDenied,
    RecursiveDeleteRequired,
    RootDenied,
)
from gxr_tools.manager.server.files import FilesService

from .file_fixtures import FakeFileAdb


def make_service(tmp_path, adb, root=False, busy=None):
    service = FilesService(
        serial="fake",
        reports_dir=str(tmp_path / "reports"),
        adb_factory=lambda **kwargs: adb,
        busy_check=busy,
        staging_dir=str(tmp_path / "staging"),
    )
    if root:
        service.set_root(True)
    return service


def test_list_dir_returns_entries_and_state(tmp_path):
    adb = FakeFileAdb()
    service = make_service(tmp_path, adb)
    result = service.list_dir("/sdcard")
    assert result["path"] == "/sdcard"
    assert result["parent"] == "/"
    assert result["writable"] is True
    assert result["root"] is False
    assert [entry["name"] for entry in result["entries"]] == [
        "Alarms",
        "Galaxy XR Haptics.zip",
        "shortcut",
    ]
    assert "ls -lAN -- /sdcard/" in adb.shell_calls


def test_list_dir_reports_permission_denied(tmp_path):
    service = make_service(tmp_path, FakeFileAdb(permission_denied=True))
    with pytest.raises(PathDenied):
        service.list_dir("/private")


def test_blocked_while_recording(tmp_path):
    service = make_service(tmp_path, FakeFileAdb(), busy=lambda: True)
    with pytest.raises(DeviceBusy):
        service.list_dir("/sdcard")


def test_download_streams_binary_data(tmp_path):
    adb = FakeFileAdb(data=b"\x00\x01binary")
    adb.files["/sdcard/test.bin"] = 9
    service = make_service(tmp_path, adb)
    stream, info, name = service.download("/sdcard/test.bin")
    assert b"".join(stream) == b"\x00\x01binary"
    assert info["size"] == 9
    assert name == "test.bin"


def test_download_rejects_directory(tmp_path):
    adb = FakeFileAdb()
    adb.dirs.add("/sdcard/DCIM")
    service = make_service(tmp_path, adb)
    with pytest.raises(InvalidPath):
        service.download("/sdcard/DCIM")


def test_upload_pushes_to_temp_then_moves(tmp_path):
    adb = FakeFileAdb()
    local = tmp_path / "photo.jpg"
    local.write_bytes(b"hello")
    service = make_service(tmp_path, adb)
    result = service.upload(str(local), "/sdcard", "photo.jpg")
    assert result["path"] == "/sdcard/photo.jpg"
    assert adb.run_calls[0][0] == "push"
    assert adb.run_calls[0][2].startswith("/sdcard/.gxr-upload-")
    assert adb.files["/sdcard/photo.jpg"] == 5
    log_path = tmp_path / "reports" / "file-actions.jsonl"
    assert log_path.exists()
    assert json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])["action"] == "upload"


def test_upload_outside_shared_storage_requires_root(tmp_path):
    adb = FakeFileAdb()
    adb.dirs.add("/data/local")
    local = tmp_path / "x.txt"
    local.write_bytes(b"x")
    service = make_service(tmp_path, adb)
    with pytest.raises(PathDenied):
        service.upload(str(local), "/data/local", "x.txt")


def test_upload_with_root_uses_tmp_then_moves(tmp_path):
    adb = FakeFileAdb()
    adb.dirs.add("/data/local")
    local = tmp_path / "x.txt"
    local.write_bytes(b"rooted")
    service = make_service(tmp_path, adb, root=True)
    service.upload(str(local), "/data/local", "x.txt")
    assert adb.run_calls[0][2].startswith("/data/local/tmp/gxr-upload-")
    assert adb.files["/data/local/x.txt"] == 6


def test_upload_conflict_requires_overwrite(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/photo.jpg"] = 5
    local = tmp_path / "photo.jpg"
    local.write_bytes(b"hello")
    service = make_service(tmp_path, adb)
    with pytest.raises(FileConflict):
        service.upload(str(local), "/sdcard", "photo.jpg")
    service.upload(str(local), "/sdcard", "photo.jpg", overwrite=True)


def test_set_root_checks_uid(tmp_path):
    service = make_service(tmp_path, FakeFileAdb(root_ok=False))
    with pytest.raises(RootDenied):
        service.set_root(True)
    assert service.root_enabled is False


def test_mkdir_and_conflict(tmp_path):
    adb = FakeFileAdb()
    service = make_service(tmp_path, adb)
    service.mkdir("/sdcard", "New")
    assert "/sdcard/New" in adb.dirs
    with pytest.raises(FileConflict):
        service.mkdir("/sdcard", "New")


def test_rename_and_conflict(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/a.txt"] = 1
    service = make_service(tmp_path, adb)
    service.rename("/sdcard/a.txt", "b.txt")
    assert "/sdcard/b.txt" in adb.files
    adb.files["/sdcard/c.txt"] = 1
    with pytest.raises(FileConflict):
        service.rename("/sdcard/b.txt", "c.txt")


def test_move_and_into_self(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/a.txt"] = 1
    adb.dirs.add("/sdcard/Download")
    service = make_service(tmp_path, adb)
    results = service.move(["/sdcard/a.txt"], "/sdcard/Download")
    assert results[0]["ok"] is True
    assert "/sdcard/Download/a.txt" in adb.files
    with pytest.raises(InvalidPath):
        service.move(["/sdcard/Download"], "/sdcard/Download")


def test_delete_requires_recursion_for_folders(tmp_path):
    adb = FakeFileAdb()
    adb.dirs.add("/sdcard/DCIM")
    service = make_service(tmp_path, adb)
    with pytest.raises(RecursiveDeleteRequired):
        service.delete(["/sdcard/DCIM"])
    results = service.delete(["/sdcard/DCIM"], recursive=True)
    assert results[0]["ok"] is True
    assert "/sdcard/DCIM" not in adb.dirs


def test_root_delete_requires_typed_confirmation(tmp_path):
    adb = FakeFileAdb()
    adb.files["/data/local/tmp/x"] = 1
    service = make_service(tmp_path, adb, root=True)
    with pytest.raises(ConfirmationRequired):
        service.delete(["/data/local/tmp/x"])
    service.delete(["/data/local/tmp/x"], confirm_text="DELETE")
    assert "/data/local/tmp/x" not in adb.files


def test_protected_paths_cannot_be_deleted(tmp_path):
    service = make_service(tmp_path, FakeFileAdb(), root=True)
    with pytest.raises(PathDenied):
        service.delete(["/system"], recursive=True, confirm_text="DELETE")


def test_cleanup_removes_staging_files(tmp_path):
    service = make_service(tmp_path, FakeFileAdb())
    temp = tmp_path / "staging" / "upload-1.part"
    temp.write_bytes(b"x")
    service.cleanup()
    assert not temp.exists()


def test_upload_rejects_folder_with_same_name(tmp_path):
    adb = FakeFileAdb()
    adb.dirs.add("/sdcard/photo.jpg")
    local = tmp_path / "photo.jpg"
    local.write_bytes(b"hello")
    service = make_service(tmp_path, adb)
    with pytest.raises(FileConflict):
        service.upload(str(local), "/sdcard", "photo.jpg")


def test_paths_with_spaces_are_quoted(tmp_path):
    adb = FakeFileAdb()
    service = make_service(tmp_path, adb)
    service.list_dir("/sdcard/My Files")
    assert "ls -lAN -- '/sdcard/My Files/'" in adb.shell_calls
    service.mkdir("/sdcard", "New Folder")
    assert "/sdcard/New Folder" in adb.dirs


def test_symlink_download_reports_target_size(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/target.bin"] = 16
    adb.links["/sdcard/link.bin"] = "/sdcard/target.bin"
    service = make_service(tmp_path, adb)
    stream, info, name = service.download("/sdcard/link.bin")
    assert info["size"] == 16
    assert name == "link.bin"
    b"".join(stream)


def test_move_overwrite_rejects_folder_target(tmp_path):
    adb = FakeFileAdb()
    adb.dirs.update({"/sdcard/src", "/sdcard/dst", "/sdcard/dst/a.txt"})
    adb.files["/sdcard/src/a.txt"] = 1
    service = make_service(tmp_path, adb)
    with pytest.raises(FileConflict):
        service.move(["/sdcard/src/a.txt"], "/sdcard/dst", overwrite=True)


def test_upload_size_mismatch_keeps_existing_target(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/photo.jpg"] = 5
    local = tmp_path / "photo.jpg"
    local.write_bytes(b"hello")
    adb.push_size_override = 3
    service = make_service(tmp_path, adb)
    with pytest.raises(FilesUnavailable):
        service.upload(str(local), "/sdcard", "photo.jpg", overwrite=True)
    assert adb.files["/sdcard/photo.jpg"] == 5


def test_listing_accepts_file_named_permission_denied(tmp_path):
    adb = FakeFileAdb(listing="total 1\n-rw-rw---- 1 u media_rw 0 2026-11-20 00:00 Permission denied\n")
    service = make_service(tmp_path, adb)
    result = service.list_dir("/sdcard")
    assert result["entries"][0]["name"] == "Permission denied"


def test_download_ticket_is_one_use(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/a.bin"] = 10
    service = make_service(tmp_path, adb)
    ticket = service.create_download_ticket("/sdcard/a.bin")
    stream, info, name = service.consume_download_ticket(ticket["ticket"])
    assert b"".join(stream) == b"file-bytes"
    assert info["size"] == 10
    assert name == "a.bin"
    with pytest.raises(FileMissing):
        service.consume_download_ticket(ticket["ticket"])


def test_download_ticket_expires(tmp_path):
    adb = FakeFileAdb()
    adb.files["/sdcard/a.bin"] = 10
    service = make_service(tmp_path, adb)
    ticket = service.create_download_ticket("/sdcard/a.bin")
    service._download_tickets[ticket["ticket"]]["expires"] = 0
    with pytest.raises(FileMissing):
        service.consume_download_ticket(ticket["ticket"])
