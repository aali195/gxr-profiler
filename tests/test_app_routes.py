import re

from fastapi.testclient import TestClient

from gxr_profiler.core.adb import AdbError
from gxr_profiler.server.app import create_app
from gxr_profiler.server.deps import get_apps_service, get_manager


def _token(client):
    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


class FakeManager:
    def __init__(self, status="idle"):
        self.status = status

    def state(self):
        return {"status": self.status}


class FakeApps:
    def __init__(self):
        self.detail_calls = []
        self.action_calls = []
        self.fail_action = None

    def list_packages(self):
        return {
            "packages": [
                {
                    "package": "com.example.app",
                    "kind": "user",
                    "state": "enabled",
                    "actions": ["disable", "uninstall"],
                    "critical": False,
                    "proc_count": 1,
                    "cpu_pct": 4.2,
                    "rss_kb": 2048,
                    "gpu_mem_kb": 1024,
                    "size_kb": 1024,
                    "threads": 12,
                    "oom_class": "cached",
                    "proc_names": ["com.example.app"],
                }
            ],
            "summary": {"total": 1},
            "action_specs": {},
        }

    def detail(self, package, root=False):
        self.detail_calls.append((package, root))
        if package == "missing.app":
            raise LookupError("package not found: missing.app")
        if package == "bad..name":
            raise ValueError("invalid package name")
        return {"package": package, "detail": {"version_name": "1.0"}, "root": {"requested": root}}

    def run_action(self, package, action, confirm=False):
        self.action_calls.append((package, action, confirm))
        if self.fail_action == "critical":
            raise PermissionError("critical system packages cannot be disabled or removed")
        if not confirm:
            raise ValueError("confirmation is required")
        return {"ok": True, "package": package, "action": action, "output": "Success"}


def _client(tmp_path, status="idle"):
    app = create_app(str(tmp_path / "runs"))
    fake_apps = FakeApps()
    fake_manager = FakeManager(status)
    app.dependency_overrides[get_apps_service] = lambda: fake_apps
    app.dependency_overrides[get_manager] = lambda: fake_manager
    client = TestClient(app)
    return client, fake_apps, fake_manager


def test_app_list_and_detail_routes(tmp_path):
    client, fake, _ = _client(tmp_path)
    listing = client.get("/api/apps")
    assert listing.status_code == 200
    assert listing.json()["packages"][0]["package"] == "com.example.app"
    assert listing.json()["packages"][0]["cpu_pct"] == 4.2
    assert listing.json()["packages"][0]["rss_kb"] == 2048
    assert listing.json()["packages"][0]["gpu_mem_kb"] == 1024
    assert listing.json()["packages"][0]["size_kb"] == 1024
    assert listing.json()["packages"][0]["threads"] == 12

    detail = client.get("/api/apps/com.example.app", params={"root": "true"})
    assert detail.status_code == 200
    assert detail.json()["root"]["requested"] is True
    assert fake.detail_calls == [("com.example.app", True)]

    assert client.get("/api/apps/missing.app").status_code == 404
    assert client.get("/api/apps/bad..name").status_code == 400


def test_app_actions_require_token_and_confirmation(tmp_path):
    client, fake, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    assert client.post("/api/apps/com.example.app/action", json={"action": "disable"}).status_code == 403
    assert (
        client.post(
            "/api/apps/com.example.app/action",
            json={"action": "disable", "confirm": False},
            headers=headers,
        ).status_code
        == 400
    )
    assert fake.action_calls[-1] == ("com.example.app", "disable", False)

    response = client.post(
        "/api/apps/com.example.app/action",
        json={"action": "disable", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert fake.action_calls[-1] == ("com.example.app", "disable", True)


def test_app_actions_reject_unknown_action_and_recording(tmp_path):
    client, _, manager = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    assert (
        client.post(
            "/api/apps/com.example.app/action",
            json={"action": "explode", "confirm": True},
            headers=headers,
        ).status_code
        == 422
    )
    manager.status = "recording"
    response = client.post(
        "/api/apps/com.example.app/action",
        json={"action": "disable", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 409


def test_app_actions_block_critical_packages(tmp_path):
    client, fake, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    fake.fail_action = "critical"
    response = client.post(
        "/api/apps/com.android.systemui/action",
        json={"action": "disable", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 403
    assert "cannot be disabled or removed" in response.json()["detail"]


def test_app_routes_map_adb_errors_to_503(tmp_path):
    client, fake, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    fake.list_packages = lambda: (_ for _ in ()).throw(AdbError("no adb device"))
    assert client.get("/api/apps").status_code == 503

    fake.detail = lambda package, root=False: (_ for _ in ()).throw(AdbError("no adb device"))
    assert client.get("/api/apps/com.example.app").status_code == 503

    fake.run_action = lambda package, action, confirm=False: (_ for _ in ()).throw(AdbError("no adb device"))
    response = client.post(
        "/api/apps/com.example.app/action",
        json={"action": "disable", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 503
