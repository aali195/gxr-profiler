"""Shared run-data shaping for the API and offline reports."""

from __future__ import annotations

from ..core.columns import EXTRA_SERIES, TEXT_SERIES
from ..core.parsers.process import is_kernel_process
from . import charts

MAX_POINTS = 1500


def series(df) -> dict:
    """Numeric + text series used by the web app and offline report."""
    import pandas as pd

    band_cols = {b["id"]: b["columns"] for b in charts.spec()["bands"]}
    out: dict = {}
    for g in charts.GROUPS:
        for s in g.series:
            if s.col in df.columns and s.col not in out:
                out[s.col] = [None if v != v else v for v in pd.to_numeric(df[s.col], errors="coerce").tolist()]
        for bid in g.bands:
            cols = [c for c in band_cols.get(bid, []) if c in df.columns]
            if not cols:
                continue
            sub = df[cols].apply(pd.to_numeric, errors="coerce")
            out[f"band::{bid}::max"] = [None if v != v else v for v in sub.max(axis=1).tolist()]
            out[f"band::{bid}::avg"] = [None if v != v else v for v in sub.mean(axis=1).tolist()]
    for col in EXTRA_SERIES:
        if col in df.columns:
            out[col] = [None if v != v else v for v in pd.to_numeric(df[col], errors="coerce").tolist()]
    for col in TEXT_SERIES:
        if col in df.columns:
            out[col] = [None if pd.isna(v) or v == "" else str(v) for v in df[col].tolist()]
    return out


def downsample(elapsed: list[float], series: dict) -> tuple[list[float], dict]:
    """Reduce a run to MAX_POINTS without changing its shape."""
    n = len(elapsed)
    if n <= MAX_POINTS:
        return elapsed, series
    stride = max(1, (n + MAX_POINTS - 1) // MAX_POINTS)
    indices = list(range(0, n, stride))
    if not indices:
        indices = [n - 1]
    elif indices[-1] != n - 1:
        if len(indices) >= MAX_POINTS:
            indices = indices[: MAX_POINTS - 1]
        indices.append(n - 1)
    return [elapsed[i] for i in indices], {k: [v[i] for i in indices] for k, v in series.items()}


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    return value


def _num(procs, col: str):
    import pandas as pd

    if col not in procs.columns:
        return None
    return pd.to_numeric(procs[col], errors="coerce")


def _mean(values) -> float | None:
    vals = [v for v in values if v is not None and not (isinstance(v, float) and v != v)]
    return sum(vals) / len(vals) if vals else None


def _last(values):
    vals = [v for v in values if v is not None and not (isinstance(v, float) and v != v)]
    return vals[-1] if vals else None


def _max(values):
    vals = [v for v in values if v is not None and not (isinstance(v, float) and v != v)]
    return max(vals) if vals else None


def _proc_key(name: str, uid, pid=None) -> str:
    uid_part = "" if uid is None or (isinstance(uid, float) and uid != uid) else str(int(uid))
    pid_part = "" if pid is None or (isinstance(pid, float) and pid != pid) else str(int(pid))
    return f"{name}|{uid_part}|{pid_part}"


def procs_for(store, label: str) -> list[dict]:
    """Aggregate all captured process snapshots, including old top-only runs."""
    procs = store.load_procs(label)
    if procs is None or procs.empty:
        return []
    numeric = (
        "pid",
        "ppid",
        "uid",
        "cpu_pct",
        "cpu_now_pct",
        "cpu_time_s",
        "rss_kb",
        "gpu_mem_kb",
        "io_read_bytes",
        "io_write_bytes",
        "io_read_bps",
        "io_write_bps",
        "net_rx_bytes",
        "net_tx_bytes",
        "net_rx_bps",
        "net_tx_bps",
        "threads",
        "oom_adj",
        "pkg_system",
        "elapsed_s",
    )
    for col in numeric:
        procs[col] = _num(procs, col)
    if "name" not in procs.columns:
        return []
    procs["name"] = procs["name"].fillna("").astype(str)
    if "uid" not in procs.columns:
        procs["uid"] = None
    if "pid" not in procs.columns:
        procs["pid"] = None
    procs["_key"] = [
        _proc_key(name, uid, pid)
        for name, uid, pid in zip(procs["name"].tolist(), procs["uid"].tolist(), procs["pid"].tolist(), strict=False)
    ]

    out: list[dict] = []
    for key, sub in procs.groupby("_key", sort=False):
        sub = sub.sort_values("elapsed_s", na_position="last") if "elapsed_s" in sub.columns else sub
        name = str(_last(sub["name"].tolist()) or "")
        uid_val = _last(sub["uid"].tolist()) if "uid" in sub.columns else None
        uid = int(uid_val) if uid_val is not None and uid_val == uid_val else None
        pid_val = _last(sub["pid"].tolist()) if "pid" in sub.columns else None
        pid = int(pid_val) if pid_val is not None and pid_val == pid_val else None
        kind = _last(sub["kind"].tolist()) if "kind" in sub.columns else None
        if not kind or kind == "unknown":
            if is_kernel_process(int(pid) if pid is not None else 0, name):
                kind = "kernel"
            elif uid is not None and 90000 <= uid < 100000:
                kind = "isolated"
            elif uid is not None and uid >= 10000:
                kind = "app"
            elif uid is not None:
                kind = "system"
            else:
                kind = "unknown"
        package = ""
        if "package" in sub.columns:
            for value in sub["package"].tolist():
                if value is None or (isinstance(value, float) and value != value):
                    continue
                text = str(value)
                if text not in ("", "nan", "None", "<NA>"):
                    package = text
        pkg_system = False
        if "pkg_system" in sub.columns:
            for value in sub["pkg_system"].tolist():
                if value is None or (isinstance(value, float) and value != value):
                    continue
                try:
                    if bool(value):
                        pkg_system = True
                        break
                except (TypeError, ValueError):
                    continue
        cpu = _mean(sub["cpu_pct"].tolist()) if "cpu_pct" in sub.columns else None
        cpu_now = _mean(sub["cpu_now_pct"].tolist()) if "cpu_now_pct" in sub.columns else None
        cpu_peak_now = _max(sub["cpu_now_pct"].tolist()) if "cpu_now_pct" in sub.columns else None
        cpu_peak = (
            cpu_peak_now
            if cpu_peak_now is not None
            else (_max(sub["cpu_pct"].tolist()) if "cpu_pct" in sub.columns else None)
        )
        cpu_last = _last(sub["cpu_now_pct"].tolist()) if "cpu_now_pct" in sub.columns else None
        if cpu_last is None and "cpu_pct" in sub.columns:
            cpu_last = _last(sub["cpu_pct"].tolist())
        oom_adj = _last(sub["oom_adj"].tolist()) if "oom_adj" in sub.columns else None
        oom_class = _last(sub["oom_class"].tolist()) if "oom_class" in sub.columns else None
        if not oom_class and oom_adj is not None:
            oom_class = _oom_class(oom_adj)
        row = {
            "key": key,
            "name": name,
            "pid": pid,
            "ppid": int(_last(sub["ppid"].tolist()))
            if "ppid" in sub.columns and _last(sub["ppid"].tolist()) is not None
            else None,
            "uid": uid,
            "kind": kind,
            "package": package,
            "pkg_system": pkg_system,
            "cpu": cpu,
            "cpu_now": cpu_now,
            "cpu_peak": cpu_peak,
            "cpu_last": cpu_last,
            "cpu_time": _max(sub["cpu_time_s"].tolist()) if "cpu_time_s" in sub.columns else None,
            "rss": _mean(sub["rss_kb"].tolist()) if "rss_kb" in sub.columns else None,
            "rss_peak": _max(sub["rss_kb"].tolist()) if "rss_kb" in sub.columns else None,
            "gpu": _mean(sub["gpu_mem_kb"].tolist()) if "gpu_mem_kb" in sub.columns else None,
            "gpu_peak": _max(sub["gpu_mem_kb"].tolist()) if "gpu_mem_kb" in sub.columns else None,
            "io_r": _mean(sub["io_read_bps"].tolist()) if "io_read_bps" in sub.columns else None,
            "io_w": _mean(sub["io_write_bps"].tolist()) if "io_write_bps" in sub.columns else None,
            "io_r_peak": _max(sub["io_read_bps"].tolist()) if "io_read_bps" in sub.columns else None,
            "io_w_peak": _max(sub["io_write_bps"].tolist()) if "io_write_bps" in sub.columns else None,
            "rx": _max(sub["net_rx_bytes"].tolist()) if "net_rx_bytes" in sub.columns else None,
            "tx": _max(sub["net_tx_bytes"].tolist()) if "net_tx_bytes" in sub.columns else None,
            "rx_bps": _mean(sub["net_rx_bps"].tolist()) if "net_rx_bps" in sub.columns else None,
            "tx_bps": _mean(sub["net_tx_bps"].tolist()) if "net_tx_bps" in sub.columns else None,
            "rx_peak": _max(sub["net_rx_bps"].tolist()) if "net_rx_bps" in sub.columns else None,
            "tx_peak": _max(sub["net_tx_bps"].tolist()) if "net_tx_bps" in sub.columns else None,
            "state": _last(sub["state"].tolist()) if "state" in sub.columns else None,
            "threads": int(_last(sub["threads"].tolist()))
            if "threads" in sub.columns and _last(sub["threads"].tolist()) is not None
            else None,
            "oom_adj": int(oom_adj) if oom_adj is not None else None,
            "oom_class": oom_class or "",
            "samples": len(sub),
        }
        out.append({k: _clean(v) for k, v in row.items()})
    return out


def _oom_class(adj: float) -> str:
    if adj < 0:
        return "system"
    if adj < 100:
        return "foreground"
    if adj < 200:
        return "visible"
    if adj < 300:
        return "perceptible"
    if adj < 900:
        return "background"
    return "cached"


def process_series_for(store, label: str) -> dict:
    """Per-process time series for the selected-process chart."""
    procs = store.load_procs(label)
    if procs is None or procs.empty or "name" not in procs.columns:
        return {}
    if not {"pid", "uid", "elapsed_s"} <= set(procs.columns):
        return {}
    for col in (
        "pid",
        "uid",
        "elapsed_s",
        "cpu_pct",
        "cpu_now_pct",
        "rss_kb",
        "gpu_mem_kb",
        "io_read_bps",
        "io_write_bps",
        "net_rx_bps",
        "net_tx_bps",
    ):
        if col in procs.columns:
            procs[col] = _num(procs, col)
    procs["name"] = procs["name"].fillna("").astype(str)
    procs["_key"] = [
        _proc_key(name, uid, pid)
        for name, uid, pid in zip(procs["name"].tolist(), procs["uid"].tolist(), procs["pid"].tolist(), strict=False)
    ]
    out: dict = {}
    for key, sub in procs.groupby("_key", sort=False):
        sub = sub.sort_values("elapsed_s", na_position="last")
        elapsed = [None if v != v else float(v) for v in sub["elapsed_s"].tolist()]

        def values(col: str, frame=sub):
            if col not in frame.columns:
                return [None] * len(frame)
            vals = frame[col].tolist()
            return [None if v is None or v != v else float(v) for v in vals]

        cpu_now = values("cpu_now_pct")
        cpu_5m = values("cpu_pct")
        cpu = [a if a is not None else b for a, b in zip(cpu_now, cpu_5m, strict=False)]
        uid_val = _last([v for v in sub["uid"].tolist() if v == v])
        metrics = {
            "cpu": cpu,
            "cpu_5m": cpu_5m,
            "rss": values("rss_kb"),
            "gpu": values("gpu_mem_kb"),
            "io_r": values("io_read_bps"),
            "io_w": values("io_write_bps"),
            "net_rx": values("net_rx_bps"),
            "net_tx": values("net_tx_bps"),
        }
        elapsed, metrics = downsample(elapsed, metrics)
        out[key] = {
            "key": key,
            "name": str(_last(sub["name"].tolist()) or ""),
            "uid": int(uid_val) if uid_val is not None else None,
            "elapsed": elapsed,
            **metrics,
        }
    return out
