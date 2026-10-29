from gxr_profiler.core import parsers as P

DISKSTATS = """   8       0 sda 100 0 2048 10 50 0 4096 20 0 30 40 0 0 0 0 0 0
   8       1 sda1 100 0 2048 10 50 0 4096 20 0 30 40 0 0 0 0 0 0
   7       0 loop0 1 0 8 0 1 0 8 0 0 1 1 0 0 0 0 0 0
 253       0 dm-0 1 0 8 0 1 0 8 0 0 1 1 0 0 0 0 0 0
"""

PSI = """some avg10=1.23 avg60=0.50 avg300=0.10 total=123
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
"""


def test_parse_diskstats_aggregates_only_whole_devices():
    d = P.parse_diskstats(DISKSTATS.splitlines())
    assert d["disk_stat_reads"] == 100
    assert d["disk_stat_writes"] == 50
    assert d["disk_stat_read_bytes"] == 2048 * 512
    assert d["disk_stat_write_bytes"] == 4096 * 512
    assert d["disk_stat_io_ms"] == 30
    assert d["disk_stat_weighted_ms"] == 40


def test_parse_psi_io():
    d = P.parse_psi_io(PSI.splitlines())
    assert d["disk_io_pressure_some"] == 1.23
    assert d["disk_io_pressure_full"] == 0.0


def test_disk_rates():
    previous = {
        "disk_stat_reads": 10,
        "disk_stat_writes": 20,
        "disk_stat_read_bytes": 1024,
        "disk_stat_write_bytes": 2048,
        "disk_stat_io_ms": 100,
        "disk_stat_weighted_ms": 200,
    }
    current = {
        "disk_stat_reads": 20,
        "disk_stat_writes": 40,
        "disk_stat_read_bytes": 1024 + 1_000_000,
        "disk_stat_write_bytes": 2048 + 2_000_000,
        "disk_stat_io_ms": 600,
        "disk_stat_weighted_ms": 3200,
    }
    r = P.disk_rates(current, previous, dt=1.0)
    assert r["disk_read_mbps"] == 1.0
    assert r["disk_write_mbps"] == 2.0
    assert r["disk_read_iops"] == 10.0
    assert r["disk_write_iops"] == 20.0
    assert r["disk_busy_pct"] == 50.0
    assert r["disk_io_latency_ms"] == 100.0
    assert P.disk_rates(current, previous, dt=0) == {}


class _SequencedAdb:
    def __init__(self, responses):
        self.responses = list(responses)

    def shell(self, script, timeout=25.0):
        return self.responses.pop(0)

    def run(self, args, timeout=25.0):
        raise AssertionError("unexpected run")

    def popen(self, args):
        raise AssertionError("unexpected popen")


def test_poller_derives_disk_rates(monkeypatch):
    from gxr_profiler.capture import poller

    first = "###DISK\n   8 0 sda 100 0 2048 10 50 0 4096 20 0 30 40 0 0 0 0 0 0\n"
    second = "###DISK\n   8 0 sda 120 0 4096 10 60 0 6144 20 0 530 1040 0 0 0 0 0 0\n"
    ticks = iter([100.0, 101.0])
    monkeypatch.setattr(poller.time, "monotonic", lambda: next(ticks))
    p = poller.Poller(_SequencedAdb([first, second]))
    assert "disk_read_mbps" not in p.poll()
    out = p.poll()
    assert out["disk_read_mbps"] == 1.048576
    assert out["disk_write_mbps"] == 1.048576
    assert out["disk_read_iops"] == 20.0
    assert out["disk_write_iops"] == 10.0
    assert out["disk_busy_pct"] == 50.0
    assert out["disk_io_latency_ms"] == (1000.0 / 30.0)
