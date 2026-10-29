import sys

import pytest

from gxr_profiler.core import naming, paths


def test_unicode_names_are_allowed():
    assert naming.validate_run_name("日本語 run") == "日本語 run"
    assert naming.validate_run_name("café-2") == "café-2"
    assert naming.base_label("café.csv") == "café"


@pytest.mark.parametrize(
    "name",
    ["a/b", "a\\b", "a:b", "a*b", "a?", "a.", "a ", "", ".hidden", "CON", "com1", "LPT9", "a" * 101],
)
def test_unsafe_names_are_rejected(name):
    with pytest.raises(ValueError):
        naming.validate_run_name(name)


def test_safe_filename_keeps_unicode():
    assert naming.safe_filename("café/日本") == "café_日本"
    assert naming.safe_filename("CON") == "run"


def test_writable_dir_and_readonly_error(tmp_path):
    target = tmp_path / "runs"
    assert paths.ensure_writable_dir(target) == str(target)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(OSError, match="not writable"):
        paths.ensure_writable_dir(blocker)


def test_frozen_defaults_next_to_exe(monkeypatch, tmp_path):
    exe = tmp_path / "gxr_profiler.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.runtime_dir() == tmp_path
    assert paths.default_runs_dir() == str(tmp_path / "runs")
    assert paths.default_reports_dir() == str(tmp_path / "reports")


def test_source_defaults_use_cwd(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.runtime_dir() == tmp_path


def test_run_name_rejects_reserved_suffixes():
    import pytest

    from gxr_profiler.core.naming import validate_run_name

    for name in ("foo.csv", "foo.CSV", "foo.events.csv", "foo.json"):
        with pytest.raises(ValueError):
            validate_run_name(name)
