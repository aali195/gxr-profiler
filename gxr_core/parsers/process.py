"""Per-process snapshot parsing."""

from __future__ import annotations

import re

CPUINFO_RE = re.compile(r"^\s*([\d.]+)%\s+(\d+)/(.+?):", re.MULTILINE)
PS_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s*$", re.MULTILINE)
GPU_PROC_RE = re.compile(r"^\s*Proc\s+(\d+)\s+total:\s*(\d+)\s*$", re.MULTILINE)
NET_UID_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", re.MULTILINE)
PROC_IO_PID_RE = re.compile(r"^PID\s+(\d+)")
PROC_IO_KEY_RE = re.compile(r"^(read_bytes|write_bytes):\s*(\d+)")
PROC_IO_PATH_RE = re.compile(r"^/proc/(\d+)/io:(read_bytes|write_bytes):\s*(\d+)")
PROC_STAT_PATH_RE = re.compile(r"^/proc/(\d+)/stat:(.*)$")
OOM_PATH_RE = re.compile(r"^/proc/(\d+)/oom_score_adj:\s*(-?\d+)")
PACKAGE_UID_RE = re.compile(r"^package:(\S+)\s+uid:(\d+)")


def parse_cpuinfo(text: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for cpu, pid, name in CPUINFO_RE.findall(text):
        out[int(pid)] = {"cpu_pct": float(cpu), "name": name.strip()}
    return out


def parse_ps(text: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for pid, uid, rss, name in PS_RE.findall(text):
        out[int(pid)] = {"uid": int(uid), "rss_kb": float(rss), "name": name.strip()}
    return out


def parse_gpu_mem(text: str) -> dict[int, float]:
    return {int(pid): float(total) / 1024.0 for pid, total in GPU_PROC_RE.findall(text)}


def parse_netstats_uid(text: str) -> dict[int, dict]:
    """Parse the per-UID byte table (last occurrence; ignores ': OK' placeholders)."""
    marker = "uid rxBytes rxPackets txBytes txPackets"
    idx = text.rfind(marker)
    if idx == -1:
        return {}
    out: dict[int, dict] = {}
    started = False
    for line in text[idx + len(marker) :].splitlines():
        s = line.strip()
        if not s:
            if started:
                break
            continue
        m = NET_UID_RE.match(s)
        if m:
            started = True
            uid, rx, _rxp, tx, _txp = m.groups()
            out[int(uid)] = {"net_rx_bytes": float(rx), "net_tx_bytes": float(tx)}
        elif started:
            break
    return out


def parse_proc_io(text: str) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    pid: int | None = None
    for line in text.splitlines():
        s = line.strip()
        m = PROC_IO_PID_RE.match(s)
        if m:
            pid = int(m.group(1))
            out[pid] = {}
            continue
        m = PROC_IO_KEY_RE.match(s)
        if m and pid is not None:
            out[pid][m.group(1)] = float(m.group(2))
    return out


def parse_proc_stats(text: str) -> dict[int, dict]:
    """Parse /proc/<pid>/stat lines, including ``grep -H`` path prefixes."""
    out: dict[int, dict] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = PROC_STAT_PATH_RE.match(line)
        if m:
            pid = int(m.group(1))
            rest = m.group(2).strip()
        else:
            first = line.split(None, 1)
            if len(first) != 2 or not first[0].isdigit():
                continue
            pid = int(first[0])
            rest = first[1]
        close = rest.rfind(")")
        if close < 0:
            continue
        comm = rest[rest.find("(") + 1 : close]
        fields = rest[close + 2 :].split()
        if len(fields) < 22:
            continue
        try:
            out[pid] = {
                "comm": comm,
                "state": fields[0],
                "ppid": int(fields[1]),
                "utime": float(fields[11]),
                "stime": float(fields[12]),
                "threads": int(fields[17]),
                "starttime": int(fields[19]),
                "rss_pages": float(fields[21]),
            }
        except (ValueError, IndexError):
            continue
    return out


def parse_oom_scores(text: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for raw in text.splitlines():
        m = OOM_PATH_RE.match(raw.strip())
        if m:
            out[int(m.group(1))] = int(m.group(2))
    return out


def parse_proc_io_paths(text: str) -> dict[int, dict[str, float]]:
    """Parse ``grep -H ... /proc/<pid>/io`` output."""
    out: dict[int, dict[str, float]] = {}
    for raw in text.splitlines():
        m = PROC_IO_PATH_RE.match(raw.strip())
        if m:
            out.setdefault(int(m.group(1)), {})[m.group(2)] = float(m.group(3))
    return out


def parse_package_uids(text: str) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for raw in text.splitlines():
        m = PACKAGE_UID_RE.match(raw.strip())
        if m:
            out.setdefault(int(m.group(2)), []).append(m.group(1))
    return out


def parse_system_packages(text: str) -> set[str]:
    out: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            out.add(line[8:].strip())
    return out


KERNEL_PREFIXES = (
    "kworker",
    "ksoftirqd",
    "kthreadd",
    "kswapd",
    "rcu",
    "migration/",
    "irq/",
    "oom_reaper",
    "watchdog/",
)


def is_kernel_process(pid: int, name: str) -> bool:
    return pid == 2 or name.startswith("[") or name.startswith(KERNEL_PREFIXES)


def process_kind(pid: int, name: str, uid: int | None, package: str, system_packages: set[str]) -> str:
    if is_kernel_process(pid, name):
        return "kernel"
    if uid is not None and 90000 <= uid < 100000:
        return "isolated"
    if package and package in system_packages:
        return "system"
    if uid is not None and uid >= 10000:
        return "app"
    if uid is not None:
        return "system"
    return "unknown"


def oom_class(adj: int | None) -> str:
    if adj is None:
        return ""
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
