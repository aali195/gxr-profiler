import json
import os

import pytest

from gxr_profiler.capture.recorder import Recorder
from gxr_profiler.capture.writer import RunWriter
from gxr_profiler.core.models import RunConfig
from tests.fake_adb import FakeAdb


def test_writer_rejects_path_separators(tmp_path):
    with pytest.raises(ValueError):
        RunWriter(str(tmp_path), "../evil")


def test_writer_refuses_existing_run(tmp_path):
    (tmp_path / "dup").mkdir()
    with pytest.raises(FileExistsError):
        RunWriter(str(tmp_path), "dup")


def test_recorder_writes_run(tmp_path):
    adb = FakeAdb()
    cfg = RunConfig(name="smoke", out_dir=str(tmp_path), duration=0.3, interval=0.05, logcat=False)
    rec = Recorder(adb, cfg)
    path = rec.run()

    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().strip().splitlines()
    assert len(lines) >= 2  # header + at least one row

    meta_path = os.path.join(tmp_path, "smoke", "meta.json")
    meta = json.loads(open(meta_path, encoding="utf-8").read())
    assert meta["schema_version"] >= 2
    assert meta["features"]["logcat"] is False
    assert meta["device_info"]["model"] == "SM-I610"
    assert meta["rows"] >= 1
    assert os.path.exists(os.path.join(tmp_path, "smoke", "data.csv"))
    assert meta["recording_started"]
    assert meta["recording_started"] >= meta["started"]


def test_cooldown_uses_selected_sensor(tmp_path, monkeypatch):
    adb = FakeAdb()
    cfg = RunConfig(
        name="cooldown",
        out_dir=str(tmp_path),
        cooldown_below=35.0,
        cooldown_sensor="CPU5",
        logcat=False,
    )
    rec = Recorder(adb, cfg)
    values = iter([40.0, 34.0])
    monkeypatch.setattr(rec.poller, "poll_thermal", lambda: {"t_CPU5": next(values), "t_AP": 20.0})
    monkeypatch.setattr("gxr_profiler.capture.recorder.time.sleep", lambda _seconds: None)
    messages = []
    rec.on_status = messages.append

    rec._cooldown()

    assert any("CPU5: 40.0" in message for message in messages)
    assert any("Baseline reached (34.0 C)" in message for message in messages)


def test_invalid_cooldown_sensor_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown cooldown sensor"):
        RunConfig(name="bad-sensor", out_dir=str(tmp_path), cooldown_sensor="BOGUS")


def test_writer_ignores_flat_files(tmp_path):
    (tmp_path / "orphan.events.csv").write_text("ts_host\n", encoding="utf-8")
    writer = RunWriter(str(tmp_path), "orphan")
    writer.open()
    writer.close()
    assert (tmp_path / "orphan" / "data.csv").exists()


def test_auxiliary_intervals_must_be_positive(tmp_path):
    for field in ("media_interval", "state_interval", "radio_interval", "sensors_interval", "processes_interval"):
        with pytest.raises(ValueError, match=field):
            RunConfig(name="bad-interval", out_dir=str(tmp_path), **{field: 0})
