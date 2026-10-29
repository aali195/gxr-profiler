"""Shared chart specification used by the static report and the web app."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..core.columns import BANDS, COLUMN_BY_NAME


@dataclass(frozen=True)
class SeriesSpec:
    col: str
    label: str
    unit: str
    tech: str
    scale: float = 1.0
    decimals: int | None = None


@dataclass(frozen=True)
class ChartGroup:
    id: str
    title: str
    unit: str
    series: list[SeriesSpec]
    bands: list[str] = ()
    section: str = ""


def _series(cols: list[str]) -> list[SeriesSpec]:
    out = []
    for c in cols:
        col = COLUMN_BY_NAME[c]
        out.append(
            SeriesSpec(
                col=c,
                label=col.label,
                unit=col.shown_unit,
                tech=col.name,
                scale=col.scale,
                decimals=col.decimals,
            )
        )
    return out


_BAND_UNITS = {b["id"]: b["unit"] for b in BANDS}


def _group(
    group_id: str,
    title: str,
    series: list[SeriesSpec],
    bands: list[str] | None = None,
    section: str = "",
) -> ChartGroup:
    bands = bands or []
    units = {s.unit for s in series}
    units |= {_BAND_UNITS[b] for b in bands if _BAND_UNITS.get(b)}
    unit = next(iter(units)) if len(units) == 1 else ""
    return ChartGroup(group_id, title, unit, series, bands, section)


# Focused groups = one topic per chart (much less cramped than one chart per
# broad category with dozens of lines).
GROUPS: list[ChartGroup] = [
    _group("thermal_cpu", "CPU core temperatures", [], ["cpu"], "Thermal"),
    _group("thermal_gpu", "GPU temperature", [], ["gpu"], "Thermal"),
    _group("thermal_npu", "Neural engine temperature", [], ["npu"], "Thermal"),
    _group(
        "thermal_surfaces",
        "Surface & component temperatures",
        _series(["t_AP", "t_skin", "t_WIFI", "t_LRP", "t_CHG", "t_BAT", "t_USB"]),
        section="Thermal",
    ),
    _group("cpu", "CPU frequency", _series(["cpu_max0", "cpu_max2"]), ["cpu_freq"], "CPU"),
    _group("cpu_util", "CPU utilisation", [], ["cpu_util"], "CPU"),
    _group("gpu", "GPU", _series(["g_clock", "g_busy", "g_temp"]), section="GPU"),
    _group(
        "cooling",
        "Throttling & cooling",
        _series(["thermal_status", "fan_step", "fan_rpm", "fan_rpm2", "fan_pwm"]),
        section="Cooling",
    ),
    _group(
        "xr",
        "XR & display",
        _series(["xr_fps", "xr_target", "xr_drops", "disp_hz", "xr_cpu", "xr_gpu", "xr_ram"]),
        section="XR",
    ),
    _group("power_saving", "Power saving", _series(["psm"]), section="Slow state"),
    _group(
        "controllers",
        "Controllers",
        _series(["ctrl_left_track", "ctrl_right_track", "ctrl_left_battery", "ctrl_right_battery"]),
        section="Controllers",
    ),
    _group("passthrough", "Passthrough", _series(["passthrough"]), section="Passthrough"),
    _group(
        "display_brightness",
        "Display brightness",
        _series(["disp_brightness", "disp_sdr_brightness"]),
        section="Media & display",
    ),
    _group(
        "media",
        "Video decode & HDR",
        _series(["media_hw_dec", "media_sw_dec", "hdr_active", "media_hdr_format"]),
        section="Media & display",
    ),
    _group(
        "audio",
        "Audio",
        _series(
            [
                "audio_out_active",
                "audio_in_active",
                "audio_out_volume_pct",
                "audio_out_bits",
                "audio_in_bits",
                "audio_out_underruns",
                "audio_out_write_ms",
            ]
        ),
        section="Audio",
    ),
    _group(
        "camera_ingest",
        "Cameras (tracked)",
        _series(["cam_head_fps", "cam_hand_fps", "cam_eye_fps", "irled_fps"]),
        section="Cameras",
    ),
    _group(
        "camera_raw",
        "Cameras (raw streams)",
        _series(["cib_ht_fps", "cib_hat_fps", "cib_eyet_fps", "cib_depthinput_fps"]),
        section="Cameras",
    ),
    _group(
        "network",
        "Wi-Fi link",
        _series(["wifi_tx", "wifi_rx", "wifi_rssi", "wifi_tx_retries"]),
        section="Network",
    ),
    _group(
        "wifi_throughput",
        "Wi-Fi throughput",
        _series(["wifi_rx_mbps", "wifi_tx_mbps", "wifi_rx_pps", "wifi_tx_pps"]),
        section="Network",
    ),
    _group(
        "wifi_quality",
        "Wi-Fi quality",
        _series(
            ["wifi_retry_pct", "wifi_lost_pps", "wifi_rx_drops", "wifi_tx_drops", "wifi_rx_errors", "wifi_tx_errors"]
        ),
        section="Network",
    ),
    _group(
        "memory",
        "Memory",
        _series(["mem_total", "mem_used", "mem_cached", "mem_available"]),
        section="System",
    ),
    _group(
        "swap",
        "Swap & zram",
        _series(["swap_total", "swap_used", "swap_free", "swap_used_pct", "zram_used_mb"]),
        section="Slow state",
    ),
    _group(
        "memory_pressure",
        "Memory pressure",
        _series(["mem_used_pct", "mem_pressure_some", "mem_pressure_full"]),
        section="Slow state",
    ),
    _group("load", "CPU load", _series(["load1", "load5", "load15"]), section="System"),
    _group("tasks", "Tasks", _series(["procs_running", "procs_total"]), section="Slow state"),
    _group("battery", "Battery", _series(["batt_temp", "batt_level"]), section="Slow state"),
    _group(
        "storage_space",
        "Storage space",
        _series(["disk_total_gb", "disk_free_gb", "disk_used_pct"]),
        section="Slow state",
    ),
    _group(
        "storage",
        "Storage I/O",
        _series(
            [
                "disk_read_mbps",
                "disk_write_mbps",
                "disk_read_iops",
                "disk_write_iops",
                "disk_busy_pct",
                "disk_io_latency_ms",
                "disk_io_pressure_some",
                "disk_io_pressure_full",
            ]
        ),
        section="System",
    ),
]


def spec() -> dict:
    return {
        "groups": [asdict(g) for g in GROUPS],
        "bands": BANDS,
    }
