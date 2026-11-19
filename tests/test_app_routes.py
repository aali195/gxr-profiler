import re

from fastapi.testclient import TestClient

from gxr_tools.core.adb import AdbError
from gxr_tools.core.recording_state import write_state
from gxr_tools.manager.server.app import create_manager_app
from gxr_tools.manager.server.deps import get_apps_service


def _token(client):
    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


class FakeApps:
    def __init__(self):
        self.detail_calls = []
        self.action_calls = []
        self.performance_calls = []
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

    def set_game_override(self, package, fps, downscale, confirm=False):
        self.performance_calls.append((package, fps, downscale, confirm))
        if self.fail_action == "critical":
            raise PermissionError("critical system packages cannot be performance-tuned")
        if not confirm:
            raise ValueError("confirmation is required")
        return {
            "ok": True,
            "package": package,
            "action": "performance",
            "command": "cmd game set --fps 90 --downscale 0.8 " + package,
            "fps": fps,
            "downscale": downscale,
        }


def _client(tmp_path):
    app = create_manager_app(serial="fake")
    fake_apps = FakeApps()
    app.dependency_overrides[get_apps_service] = lambda: fake_apps
    return TestClient(app), fake_apps


def test_app_list_and_detail_routes(tmp_path):
    client, fake = _client(tmp_path)
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
    client, fake = _client(tmp_path)
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
    client, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    assert (
        client.post(
            "/api/apps/com.example.app/action",
            json={"action": "explode", "confirm": True},
            headers=headers,
        ).status_code
        == 422
    )
    write_state(True, label="test run")
    response = client.post(
        "/api/apps/com.example.app/action",
        json={"action": "disable", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 409


def test_app_actions_block_critical_packages(tmp_path):
    client, fake = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    fake.fail_action = "critical"
    response = client.post(
        "/api/apps/com.android.systemui/action",
        json={"action": "disable", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 403
    assert "cannot be disabled or removed" in response.json()["detail"]


def test_app_performance_requires_token_and_confirmation(tmp_path):
    client, fake = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    assert (
        client.post(
            "/api/apps/com.example.app/performance",
            json={"fps": "90", "downscale": "0.8"},
        ).status_code
        == 403
    )
    response = client.post(
        "/api/apps/com.example.app/performance",
        json={"fps": "90", "downscale": "0.8", "confirm": False},
        headers=headers,
    )
    assert response.status_code == 400
    assert fake.performance_calls[-1] == ("com.example.app", "90", "0.8", False)

    response = client.post(
        "/api/apps/com.example.app/performance",
        json={"fps": "90", "downscale": "0.8", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert fake.performance_calls[-1] == ("com.example.app", "90", "0.8", True)


def test_app_performance_rejects_invalid_values_and_recording(tmp_path):
    client, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    response = client.post(
        "/api/apps/com.example.app/performance",
        json={"fps": "72", "downscale": "0.8", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 422
    response = client.post(
        "/api/apps/com.example.app/performance",
        json={"fps": "90", "downscale": "0.55", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 422

    write_state(True, label="test run")
    response = client.post(
        "/api/apps/com.example.app/performance",
        json={"fps": "90", "downscale": "0.8", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 409


def test_app_performance_blocks_critical_packages(tmp_path):
    client, fake = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    fake.fail_action = "critical"
    response = client.post(
        "/api/apps/com.android.systemui/performance",
        json={"fps": "90", "downscale": "0.8", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 403
    assert "cannot be performance-tuned" in response.json()["detail"]


def test_app_routes_map_adb_errors_to_503(tmp_path):
    client, fake = _client(tmp_path)
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

    fake.set_game_override = lambda package, fps, downscale, confirm=False: (_ for _ in ()).throw(
        AdbError("no adb device")
    )
    response = client.post(
        "/api/apps/com.example.app/performance",
        json={"fps": "90", "downscale": "0.8", "confirm": True},
        headers=headers,
    )
    assert response.status_code == 503
