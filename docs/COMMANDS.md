# Headset commands, sources & polling

Every command in gxr-profiler is **read-only**. The only privileged commands use
`su -c` to read root-only files; there are no writes, pushes, `setprop`,
sysfs writes, logcat clears, or thermalservice overrides.

Device: **Samsung Galaxy XR (SM-I610)**, Android 14, Snapdragon XR2+ Gen 2
(`SXR2230P`), Adreno 740.

Related: [README](../README.md) for columns/usage, [research notes](README.md)
for findings and device quirks.

## Cadence at a glance

| When | What | Default rate | Root |
|---|---|---:|---|
| Once per run | Device/build/panel/audio/KernelSU snapshot | 1× | Only panel + `su -c id` |
| Once per run | Device clock baseline | 1× | No |
| Start and end of run | Modes, hand tracking, controllers, passthrough, initial poll | 2× | Follows poll/fan setting |
| Continuous | `logcat -v time -T 1` event stream | Event-driven | No |
| Poll | Fast 1 Hz sysfs/`/proc`; state/radios on slower cadences | `--interval` = 1 s | Fan section only with `--root` |
| Media | Decoder, display/HDR, audio, audio policy state | 30 s Standard / 10 s Detailed | No |
| Processes | CPU/RSS/GPU memory/UID network | 10 s Standard / 5 s Detailed | I/O with `--root --process-io` |
| Sensors | Android SensorService summary | `--sensors` = 10 s Detailed / 5 s Everything | No |

Rates derived from cumulative counters (disk, CPU) use deltas between polls.
The first poll seeds the baseline; the first row therefore has no rate. When
`--cooldown` is set, gxr-profiler polls the thermal HAL once per second until the selected
cooldown sensor is at or below the target; those cooldown polls are not written to the
run. The sensor defaults to `AP` and is selectable in the UI / via `--sensor`.
`--cooldown-max-wait` (or the UI advanced field) stops waiting after N seconds;
`0` means no limit.

## 1 Hz poll (`--interval` seconds)

The exact poll script is built in
[`gxr_profiler/capture/poller.py`](../gxr_profiler/capture/poller.py):

```sh
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
```

With `--root`, this fan block is inserted before `###END`:

```sh
echo '###FAN'
su -c 'cat /sys/class/sec_fan/fan/curr_rpm; cat /sys/class/sec_fan/fan/curr_rpm2; cat /sys/class/sec_fan/fan/get_status' 2>/dev/null
```

### Poll section → data

| Section | Data produced |
|---|---|
| `FREQ` | `f_cpu0..5` (kHz) |
| `PMAX` | `cpu_max0`, `cpu_max2` (kHz) |
| `GCLK` | `g_clock` (MHz), `g_devfreq` (Hz) |
| `GBUSY`, `GBUSYN` | `g_busy` (%), `g_busy_num`/`g_busy_den` |
| `GTMP`, `GTHR` | `g_temp` (°C), `g_throttling` |
| `SEC` | `sec_ap`, `sec_lp`, `sec_wf` (°C) |
| `LOAD` | `load1/5/15`, `procs_running`, `procs_total` |
| `MEM` | `mem_total`, `mem_used`, `mem_cached`, `mem_available`, `mem_free`, `mem_used_pct`, `swap_total`, `swap_used`, `swap_free`, `swap_used_pct` |
| `STAT` | `cpu_util0..5` (delta), `procs_running` |
| `PRESSURE_MEM` | `mem_pressure_some`, `mem_pressure_full` (PSI avg10) |
| `ZRAM` | `zram_used_mb` |
| `DF` | `disk_total_gb`, `disk_free_gb`, `disk_used_pct` |
| `BATT` | `batt_level`, `batt_temp`, `batt_status`, `batt_ac`, `batt_usb` |
| `WIFI` | `wifi_tx`, `wifi_rx` (link speeds), `wifi_rssi`, `wifi_link`, `wifi_freq`, `wifi_std`, `wifi_max_tx/rx`, cumulative counters, and per-second `wifi_tx_pps`, `wifi_rx_pps`, `wifi_retry_pps`, `wifi_retry_pct`, `wifi_lost_pps` |
| `NETDEV` | `wifi_rx_mbps`, `wifi_tx_mbps` (wlan0 byte deltas), and cumulative `wifi_rx/tx_drops`, `wifi_rx/tx_errors` |
| `BT` | `bt_on`, `bt_state` |
| `LOC` | `loc_enabled`, `loc_mode`, `loc_mode_name`, `loc_providers` |
| `DISK` | `disk_read_mbps`, `disk_write_mbps`, `disk_read_iops`, `disk_write_iops`, `disk_busy_pct`, `disk_io_latency_ms`, `disk_io_pressure_some/full` |
| `THERM` | `t_*` temperatures, `thermal_status`, `thermal_max_sev` |
| `FAN` (`--root`) | `fan_rpm`, `fan_rpm2`, `fan_pwm` |

**Notes**

- `/proc/diskstats` is aggregated over whole devices only (`sd*`, `mmcblk*`,
  `nvme*n*`, `vd*`, `xvd*`); partitions, `dm-*`, `loop*` and `zram*` are
  excluded. Sector counts use 512 B units.
- `/proc/stat` and `/proc/diskstats` counters are cumulative. gxr-profiler records
  deltas between polls for utilisation/throughput/IOPS/busy/latency.
- `dumpsys thermalservice` is the primary named-temperature source; logcat is
  supplementary/event-driven.
- Poll timeout is 8 s (the normal poll should complete well under 1 s).
- `wifi_rx_mbps`/`wifi_tx_mbps` are **actual interface throughput** from `/proc/net/dev`,
  not the negotiated link speed. This is the best proxy for streamed PCVR bitrate; it
  includes all wlan0 traffic.
- Direct end-to-end latency/RTT is not exposed by Android. `dumpsys wifi` has channel
  contention times and radio TX/RX time, but not network RTT; an optional ping target
  would be needed for that. `cmd wifi status` does expose retry and lost-packet rates,
  which are useful loss/latency proxies.

## Continuous logcat stream

Started with (unless `--no-logcat`):

```sh
logcat -v time -T 1
```

gxr-profiler filters in Python because `logcat -s` misses colon tags such as
`SSRM:Temperature` and `-e` matches messages rather than tags.

| Source tag/message | Data |
|---|---|
| `DynamicPolicyManager` JSON | `thermal_status`, `xr_fps`, `xr_target`, `xr_drops`, `xr_cpu`, `xr_gpu`, `xr_ram`, `disp_hz`, `psm` |
| `thermal_changed` | temperature + severity (`t_*`, `sev_*`) on threshold crossings |
| `SSRM:Temperature` / `SSRM:S` | supplementary temperatures |
| `SSRM:w` | `fan_step` |
| `ThermalManagerService` | Dcvsh CPU caps (`dcvsh_0/2_limit`, `dcvsh_0/2_max`) |
| `XrHeartbeat` messages | `cam_eye_fps`, `cam_head_fps`, `cam_hand_fps`, `irled_fps` |
| `[CIB]` messages | raw camera stream rates (`cib_*_{fps,hz}`) |
| `IRLedController` tag | IR LED rate |
| `SXRC_TSVC` | controller connection, battery, firmware, triggers, grip, sticks |
| `SXRC_POSE` | per-controller pose status/quality → tracking |
| `CpmInput` | controller start/stop tracking |
| `PassthroughStateManager` | passthrough requested mode → `passthrough`, `passthrough_mode` |

Logcat is **event-driven**, not a fixed poll. Thermal/fan events are also
written to `<run>.events.csv`; other values are folded into the next 1 Hz row.

## Media/display/audio (every 10 s, always on)

```sh
echo '###MEDIA'
dumpsys media.metrics 2>/dev/null | grep -E 'android.media.mediacodec.mode=(video|audio)' | tail -20

echo '###DISPLAY'
dumpsys display 2>/dev/null | grep -E 'Display Brightness=|Display SdrBrightness=|mBrightnessState='

echo '###SFHDR'
dumpsys SurfaceFlinger 2>/dev/null | grep -oE 'dataspace=[A-Za-z0-9_]+|format: *[A-Z0-9_]+|Current color mode:.*' | sort -u

echo '###AUDIO'
dumpsys audio 2>/dev/null

echo '###FLINGER'
dumpsys media.audio_flinger 2>/dev/null | grep -E '^(Output|Input) thread|^[[:space:]]+(Standby:|Sample rate:|HAL format:|Channel count:|Output devices:|Input device:|Audio source:|Master volume:|Master mute:|Normal mixer raw underrun counters:|Threadloop write latency stats:|Process time ms stats:|Timestamp stats:|[0-9]+ Tracks of which)'
```

| Section | Data |
|---|---|
| `MEDIA` | `media_codec`, `media_codecs`, `media_app`, `media_mime`, resolution, profile, bit depth, HDR format, hardware/software; audio codec name/MIME/app/rate/channels/age |
| `DISPLAY` | `disp_brightness`, `disp_sdr_brightness` |
| `SFHDR` | `hdr_active`, `disp_bit_depth`, `disp_color_mode` |
| `AUDIO` | audio app, active players, volume/mute, mic mute |
| `FLINGER` | active output/input thread, device, format, bits, channels, rate, underruns, write latency |

Timeout: 25 s. No root.

## Recording cadence (schema 6)

The recorder uses a **fast 1 Hz** shell containing only cheap sysfs and `/proc`
reads. Slow sections run separately and are merged into every 1 Hz row:

- **State**: battery, Wi-Fi status, thermal service (and fan with `--root`) — Standard 5 s
- **Radio**: Bluetooth, location, disk-free — Standard 30 s
- **Media/audio/display**: 30 s Standard, 10 s Detailed/Everything
- **Sensors**: off Standard, 10 s Detailed, 5 s Everything
- **Processes**: 10 s Standard, 5 s Detailed/Everything; non-kernel by default
- **Everything**: state 1 s, radios 5 s, root fan, kernel threads and process I/O

The full combined command shown above is also used for start/end state and
cooldown sampling. Older runs keep their original cadence.

## Per-process snapshot (`--processes`, default every 10 s)

Base script:

```sh
echo '###CPUINFO'; dumpsys cpuinfo
echo '###PS'; ps -A -o PID,UID,RSS,NAME
echo '###STAT'; grep -H '' /proc/[0-9]*/stat 2>/dev/null
echo '###OOM'; grep -H '' /proc/[0-9]*/oom_score_adj 2>/dev/null
echo '###GPUMEM'; dumpsys gpu | sed -n '/Memory snapshot for GPU/,/driverPackageName/p'
echo '###NET'; dumpsys netstats
```

Package map, loaded once per recording:

```sh
echo '###PKGS'; pm list packages -U
echo '###SYSPKGS'; pm list packages -s
```

Root-only per-process I/O (same interval, only with `--root --process-io`):

```sh
su -c 'echo "###IO"; grep -H -E "^(read_bytes|write_bytes):" /proc/[0-9]*/io 2>/dev/null'
```

| Source | Data |
|---|---|
| `dumpsys cpuinfo` | `cpu_pct`, process name (~5 min sliding window) |
| `ps` | `uid`, `rss_kb`, process name |
| `/proc/<pid>/stat` | `cpu_now_pct` (interval delta), `cpu_time_s`, `ppid`, `state`, `threads` |
| `/proc/<pid>/oom_score_adj` | `oom_adj`, `oom_class` |
| `pm list packages -U` / `-s` | `package`, `pkg_system`, process `kind` |
| `dumpsys gpu` | `gpu_mem_kb` per PID |
| `dumpsys netstats` | `net_rx_bytes`, `net_tx_bytes` per UID (cumulative), plus `net_*_bps` deltas |
| `/proc/<pid>/io` (`--root --process-io`) | `io_read_bytes`, `io_write_bytes`, `io_read_bps`, `io_write_bps` |

By default captures all **non-kernel** processes. `--processes-kernel` adds kernel threads;
`--processes-top N` caps the captured list (`0` = all). Timeout: 14 s for the base snapshot,
10 s for root I/O. Network remains per-UID, so processes sharing a UID show the same value.
## Android sensor-service summary (`--sensors`, 10 s Detailed / 5 s Everything)

```sh
dumpsys sensorservice
```

Writes `sensors_total`, `sensors_running`, `sensors_disabled_clients`,
`sensors_active`, `sensor_conns`, `sensor_rate_min_ms`,
`sensor_rate_max_ms`, `sensor_max_hz`. XR IMUs bypass Android SensorService,
so this usually reflects only Android sensor clients (e.g. offbody).

## Start/end session state (twice per run)

Commands are in
[`gxr_profiler/capture/session.py`](../gxr_profiler/capture/session.py):

```sh
settings get global low_power
dumpsys com.google.xr.frameworks.perception.IPerceptionLifecycleManager/default
logcat -d -s SXRC_TSVC CpmInput SXRC_POSE 2>/dev/null | grep -E 'updateDeviceState|tracking for hand_controller|Contr\['
logcat -d -s PassthroughStateManager 2>/dev/null | tail -n 1
```

Fallback for passthrough if no logcat state:

```sh
dumpsys cpm 2>/dev/null | grep -A6 'XrPassthroughController:'
```

Also runs one normal poll and seeds `psm`, `disp_hz`, `batt_ac`, `batt_level`,
`batt_temp` and `thermal_status`. Resulting start/end state includes
`low_power`, `hand_tracking_active`, controller connection/battery/tracking,
`passthrough` and `passthrough_mode`.

Device-clock baseline (once, before logcat):

```sh
date +'%m-%d %H:%M:%S'
```

## One-time device/build snapshot (once per run)

Properties:

```sh
getprop
```

Main snapshot script:

```sh
echo '###UNAME'; uname -a
echo '###MEM'; grep MemTotal /proc/meminfo
echo '###DF'; df -h /data
echo '###GPU'; cat /sys/class/kgsl/kgsl-3d0/gpu_model; echo
cat /sys/class/kgsl/kgsl-3d0/max_gpuclk; echo
cat /sys/class/kgsl/kgsl-3d0/gpu_available_frequencies; echo
echo '###DISPLAY'; dumpsys display 2>/dev/null | grep -m2 -E 'DisplayDeviceInfo|mActiveSfDisplayMode'
echo '###BATTERY'; dumpsys battery
echo '###WIFI'; cmd wifi status 2>/dev/null | head -6
echo '###IP'; ip -4 addr show wlan0 2>/dev/null
echo '###SELINUX'; getenforce
echo '###THERMAL'; dumpsys thermalservice 2>/dev/null | grep -m1 -iE 'ThermalHAL'
```

Additional one-time snapshot commands:

```sh
ls /vendor/etc/display
dumpsys media.audio_policy
getprop ril.manufacturedate
getprop mdc.country_code
getprop mdc.countryiso_code
getprop ro.csc.sales_code
getprop persist.sys.locale
dumpsys cpm 2>/dev/null | grep -A1 'IPD Data'
settings get system eye_tracking_calibration_needed
settings get system user_eye_calibration_status
settings get system user_face_calibration_in_progress
echo '@@SECURE'; settings list secure | grep '^guardian_'
echo '@@SYSTEM'; settings list system | grep -E '^guardian_|^toggle_guardian'
```

`getprop` already includes the manufacture/region properties in the full property dump; the
individual commands are listed for clarity. `ril.manufacturedate` is `YYYYMMDD`. Region uses
`mdc.country_code` / `mdc.countryiso_code`, CSC uses `ro.csc.sales_code`, and locale uses
`persist.sys.locale`. Boundary keys are split: most `guardian_*` keys are secure; `guardian_radius`
and `toggle_guardian` are system.

Root-only calibration and first-setup timestamps (`--root`, read-only):

```sh
su -c 'echo @@IPD; cat /data/vendor/openpx/calibration/records/ipd.textproto 2>/dev/null; \
echo @@EYE_MTIME; stat -c %Y /data/vendor/openpx/eye_tracking/eye_tracking_calibration.bin 2>/dev/null; \
echo @@FACE_MTIME; stat -c %Y /data/vendor/openpx/face_tracking/face_tracking_calibration.pb 2>/dev/null; \
echo @@IPD_MTIME; stat -c %Y /data/vendor/openpx/calibration/records/ipd.textproto 2>/dev/null'
su -c 'stat -c %Y /data/system/users/0/settings_ssaid.xml /data/system/users/0/settings_secure.xml 2>/dev/null'
```

The smallest user-settings mtime is reported as **First setup (approx.)**, with a derived day
count. It is not an authoritative reset timestamp.

Root-only active panel identification (`--root`):

```sh
su -c 'echo @@TYPE; cat /sys/class/lcd/panel/lcd_type 2>/dev/null; \
echo @@CMD; grep -o dsi_display0=[^:]* /proc/cmdline 2>/dev/null; \
echo @@EDID; strings /sys/class/drm/card0-DSI-1/edid 2>/dev/null | grep XR2'
```

Root detection:

```sh
command -v su; command -v ksud; command -v magisk
# only with --root:
su -c id
```

This fills `device_info`: model/device/product/board/SoC, build and
fingerprint, Android/SDK, security patch, kernel, RAM, storage, GPU model and
frequencies, manufacture date, region/CSC/locale, panel variants and active panel,
display capabilities, audio formats/rates, Wi-Fi link, IP, SELinux, thermal HAL,
root manager, calibration metadata, guardian/boundary state, and the approximate
first-setup date.

## Root requirement summary

| Data | Root needed? |
|---|---|
| All normal 1 Hz telemetry, logcat, media, process CPU/RSS/GPU/net, sensors | No |
| Fan RPM/PWM (`fan_*`) | Yes, `--root` |
| Per-process disk I/O (`io_*`) | Yes, `--root` + `--process-io` |
| Active panel / LCD type / EDID | Yes, `--root` |
| Measured IPD + eye/face calibration file dates | Yes, `--root` |
| Approximate first setup date (user-settings mtimes) | Yes, `--root` |
| `su -c id` manager confirmation | Yes, `--root` |
| Manufacture date, region/CSC/locale, boundary, current IPD/cal status | No |
| All other device/build/panel variants | No |

`su -c` reads may trigger a KernelSU/Magisk prompt once. No command changes
device state.
