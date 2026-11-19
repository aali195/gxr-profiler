import re

from fastapi.testclient import TestClient

from gxr_profiler.server.app import create_app
from gxr_profiler.server.apps import AppsService
from gxr_profiler.server.deps import get_apps_service, get_manager

from .install_fixtures import FakeInstallAdb, build_apk


class FakeManager:
    def __init__(self, status="idle"):
        self.status = status

    def state(self):
        return {"status": self.status}


def _token(client):
    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


def _client(tmp_path, status="idle"):
    app = create_app(str(tmp_path / "runs"))
    adb = FakeInstallAdb()
    service = AppsService(
        serial="fake",
        reports_dir=str(tmp_path / "reports"),
        staging_dir=str(tmp_path / "staging"),
        adb_factory=lambda serial=None: adb,
    )
    manager = FakeManager(status)
    app.dependency_overrides[get_apps_service] = lambda: service
    app.dependency_overrides[get_manager] = lambda: manager
    return TestClient(app), service, manager, adb


def test_install_stage_preview_and_discard(tmp_path):
    client, service, _, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    apk = build_apk(tmp_path / "game.apk", "com.example.game").read_bytes()

    assert (
        client.post(
            "/api/apps/install/stage",
            params={"name": "game.apk"},
            content=apk,
            headers={"Content-Type": "application/octet-stream"},
        ).status_code
        == 403
    )

    response = client.post(
        "/api/apps/install/stage",
        params={"name": "game.apk", "path": "game.apk"},
        content=apk,
        headers={**headers, "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    staged = response.json()["files"][0]
    assert staged["package"] == "com.example.game"
    assert staged["sha256"]

    preview = client.post(
        "/api/apps/install/preview",
        json={"items": [staged["id"]], "options": {}},
        headers=headers,
    )
    assert preview.status_code == 200
    assert preview.json()["ok"] is True
    assert preview.json()["groups"][0]["package"] == "com.example.game"

    state = client.get("/api/apps/install/state")
    assert state.status_code == 200
    assert state.json()["files"][0]["id"] == staged["id"]
    assert state.json()["job"] is None

    assert client.delete(f"/api/apps/install/stage/{staged['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/apps/install/stage/{staged['id']}", headers=headers).status_code == 404
    assert service.install.list_staged() == []

    cleared = client.delete("/api/apps/install/stage", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["removed"] == 0


def test_install_stage_rejects_bad_names_and_bodies(tmp_path):
    client, _, _, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client), "Content-Type": "application/octet-stream"}
    response = client.post(
        "/api/apps/install/stage",
        params={"name": "setup.exe"},
        content=b"x",
        headers=headers,
    )
    assert response.status_code == 400
    response = client.post(
        "/api/apps/install/stage",
        params={"name": "../evil.apk"},
        content=b"x",
        headers=headers,
    )
    assert response.status_code == 400


def test_install_start_requires_confirmation_and_blocks_recording(tmp_path):
    client, _, manager, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    apk = build_apk(tmp_path / "game.apk", "com.example.game").read_bytes()
    staged = client.post(
        "/api/apps/install/stage",
        params={"name": "game.apk"},
        content=apk,
        headers={**headers, "Content-Type": "application/octet-stream"},
    ).json()["files"][0]

    response = client.post(
        "/api/apps/install",
        json={"items": [staged["id"]], "confirm": False},
        headers=headers,
    )
    assert response.status_code == 400

    manager.status = "recording"
    response = client.post(
        "/api/apps/install",
        json={"items": [staged["id"]], "confirm": True},
        headers=headers,
    )
    assert response.status_code == 409


def test_install_status_unknown_job(tmp_path):
    client, _, _, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    assert client.get("/api/apps/install/missing", headers=headers).status_code == 404


def test_install_preview_validation_errors(tmp_path):
    client, _, _, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post(
        "/api/apps/install/preview",
        json={"items": [], "options": {}},
        headers=headers,
    )
    assert response.status_code == 422
    response = client.post(
        "/api/apps/install/preview",
        json={"items": ["missing"]},
        headers=headers,
    )
    assert response.status_code == 400
