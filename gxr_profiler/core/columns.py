"""Single source of truth for run columns and their display metadata.

The CSV keeps base units; ``display_unit``/``scale``/``decimals`` are used by the
tables, charts and offline report. Keep this module free of I/O so the CLI, API
and report generator can all import it cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    label: str
    group: str
    kind: str = "poll"
    source: str = ""
    unit: str = ""
    display_unit: str | None = None
    scale: float = 1.0
    decimals: int | None = None
    text: bool = False
    extra: bool = False

    @property
    def shown_unit(self) -> str:
        return self.unit if self.display_unit is None else self.display_unit


def _c(
    name: str,
    label: str,
    group: str,
    source: str,
    unit: str = "",
    *,
    kind: str = "poll",
    display: str | None = None,
    scale: float = 1.0,
    decimals: int | None = None,
    text: bool = False,
    extra: bool = False,
) -> Column:
    return Column(name, label, group, kind, source, unit, display, scale, decimals, text, extra)


# ---- meta -----------------------------------------------------------------
META_SPECS = [
    _c("ts_host", "Host timestamp", "meta", "host clock", "epoch", kind="meta"),
    _c("ts_dev", "Device timestamp", "meta", "device clock", "string", kind="meta"),
    _c("elapsed_s", "Elapsed", "meta", "derived from ts_host", "s", kind="meta", decimals=1),
    _c("poll_ok", "Poll OK", "meta", "derived (1 = poll returned data)", "bool", kind="meta"),
]

# ---- state / event-derived ------------------------------------------------
TEMP_SENSORS = [
    "AP",
    "CPU0",
    "CPU1",
    "CPU2",
    "CPU3",
    "CPU4",
    "CPU5",
    "GPU0",
    "GPU1",
    "GPU2",
    "GPU3",
    "GPU4",
    "GPU5",
    "GPU6",
    "GPU7",
    "nsp0",
    "nsp1",
    "nsp2",
    "skin",
    "WIFI",
    "LRP",
    "BAT",
    "CHG",
    "USB",
]

_TEMP_LABELS = {
    "AP": "Application processor",
    "skin": "Front surface",
    "WIFI": "Wi-Fi chip",
    "LRP": "Power path",
    "BAT": "Battery",
    "CHG": "Charger IC",
    "USB": "USB port",
}
for _i in range(6):
    _TEMP_LABELS[f"CPU{_i}"] = f"CPU core {_i}"
for _i in range(8):
    _TEMP_LABELS[f"GPU{_i}"] = f"GPU slice {_i}"
for _i in range(3):
    _TEMP_LABELS[f"nsp{_i}"] = f"Neural core {_i}"

CIB_STREAMS = ["ht", "pht", "hat", "phat", "eyet", "peyet", "depthtof", "pdepthtof", "depthinput", "pdepthinput"]
_CIB_LABELS = {
    "ht": "Head camera (raw)",
    "pht": "Head camera (raw, P)",
    "hat": "Hand camera (raw)",
    "phat": "Hand camera (raw, P)",
    "eyet": "Eye camera (raw)",
    "peyet": "Eye camera (raw, P)",
    "depthtof": "Depth ToF (raw)",
    "pdepthtof": "Depth ToF (raw, P)",
    "depthinput": "Depth input (raw)",
    "pdepthinput": "Depth input (raw, P)",
}

_THERMAL_SOURCE = "dumpsys thermalservice"
_STATE_SPECS: list[Column] = [
    _c("thermal_status", "Thermal throttle level (0-6)", "thermal", _THERMAL_SOURCE, "level 0-6", decimals=0),
    _c(
        "thermal_max_sev",
        "Worst sensor severity",
        "thermal",
        "max per-sensor severity",
        "level",
        kind="derived",
        decimals=0,
    ),
    _c("fan_step", "Fan step", "fan", "logcat SSRM:w", "step", kind="event", decimals=0),
]
_STATE_SPECS += [
    _c(f"t_{s}", _TEMP_LABELS[s], "thermal", _THERMAL_SOURCE, "°C", display="°C", decimals=1) for s in TEMP_SENSORS
]
for cluster in (0, 2):
    _STATE_SPECS += [
        _c(
            f"dcvsh_{cluster}_limit",
            f"CPU cluster {cluster // 2} limit",
            "cpu",
            "logcat ThermalManagerService",
            "kHz",
            kind="event",
            display="MHz",
            scale=0.001,
            decimals=0,
        ),
        _c(
            f"dcvsh_{cluster}_max",
            f"CPU cluster {cluster // 2} max",
            "cpu",
            "logcat ThermalManagerService",
            "kHz",
            kind="event",
            display="MHz",
            scale=0.001,
            decimals=0,
        ),
    ]
_STATE_SPECS += [
    _c("xr_fps", "XR frame rate", "xr", "logcat DynamicPolicyManager", "Hz", kind="event", display="fps", decimals=0),
    _c(
        "xr_target",
        "XR target rate",
        "xr",
        "logcat DynamicPolicyManager",
        "Hz",
        kind="event",
        display="fps",
        decimals=0,
    ),
    _c("xr_drops", "Missed frames", "xr", "logcat DynamicPolicyManager", "drops/s", kind="event", decimals=1),
    _c(
        "xr_cpu",
        "CPU utilisation",
        "xr",
        "logcat DynamicPolicyManager",
        "fraction",
        kind="event",
        display="%",
        scale=100.0,
        decimals=1,
    ),
    _c(
        "xr_gpu",
        "GPU utilisation",
        "xr",
        "logcat DynamicPolicyManager",
        "fraction",
        kind="event",
        display="%",
        scale=100.0,
        decimals=1,
    ),
    _c(
        "xr_ram",
        "RAM utilisation",
        "xr",
        "logcat DynamicPolicyManager",
        "fraction",
        kind="event",
        display="%",
        scale=100.0,
        decimals=1,
    ),
    _c("disp_hz", "Display refresh rate", "display", "logcat DynamicPolicyManager", "Hz", kind="event", decimals=0),
    _c(
        "passthrough",
        "Passthrough",
        "display",
        "logcat PassthroughStateManager",
        "bool",
        kind="event",
        display="on/off",
    ),
    _c("passthrough_mode", "Passthrough mode", "display", "logcat PassthroughStateManager", text=True),
    _c("psm", "Power saving", "display", "logcat DynamicPolicyManager", "bool", kind="event", display="on/off"),
    _c(
        "ctrl_left_connected",
        "Left controller connected",
        "controller",
        "logcat SXRC_TSVC",
        "bool",
        kind="event",
        display="on/off",
        extra=True,
    ),
    _c(
        "ctrl_right_connected",
        "Right controller connected",
        "controller",
        "logcat SXRC_TSVC",
        "bool",
        kind="event",
        display="on/off",
        extra=True,
    ),
    _c(
        "ctrl_left_track",
        "Left controller tracking",
        "controller",
        "logcat CpmInput",
        "bool",
        kind="event",
        display="on/off",
    ),
    _c(
        "ctrl_right_track",
        "Right controller tracking",
        "controller",
        "logcat CpmInput",
        "bool",
        kind="event",
        display="on/off",
    ),
    _c(
        "ctrl_left_battery",
        "Left controller battery",
        "controller",
        "logcat SXRC_TSVC",
        "%",
        kind="event",
        decimals=0,
    ),
    _c(
        "ctrl_right_battery",
        "Right controller battery",
        "controller",
        "logcat SXRC_TSVC",
        "%",
        kind="event",
        decimals=0,
    ),
    _c(
        "ctrl_active",
        "Controllers active",
        "controller",
        "derived from tracking/connection",
        "bool",
        kind="derived",
        display="on/off",
        extra=True,
    ),
    _c("cam_eye_fps", "Eye tracking camera", "camera", "logcat XrHeartbeat", "fps", kind="event", decimals=0),
    _c("cam_head_fps", "Head tracking camera", "camera", "logcat XrHeartbeat", "fps", kind="event", decimals=0),
    _c("cam_hand_fps", "Hand tracking camera", "camera", "logcat XrHeartbeat", "fps", kind="event", decimals=0),
    _c("irled_fps", "Eye IR illumination", "camera", "logcat XrHeartbeat", "fps", kind="event", decimals=0),
]
for _s in CIB_STREAMS:
    _STATE_SPECS += [
        _c(f"cib_{_s}_fps", _CIB_LABELS[_s], "camera", "logcat [CIB]", "fps", kind="event", decimals=0),
        _c(f"cib_{_s}_hz", f"{_CIB_LABELS[_s]} rate", "camera", "logcat [CIB]", "Hz", kind="event", decimals=0),
    ]

SENSOR_SPECS = [
    _c("sensors_total", "Hardware sensors", "sensors", "dumpsys sensorservice (opt-in)", "count", decimals=0),
    _c("sensors_running", "Running sensors", "sensors", "dumpsys sensorservice (opt-in)", "count", decimals=0),
    _c(
        "sensors_disabled_clients",
        "Disabled clients",
        "sensors",
        "dumpsys sensorservice (opt-in)",
        "count",
        decimals=0,
    ),
    _c("sensors_active", "Active sensor entries", "sensors", "dumpsys sensorservice (opt-in)", "count", decimals=0),
    _c("sensor_conns", "Sensor connections", "sensors", "dumpsys sensorservice (opt-in)", "count", decimals=0),
    _c(
        "sensor_rate_min_ms",
        "Fastest sensor period",
        "sensors",
        "dumpsys sensorservice (opt-in)",
        "ms",
        decimals=1,
    ),
    _c(
        "sensor_rate_max_ms",
        "Slowest sensor period",
        "sensors",
        "dumpsys sensorservice (opt-in)",
        "ms",
        decimals=1,
    ),
    _c("sensor_max_hz", "Sensor sample rate", "sensors", "dumpsys sensorservice (opt-in)", "Hz", decimals=0),
]

_MEDIA_SOURCE = "dumpsys media.metrics/resource_manager"
MEDIA_SPECS = [
    _c(
        "media_active",
        "Video decode active",
        "media",
        "dumpsys media.resource_manager",
        "bool",
        display="on/off",
        extra=True,
    ),
    _c(
        "media_poll_ok",
        "Media poll OK",
        "media",
        "dumpsys media.metrics/resource_manager",
        "bool",
        display="on/off",
        extra=True,
    ),
    _c("media_codec", "Video decoder", "media", _MEDIA_SOURCE, text=True),
    _c("media_app", "Decoder process", "media", _MEDIA_SOURCE, text=True),
    _c("media_mime", "Video codec", "media", _MEDIA_SOURCE, text=True),
    _c("media_codecs", "Decoders seen", "media", _MEDIA_SOURCE, text=True),
    _c("media_w", "Video width", "media", _MEDIA_SOURCE, "px", decimals=0, extra=True),
    _c("media_h", "Video height", "media", _MEDIA_SOURCE, "px", decimals=0, extra=True),
    _c("media_profile", "Codec profile", "media", _MEDIA_SOURCE, "enum", display="", decimals=0, extra=True),
    _c("media_bit_depth", "Stream bit depth", "media", _MEDIA_SOURCE, "bit", decimals=0, extra=True),
    _c("media_hdr_format", "Stream HDR format", "media", _MEDIA_SOURCE, "enum", display="", decimals=0),
    _c("media_hw_dec", "Hardware decode", "media", _MEDIA_SOURCE, "bool", display="on/off"),
    _c("media_sw_dec", "Software decode", "media", _MEDIA_SOURCE, "bool", display="on/off"),
    _c("hdr_active", "HDR output", "display", "SurfaceFlinger dataspaces", "bool", display="on/off"),
    _c("disp_bit_depth", "Active bit depth", "display", "SurfaceFlinger layer formats", "bit", decimals=0, extra=True),
    _c("disp_color_mode", "Color mode", "display", "SurfaceFlinger color mode", text=True),
    _c(
        "disp_brightness",
        "Display brightness",
        "display",
        "dumpsys display",
        "0-1",
        display="%",
        scale=100.0,
        decimals=0,
    ),
    _c(
        "disp_sdr_brightness",
        "SDR brightness",
        "display",
        "dumpsys display",
        "0-1",
        display="%",
        scale=100.0,
        decimals=0,
    ),
]

_AUDIO_SOURCE = "dumpsys audio / media.audio_flinger / media.metrics"
AUDIO_SPECS = [
    _c("audio_out_active", "Speaker active", "audio", _AUDIO_SOURCE, "bool", display="on/off"),
    _c("audio_out_device", "Output device", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_out_format", "Output format", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_out_bits", "Output bit depth", "audio", _AUDIO_SOURCE, "bit", decimals=0),
    _c("audio_out_channels", "Output channels", "audio", _AUDIO_SOURCE, display="", decimals=0, extra=True),
    _c(
        "audio_out_rate",
        "Output sample rate",
        "audio",
        _AUDIO_SOURCE,
        "Hz",
        display="kHz",
        scale=0.001,
        decimals=1,
        extra=True,
    ),
    _c("audio_out_volume_pct", "Music volume", "audio", _AUDIO_SOURCE, "%", decimals=0),
    _c("audio_out_mute", "Speaker muted", "audio", _AUDIO_SOURCE, "bool", display="on/off", extra=True),
    _c("audio_out_underruns", "Output underruns", "audio", _AUDIO_SOURCE, "count", display="", decimals=0),
    _c("audio_out_write_ms", "Write latency", "audio", _AUDIO_SOURCE, "ms", decimals=1),
    _c("audio_in_active", "Microphone active", "audio", _AUDIO_SOURCE, "bool", display="on/off"),
    _c("audio_in_device", "Input device", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_in_format", "Input format", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_in_bits", "Input bit depth", "audio", _AUDIO_SOURCE, "bit", decimals=0),
    _c("audio_in_channels", "Input channels", "audio", _AUDIO_SOURCE, display="", decimals=0, extra=True),
    _c(
        "audio_in_rate",
        "Input sample rate",
        "audio",
        _AUDIO_SOURCE,
        "Hz",
        display="kHz",
        scale=0.001,
        decimals=1,
        extra=True,
    ),
    _c("audio_in_source", "Input source", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_mic_mute", "Mic muted", "audio", _AUDIO_SOURCE, "bool", display="on/off", extra=True),
    _c("audio_players", "Active players", "audio", _AUDIO_SOURCE, "count", display="", decimals=0, extra=True),
    _c("audio_app", "Audio app", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_codec", "Audio codec", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_codec_mime", "Audio MIME", "audio", _AUDIO_SOURCE, text=True),
    _c("audio_codec_app", "Audio decoder app", "audio", _AUDIO_SOURCE, text=True),
    _c(
        "audio_codec_rate",
        "Audio codec rate",
        "audio",
        _AUDIO_SOURCE,
        "Hz",
        display="kHz",
        scale=0.001,
        decimals=1,
        extra=True,
    ),
    _c("audio_codec_channels", "Audio codec channels", "audio", _AUDIO_SOURCE, display="", decimals=0, extra=True),
    _c("audio_codec_age_s", "Audio codec age", "audio", _AUDIO_SOURCE, "s", decimals=1, extra=True),
]

STATE_SPECS = _STATE_SPECS + SENSOR_SPECS + MEDIA_SPECS + AUDIO_SPECS

# ---- 1 Hz poll ------------------------------------------------------------
_POLL_SPECS: list[Column] = []
for _i in range(6):
    _POLL_SPECS.append(
        _c(
            f"f_cpu{_i}",
            f"CPU core {_i} frequency",
            "cpu",
            "sysfs cpufreq scaling_cur_freq",
            "kHz",
            display="MHz",
            scale=0.001,
            decimals=0,
        )
    )
    _POLL_SPECS.append(_c(f"cpu_util{_i}", f"CPU core {_i} utilisation", "cpu", "/proc/stat", "%", decimals=0))
_POLL_SPECS += [
    _c(
        "cpu_max0",
        "CPU frequency cap (cluster 0)",
        "cpu",
        "sysfs cpufreq scaling_max_freq",
        "kHz",
        display="MHz",
        scale=0.001,
        decimals=0,
    ),
    _c(
        "cpu_max2",
        "CPU frequency cap (cluster 1)",
        "cpu",
        "sysfs cpufreq scaling_max_freq",
        "kHz",
        display="MHz",
        scale=0.001,
        decimals=0,
    ),
    _c("g_clock", "GPU clock", "gpu", "sysfs kgsl clock_mhz", "MHz", decimals=0),
    _c(
        "g_devfreq",
        "GPU frequency (derived)",
        "gpu",
        "derived from g_clock",
        "Hz",
        display="MHz",
        scale=1e-6,
        decimals=0,
    ),
    _c("g_busy", "GPU utilisation", "gpu", "sysfs kgsl gpu_busy_percentage", "%", decimals=0),
    _c("g_busy_num", "GPU busy ticks", "gpu", "sysfs kgsl gpubuspy", "ticks", decimals=0),
    _c("g_busy_den", "GPU busy total", "gpu", "sysfs kgsl gpubuspy", "ticks", decimals=0),
    _c("g_temp", "GPU temperature", "gpu", "sysfs kgsl temp", "°C", decimals=1),
    _c("g_throttling", "GPU throttled", "gpu", "sysfs kgsl throttling", "flag", decimals=0),
    _c("fan_rpm", "Fan speed (left)", "fan", "sysfs sec_fan (root)", "rpm", decimals=0),
    _c("fan_rpm2", "Fan speed (right)", "fan", "sysfs sec_fan (root)", "rpm", decimals=0),
    _c("fan_pwm", "Fan PWM", "fan", "sysfs sec_fan (root)", decimals=0),
    _c("sec_ap", "AP thermistor", "thermal", "sysfs sec-*-thermistor", "°C", decimals=1),
    _c("sec_lp", "LP thermistor", "thermal", "sysfs sec-*-thermistor", "°C", decimals=1),
    _c("sec_wf", "Wi-Fi thermistor", "thermal", "sysfs sec-*-thermistor", "°C", decimals=1),
    _c("load1", "CPU load (1 min)", "system", "/proc/loadavg", decimals=2),
    _c("load5", "CPU load (5 min)", "system", "/proc/loadavg", decimals=2),
    _c("load15", "CPU load (15 min)", "system", "/proc/loadavg", decimals=2),
    _c("procs_running", "Runnable tasks", "system", "/proc/loadavg", "tasks", display="", decimals=0),
    _c("procs_total", "Total tasks", "system", "/proc/loadavg", "tasks", display="", decimals=0),
    _c(
        "mem_total",
        "Total memory",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c(
        "mem_used",
        "Used memory",
        "system",
        "/proc/meminfo (total - available)",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c(
        "mem_cached",
        "Cached memory",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c(
        "mem_available",
        "Available memory",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c(
        "mem_free",
        "Free memory (raw)",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c("mem_used_pct", "Memory used", "system", "/proc/meminfo", "%", decimals=1),
    _c(
        "swap_total",
        "Total swap",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c(
        "swap_used",
        "Used swap",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c(
        "swap_free",
        "Free swap",
        "system",
        "/proc/meminfo",
        "kB",
        display="GB",
        scale=1 / 1048576,
        decimals=2,
    ),
    _c("swap_used_pct", "Swap used", "system", "/proc/meminfo", "%", decimals=1),
    _c("mem_pressure_some", "Memory pressure (some)", "system", "/proc/pressure/memory", "%", decimals=1),
    _c("mem_pressure_full", "Memory pressure (full)", "system", "/proc/pressure/memory", "%", decimals=1),
    _c("zram_used_mb", "Zram memory footprint", "system", "/sys/block/zram0/mm_stat", "MB", decimals=1),
    _c("batt_temp", "Battery temperature", "battery", "dumpsys battery", "°C", decimals=1),
    _c("batt_level", "Battery level", "battery", "dumpsys battery", "%", decimals=0),
    _c("batt_status", "Battery status", "battery", "dumpsys battery", "enum", display="", decimals=0, extra=True),
    _c("batt_ac", "On AC power", "battery", "dumpsys battery", "bool", display="", decimals=0, extra=True),
    _c("batt_usb", "On USB power", "battery", "dumpsys battery", "bool", display="", decimals=0),
    _c("wifi_rssi", "Wi-Fi signal", "network", "cmd wifi status", "dBm", decimals=0),
    _c("wifi_tx", "Wi-Fi Tx link speed", "network", "cmd wifi status", "Mbps", decimals=0),
    _c("wifi_rx", "Wi-Fi Rx link speed", "network", "cmd wifi status", "Mbps", decimals=0),
    _c("wifi_link", "Wi-Fi link speed", "network", "cmd wifi status", "Mbps", decimals=0),
    _c("wifi_freq", "Wi-Fi frequency", "network", "cmd wifi status", "MHz", decimals=0),
    _c("wifi_std", "Wi-Fi standard", "network", "cmd wifi status", "code", display="", decimals=0),
    _c("wifi_max_tx", "Max Wi-Fi send rate", "network", "cmd wifi status", "Mbps", decimals=0),
    _c("wifi_max_rx", "Max Wi-Fi receive rate", "network", "cmd wifi status", "Mbps", decimals=0),
    _c("wifi_tx_retries", "Wi-Fi retransmits", "network", "cmd wifi status", display="", decimals=0),
    _c("wifi_lost", "Wi-Fi lost packets", "network", "cmd wifi status", display="", decimals=0),
    _c("wifi_tx_pkts", "Wi-Fi sent packets", "network", "cmd wifi status", decimals=0),
    _c("wifi_rx_pkts", "Wi-Fi received packets", "network", "cmd wifi status", decimals=0),
    _c("wifi_rx_mbps", "Wi-Fi receive throughput", "network", "/proc/net/dev (wlan0)", "Mbps", decimals=1),
    _c("wifi_tx_mbps", "Wi-Fi send throughput", "network", "/proc/net/dev (wlan0)", "Mbps", decimals=1),
    _c("wifi_tx_pps", "Wi-Fi sent packets/s", "network", "cmd wifi status", "pps", decimals=1),
    _c("wifi_rx_pps", "Wi-Fi received packets/s", "network", "cmd wifi status", "pps", decimals=1),
    _c("wifi_retry_pps", "Wi-Fi retransmits/s", "network", "cmd wifi status", "pps", decimals=1),
    _c("wifi_retry_pct", "Wi-Fi retry rate", "network", "cmd wifi status", "%", decimals=1),
    _c("wifi_lost_pps", "Wi-Fi lost packets/s", "network", "cmd wifi status", "pps", decimals=1),
    _c(
        "wifi_rx_drops",
        "Wi-Fi Rx dropped (total)",
        "network",
        "/proc/net/dev (wlan0)",
        "packets",
        display="",
        decimals=0,
    ),
    _c(
        "wifi_tx_drops",
        "Wi-Fi Tx dropped (total)",
        "network",
        "/proc/net/dev (wlan0)",
        "packets",
        display="",
        decimals=0,
    ),
    _c(
        "wifi_rx_errors",
        "Wi-Fi Rx errors (total)",
        "network",
        "/proc/net/dev (wlan0)",
        "packets",
        display="",
        decimals=0,
    ),
    _c(
        "wifi_tx_errors",
        "Wi-Fi Tx errors (total)",
        "network",
        "/proc/net/dev (wlan0)",
        "packets",
        display="",
        decimals=0,
    ),
    _c("bt_on", "Bluetooth", "radio", "settings / dumpsys bluetooth_manager", "bool", display="on/off", extra=True),
    _c("bt_state", "Bluetooth state", "radio", "dumpsys bluetooth_manager", text=True),
    _c("loc_enabled", "Location services", "radio", "cmd location", "bool", display="on/off", extra=True),
    _c(
        "loc_mode",
        "Location mode",
        "radio",
        "settings secure location_mode",
        "0-3",
        display="",
        decimals=0,
        extra=True,
    ),
    _c("loc_mode_name", "Location accuracy", "radio", "settings secure location_mode", text=True),
    _c("loc_providers", "Location providers", "radio", "settings secure location_mode", text=True),
    _c("disk_read_mbps", "Disk read", "storage", "/proc/diskstats", "MB/s", decimals=1),
    _c("disk_write_mbps", "Disk write", "storage", "/proc/diskstats", "MB/s", decimals=1),
    _c("disk_read_iops", "Disk read IOPS", "storage", "/proc/diskstats", "IOPS", display="", decimals=0),
    _c("disk_write_iops", "Disk write IOPS", "storage", "/proc/diskstats", "IOPS", display="", decimals=0),
    _c("disk_busy_pct", "Disk busy", "storage", "/proc/diskstats", "%", decimals=0),
    _c("disk_io_latency_ms", "Disk I/O latency", "storage", "/proc/diskstats", "ms", decimals=1),
    _c("disk_io_pressure_some", "I/O pressure (some)", "storage", "/proc/pressure/io", "%", decimals=1),
    _c("disk_io_pressure_full", "I/O pressure (full)", "storage", "/proc/pressure/io", "%", decimals=1),
    _c("disk_total_gb", "Data partition size", "storage", "df -k /data", "GB", decimals=1),
    _c("disk_free_gb", "Free storage", "storage", "df -k /data", "GB", decimals=1),
    _c("disk_used_pct", "Storage used", "storage", "df -k /data", "%", decimals=1),
]

COLUMNS = META_SPECS + STATE_SPECS + _POLL_SPECS
COLUMN_BY_NAME = {c.name: c for c in COLUMNS}

REPORT_COLUMNS = [c.name for c in COLUMNS]
STATE_COLUMNS = [c.name for c in STATE_SPECS]
POLL_COLUMNS = [c.name for c in _POLL_SPECS]
CIB_COLUMNS = [f"cib_{s}_{m}" for s in CIB_STREAMS for m in ("fps", "hz")]
SENSOR_COLUMNS = [c.name for c in SENSOR_SPECS]
MEDIA_COLUMNS = [c.name for c in MEDIA_SPECS]
AUDIO_COLUMNS = [c.name for c in AUDIO_SPECS]

TEXT_SERIES = tuple(c.name for c in COLUMNS if c.text)
EXTRA_SERIES = tuple(c.name for c in COLUMNS if c.extra and not c.text)

# Multi-sensor families rendered as hottest/average bands.
_BAND_DEFS = [
    ("cpu", "CPU cores", "thermal", [f"t_CPU{i}" for i in range(6)]),
    ("gpu", "GPU slices", "thermal", [f"t_GPU{i}" for i in range(8)]),
    ("npu", "Neural engine", "thermal", [f"t_nsp{i}" for i in range(3)]),
    ("cpu_freq", "CPU frequency", "cpu", [f"f_cpu{i}" for i in range(6)]),
    ("cpu_util", "CPU utilisation", "cpu", [f"cpu_util{i}" for i in range(6)]),
]


def _band_specs() -> list[dict]:
    out = []
    for bid, label, group, cols in _BAND_DEFS:
        c = COLUMN_BY_NAME[cols[0]]
        out.append(
            {
                "id": bid,
                "label": label,
                "unit": c.shown_unit,
                "scale": c.scale,
                "decimals": c.decimals,
                "group": group,
                "columns": cols,
            }
        )
    return out


BANDS = _band_specs()

EVENT_COLUMNS = ["ts_host", "ts_dev", "tag", "name", "key", "value"]
PROC_COLUMNS = [
    "ts_host",
    "ts_dev",
    "elapsed_s",
    "pid",
    "ppid",
    "uid",
    "name",
    "kind",
    "package",
    "pkg_system",
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
    "state",
    "threads",
    "oom_adj",
    "oom_class",
]


def temp_sensor_options() -> list[dict[str, str]]:
    """Selectable cooldown sensors with their human-readable labels."""
    return [{"id": sensor, "label": COLUMN_BY_NAME[f"t_{sensor}"].label} for sensor in TEMP_SENSORS]
