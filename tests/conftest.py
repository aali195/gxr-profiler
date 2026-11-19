import pytest


@pytest.fixture(autouse=True)
def _isolate_shared_state(tmp_path, monkeypatch):
    """Keep recording-state/heartbeat files out of the repository."""
    monkeypatch.setenv("GXR_STATE_DIR", str(tmp_path / "gxr-state"))
