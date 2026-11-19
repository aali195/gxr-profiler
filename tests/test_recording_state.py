import json
from datetime import UTC, datetime, timedelta

from gxr_core.recording_state import (
    RecordingMarker,
    is_recording,
    read_state,
    state_path,
    write_state,
)


def test_marker_writes_active_and_inactive_state(tmp_path):
    marker = RecordingMarker(path=tmp_path)
    marker.start("benchmark")
    active = read_state(tmp_path)
    assert active["active"] is True
    assert active["stale"] is False
    assert active["label"] == "benchmark"
    assert active["status"] == "recording"
    assert is_recording(tmp_path) is True

    marker.stop(status="done")
    inactive = read_state(tmp_path)
    assert inactive["active"] is False
    assert inactive["stale"] is False
    assert inactive["status"] == "done"
    assert is_recording(tmp_path) is False


def test_stale_active_marker_is_ignored(tmp_path):
    old = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    write_state(
        True,
        label="crashed-run",
        status="recording",
        started_at=old,
        updated_at=old,
        path=tmp_path,
    )
    state = read_state(tmp_path)
    assert state["active"] is False
    assert state["stale"] is True
    assert state["label"] == "crashed-run"
    assert is_recording(tmp_path) is False


def test_missing_or_invalid_state_is_inactive(tmp_path):
    assert read_state(tmp_path)["active"] is False
    state_path(tmp_path).write_text("{not json", encoding="utf-8")
    state = read_state(tmp_path)
    assert state["active"] is False
    assert state["stale"] is False


def test_state_file_shape(tmp_path):
    write_state(
        True,
        label="run",
        status="recording",
        started_at="2026-01-01T00:00:00+00:00",
        updated_at=datetime.now(UTC).isoformat(),
        token="abc",
        path=tmp_path,
    )
    payload = json.loads(state_path(tmp_path).read_text(encoding="utf-8"))
    assert payload["active"] is True
    assert payload["label"] == "run"
    assert payload["pid"] > 0
    assert payload["token"] == "abc"
    assert payload["started_at"] == "2026-01-01T00:00:00+00:00"


def test_stopping_an_older_marker_keeps_the_newer_recording(tmp_path):
    first = RecordingMarker(path=tmp_path)
    first.start("first")
    second = RecordingMarker(path=tmp_path)
    second.start("second")
    try:
        first.stop(status="done")
        state = read_state(tmp_path)
        assert state["active"] is True
        assert state["label"] == "second"
    finally:
        second.stop(status="done")
    assert read_state(tmp_path)["active"] is False
