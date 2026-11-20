from gxr_tools.manager.core.file_entries import parse_ls_listing


def test_parse_listing_keeps_spaces_and_symlinks():
    text = """total 12
drwxrws--- 2 u0_a236 media_rw 3452 2026-11-16 22:16 Alarms
-rwxrwx--- 1 u0_a236 media_rw 241898 2026-10-19 20:52 Galaxy XR Haptics.zip
lrwxrwxrwx 1 root root 21 2008-12-31 15:00 shortcut -> /sdcard/Download
"""
    entries = parse_ls_listing(text, "/sdcard")
    assert [entry.name for entry in entries] == [
        "Alarms",
        "Galaxy XR Haptics.zip",
        "shortcut",
    ]
    assert entries[0].kind == "dir"
    assert entries[1].kind == "file"
    assert entries[1].size == 241898
    assert entries[1].modified == "2026-10-19 20:52"
    assert entries[2].kind == "link"
    assert entries[2].target == "/sdcard/Download"
    assert entries[2].path == "/sdcard/shortcut"


def test_parse_listing_hides_upload_temps():
    text = """total 1
-rw-rw---- 1 u0_a236 media_rw 10 2026-11-20 00:00 .gxr-upload-abc
-rw-rw---- 1 u0_a236 media_rw 10 2026-11-20 00:00 keep.txt
"""
    entries = parse_ls_listing(text, "/sdcard")
    assert [entry.name for entry in entries] == ["keep.txt"]


def test_parse_listing_skips_errors_and_junk():
    text = """ls: /private: Permission denied
total 1
not a real row
"""
    assert parse_ls_listing(text, "/sdcard") == []
