from fastapi.testclient import TestClient

from gxr_core.recording_state import clear_state, write_state
from gxr_manager.server.app import create_manager_app
from gxr_profiler.server.app import create_app


def test_profiler_and_manager_route_surfaces_are_separate(tmp_path):
    profiler = TestClient(create_app(str(tmp_path / "runs"), serial="fake"))
    manager = TestClient(create_manager_app(serial="fake"))

    assert profiler.get("/api/runs").status_code == 200
    assert profiler.get("/api/apps").status_code == 404
    assert profiler.get("/api/settings").status_code == 404
    assert profiler.get("/api/debug/status").status_code == 404
    assert profiler.get("/api/apps/install/state").status_code == 404

    assert manager.get("/api/runs").status_code == 404
    assert manager.get("/api/record/status").status_code == 404
    assert manager.get("/api/spec").status_code == 404
    assert manager.get("/api/apps").status_code != 404
    assert manager.get("/api/recording").status_code == 200


def test_manager_recording_status_route():
    manager = TestClient(create_manager_app(serial="fake"))
    write_state(True, label="route-test")
    state = manager.get("/api/recording")
    assert state.status_code == 200
    assert state.json()["active"] is True
    assert state.json()["label"] == "route-test"
    clear_state()
    assert manager.get("/api/recording").json()["active"] is False
