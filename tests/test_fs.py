import json

from gxr_profiler.core.fs import atomic_write_json, atomic_write_text


def test_atomic_writes(tmp_path):
    text_path = tmp_path / "note.txt"
    atomic_write_text(text_path, "hello")
    assert text_path.read_text(encoding="utf-8") == "hello"
    assert not list(tmp_path.glob(".note.txt.tmp-*"))

    json_path = tmp_path / "meta.json"
    atomic_write_json(json_path, {"label": "run", "rows": 2})
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"label": "run", "rows": 2}
    assert not list(tmp_path.glob(".meta.json.tmp-*"))
