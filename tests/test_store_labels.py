import json

from gxr_profiler.capture.columns import REPORT_COLUMNS
from gxr_profiler.core import labels, schema
from gxr_profiler.report import charts
from gxr_profiler.report.data import MAX_POINTS, downsample
from gxr_profiler.runs.store import RunStore


def test_labels_friendly_names():
    assert labels.label("t_LRP").name == "Power path"
    assert labels.label("g_busy").name == "GPU utilisation"
    assert labels.label("fan_rpm").unit == "rpm"
    assert labels.friendly("mem_available") == "Available memory"


def test_bands_defined():
    bands = {b["id"] for b in labels.BANDS}
    assert {"cpu", "gpu", "npu"} <= bands


def test_display_units():
    spec = charts.spec()
    groups = {g["id"]: g for g in spec["groups"]}
    series = {s["col"]: s for g in spec["groups"] for s in g["series"]}
    assert series["cpu_max0"]["unit"] == "MHz"
    assert series["cpu_max0"]["scale"] == 0.001
    assert series["mem_available"]["unit"] == "GB"
    assert series["mem_available"]["scale"] < 1
    assert series["xr_cpu"]["unit"] == "%"
    assert series["xr_cpu"]["scale"] == 100.0
    assert series["disp_brightness"]["unit"] == "%"
    assert series["disp_brightness"]["scale"] == 100.0
    assert series["xr_fps"]["unit"] == "fps"
    assert groups["cpu"]["unit"] == "MHz"
    bands = {b["id"]: b for b in spec["bands"]}
    assert bands["cpu_freq"]["unit"] == "MHz"
    assert bands["cpu_freq"]["scale"] == 0.001
    for g in spec["groups"]:
        units = {s["unit"] for s in g["series"]}
        units |= {bands[b]["unit"] for b in g["bands"]}
        if g["unit"]:
            assert units == {g["unit"]}, (g["id"], units, g["unit"])


def test_report_columns_snapshot():
    from pathlib import Path

    snapshot = json.loads((Path(__file__).parent / "columns_snapshot.json").read_text(encoding="utf-8"))
    assert REPORT_COLUMNS == snapshot


def test_columns_have_metadata_and_charts_are_known():
    missing = [c for c in REPORT_COLUMNS if not schema.describe(c).get("source")]
    assert not missing
    known = set(REPORT_COLUMNS)
    assert all(s.col in known for g in charts.GROUPS for s in g.series)
    assert all(c in known for b in charts.spec()["bands"] for c in b["columns"])


def test_downsample_keeps_shape():
    for n in (MAX_POINTS, MAX_POINTS + 1, MAX_POINTS * 2, MAX_POINTS * 2 + 1):
        series = {"a": list(range(n))}
        elapsed, out = downsample(list(range(n)), series)
        assert len(elapsed) <= MAX_POINTS
        assert len(out["a"]) == len(elapsed)
        assert elapsed[-1] == n - 1


def test_new_run_directory_layout(tmp_path):
    from gxr_profiler.capture.writer import RunWriter

    writer = RunWriter(str(tmp_path), "new-layout")
    writer.open()
    writer.write_row({"elapsed_s": "0"})
    writer.close()
    run_dir = tmp_path / "new-layout"
    assert (run_dir / "data.csv").exists()
    assert (run_dir / "events.csv").exists()
    (run_dir / "meta.json").write_text(
        json.dumps({"label": "new-layout", "rows": 1, "features": {"profile": "standard"}}), encoding="utf-8"
    )

    store = RunStore(str(tmp_path))
    assert [r.label for r in store.list()] == ["new-layout"]
    meta, frame = store.load("new-layout")
    assert meta["label"] == "new-layout"
    assert len(frame) == 1
    assert store.list()[0].profile == "standard"
    assert store.update("new-layout", name="renamed") == "renamed"
    assert (tmp_path / "renamed" / "data.csv").exists()
    store.delete("renamed")
    assert not (tmp_path / "renamed").exists()


def test_store_path_rejects_traversal(tmp_path):
    import pytest

    store = RunStore(str(tmp_path))
    for label in ("../evil", "a/b", "a\\b", "..", "C:evil"):
        with pytest.raises(ValueError):
            store.load(label)


def test_store_roundtrip(tmp_path):
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
                "started": "2026-01-01T00:00:00Z",
                "device_info": {
                    "model": "SM-I610",
                    "build_display_id": "BUILD1",
                    "panel": {"active": "XR2_SONY_ECX344A"},
                },
                "start_state": {"low_power": 1, "hand_tracking_active": True},
            }
        ),
        encoding="utf-8",
    )

    store = RunStore(str(runs))
    items = store.list()
    assert len(items) == 1
    s = items[0]
    assert s.label == "before" and s.power_saving is True and s.hand_tracking is True
    assert s.profile == ""
    assert s.panel == "XR2_SONY_ECX344A"
    meta, df = store.load("before")
    assert meta["label"] == "before" and len(df) == 1


def test_store_update_rename_and_notes(tmp_path):
    import pytest

    runs = tmp_path / "runs"
    runs.mkdir()
    before = runs / "before"
    before.mkdir()
    (before / "data.csv").write_text(",".join(REPORT_COLUMNS) + "\n1.0,x,0.0,1\n", encoding="utf-8")
    (before / "meta.json").write_text(json.dumps({"label": "before", "rows": 1}), encoding="utf-8")
    (before / "events.csv").write_text("ts_host\n", encoding="utf-8")

    store = RunStore(str(runs))
    new = store.update("before", name="after run", notes="hello")
    assert new == "after run"
    assert not before.exists()
    assert (runs / "after run" / "data.csv").exists()
    assert (runs / "after run" / "events.csv").exists()
    meta, _ = store.load("after run")
    assert meta["label"] == "after run" and meta["notes"] == "hello"

    dup = runs / "dup"
    dup.mkdir()
    (dup / "data.csv").write_text(",".join(REPORT_COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        store.update("after run", name="dup")
    with pytest.raises(ValueError):
        store.update("after run", name="../evil")


def test_store_delete(tmp_path):
    import pytest

    from gxr_profiler.core.adb import RunNotFound

    runs = tmp_path / "runs"
    runs.mkdir()
    doomed = runs / "doomed"
    doomed.mkdir()
    for name in ("data.csv", "events.csv", "procs.csv", "meta.json"):
        (doomed / name).write_text("x", encoding="utf-8")
    keep = runs / "keep"
    keep.mkdir()
    (keep / "data.csv").write_text("x", encoding="utf-8")

    store = RunStore(str(runs))
    store.delete("doomed")
    assert not doomed.exists()
    assert keep.exists()
    with pytest.raises(RunNotFound):
        store.delete("doomed")
    with pytest.raises(ValueError):
        store.delete("../evil")


def test_flat_runs_are_not_listed(tmp_path):
    import pytest

    from gxr_profiler.core.adb import RunNotFound

    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "legacy.csv").write_text(",".join(REPORT_COLUMNS) + "\n1.0,x,0.0,1\n", encoding="utf-8")
    (runs / "legacy.meta.json").write_text(json.dumps({"label": "legacy", "rows": 1}), encoding="utf-8")

    store = RunStore(str(runs))
    assert store.list() == []
    with pytest.raises(RunNotFound):
        store.load("legacy")


def test_store_lists_data_only_incomplete_run(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    broken = runs / "broken"
    broken.mkdir()
    (broken / "data.csv").write_text(",".join(REPORT_COLUMNS) + "\n1.0,x,0.0,1\n", encoding="utf-8")
    store = RunStore(str(runs))
    assert [r.label for r in store.list()] == ["broken"]
    assert store.load("broken")[1].shape[0] == 1
