import re
import threading

from fastapi.testclient import TestClient

from gxr_tools.manager.server.app import create_manager_app
from gxr_tools.manager.server.deps import get_debug_manager


class FakeDebugManager:
    def __init__(self) -> None:
        self.status = "idle"
        self.error = ""
        self.started = ""
        self.finished = ""
        self.report = None
        self.running = False
        self.options = None
        self.lock = threading.Lock()

    def start(self, options):
        if self.running:
            raise RuntimeError("a diagnostics snapshot is already running")
        self.options = options
        self.running = True
        self.status = "running"

    def state(self):
        return {
            "status": self.status,
            "started": self.started,
            "finished": self.finished,
            "error": self.error,
            "running": self.running,
            "collected_at": (self.report or {}).get("collected_at"),
            "saved": (self.report or {}).get("saved") or {},
        }

    def latest(self):
        return self.report


def _token(client):
    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


def test_debug_routes(tmp_path):
    app = create_manager_app(serial="fake")
    fake = FakeDebugManager()
    app.dependency_overrides[get_debug_manager] = lambda: fake
    client = TestClient(app)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    assert client.get("/api/debug/status").json()["status"] == "idle"
    assert client.get("/api/debug/report").status_code == 404

    assert client.post("/api/debug/collect", json={"root": True}).status_code == 403
    response = client.post(
        "/api/debug/collect",
        json={"root": True, "include_tombstones": True, "log_lines": 500},
        headers=headers,
    )
    assert response.status_code == 200
    assert fake.options["root"] is True
    assert fake.options["include_tombstones"] is True
    assert client.get("/api/debug/status").json()["status"] == "running"

    # A second request while the first is running is rejected.
    assert client.post("/api/debug/collect", json={}, headers=headers).status_code == 409

    fake.report = {"collected_at": "2026-11-17T00:00:00Z", "issues": [], "saved": {"json": "x"}}
    fake.running = False
    fake.status = "done"
    report = client.get("/api/debug/report")
    assert report.status_code == 200
    assert report.json()["collected_at"].startswith("2026-11-17")
    assert client.get("/api/debug/status").json()["saved"]["json"] == "x"


def test_debug_request_validation(tmp_path):
    app = create_manager_app(serial="fake")
    fake = FakeDebugManager()
    app.dependency_overrides[get_debug_manager] = lambda: fake
    client = TestClient(app)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    assert client.post("/api/debug/collect", json={"log_lines": 1}, headers=headers).status_code == 422
    assert client.post("/api/debug/collect", json={"log_lines": 9000}, headers=headers).status_code == 422
