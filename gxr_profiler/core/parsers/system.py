"""Battery, Wi-Fi, memory, load and GPU-busy parsing."""

from __future__ import annotations

import re


def parse_battery(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"level:\s*(\d+)", line)
        if m:
            out["batt_level"] = float(m.group(1))
        m = re.match(r"temperature:\s*(-?\d+)", line)
        if m:
            out["batt_temp"] = float(m.group(1)) / 10.0
        m = re.match(r"status:\s*(\d+)", line)
        if m:
            out["batt_status"] = float(m.group(1))
        m = re.match(r"AC powered:\s*(true|false)", line)
        if m:
            out["batt_ac"] = 1.0 if m.group(1) == "true" else 0.0
        m = re.match(r"USB powered:\s*(true|false)", line)
        if m:
            out["batt_usb"] = 1.0 if m.group(1) == "true" else 0.0
    return out


def parse_wifi_status(text: str) -> dict[str, float]:
    out: dict[str, float] = {}

    def grab(key: str, pattern: str) -> None:
        m = re.search(pattern, text)
        if m:
            out[key] = float(m.group(1))

    grab("wifi_rssi", r"RSSI:\s*(-?\d+)")
    grab("wifi_tx", r"\bTx Link speed:\s*(\d+)")
    grab("wifi_rx", r"\bRx Link speed:\s*(\d+)")
    grab("wifi_link", r"(?<!Tx )(?<!Rx )\bLink speed:\s*(\d+)")
    grab("wifi_freq", r"Frequency:\s*(\d+)")
    grab("wifi_std", r"Wi-Fi standard:\s*(\d+)")
    grab("wifi_max_tx", r"Max Supported Tx Link speed:\s*(\d+)")
    grab("wifi_max_rx", r"Max Supported Rx Link speed:\s*(\d+)")
    grab("wifi_tx_retries", r"retriedTxPackets:\s*(\d+)")
    grab("wifi_lost", r"lostTxPackets:\s*(\d+)")
    grab("wifi_tx_pkts", r"successfulTxPackets:\s*(\d+)")
    grab("wifi_rx_pkts", r"successfulRxPackets:\s*(\d+)")
    grab("wifi_tx_pps", r"successfulTxPacketsPerSecond:\s*([0-9.]+)")
    grab("wifi_rx_pps", r"successfulRxPacketsPerSecond:\s*([0-9.]+)")
    grab("wifi_retry_pps", r"retriedTxPacketsPerSecond:\s*([0-9.]+)")
    grab("wifi_lost_pps", r"lostTxPacketsPerSecond:\s*([0-9.]+)")
    if out.get("wifi_tx_pps"):
        out["wifi_retry_pct"] = 100.0 * out.get("wifi_retry_pps", 0.0) / out["wifi_tx_pps"]
    return out


NETDEV_RAW_KEYS = [
    "netdev_rx_bytes",
    "netdev_rx_packets",
    "netdev_rx_errors",
    "netdev_rx_drops",
    "netdev_tx_bytes",
    "netdev_tx_packets",
    "netdev_tx_errors",
    "netdev_tx_drops",
]


def parse_netdev(lines: list[str]) -> dict[str, float]:
    """Parse the wlan0 row from /proc/net/dev (cumulative counters)."""
    for line in lines:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        if name.strip() != "wlan0":
            continue
        fields = rest.split()
        if len(fields) < 16:
            return {}
        try:
            rx_bytes, rx_packets, rx_errors, rx_drops = (int(v) for v in fields[:4])
            tx_bytes, tx_packets, tx_errors, tx_drops = (int(v) for v in fields[8:12])
        except ValueError:
            return {}
        return {
            "netdev_rx_bytes": float(rx_bytes),
            "netdev_rx_packets": float(rx_packets),
            "netdev_rx_errors": float(rx_errors),
            "netdev_rx_drops": float(rx_drops),
            "netdev_tx_bytes": float(tx_bytes),
            "netdev_tx_packets": float(tx_packets),
            "netdev_tx_errors": float(tx_errors),
            "netdev_tx_drops": float(tx_drops),
        }
    return {}


def netdev_rates(current: dict[str, float], previous: dict[str, float], dt: float) -> dict[str, float]:
    out = {
        "wifi_rx_drops": current.get("netdev_rx_drops", 0.0),
        "wifi_tx_drops": current.get("netdev_tx_drops", 0.0),
        "wifi_rx_errors": current.get("netdev_rx_errors", 0.0),
        "wifi_tx_errors": current.get("netdev_tx_errors", 0.0),
    }
    if dt <= 0:
        return out
    rx_bytes = current.get("netdev_rx_bytes", 0.0) - previous.get("netdev_rx_bytes", 0.0)
    tx_bytes = current.get("netdev_tx_bytes", 0.0) - previous.get("netdev_tx_bytes", 0.0)
    out["wifi_rx_mbps"] = max(0.0, rx_bytes * 8.0 / dt / 1e6)
    out["wifi_tx_mbps"] = max(0.0, tx_bytes * 8.0 / dt / 1e6)
    return out


def parse_gpubusy(text: str) -> dict[str, float]:
    nums = re.findall(r"-?\d+", text)
    out: dict[str, float] = {}
    if len(nums) >= 2:
        out["g_busy_num"] = float(nums[0])
        out["g_busy_den"] = float(nums[1])
    return out


def parse_loadavg(text: str) -> dict[str, float]:
    parts = text.split()
    out: dict[str, float] = {}
    if len(parts) >= 3:
        try:
            out["load1"] = float(parts[0])
            out["load5"] = float(parts[1])
            out["load15"] = float(parts[2])
        except ValueError:
            pass
    if len(parts) >= 4 and "/" in parts[3]:
        run, total = parts[3].split("/", 1)
        try:
            out["procs_running"] = float(run)
            out["procs_total"] = float(total)
        except ValueError:
            pass
    return out


_MEM_KEYS = {
    "MemTotal": "mem_total",
    "MemFree": "mem_free",
    "MemAvailable": "mem_available",
    "Cached": "mem_cached",
    "Buffers": "mem_buffers",
    "SwapTotal": "swap_total",
    "SwapFree": "swap_free",
    "Dirty": "mem_dirty",
    "Writeback": "mem_writeback",
}


def parse_meminfo(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s*(\d+)", line.strip())
        if m and m.group(1) in _MEM_KEYS:
            values[_MEM_KEYS[m.group(1)]] = float(m.group(2))
    out = dict(values)
    total = values.get("mem_total")
    available = values.get("mem_available")
    if total and available is not None:
        used = max(0.0, total - available)
        out["mem_used"] = used
        out["mem_used_pct"] = used / total * 100.0
    swap_total = values.get("swap_total")
    swap_free = values.get("swap_free")
    if swap_total and swap_free is not None:
        used = max(0.0, swap_total - swap_free)
        out["swap_used"] = used
        out["swap_used_pct"] = used / swap_total * 100.0
    return out


CPU_STAT_CORES = 6


def parse_proc_stat(lines: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        if parts[0].startswith("cpu") and parts[0][3:].isdigit():
            core = int(parts[0][3:])
            if core >= CPU_STAT_CORES:
                continue
            try:
                nums = [int(x) for x in parts[1:9]]
            except ValueError:
                continue
            if len(nums) >= 8:
                out[f"cpu_stat{core}_total"] = float(sum(nums))
                out[f"cpu_stat{core}_idle"] = float(nums[3] + nums[4])
        elif parts[0] == "procs_running" and len(parts) >= 2:
            out["procs_running"] = float(parts[1])
    return out


CPU_STAT_RAW_KEYS = [f"cpu_stat{i}_{kind}" for i in range(CPU_STAT_CORES) for kind in ("total", "idle")]


def cpu_rates(current: dict[str, float], previous: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for core in range(CPU_STAT_CORES):
        total = current.get(f"cpu_stat{core}_total", 0.0) - previous.get(f"cpu_stat{core}_total", 0.0)
        idle = current.get(f"cpu_stat{core}_idle", 0.0) - previous.get(f"cpu_stat{core}_idle", 0.0)
        if total > 0:
            out[f"cpu_util{core}"] = min(100.0, max(0.0, 100.0 * (1.0 - idle / total)))
    return out


def parse_psi_memory(lines: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in lines:
        m = re.match(r"^(some|full)\s+avg10=([\d.]+)", line.strip())
        if m:
            out[f"mem_pressure_{m.group(1)}"] = float(m.group(2))
    return out


def parse_zram(lines: list[str]) -> dict[str, float]:
    if not lines:
        return {}
    parts = lines[0].split()
    if len(parts) < 3:
        return {}
    try:
        return {"zram_used_mb": float(parts[2]) / 1e6}
    except ValueError:
        return {}


def parse_df_usage(lines: list[str]) -> dict[str, float]:
    for line in reversed(lines):
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            return {
                "disk_total_gb": float(parts[1]) / 1048576,
                "disk_free_gb": float(parts[3]) / 1048576,
                "disk_used_pct": float(parts[4].rstrip("%")),
            }
        except ValueError:
            continue
    return {}
