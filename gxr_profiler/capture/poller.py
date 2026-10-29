"""The 1 Hz read-only device poll (clocks, GPU, sensors, memory, battery, wifi)."""

from __future__ import annotations

import time

from ..core import parsers as P
from ..core.adb import AdbClient

POLL_SCRIPT = r"""
echo '###FREQ'
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null
echo '###PMAX'
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq 2>/dev/null
cat /sys/devices/system/cpu/cpufreq/policy2/scaling_max_freq 2>/dev/null
echo '###GCLK'
cat /sys/class/kgsl/kgsl-3d0/clock_mhz 2>/dev/null
echo '###GBUSY'
cat /sys/class/kgsl/kgsl-3d0/gpu_busy_percentage 2>/dev/null
echo '###GBUSYN'
cat /sys/class/kgsl/kgsl-3d0/gpubusy 2>/dev/null
echo '###GTMP'
cat /sys/class/kgsl/kgsl-3d0/temp 2>/dev/null
echo '###GTHR'
cat /sys/class/kgsl/kgsl-3d0/throttling 2>/dev/null
echo '###SEC'
cat /sys/class/sec/sec-ap-thermistor/temperature 2>/dev/null
cat /sys/class/sec/sec-lp-thermistor/temperature 2>/dev/null
cat /sys/class/sec/sec-wf-thermistor/temperature 2>/dev/null
echo '###LOAD'
cat /proc/loadavg 2>/dev/null
echo '###MEM'
grep -E '^(MemTotal|MemFree|MemAvailable|Cached|SwapTotal|SwapFree):' /proc/meminfo 2>/dev/null
echo '###STAT'
grep -E '^cpu|^procs_running' /proc/stat 2>/dev/null
echo '###PRESSURE_MEM'
cat /proc/pressure/memory 2>/dev/null
echo '###ZRAM'
cat /sys/block/zram0/mm_stat 2>/dev/null
echo '###DF'
df -k /data 2>/dev/null | tail -n 1
echo '###BATT'
dumpsys battery 2>/dev/null
echo '###WIFI'
cmd wifi status 2>/dev/null
echo '###NETDEV'
cat /proc/net/dev 2>/dev/null
echo '###BT'
settings get global bluetooth_on 2>/dev/null
dumpsys bluetooth_manager 2>/dev/null | grep -m2 -E '^  enabled:|^  state:'
echo '###LOC'
settings get secure location_mode 2>/dev/null
settings get secure location_providers_allowed 2>/dev/null
cmd location is-location-enabled 2>/dev/null
echo '###DISK'
cat /proc/diskstats 2>/dev/null
cat /proc/pressure/io 2>/dev/null
echo '###THERM'
dumpsys thermalservice 2>/dev/null
echo '###END'
"""

FAN_SECTION = r"""
echo '###FAN'
su -c 'cat /sys/class/sec_fan/fan/curr_rpm; cat /sys/class/sec_fan/fan/curr_rpm2; cat /sys/class/sec_fan/fan/get_status' 2>/dev/null
"""


def _ints(lines: list[str]) -> list[float]:
    out: list[float] = []
    for ln in lines:
        for tok in ln.replace("%", " ").split():
            try:
                out.append(float(tok))
            except ValueError:
                pass
    return out


def parse_poll(text: str) -> dict[str, float | str]:
    sec = P.split_sections(text)
    out: dict[str, float | str] = {}

    for i, v in enumerate(_ints(sec.get("FREQ", []))[:6]):
        out[f"f_cpu{i}"] = v

    pmax = _ints(sec.get("PMAX", []))
    if len(pmax) >= 1:
        out["cpu_max0"] = pmax[0]
    if len(pmax) >= 2:
        out["cpu_max2"] = pmax[1]

    def first(name: str) -> float | None:
        vals = _ints(sec.get(name, []))
        return vals[0] if vals else None

    gc = first("GCLK")
    if gc is not None:
        out["g_clock"] = gc
        out["g_devfreq"] = gc * 1_000_000.0
    gb = first("GBUSY")
    if gb is not None:
        out["g_busy"] = gb
    gt = first("GTMP")
    if gt is not None:
        out["g_temp"] = gt / 1000.0
    gth = first("GTHR")
    if gth is not None:
        out["g_throttling"] = gth
    out.update(P.parse_gpubusy(" ".join(sec.get("GBUSYN", []))))

    sec_t = _ints(sec.get("SEC", []))
    for i, key in enumerate(["sec_ap", "sec_lp", "sec_wf"]):
        if i < len(sec_t):
            out[key] = sec_t[i] / 10.0

    out.update(P.parse_loadavg(" ".join(sec.get("LOAD", []))))
    out.update(P.parse_meminfo("\n".join(sec.get("MEM", []))))
    out.update(P.parse_proc_stat(sec.get("STAT", [])))
    out.update(P.parse_psi_memory(sec.get("PRESSURE_MEM", [])))
    out.update(P.parse_zram(sec.get("ZRAM", [])))
    out.update(P.parse_df_usage(sec.get("DF", [])))
    out.update(P.parse_battery("\n".join(sec.get("BATT", []))))
    out.update(P.parse_wifi_status("\n".join(sec.get("WIFI", []))))
    out.update(P.parse_netdev(sec.get("NETDEV", [])))
    out.update(P.parse_radios(sec.get("BT", []), sec.get("LOC", [])))
    out.update(P.parse_diskstats(sec.get("DISK", [])))
    out.update(P.parse_psi_io(sec.get("DISK", [])))
    out.update(P.parse_thermalservice("\n".join(sec.get("THERM", []))))
    out.update(P.parse_fan_root(sec.get("FAN", [])))
    return out


# Fast poll: cheap sysfs/proc only, safe at 1 Hz. Slow dumpsys/state commands
# live in STATE_SCRIPT/RADIO_SCRIPT and are merged into MetricState by the
# recorder's auxiliary worker.
FAST_SCRIPT = r"""
echo '###FREQ'
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq 2>/dev/null
echo '###PMAX'
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq 2>/dev/null
cat /sys/devices/system/cpu/cpufreq/policy2/scaling_max_freq 2>/dev/null
echo '###GCLK'
cat /sys/class/kgsl/kgsl-3d0/clock_mhz 2>/dev/null
echo '###GBUSY'
cat /sys/class/kgsl/kgsl-3d0/gpu_busy_percentage 2>/dev/null
echo '###GBUSYN'
cat /sys/class/kgsl/kgsl-3d0/gpubusy 2>/dev/null
echo '###GTMP'
cat /sys/class/kgsl/kgsl-3d0/temp 2>/dev/null
echo '###GTHR'
cat /sys/class/kgsl/kgsl-3d0/throttling 2>/dev/null
echo '###SEC'
cat /sys/class/sec/sec-ap-thermistor/temperature 2>/dev/null
cat /sys/class/sec/sec-lp-thermistor/temperature 2>/dev/null
cat /sys/class/sec/sec-wf-thermistor/temperature 2>/dev/null
echo '###LOAD'
cat /proc/loadavg 2>/dev/null
echo '###MEM'
grep -E '^(MemTotal|MemFree|MemAvailable|Cached|SwapTotal|SwapFree):' /proc/meminfo 2>/dev/null
echo '###STAT'
grep -E '^cpu|^procs_running' /proc/stat 2>/dev/null
echo '###PRESSURE_MEM'
cat /proc/pressure/memory 2>/dev/null
echo '###ZRAM'
cat /sys/block/zram0/mm_stat 2>/dev/null
echo '###NETDEV'
cat /proc/net/dev 2>/dev/null
echo '###DISK'
cat /proc/diskstats 2>/dev/null
cat /proc/pressure/io 2>/dev/null
echo '###END'
"""

STATE_SCRIPT = r"""
echo '###BATT'
dumpsys battery 2>/dev/null
echo '###WIFI'
cmd wifi status 2>/dev/null
echo '###THERM'
dumpsys thermalservice 2>/dev/null
echo '###END'
"""

PREVIEW_SCRIPT = r"""
echo '###BATT'
dumpsys battery 2>/dev/null
echo '###THERM'
dumpsys thermalservice 2>/dev/null
echo '###END'
"""

RADIO_SCRIPT = r"""
echo '###BT'
settings get global bluetooth_on 2>/dev/null
dumpsys bluetooth_manager 2>/dev/null | grep -m2 -E '^  enabled:|^  state:'
echo '###LOC'
settings get secure location_mode 2>/dev/null
settings get secure location_providers_allowed 2>/dev/null
cmd location is-location-enabled 2>/dev/null
echo '###DF'
df -k /data 2>/dev/null | tail -n 1
echo '###END'
"""


class Poller:
    def __init__(self, adb: AdbClient, use_root: bool = False) -> None:
        self.adb = adb
        self.use_root = use_root
        self._disk_prev: dict[str, float] = {}
        self._disk_t: float | None = None
        self._net_prev: dict[str, float] = {}
        self._net_t: float | None = None
        self._cpu_prev: dict[str, float] = {}

    def script(self) -> str:
        if self.use_root:
            return POLL_SCRIPT.replace("echo '###END'", FAN_SECTION + "echo '###END'")
        return POLL_SCRIPT

    def _apply_rates(self, out: dict[str, float | str]) -> dict[str, float | str]:
        now = time.monotonic()
        current = {k: float(out.pop(k)) for k in P.DISK_RAW_KEYS if k in out}
        if current and self._disk_prev and self._disk_t is not None:
            out.update(P.disk_rates(current, self._disk_prev, now - self._disk_t))
        if current:
            self._disk_prev = current
            self._disk_t = now
        net_current = {k: float(out.pop(k)) for k in P.NETDEV_RAW_KEYS if k in out}
        if net_current:
            dt = now - self._net_t if self._net_t is not None else 0.0
            out.update(P.netdev_rates(net_current, self._net_prev, dt))
            self._net_prev = net_current
            self._net_t = now
        cpu_current = {k: float(out.pop(k)) for k in P.CPU_STAT_RAW_KEYS if k in out}
        if cpu_current and self._cpu_prev:
            out.update(P.cpu_rates(cpu_current, self._cpu_prev))
        if cpu_current:
            self._cpu_prev = cpu_current
        return out

    def poll(self) -> dict[str, float | str]:
        """Combined one-shot poll, used for start/end state and compatibility."""
        return self._apply_rates(parse_poll(self.adb.shell(self.script(), timeout=8.0)))

    def poll_fast(self) -> dict[str, float | str]:
        return self._apply_rates(parse_poll(self.adb.shell(FAST_SCRIPT, timeout=8.0)))

    def poll_state(self) -> dict[str, float | str]:
        script = STATE_SCRIPT
        if self.use_root:
            script = script.replace("echo '###END'", FAN_SECTION + "echo '###END'")
        return parse_poll(self.adb.shell(script, timeout=10.0))

    def poll_thermal(self) -> dict[str, float]:
        """Read live thermal HAL temperatures without the rest of the state poll."""
        return P.parse_thermalservice(self.adb.shell("dumpsys thermalservice 2>/dev/null", timeout=8.0))

    def poll_preview(self) -> dict[str, float | str]:
        """Lightweight manual preview: battery + thermal service only."""
        return parse_poll(self.adb.shell(PREVIEW_SCRIPT, timeout=10.0))

    def poll_radio(self) -> dict[str, float | str]:
        return parse_poll(self.adb.shell(RADIO_SCRIPT, timeout=10.0))
