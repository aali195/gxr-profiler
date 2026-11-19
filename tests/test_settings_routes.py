import re

from fastapi.testclient import TestClient

from gxr_tools.core.adb import AdbError
from gxr_tools.core.recording_state import write_state
from gxr_tools.manager.server.app import create_manager_app
from gxr_tools.manager.server.deps import get_settings_service


def _token(client):
    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


class FakeSettings:
    def __init__(self):
        self.calls = []
        self.fail = ""

    def snapshot(self):
        if self.fail == "adb":
            raise AdbError("no adb device")
        return {"sections": [], "checked_at": "2026-11-17T00:00:00Z"}

    def set_enabled(self, setting_id, enabled):
        self.calls.append((setting_id, enabled))
        if setting_id == "missing":
            raise ValueError("unknown setting: missing")
        if self.fail == "adb":
            raise AdbError("no adb device")
        return {"ok": True, "setting_id": setting_id, "enabled": enabled, "output": ""}

    def set_value(self, setting_id, value):
        self.calls.append((setting_id, value))
        if setting_id == "missing":
            raise ValueError("unknown setting: missing")
        if self.fail == "adb":
            raise AdbError("no adb device")
        return {"ok": True, "setting_id": setting_id, "value": value, "output": ""}


def _client(tmp_path):
    app = create_manager_app(serial="fake")
    settings = FakeSettings()
    app.dependency_overrides[get_settings_service] = lambda: settings
    return TestClient(app), settings


def test_settings_routes_and_token_guard(tmp_path):
    client, settings = _client(tmp_path)
    assert client.get("/api/settings").status_code == 200

    assert client.post("/api/settings/hide_recording_indicator", json={"enabled": True}).status_code == 403
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post(
        "/api/settings/hide_recording_indicator",
        json={"enabled": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert settings.calls == [("hide_recording_indicator", True)]


def test_settings_routes_accept_choice_values(tmp_path):
    client, settings = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post("/api/settings/guardian_radius", json={"value": "1"}, headers=headers)
    assert response.status_code == 200
    assert settings.calls == [("guardian_radius", "1")]


def test_settings_routes_reject_invalid_and_recording(tmp_path):
    client, _settings = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    assert client.post("/api/settings/missing", json={"enabled": True}, headers=headers).status_code == 400
    assert client.post("/api/settings/hide_recording_indicator", json={}, headers=headers).status_code == 422
    assert (
        client.post(
            "/api/settings/hide_recording_indicator",
            json={"enabled": True, "value": "1"},
            headers=headers,
        ).status_code
        == 422
    )

    write_state(True, label="test run")
    assert (
        client.post(
            "/api/settings/hide_recording_indicator",
            json={"enabled": True},
            headers=headers,
        ).status_code
        == 409
    )


def test_settings_routes_map_adb_errors(tmp_path):
    client, settings = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    settings.fail = "adb"
    assert client.get("/api/settings").status_code == 503
    assert (
        client.post(
            "/api/settings/hide_recording_indicator",
            json={"enabled": True},
            headers=headers,
        ).status_code
        == 503
    )
