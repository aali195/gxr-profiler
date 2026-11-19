import pytest

from gxr_tools.manager.cli import app as manager_cli
from gxr_tools.manager.server import app as manager_server


def test_manager_windowed_entry_accepts_argv(monkeypatch):
    calls = []
    monkeypatch.setattr(manager_server, "run_ui", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(SystemExit):
        manager_cli.main(["ui"])

    assert calls == [{"port": 8766, "browser": False, "serial": None}]
