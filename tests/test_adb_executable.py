import os

from gxr_core.adb import resolve_adb_executable


def _name() -> str:
    return "adb.exe" if os.name == "nt" else "adb"


def test_adb_env_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("ADB", "custom-adb")
    (tmp_path / _name()).write_text("", encoding="utf-8")
    assert resolve_adb_executable(tmp_path) == "custom-adb"


def test_adb_directly_next_to_runtime(monkeypatch, tmp_path):
    monkeypatch.delenv("ADB", raising=False)
    direct = tmp_path / _name()
    direct.write_text("", encoding="utf-8")
    assert resolve_adb_executable(tmp_path) == str(direct)


def test_platform_tools_fallback_and_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv("ADB", raising=False)
    platform_tools = tmp_path / "platform-tools"
    platform_tools.mkdir()
    fallback = platform_tools / _name()
    fallback.write_text("", encoding="utf-8")
    assert resolve_adb_executable(tmp_path) == str(fallback)

    direct = tmp_path / _name()
    direct.write_text("", encoding="utf-8")
    assert resolve_adb_executable(tmp_path) == str(direct)


def test_adb_path_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("ADB", raising=False)
    assert resolve_adb_executable(tmp_path) == "adb"
