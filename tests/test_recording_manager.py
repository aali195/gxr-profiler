from gxr_profiler.core.models import RunConfig
from gxr_profiler.server import recording


class _FakeRecorder:
    def __init__(self, adb, cfg, on_sample=None):
        self.adb = adb
        self.cfg = cfg

    def run(self):
        pass

    def stop(self):
        pass


def test_record_manager_waits_for_adb(monkeypatch, tmp_path):
    calls = []

    def fake_resolve(serial=None, **kwargs):
        calls.append(kwargs)
        return "fake"

    monkeypatch.setattr(recording, "resolve_serial", fake_resolve)
    monkeypatch.setattr(recording, "Recorder", _FakeRecorder)
    manager = recording.RecordManager(str(tmp_path))
    manager.start(RunConfig(name="run", out_dir=str(tmp_path), processes=False))
    try:
        assert calls == [
            {
                "wait_seconds": recording.CONNECT_WAIT_S,
                "poll_seconds": recording.CONNECT_POLL_S,
            }
        ]
    finally:
        manager.shutdown()
