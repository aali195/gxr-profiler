import csv
from pathlib import Path

from gxr_profiler.capture.processes import ProcessSampler
from gxr_profiler.capture.writer import RunWriter
from gxr_profiler.core import parsers as P
from gxr_profiler.core.columns import PROC_COLUMNS
from gxr_profiler.report.data import process_series_for, procs_for
from gxr_profiler.runs.store import RunStore
from tests.fake_adb import FakeAdb

STAT = """###STAT
/proc/10/stat:10 (init) S 1 0 0 0 0 0 0 0 0 0 100 50 0 0 20 0 10 0 1000 0 0
/proc/20/stat:20 (com.foo) S 1 0 0 0 0 0 0 0 0 0 200 90 0 0 20 0 12 0 1001 0 0
/proc/2/stat:2 ([kthreadd]) S 0 0 0 0 0 0 0 0 0 0 1 1 0 0 20 0 1 0 1 0 0
###OOM
/proc/10/oom_score_adj:-800
/proc/20/oom_score_adj:905
/proc/2/oom_score_adj:-1000
###PS
  10 1000 2048 init
  20 10000 2048 com.foo
  2 0 0 [kthreadd]
"""

PACKAGES = """###PKGS
package:com.foo uid:10000
###SYSPKGS
package:com.android.systemui
"""


def test_process_parsers():
    stats = P.parse_proc_stats(STAT.split("###STAT\n", 1)[1].split("###OOM", 1)[0])
    assert stats[20]["state"] == "S"
    assert stats[20]["utime"] == 200
    assert stats[20]["threads"] == 12
    assert stats[20]["starttime"] == 1001
    assert P.parse_oom_scores(STAT.split("###OOM\n", 1)[1].split("###PS", 1)[0])[20] == 905
    assert P.parse_package_uids(PACKAGES.split("###PKGS\n", 1)[1].split("###SYSPKGS", 1)[0])[10000] == ["com.foo"]
    assert P.oom_class(-800) == "system"
    assert P.oom_class(905) == "cached"
    assert P.process_kind(20, "com.foo", 10000, "com.foo", set()) == "app"
    assert P.is_kernel_process(2, "[kthreadd]")
    assert P.is_kernel_process(123, "kworker/4")


def test_process_sampler_all_non_kernel(tmp_path):
    adb = FakeAdb(process_response=STAT, package_response=PACKAGES)
    writer = RunWriter(str(tmp_path), "all")
    writer.open(with_procs=True)
    sampler = ProcessSampler(adb, writer, top=0, include_kernel=False)
    sampler.poll(10.0, 0.0)
    adb.process_response = STAT.replace("200 90", "300 100")
    sampler.poll(15.0, 0.0)
    writer.close()

    with Path(writer.procs_path).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4  # 2 processes x 2 snapshots
    assert {r["name"] for r in rows} == {"init", "com.foo"}
    foo = next(r for r in rows if r["name"] == "com.foo" and r["cpu_now_pct"])
    assert foo["uid"] == "10000"
    assert foo["kind"] == "app"
    assert foo["package"] == "com.foo"
    assert foo["oom_class"] == "cached"
    assert float(foo["cpu_now_pct"]) > 0
    assert "cpu_time_s" in foo


def test_process_sampler_kernel_opt_in(tmp_path):
    adb = FakeAdb(process_response=STAT, package_response=PACKAGES)
    writer = RunWriter(str(tmp_path), "kernel")
    writer.open(with_procs=True)
    sampler = ProcessSampler(adb, writer, top=0, include_kernel=True)
    sampler.poll(10.0, 0.0)
    writer.close()
    with Path(writer.procs_path).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert {r["name"] for r in rows} == {"init", "com.foo", "[kthreadd]"}


def test_procs_for_aggregates_and_series(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    run = runs / "all"
    run.mkdir()
    path = run / "procs.csv"
    rows = []
    for i, name in enumerate(("init", "com.foo")):
        rows.append(
            {
                "ts_host": "1",
                "ts_dev": "x",
                "elapsed_s": "0",
                "pid": str(10 + i),
                "ppid": "1",
                "uid": str(1000 + i * 9000),
                "name": name,
                "kind": "system" if name == "init" else "app",
                "package": "" if name == "init" else "com.foo",
                "pkg_system": "0",
                "cpu_pct": "1",
                "cpu_now_pct": "2",
                "cpu_time_s": "10",
                "rss_kb": "2048",
                "gpu_mem_kb": "4096",
                "io_read_bytes": "1",
                "io_write_bytes": "2",
                "io_read_bps": "3",
                "io_write_bps": "4",
                "net_rx_bytes": "5",
                "net_tx_bytes": "6",
                "net_rx_bps": "7",
                "net_tx_bps": "8",
                "state": "S",
                "threads": "3",
                "oom_adj": "905" if name == "com.foo" else "-800",
                "oom_class": "cached" if name == "com.foo" else "system",
            }
        )
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=PROC_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    store = RunStore(str(runs))
    got = procs_for(store, "all")
    assert len(got) == 2
    foo = next(r for r in got if r["name"] == "com.foo")
    assert foo["key"] == "com.foo|10000|11"
    assert foo["package"] == "com.foo"
    assert foo["oom_class"] == "cached"
    assert foo["cpu_peak"] == 2
    series = process_series_for(store, "all")
    assert series[foo["key"]]["elapsed"] == [0.0]
    assert series[foo["key"]]["cpu"] == [2.0]
