import threading

from gxr_tools.core.recording_state import read_state
from gxr_tools.profiler.core.models import RunConfig
from gxr_tools.profiler.server import recording


class _FakeRecorder:
    def __init__(self, adb, cfg, on_sample=None):
        self.adb = adb
        self.cfg = cfg
        self.stopped = False

    def run(self):
        pass

    def stop(self):
        self.stopped = True


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


class _BlockingRecorder(_FakeRecorder):
    def __init__(self, adb, cfg, on_sample=None):
        super().__init__(adb, cfg, on_sample)
        self.release = threading.Event()

    def run(self):
        self.release.wait(5.0)

    def stop(self):
        self.stopped = True
        self.release.set()


def test_record_manager_holds_the_shared_marker_until_shutdown(monkeypatch, tmp_path):
    monkeypatch.setattr(recording, "resolve_serial", lambda serial=None, **kwargs: "fake")
    monkeypatch.setattr(recording, "Recorder", _BlockingRecorder)
    manager = recording.RecordManager(str(tmp_path))
    manager.start(RunConfig(name="marker-run", out_dir=str(tmp_path), processes=False))
    try:
        state = read_state()
        assert state["active"] is True
        assert state["status"] == "recording"
        assert state["label"] == "marker-run"
    finally:
        manager.shutdown()
    assert read_state()["active"] is False


def test_record_manager_keeps_final_elapsed(monkeypatch, tmp_path):
    class _TimedRecorder(_BlockingRecorder):
        recording_elapsed_s = 2.5

    monkeypatch.setattr(recording, "resolve_serial", lambda serial=None, **kwargs: "fake")
    monkeypatch.setattr(recording, "Recorder", _TimedRecorder)
    manager = recording.RecordManager(str(tmp_path))
    manager.start(RunConfig(name="timed-run", out_dir=str(tmp_path), processes=False))
    try:
        assert manager.state()["elapsed"] == 0.0
    finally:
        manager.shutdown()
    assert manager.state()["elapsed"] == 2.5
