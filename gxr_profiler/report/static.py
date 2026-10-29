"""Offline report: the real web app with data and assets inlined."""

from __future__ import annotations

import copy
import json
import math
import os
from datetime import UTC, datetime

from ..core.adb import RunNotFound
from ..core.columns import temp_sensor_options
from ..core.fs import atomic_write_text
from ..core.models import CAPTURE_PROFILES
from ..core.naming import safe_filename
from ..core.paths import default_reports_dir, default_runs_dir, ensure_writable_dir
from ..runs.store import RunStore
from . import charts
from .data import downsample, process_series_for, procs_for
from .data import series as build_series

_WEB = os.path.join(os.path.dirname(__file__), "..", "server", "web")
MAX_COMPARE_RUNS = 6
_PIN_LIMITS = {"table": 20, "graph": 12, "process": 6}
_PIN_TEXT_FIELDS = ("label", "unit", "section", "groupSection", "groupId", "name", "package", "kind")


def _clean_pins(pins) -> dict:
    """Keep export pins small, predictable and JSON-safe."""
    out = {kind: [] for kind in _PIN_LIMITS}
    if not isinstance(pins, dict):
        return out
    for kind, limit in _PIN_LIMITS.items():
        items = pins.get(kind)
        if not isinstance(items, list):
            continue
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                continue
            clean = {"key": key[:200]}
            for field in _PIN_TEXT_FIELDS:
                value = item.get(field)
                if isinstance(value, str):
                    clean[field] = value[:200]
            for field in ("uid", "scale", "decimals"):
                value = item.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    clean[field] = value
            out[kind].append(clean)
    return out


def _web(rel: str) -> str:
    with open(os.path.join(_WEB, rel), encoding="utf-8") as fh:
        return fh.read()


def _inline_block(html: str, name: str, content: str) -> str:
    start = f"<!-- gxr-profiler:{name}:start -->"
    end = f"<!-- gxr-profiler:{name}:end -->"
    if start not in html or end not in html:
        raise RuntimeError(f"index.html is missing the '{name}' asset markers")
    head, rest = html.split(start, 1)
    _, tail = rest.split(end, 1)
    return head + start + "\n" + content + "\n" + end + tail


def _redact_meta(meta: dict) -> dict:
    """Strip network/device identifiers from shareable reports."""
    clean = copy.deepcopy(meta)
    clean.pop("wifi_ssid", None)
    di = clean.get("device_info")
    if isinstance(di, dict):
        for key in ("serial", "serialno", "ap_serial"):
            di.pop(key, None)
        wifi = di.get("wifi")
        if isinstance(wifi, dict):
            for key in ("ssid", "bssid", "ip", "mac", "guid"):
                wifi.pop(key, None)
    return clean


def _dataset(label: str, meta: dict, df) -> dict:
    elapsed = [float(x) for x in df["elapsed_s"].tolist()] if "elapsed_s" in df.columns else []
    elapsed, series = downsample(elapsed, build_series(df))
    return {"label": label, "meta": _redact_meta(meta), "elapsed": elapsed, "series": series}


def build(labels_list: list[str], runs_dir: str | None = None, pins=None) -> str:
    """Return a self-contained copy of the web app for the selected runs."""
    if isinstance(labels_list, str):
        labels_list = [labels_list]
    labels_list = list(dict.fromkeys(str(label) for label in labels_list))
    if len(labels_list) > MAX_COMPARE_RUNS:
        raise ValueError(f"too many runs selected (maximum {MAX_COMPARE_RUNS})")
    store = RunStore(runs_dir or default_runs_dir())
    summaries = {r.label: r.to_dict() for r in store.list()}
    missing = [label for label in labels_list if label not in summaries]
    if missing:
        raise RunNotFound("run not found: " + ", ".join(missing))

    datasets: dict[str, dict] = {}
    procs: dict[str, list] = {}
    proc_series: dict[str, dict] = {}
    for label in labels_list:
        meta, df = store.load(label)
        datasets[label] = _dataset(label, meta, df)
        procs[label] = procs_for(store, label)
        proc_series[label] = process_series_for(store, label)

    payload = {
        "spec": {
            **charts.spec(),
            "capture_profiles": CAPTURE_PROFILES,
            "cooldown_sensors": temp_sensor_options(),
        },
        "runs": [summaries[label] for label in labels_list],
        "datasets": datasets,
        "procs": procs,
        "proc_series": proc_series,
        "labels": labels_list,
        "compare": labels_list if len(labels_list) > 1 else [],
        "pins": _clean_pins(pins),
        "exported": datetime.now(UTC).isoformat(),
    }

    html = _web("index.html")
    css = _web("styles.css")
    echarts = _web(os.path.join("vendor", "echarts.min.js")).replace("</script", "<\\/script")
    appjs = _web("app.js").replace("</script", "<\\/script")
    data = json.dumps(payload, separators=(",", ":"))
    data = (
        data.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    data_js = f"window.GXR_PROFILER_OFFLINE = {data};"

    html = _inline_block(html, "styles", f"<style>{css}</style>")
    html = _inline_block(html, "echarts", f"<script>{echarts}</script>")
    html = _inline_block(html, "app", f"<script>{data_js}</script>\n<script>{appjs}</script>")
    return html.replace("<title>gxr_profiler</title>", "<title>gxr_profiler report</title>")


def generate(labels_list: list[str], runs_dir: str | None = None, out: str | None = None) -> str:
    """Write the report to disk and return its absolute path."""
    html = build(labels_list, runs_dir=runs_dir)
    if out is None:
        name = safe_filename("_vs_".join(labels_list)) + ".html"
        out = os.path.join(default_reports_dir(), name)
    ensure_writable_dir(os.path.dirname(out) or ".")
    atomic_write_text(out, html)
    return os.path.abspath(out)
