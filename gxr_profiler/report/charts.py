"""Shared chart specification used by the static report and the web app."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..core.columns import (
    BANDS,
    COLUMN_BY_NAME,
    THERMAL_ZONE_AUX_COLS,
    THERMAL_ZONE_MAIN_COLS,
    THERMAL_ZONE_RAW_CPU0_COLS,
    THERMAL_ZONE_RAW_CPU1_COLS,
)


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


# Focused groups = one topic/unit per chart. Tables reuse the same group titles,
# so the grouping also keeps the table rows easy to scan.
GROUPS: list[ChartGroup] = [
    # Thermal
    _group("thermal_cpu", "CPU core temperatures", [], ["cpu"], "Thermal"),
    _group("thermal_gpu", "GPU temperatures", [], ["gpu"], "Thermal"),
    _group("thermal_npu", "Neural engine temperatures", [], ["npu"], "Thermal"),
    _group(
        "thermal_surfaces",
        "Surface & component temperatures",
        _series(["t_AP", "t_WIFI", "t_LRP", "t_CHG", "t_USB", "ddr_temp"]),
        section="Thermal",
    ),
    _group(
        "thermal_media",
        "Video & camera temperatures",
        _series(THERMAL_ZONE_MAIN_COLS),
        section="Thermal",
    ),
    # CPU
    _group("cpu", "CPU frequency", _series(["cpu_max0", "cpu_max2"]), ["cpu_freq"], "CPU"),
    _group("cpu_util", "CPU utilisation", [], ["cpu_util"], "CPU"),
    # GPU
    _group("gpu_clock", "GPU clock", _series(["g_clock"]), section="GPU"),
    _group("gpu_busy", "GPU utilisation", _series(["g_busy"]), section="GPU"),
    _group("gpu_temp", "GPU temperature", _series(["g_temp"]), section="GPU"),
    _group("gpu_throttle", "GPU throttling", _series(["g_throttling"]), section="GPU"),
    # Cooling
    _group("thermal_status", "Thermal status", _series(["thermal_status"]), section="Cooling"),
    _group("fan_step", "Fan step", _series(["fan_step"]), section="Cooling"),
    _group("fan_speed", "Fan speed", _series(["fan_rpm", "fan_rpm2"]), section="Cooling"),
    _group("fan_pwm", "Fan PWM", _series(["fan_pwm"]), section="Cooling"),
    # XR / display
    _group("xr_fps", "XR frame rate", _series(["xr_fps", "xr_target"]), section="XR"),
    _group("xr_drops", "XR missed frames", _series(["xr_drops"]), section="XR"),
    _group(
        "xr_util",
        "XR utilisation",
        _series(["xr_cpu", "xr_gpu", "xr_ram"]),
        section="XR",
    ),
    _group("display_refresh", "Display refresh rate", _series(["disp_hz"]), section="XR"),
    # Cameras
    _group(
        "camera_ingest",
        "Cameras (tracked)",
        _series(["cam_head_fps", "cam_hand_fps", "cam_eye_fps", "irled_fps"]),
        section="Cameras",
    ),
    # Memory
    _group(
        "memory",
        "Memory",
        _series(["mem_total", "mem_used", "mem_cached", "mem_available", "mem_free"]),
        section="Memory",
    ),
    _group("swap", "Swap", _series(["swap_total", "swap_used", "swap_free"]), section="Memory"),
    _group("zram", "Zram", _series(["zram_used_mb"]), section="Memory"),
    _group(
        "memory_pressure",
        "Memory pressure",
        _series(["mem_used_pct", "swap_used_pct", "mem_pressure_some", "mem_pressure_full"]),
        section="Memory",
    ),
    # Storage
    _group(
        "storage_capacity",
        "Storage capacity",
        _series(["disk_total_gb", "disk_free_gb"]),
        section="Storage",
    ),
    _group("storage_used", "Storage used", _series(["disk_used_pct"]), section="Storage"),
    _group(
        "storage_throughput",
        "Storage throughput",
        _series(["disk_read_mbps", "disk_write_mbps"]),
        section="Storage",
    ),
    _group(
        "storage_iops",
        "Storage IOPS",
        _series(["disk_read_iops", "disk_write_iops"]),
        section="Storage",
    ),
    _group("storage_latency", "Storage latency", _series(["disk_io_latency_ms"]), section="Storage"),
    _group(
        "storage_busy",
        "Storage busy & pressure",
        _series(["disk_busy_pct", "disk_io_pressure_some", "disk_io_pressure_full"]),
        section="Storage",
    ),
    # Network
    _group(
        "wifi_link_speed",
        "Wi-Fi link speed",
        _series(["wifi_tx", "wifi_rx"]),
        section="Network",
    ),
    _group("wifi_signal", "Wi-Fi signal", _series(["wifi_rssi"]), section="Network"),
    _group("wifi_retries", "Wi-Fi retransmits", _series(["wifi_tx_retries"]), section="Network"),
    _group(
        "wifi_throughput",
        "Wi-Fi throughput",
        _series(["wifi_rx_mbps", "wifi_tx_mbps"]),
        section="Network",
    ),
    _group(
        "wifi_packet_rate",
        "Wi-Fi packet rate",
        _series(["wifi_rx_pps", "wifi_tx_pps"]),
        section="Network",
    ),
    _group("wifi_retry_rate", "Wi-Fi retry rate", _series(["wifi_retry_pct"]), section="Network"),
    _group("wifi_loss_rate", "Wi-Fi loss rate", _series(["wifi_lost_pps"]), section="Network"),
    _group(
        "wifi_error_counters",
        "Wi-Fi error counters",
        _series(["wifi_rx_drops", "wifi_tx_drops", "wifi_rx_errors", "wifi_tx_errors"]),
        section="Network",
    ),
    # System
    _group("load", "CPU load", _series(["load1", "load5", "load15"]), section="System"),
    _group("tasks", "Tasks", _series(["procs_running", "procs_total"]), section="System"),
    # Power & battery
    _group("battery_level", "Battery level", _series(["batt_level"]), section="Power & battery"),
    _group("battery_drain", "Battery drain rate", _series(["batt_drain_pct_h"]), section="Power & battery"),
    _group("battery_temp", "Battery temperature", _series(["batt_temp"]), section="Power & battery"),
    _group(
        "battery_source",
        "Battery power source",
        _series(["batt_ac", "batt_usb"]),
        section="Power & battery",
    ),
    _group("battery_status", "Battery status", _series(["batt_status"]), section="Power & battery"),
    _group("power_voltage", "Power rail voltage", _series(["max_ch1_voltage"]), section="Power & battery"),
    _group("power_current", "Power rail current", _series(["max_ch1_current"]), section="Power & battery"),
    _group("power_power", "Power rail power", _series(["max_ch1_power"]), section="Power & battery"),
    _group("power_energy", "Power rail energy", _series(["max_ch1_energy_wh"]), section="Power & battery"),
    _group("power_saving", "Power saving", _series(["psm"]), section="Power & battery"),
    # Raw thermal (extra)
    _group(
        "thermal_aux",
        "AOSS & CPUSS temperatures",
        _series(THERMAL_ZONE_AUX_COLS),
        section="Raw thermal",
    ),
    _group(
        "thermal_raw_cpu0",
        "Raw CPU cluster 0 temperatures",
        _series(THERMAL_ZONE_RAW_CPU0_COLS),
        section="Raw thermal",
    ),
    _group(
        "thermal_raw_cpu1",
        "Raw CPU cluster 1 temperatures",
        _series(THERMAL_ZONE_RAW_CPU1_COLS),
        section="Raw thermal",
    ),
    # Controllers / passthrough (extra)
    _group(
        "controller_tracking",
        "Controller tracking",
        _series(["ctrl_left_track", "ctrl_right_track", "ctrl_left_connected", "ctrl_right_connected"]),
        section="Controllers",
    ),
    _group(
        "controller_battery",
        "Controller battery",
        _series(["ctrl_left_battery", "ctrl_right_battery"]),
        section="Controllers",
    ),
    _group("passthrough", "Passthrough", _series(["passthrough"]), section="Passthrough"),
    # Media & display (extra)
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
    # Audio (extra)
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
    # Cameras (raw streams, extra)
    _group(
        "camera_raw",
        "Cameras (raw streams)",
        _series(["cib_ht_fps", "cib_hat_fps", "cib_eyet_fps", "cib_depthinput_fps"]),
        section="Cameras (raw)",
    ),
]


def spec() -> dict:
    return {
        "groups": [asdict(g) for g in GROUPS],
        "bands": BANDS,
    }
