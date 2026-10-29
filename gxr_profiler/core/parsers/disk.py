"""Storage I/O counters from /proc/diskstats and /proc/pressure/io."""

from __future__ import annotations

import re

SECTOR_BYTES = 512
DISK_RAW_KEYS = (
    "disk_stat_reads",
    "disk_stat_writes",
    "disk_stat_read_bytes",
    "disk_stat_write_bytes",
    "disk_stat_io_ms",
    "disk_stat_weighted_ms",
)

_BASE_DEVICE = re.compile(r"^(?:sd[a-z]+|mmcblk[0-9]+|nvme[0-9]+n[0-9]+|vd[a-z]+|xvd[a-z]+)$")
_PSI = re.compile(r"^(some|full)\s+avg10=([\d.]+)")


def _is_base_device(name: str) -> bool:
    return bool(_BASE_DEVICE.match(name))


def parse_diskstats(lines: list[str]) -> dict[str, float]:
    """Aggregate whole-device counters, excluding partitions, dm, loop and zram."""
    totals = dict.fromkeys(DISK_RAW_KEYS, 0.0)
    found = False
    for line in lines:
        parts = line.split()
        if len(parts) < 14:
            continue
        if not _is_base_device(parts[2]):
            continue
        try:
            reads = int(parts[3])
            sectors_read = int(parts[5])
            writes = int(parts[7])
            sectors_written = int(parts[9])
            io_ms = int(parts[12])
            weighted_ms = int(parts[13])
        except ValueError:
            continue
        found = True
        totals["disk_stat_reads"] += reads
        totals["disk_stat_writes"] += writes
        totals["disk_stat_read_bytes"] += sectors_read * SECTOR_BYTES
        totals["disk_stat_write_bytes"] += sectors_written * SECTOR_BYTES
        totals["disk_stat_io_ms"] += io_ms
        totals["disk_stat_weighted_ms"] += weighted_ms
    return totals if found else {}


def parse_psi_io(lines: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in lines:
        m = _PSI.match(line.strip())
        if m:
            out[f"disk_io_pressure_{m.group(1)}"] = float(m.group(2))
    return out


def disk_rates(current: dict[str, float], previous: dict[str, float], dt: float) -> dict[str, float]:
    """Convert cumulative counters into rates over ``dt`` seconds."""
    if not current or not previous or dt <= 0:
        return {}
    read_delta = current["disk_stat_read_bytes"] - previous["disk_stat_read_bytes"]
    write_delta = current["disk_stat_write_bytes"] - previous["disk_stat_write_bytes"]
    read_ops = current["disk_stat_reads"] - previous["disk_stat_reads"]
    write_ops = current["disk_stat_writes"] - previous["disk_stat_writes"]
    io_delta = current["disk_stat_io_ms"] - previous["disk_stat_io_ms"]
    weighted_delta = current["disk_stat_weighted_ms"] - previous["disk_stat_weighted_ms"]
    ops = read_ops + write_ops
    return {
        "disk_read_mbps": max(0.0, read_delta) / dt / 1e6,
        "disk_write_mbps": max(0.0, write_delta) / dt / 1e6,
        "disk_read_iops": max(0.0, read_ops) / dt,
        "disk_write_iops": max(0.0, write_ops) / dt,
        "disk_busy_pct": min(100.0, max(0.0, io_delta) / (dt * 1000.0) * 100.0),
        "disk_io_latency_ms": (max(0.0, weighted_delta) / ops) if ops > 0 else 0.0,
    }
