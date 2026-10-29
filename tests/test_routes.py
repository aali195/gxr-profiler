import json
import threading

from fastapi.testclient import TestClient

from gxr_profiler.capture.columns import REPORT_COLUMNS
from gxr_profiler.server.app import create_app
from gxr_profiler.server.deps import get_manager
from gxr_profiler.server.routers import record as record_router


def _make_run(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    run = runs / "before"
    run.mkdir()
    (run / "data.csv").write_text(",".join(REPORT_COLUMNS) + "\n1.0,x,0.0,1\n", encoding="utf-8")
    (run / "meta.json").write_text(
        json.dumps({"label": "before", "rows": 1, "started": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    (run / "procs.csv").write_text(
        "name,uid,pid,elapsed_s,cpu_pct,cpu_now_pct,rss_kb,oom_adj,oom_class\ncom.foo,10000,42,0,1,2,2048,905,cached\n",
        encoding="utf-8",
    )
    return runs


def test_read_endpoints_and_offline_report(tmp_path):
    runs = _make_run(tmp_path)
    client = TestClient(create_app(str(runs)))

    spec = client.get("/api/spec")
    assert spec.status_code == 200 and spec.json()["groups"]

    listing = client.get("/api/runs")
    assert listing.status_code == 200
    assert listing.json()[0]["label"] == "before"

    detail = client.get("/api/runs/before")
    assert detail.status_code == 200
    assert detail.json()["meta"]["label"] == "before"
    assert "series" in detail.json()

    report = client.get("/api/report", params={"labels": "before"})
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert "attachment;" in report.headers["content-disposition"]
    assert b"GXR_PROFILER_OFFLINE" in report.content
    assert b"/static/" not in report.content
    assert b"<!-- gxr-profiler:styles:start -->" in report.content

    procs = client.get("/api/runs/before/procs")
    assert procs.status_code == 200
    assert procs.json()[0]["name"] == "com.foo"
    series = client.get("/api/runs/before/procs/series")
    assert series.status_code == 200
    assert "com.foo|10000|42" in series.json()
    assert b"proc_series" in report.content

    assert client.get("/api/report").status_code == 400
    assert client.get("/api/report", params={"labels": "missing"}).status_code == 404

    pinned = client.get(
        "/api/report",
        params={
            "labels": "before",
            "pins": json.dumps({"graph": [{"key": "t_AP", "label": "Pinned AP probe"}]}),
        },
    )
    assert pinned.status_code == 200
    assert b"Pinned AP probe" in pinned.content
    assert client.get("/api/report", params={"labels": "before", "pins": "{"}).status_code == 400


def _token(client):
    import re

    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


def test_invalid_recording_name_is_rejected(tmp_path):
    runs = _make_run(tmp_path)
    client = TestClient(create_app(str(runs)))
    response = client.post(
        "/api/record", json={"name": "../evil", "duration": 1}, headers={"X-GXR-Profiler-Token": _token(client)}
    )
    assert response.status_code == 400
    assert client.get("/api/record/status").json()["status"] == "idle"


def test_unicode_run_and_report_filename(tmp_path):
    runs = _make_run(tmp_path)
    run = runs / "café"
    run.mkdir()
    (run / "data.csv").write_text(",".join(REPORT_COLUMNS) + "\n1.0,x,0.0,1\n", encoding="utf-8")
    (run / "meta.json").write_text(json.dumps({"label": "café", "rows": 1}), encoding="utf-8")
    client = TestClient(create_app(str(runs)))

    assert client.get("/api/runs/caf%C3%A9").status_code == 200
    report = client.get("/api/report", params={"labels": "café"})
    assert report.status_code == 200
    disposition = report.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "%C3%A9" in disposition


def test_invalid_run_label_is_rejected(tmp_path):
    runs = _make_run(tmp_path)
    client = TestClient(create_app(str(runs)))
    # The store rejects separators; the route should surface a 400, not a 500.
    response = client.get("/api/runs/a%5Cb")
    assert response.status_code == 400


class FakeManager:
    def __init__(self, runs_dir: str) -> None:
        self.runs_dir = runs_dir
        self.serial = None
        self.status = "idle"
        self.label = ""
        self.events = []
        self.lock = threading.Lock()
        self.started = None
        self.stopped = False

    def start(self, cfg):
        self.started = cfg
        self.status = "recording"
        self.label = cfg.name

    def stop(self):
        self.stopped = True
        self.status = "done"

    def state(self):
        return {"status": self.status, "label": self.label, "rows": 0, "running": False}


def test_record_routes_with_injected_manager(tmp_path):
    runs = _make_run(tmp_path)
    app = create_app(str(runs))
    fake = FakeManager(str(runs))
    app.dependency_overrides[get_manager] = lambda: fake
    client = TestClient(app)
    headers = {"X-GXR-Profiler-Token": _token(client)}

    response = client.post("/api/record", json={"name": "new run", "duration": 5, "interval": 0.5}, headers=headers)
    assert response.status_code == 200
    assert fake.started is not None
    assert fake.started.name == "new run"
    assert fake.started.out_dir == str(runs)
    assert fake.started.duration == 5.0
    assert fake.started.interval == 0.5

    assert client.post("/api/record/stop", headers=headers).status_code == 200
    assert fake.stopped is True
    assert client.get("/api/record/status").json()["status"] == "done"


def test_preview_route_returns_lightweight_metrics(tmp_path, monkeypatch):
    runs = _make_run(tmp_path)
    app = create_app(str(runs))
    fake = FakeManager(str(runs))
    app.dependency_overrides[get_manager] = lambda: fake
    client = TestClient(app)

    class FakePoller:
        def __init__(self, adb):
            self.adb = adb

        def poll_preview(self):
            return {"thermal_status": 2.0, "t_CPU0": 51.5, "sev_CPU0": 1.0, "batt_level": 88.0}

    monkeypatch.setattr(record_router, "Poller", FakePoller)
    monkeypatch.setattr(record_router, "RealAdb", lambda serial=None: object())
    monkeypatch.setattr(record_router, "resolve_serial", lambda serial=None: "fake")
    response = client.get("/api/preview")
    assert response.status_code == 200
    assert response.json()["thermal_status"] == 2.0
    assert response.json()["thermal_max_sev"] == 1.0

    fake.status = "recording"
    assert client.get("/api/preview").status_code == 409


def test_local_mutation_guard(tmp_path):
    import re

    runs = _make_run(tmp_path)
    app = create_app(str(runs))
    fake = FakeManager(str(runs))
    app.dependency_overrides[get_manager] = lambda: fake
    client = TestClient(app)

    html = client.get("/").text
    token = re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)
    body = {"name": "guarded", "duration": 1, "interval": 1}

    assert client.post("/api/record", json=body, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/record", json=body).status_code == 403
    assert (
        client.post(
            "/api/record",
            json=body,
            headers={"Origin": "http://127.0.0.1:8765"},
        ).status_code
        == 403
    )
    response = client.post(
        "/api/record",
        json=body,
        headers={"Origin": "http://127.0.0.1:8765", "X-GXR-Profiler-Token": token},
    )
    assert response.status_code == 200
