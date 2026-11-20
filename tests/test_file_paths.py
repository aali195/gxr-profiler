import pytest

from gxr_tools.manager.core.file_errors import InvalidName, InvalidPath, PathDenied
from gxr_tools.manager.core.file_paths import (
    basename,
    ensure_mutable,
    ensure_not_within,
    ensure_writable,
    is_protected,
    is_within,
    join_path,
    normalize_path,
    parent_path,
    validate_name,
    writable_without_root,
)


def test_normalize_path():
    assert normalize_path("/sdcard/../Download") == "/Download"
    assert normalize_path("//sdcard/") == "/sdcard"
    assert normalize_path("/") == "/"


@pytest.mark.parametrize("value", ["", "sdcard", "/bad\npath", "/bad\x00path"])
def test_normalize_path_rejects_bad_values(value):
    with pytest.raises(InvalidPath):
        normalize_path(value)


def test_validate_name():
    assert validate_name("Galaxy XR Haptics.zip") == "Galaxy XR Haptics.zip"
    for value in ["", ".", "..", "a/b", "a\\b", "a\nb"]:
        with pytest.raises(InvalidName):
            validate_name(value)


def test_join_and_parent():
    assert join_path("/sdcard", "Download") == "/sdcard/Download"
    assert parent_path("/sdcard/Download") == "/sdcard"
    assert parent_path("/") is None
    assert basename("/sdcard/Download/file.txt") == "file.txt"


def test_protected_roots_and_shared_writes():
    for path in [
        "/",
        "/system",
        "/system/etc",
        "/data",
        "/data/system",
        "/data/app/x",
        "/data/user",
        "/data/user_de",
        "/data/local",
        "/data/dalvik-cache",
        "/data/tombstones",
        "/data/media",
        "/proc/1",
    ]:
        assert is_protected(path), path
    assert not is_protected("/sdcard/Download")
    assert not is_protected("/data/local/tmp/gxr.txt")
    assert not is_protected("/data/media/0/Download")
    assert writable_without_root("/sdcard/Download")
    assert writable_without_root("/data/local/tmp/x")
    assert not writable_without_root("/data/system/x")


def test_ensure_mutable_and_writable():
    with pytest.raises(PathDenied):
        ensure_mutable("/system/bin/sh")
    with pytest.raises(PathDenied):
        ensure_writable("/data/system/x", root=False)
    ensure_writable("/data/system/x", root=True)


def test_is_within():
    assert is_within("/sdcard/Download", "/sdcard")
    assert is_within("/sdcard", "/sdcard")
    assert not is_within("/sdcard2/file", "/sdcard")
    with pytest.raises(InvalidPath):
        ensure_not_within("/sdcard/A/B", "/sdcard/A")
