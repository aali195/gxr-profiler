import json

from gxr_profiler.capture.columns import REPORT_COLUMNS
from gxr_profiler.report.static import _clean_pins
from gxr_profiler.server import export


class FakeWindow:
    def __init__(self, path):
        self.path = path

    def create_file_dialog(self, *args, **kwargs):
        return str(self.path)


class FakeWebview:
    SAVE_DIALOG = 2


def test_export_service_writes_self_contained_report(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    run = runs / "before"
    run.mkdir()
    (run / "data.csv").write_text(",".join(REPORT_COLUMNS) + "\n1.0,x,0.0,1\n", encoding="utf-8")
    (run / "meta.json").write_text(
        json.dumps(
            {
                "label": "before",
                "rows": 1,
                "wifi_ssid": "SecretNet",
                "device_info": {
                    "serial": "SERIAL123",
                    "wifi": {"ssid": "SecretNet", "bssid": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.9"},
                },
            }
        ),
        encoding="utf-8",
    )

    default_reports = tmp_path / "reports"
    monkeypatch.setattr(export, "default_reports_dir", lambda: str(default_reports))
    target = tmp_path / "out.html"

    service = export.ExportService(str(runs))
    pins = {"graph": [{"key": "t_AP", "label": "Pinned AP probe", "unit": "°C"}]}
    result = service.save_report(["before"], FakeWindow(target), FakeWebview(), pins=pins)
    assert result["ok"] is True
    assert result["path"].endswith("out.html")
    content = target.read_text(encoding="utf-8")
    assert "GXR_PROFILER_OFFLINE" in content
    assert "Pinned AP probe" in content
    assert "/static/" not in content
    assert "SecretNet" not in content
    assert "SERIAL123" not in content
    assert "aa:bb:cc:dd:ee:ff" not in content


def test_export_service_missing_run(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(export, "default_reports_dir", lambda: str(tmp_path / "reports"))
    service = export.ExportService(str(runs))
    result = service.save_report(["missing"], FakeWindow(tmp_path / "out.html"), FakeWebview())
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_js_api_has_no_serializable_state(tmp_path):
    service = export.ExportService(str(tmp_path))
    api = export.make_js_api(service, lambda: None, FakeWebview())
    assert api.__dict__ == {}


def test_clean_pins_keeps_only_expected_fields():
    cleaned = _clean_pins(
        {
            "graph": [{"key": "t_AP", "label": "AP", "uid": True, "extra": "drop me"}],
            "table": "not a list",
            "process": [{"key": ""}, {"key": "proc", "name": "com.example"}],
        }
    )
    assert cleaned["graph"] == [{"key": "t_AP", "label": "AP"}]
    assert cleaned["table"] == []
    assert cleaned["process"] == [{"key": "proc", "name": "com.example"}]
