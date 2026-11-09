# GXR Profiler - detailed guide & findings

Detailed notes for **Samsung Galaxy XR (SM-I610)**, Android 14, Snapdragon XR2+ Gen 2 (`SXR2230P`) and Adreno 740. All investigation and capture uses read-only commands.

Quick start, screenshots and the packaged UI are in the root [README](../README.md). CLI usage is in [CLI.md](CLI.md), developer setup in [DEVELOPMENT.md](DEVELOPMENT.md), and every headset command in [COMMANDS.md](COMMANDS.md).

## Contents

- [Device support](#device-support)
- [Capture profiles & overhead](#capture-profiles--overhead)
- [Output & schema](#output--schema)
- [Safety & fair runs](#safety--fair-runs)
- [Research & findings](#research--findings)
- [Data sources](#data-sources)
- [Findings index](#findings-index)
- [Key findings](#key-findings)

## Device support

**Samsung Galaxy XR (SM-I610) is the only tested and supported target.** The core recorder, storage, UI, reports and generic `/proc` metrics are portable, but the measurement schema and parsers include Galaxy XR / Samsung-specific thermal paths, fan/panel sysfs, CPU/GPU/NPU layouts, and Meta/Samsung XR logcat tags.

A **rooted Meta Quest Pro** may start and record, but is **not supported** out of the box. Root (`su -c`) only helps with reads such as `/proc/<pid>/io`; it does not provide Samsung thermistor paths, `sec_fan` paths, the XR2+ sensor layout, or Meta-specific XR telemetry. Expect roughly **40-55%** of the intended metrics to populate, with XR frame/controller/passthrough/camera and thermal/fan/panel charts largely empty. Do not treat Quest Pro results as validated until a device-specific profile and sanitized Quest logs/commands are added.

## Capture profiles & overhead

The UI exposes three presets and keeps individual options/interval overrides. **Cooldown target** is a temperature in °C: the recorder waits until the selected cooldown sensor is at or below it before starting; the sensor is selectable (AP is the application processor). **Cooldown max wait** is in the advanced intervals section; `0` waits indefinitely.

| Profile | Defaults |
|---|---|
| **Standard** | Core 1 Hz poll, logcat, all non-kernel processes every 10 s, media every 30 s, battery/Wi-Fi/thermal every 5 s, radios every 30 s; no sensors/root/I/O |
| **Detailed** | Standard plus sensors every 10 s, processes every 5 s, media every 10 s |
| **Everything** | All sources, kernel threads, root fan, process disk I/O; state every 1 s, radios every 5 s, processes/media every 5/10 s |

**Approximate idle overhead on SM-I610**, measured from the device's `adbd` + `sh` processes. These are ballpark values, not a promise: workload, root prompts and Wi-Fi traffic change them.

| Measurement | adbd | sh | combined |
|---|---:|---:|---:|
| Standard profile (logcat on) | ~4.5% | ~1.3% | **~5.8%** |
| Detailed (no logcat) | ~4.8% | ~1.0% | **~5.8%** |
| Everything profile | ~7.9% | ~1.3% | **~9.1%** |
| Previous all-on `idle-processes` capture | 7.07% | 1.33% | ~8.4% |

Rough incremental estimates over the fast 1 Hz core:

| Option | Approx. extra adbd+sh CPU |
|---|---:|
| Logcat | +0.1-0.4% |
| Non-kernel process snapshot, 10 s | ~2-3% |
| Process snapshot at 5 s | +1-2% over the 10 s form |
| Kernel threads | +0.2-0.6% |
| Per-process disk I/O (root) | +0.5-1.5% |
| Sensors every 5 s | +0.2-0.8% |
| Media/audio/display every 10 s vs 30 s | +0.1-0.3% |
| Root fan at state cadence (1 s in Everything) | +0.2-0.5% |

The fast poll does only cheap sysfs/`/proc` reads. Battery, Wi-Fi, thermal, radios, media, sensors and processes have separate cadences, and slow samplers run off the 1 Hz writer path so they cannot drop rows. The default Standard profile is expected to be near **5-6%** `adbd+sh` on an idle headset, versus roughly **9%** for Everything.

## Output & schema

Each new run is a directory:

```text
runs/<label>/data.csv       wide 1 Hz rows (one column per metric)
runs/<label>/events.csv     parsed logcat events (audit trail)
runs/<label>/procs.csv      per-process snapshots, only with --processes
runs/<label>/meta.json      manifest: schema/tool version, features, start/end state, column metadata
reports/<a>_vs_<b>.html     self-contained offline viewer (data + CSS/JS + ECharts inlined)
```

Runs are always stored in per-run directories.

Run names may use Unicode letters/digits plus spaces, `.`, `_` and `-` (max 100 characters). Path separators, Windows-invalid characters, reserved device names and trailing dots/spaces are rejected. Recording refuses to overwrite an existing run name.

**Why wide CSV.** One row per second loads trivially in pandas and plots directly; event-derived values are forward-filled into the row (last known). Raw parsed events stay in `.events.csv`.

**Columns (231).** Groups:

- `meta`: `ts_host` (epoch), `ts_dev`, `elapsed_s`, `poll_ok` (0/1 - did the poll succeed).
- `thermal`: `t_*` temps (C), `thermal_status`, `thermal_max_sev`, `sec_*` (C), `ddr_temp` (C), `video_temp`, `camera0/1_temp`, plus `aoss*`, `cpuss*` and `rawcpu_*` extras.
- `power`: `max_ch1_voltage` (V), `max_ch1_current` (A), `max_ch1_power` (W); extra for energy (`max_ch1_energy_wh`).
- `battery`: `batt_temp` (C), `batt_level` (%), `batt_drain_pct_h` (%/h), `batt_status`, `batt_ac`, `batt_usb`.
- `cpu`: `f_cpu0..5`, `cpu_util0..5` (%), `cpu_max0/2` (kHz), `dcvsh_*` (kHz).
- `gpu`: `g_clock` (MHz), `g_busy` (%), `g_busy_num/den`, `g_temp` (C), `g_throttling`.
- `fan`: `fan_step`, `fan_rpm`, `fan_rpm2` (rpm), `fan_pwm` (`--root`).
- `xr` / `display`: `xr_fps`, `xr_target` (Hz), `xr_drops`, `xr_cpu/gpu/ram` (fractions), `disp_hz`, `psm`, `disp_brightness`, `disp_sdr_brightness` (0-1), `hdr_active` (0/1), `disp_bit_depth` (8/10), `disp_color_mode` (NATIVE/SRGB/DISPLAY_P3), `passthrough` (0/1), `passthrough_mode` (Home / Window / SpatialApi / Disabled / ...).
- `media` (always on): `media_active` (current video-decoder allocation), `media_poll_ok` (fresh media/audio/display sample), `media_codec` / `media_codecs` (e.g. `c2.qti.av1.decoder`), `media_app`, `media_mime`, `media_w/h` (px), `media_profile`, `media_bit_depth` (8/10), `media_hdr_format`, `media_hw_dec`, `media_sw_dec` (0/1). Active decoder name/resolution come from `media.resource_manager`; `media.metrics` is only the last completed/flushed session. Encoders are excluded. HDR output comes from visible SurfaceFlinger layers; stream HDR format remains separate.
- `audio` (always on): `audio_out_*` (device, format, bits, channels, rate, volume, mute, underruns, write latency, active), `audio_in_*` (device, format, bits, channels, rate, source, active), `audio_mic_mute`, `audio_players`, `audio_app`, and `audio_codec*` (component, MIME, app, rate, channels, age).
- `camera`: `cam_*_fps`, `irled_fps`, `cib_*_{fps,hz}`.
- `radio` (state/radio cadence: 30 s Standard, 5 s Everything): `bt_on`, `bt_state`, `loc_enabled`, `loc_mode` / `loc_mode_name`, `loc_providers`.
- `controller`: `ctrl_left/right_connected`, `ctrl_left/right_track`, `ctrl_left/right_battery` (%), `ctrl_active`.
- `storage` (I/O at 1 Hz; `df` usage at radio cadence): `disk_read_mbps`, `disk_write_mbps`, `disk_read_iops`, `disk_write_iops`, `disk_busy_pct`, `disk_io_latency_ms`, `disk_io_pressure_some` / `_full`, `disk_total_gb`, `disk_free_gb`, `disk_used_pct`.
- `sensors` (`--sensors`): `sensors_*`, `sensor_rate_*`, `sensor_max_hz`.
- `system` / `network`: `load*`, `procs_*`, `mem_*` (kB), `swap_*`, `mem_pressure_*`, `zram_used_mb`, `wifi_*` (link speeds, actual Rx/Tx Mbps, packet/retry/loss rates, drops/errors).

**Calibration metadata.** With `--root`, a read-only `su -c` reads the OpenXR calibration files under `/data/vendor/openpx`: measured IPD plus eye/face calibration file timestamps. It also uses the earliest user-settings file timestamp as an approximate first-setup date. Without root, the current rendering IPD and calibration status are still read where available. Guardian/boundary state comes read-only from Android secure/system settings. The manufacture date comes from `ril.manufacturedate`.

**Media & display (always on).** `dumpsys media.metrics` supplies the most recent video codec session (component, MIME, resolution, profile, HDR format). `c2.qti.*` / `OMX.qcom.*` count as hardware, `c2.android.*` / `OMX.google.*` as software. Brightness comes from `dumpsys display`; `hdr_active` is set when a visible SurfaceFlinger layer reports an HDR dataspace; it is independent of `media_hdr_format`, which describes the last completed stream. `disp_bit_depth` / `disp_color_mode` come from visible SurfaceFlinger layer formats and the current color mode; `media_bit_depth` is inferred from the codec profile (e.g. HEVC Main10, AV1 Main10, VP9 Profile 2/3, AVC High10). Sampled every 30 s by default (10 s in Detailed/Everything).

**Audio (always on).** `dumpsys audio` gives the focus app, active player count, music volume/mute and mic mute; `dumpsys media.audio_flinger` gives the active output/input thread (device, PCM format, sample rate, channels, underruns, write latency); `dumpsys media.audio_policy` supplies the one-time device capabilities (speaker formats/rates, built-in and back mics). `media.metrics` audio codec records add the source codec, with `audio_codec_age_s` so the UI only shows a codec seen in the last 5 minutes. Audio and media fields that are idle or whose poll failed are shown as last-seen and visually muted.

**Radios (30 s Standard / 5 s Everything).** Bluetooth comes from `settings get global bluetooth_on` plus `dumpsys bluetooth_manager` (`enabled` and the adapter `state`), because `cmd bluetooth_manager get-state` is not implemented on this build. Location comes from `settings secure location_mode` (0=off, 1=device only, 2=battery saving, 3=high accuracy), `settings secure location_providers_allowed`, and `cmd location is-location-enabled`. Bluetooth and location are shown in **Modes & input** and kept in the CSV, but are intentionally not plotted. Slow, near-binary or usually-zero extras live under **Extra** (Cameras (raw), Media & display, Audio, Controllers, Passthrough, Raw thermal) so the main performance graphs stay focused.

**Controllers (event-derived).** Samsung XR emits connection/battery state in `SXRC_TSVC`, pose status in `SXRC_POSE`, and `CpmInput` start/stop tracking events. gxr-profiler records per-side connection, tracking and battery, plus `ctrl_active`, and adds a **controllers** / **no-controllers** run badge (shown only when active) and Modes & input row alongside hands.

**Passthrough.** `PassthroughStateManager` reports the current requested mode (`Home`, `Window`, `SpatialApi`, `Disabled`, `Lockscreen`, ...) and `dumpsys cpm` exposes `passthroughRunning`. gxr-profiler records `passthrough`/`passthrough_mode`, seeds them at run start, follows mode changes from logcat, and adds a **passthrough** badge when passthrough is active.

**Storage I/O (1 Hz counters; `df` at radio cadence).** `/proc/diskstats` is aggregated over whole block devices (`sd*`, `mmcblk*`, `nvme*n*`, `vd*`, `xvd*`); partitions, `dm-*`, `loop*` and `zram*` are excluded. Sectors are converted at 512 B, and throughput/IOPS/busy/latency are deltas between polls. `/proc/pressure/io` adds PSI `some`/`full` avg10 when the kernel exposes it; `df -k /data` adds total, free and used percentage.

**Memory & CPU (1 Hz).** `/proc/meminfo` supplies total, used (`total - available`), cached, available and swap totals with percentages. `/proc/pressure/memory` adds PSI `some`/`full`, and `/sys/block/zram0/mm_stat` adds the zram memory footprint. `/proc/stat` provides per-core CPU utilisation from idle/total deltas and the runnable-task count. DDR temperature comes from the kernel `ddr` thermal zone (`/sys/class/thermal/thermal_zone15/temp`, with a fallback lookup by zone type); it is shell-readable and not part of the thermal HAL named set.

**Extra raw thermals (1 Hz).** The poll also reads selected raw thermal zones by `type`: `video`, `camera-0/1`, `aoss-0/1`, `cpuss-0/1`, and the 12 `cpu-*` cluster/core zones. The raw CPU and AOSS/CPUSS zones are shown under **Extra -> Raw thermal**.

**Power rail (1 Hz).** `/sys/class/sec/max34427/all_ch1` exposes current, power and voltage for an unlabeled rail; the UI calls it **Power rail 1**. gxr-profiler records those values under `power`. This is not battery or SoC power; the rail label is not exposed in sysfs. It also integrates rail power into cumulative `max_ch1_energy_wh` under **Power & battery**. Rail 2 was always zero on this unit and is not stored. The MAX34427 accumulator registers are not recorded because they reset/roll and are not reliable cumulative counters.

**Battery (state cadence).** `dumpsys battery` supplies level, temperature, AC/USB state and status. `batt_drain_pct_h` is a rolling 5 min level slope (positive = discharging). The battery and rail charts and state table are under the normal **Power & battery** section.

**Display units.** The CSV keeps base units for analysis (kHz, kB, fractions, 0-1), while the web UI and static report convert for readability: CPU frequencies in **MHz**, memory in **GB**, utilisation and brightness in **%**, audio sample rates in **kHz**, temperatures in **°C**, frame rates in **fps**, and latency in **ms**. Units are shown in table headers and chart axes.

Exact unit/source per column is in `.meta.json -> columns_meta` (`group`, `unit`, `kind` = poll/event/derived/meta, `source`).

**Per-process file (`--processes`).** Long format, sampled every `--processes-interval`:

```text
ts_host, ts_dev, elapsed_s, pid, ppid, uid, name, kind, package, pkg_system,
cpu_pct, cpu_now_pct, cpu_time_s, rss_kb, gpu_mem_kb,
io_read_bytes, io_write_bytes, io_read_bps, io_write_bps,
net_rx_bytes, net_tx_bytes, net_rx_bps, net_tx_bps,
state, threads, oom_adj, oom_class
```

- By default **all non-kernel processes** are captured. Use `--processes-kernel` to include kernel threads; `--processes-top N` caps the list when a smaller file is wanted (`0` = all).
- `cpu_pct` is the ~5-minute `dumpsys cpuinfo` value (top entries only). `cpu_now_pct` is the interval delta from `/proc/<pid>/stat` (per-core scale, 100 = one core), so every process gets a current CPU value; `cpu_time_s` is cumulative CPU time. `rss_kb` comes from `ps`; `gpu_mem_kb` is GPU memory per PID (not utilisation).
- `kind` is `kernel`, `system`, `app`, `isolated` or `unknown`. `package` and `pkg_system` map the process to an installed package when possible (`pm list packages -U/-s`), so system apps can be separated from normal apps. `oom_adj`/`oom_class` (`system`, `foreground`, `visible`, `perceptible`, `background`, `cached`) come from `/proc/<pid>/oom_score_adj`.
- `state` (`R/S/D/Z/T/I`), `threads`, and `ppid` come from `/proc/<pid>/stat`.
- `io_*_bytes` are cumulative `/proc/<pid>/io` counters and `io_*_bps` are deltas between snapshots; both are only populated with `--root --processes` (the kernel restricts `/proc/<pid>/io`).
- `net_rx/tx_bytes` are **per-UID cumulative** (from `dumpsys netstats`) and `net_rx/tx_bps` are deltas; rows sharing a UID repeat the same network value. Network is not available per PID.
- Process rows are stored per PID, so two processes with the same name remain distinct. Across snapshots the viewer aggregates by PID; old top-N runs naturally contain fewer rows.
- The Processes tab loads the full list, supports client-side sorting/filtering, and includes the selected-process timeline. Exported HTML embeds those series and works offline.

**Manifest (`meta.json`).**

```text
schema_version, tool_version, label, started, recording_started, ended,
duration_s, duration_actual_s, rows, columns,
features {logcat, root_fan, sensors, sensors_interval_s,
          processes, processes_interval_s, processes_top, processes_kernel, process_io,
          media_interval_s, state_interval_s, radio_interval_s, profile},
start_state / end_state {low_power, hand_tracking_active, batt_ac, batt_level,
                          batt_temp, ddr_temp, thermal_status; psm/disp_hz when available},
device_model, android, platform, wifi_ssid, cooldown_sensor, cooldown_below, cooldown_max_wait,
notes, columns_meta,
device_info   # one-time device/build/region/manufacture/setup/panel/display/audio/Wi-Fi/root/calibration/boundary snapshot
```

**Run format.** Runs are stored only in the `runs/<label>/` directory layout. Existing results are not rewritten; deleting or renaming a run is an explicit user action.

## Safety & fair runs

- Every command is read-only: `cat`, `getprop`, `dumpsys`, `cmd wifi status`, `logcat`, `ps`.
- `--root` only runs read-only `su -c` reads (fan RPM/PWM, active panel, measured IPD/calibration mtimes, approximate first-setup mtime, `/proc/<pid>/io`); it may trigger a root prompt. There are no `push`/`setprop`/sysfs writes and no thermalservice inject/override.
- Nothing persists on the headset.
- Raw device captures are not stored in the repository. Add only sanitized excerpts under `docs/examples/`; never commit serials, account names, or Wi-Fi identifiers.
- Exported HTML redacts Wi-Fi SSID/BSSID/IP and serial fields; full values remain only in local run files.

For fair runs: unplug AC (charging adds heat), keep identical workload/duration, and use `--cooldown` so both runs start from the same temperature.

## Research & findings

- [`gxr-findings/`](gxr-findings/) - topic files. Each starts with **Tests & results**, then a short **Findings** summary, then the full **Details**.
- [`COMMANDS.md`](COMMANDS.md) - every headset command, polling cadence and root requirement.
- [`examples/`](examples/) - curated, sanitized snippets and device quirks worth citing.

Raw captures are deliberately not stored in the repository. Add only small, sanitized, read-only outputs (or the command plus a short excerpt). Do not add serial numbers, account names, Wi-Fi identifiers, or other personal data.

### Data sources

Read-only sources: a **logcat stream** + a **1 Hz poll**. Full command and cadence reference: [COMMANDS.md](COMMANDS.md).

| Metric | Source |
|---|---|
| Named temps: CPU0-5, GPU0-7, nsp0-2, AP, skin, WIFI, LRP, BAT, CHG, USB | `dumpsys thermalservice` (HAL, 1 Hz) + logcat `thermal_changed`, `SSRM:Temperature` |
| Throttle severity per sensor + global thermal status | `dumpsys thermalservice` + `thermal_changed`, `DynamicPolicyManager` |
| Fan step (observed 1-7) | logcat `SSRM:w limitFanStrength` |
| CPU thermal caps (`scaling_max_freq`) + Dvcsh limits | sysfs `/sys/.../cpufreq/policy*/scaling_max_freq`, logcat `ThermalManagerService` |
| XR FPS vs target, frame drops/s, CPU/GPU/RAM util | logcat `DynamicPolicyManager` |
| Display refresh Hz + power-save state (`disp_hz`, `psm`) | logcat `DynamicPolicyManager` |
| Camera/tracking service ingest rates (`cam_eye_fps`, `cam_head_fps`, `cam_hand_fps`, `irled_fps`) | logcat `XrHeartbeat` service heartbeats |
| Raw CIB stream rates (`cib_ht/hat/eyet/depthinput/depthtof_fps`, and `P-` variants) | logcat `[CIB]` `client_state` |
| Controller connection/battery/tracking | logcat `SXRC_TSVC`, `SXRC_POSE`, `CpmInput` |
| Passthrough mode / running | logcat `PassthroughStateManager`, `dumpsys cpm` (`XrPassthroughController`) |
| CPU per-core freq + policy max, GPU clock/busy/temp/throttle | sysfs `/sys/.../cpufreq`, `/sys/class/kgsl/kgsl-3d0` |
| AP/LRP/WiFi thermistor, load | `sec-*-thermistor`, `/proc` |
| Battery level/temp/AC/USB/status, derived drain rate | `dumpsys battery` (state cadence) |
| DDR (RAM) temperature | sysfs `/sys/class/thermal/thermal_zone15/temp` (`type=ddr`, fallback by zone type, 1 Hz) |
| Video, camera, AOSS/CPUSS and raw CPU temperatures | sysfs `/sys/class/thermal/thermal_zone*/type` + `temp` (1 Hz) |
| Power rail voltage/current/power | sysfs power-rail monitor (`max34427`), `all_ch1` (1 Hz) |
| Power rail energy | derived from rail power (1 Hz) |
| Battery drain rate | derived from `dumpsys battery` level |
| RAM total/used/cached/available, swap, zram, memory pressure | `/proc/meminfo`, `/proc/pressure/memory`, `/sys/block/zram0/mm_stat` |
| CPU utilisation per core, runnable tasks | `/proc/stat` |
| Storage capacity, free space, used % | `df -k /data` |
| WiFi link (Tx/Rx link speed, RSSI, band), packet/retry/loss rates | `cmd wifi status` |
| WiFi actual Rx/Tx throughput, dropped/errors | `/proc/net/dev` (`wlan0`) |
| Fan RPM/PWM | sysfs `/sys/class/sec_fan/fan/*` (root, read-only `su -c`) |
| Per-process CPU / RSS / GPU-mem / per-UID net / type / OOM | `dumpsys cpuinfo`, `ps`, `/proc/<pid>/stat`, `/proc/<pid>/oom_score_adj`, `pm list packages`, `dumpsys gpu`, `dumpsys netstats` |
| Per-process disk I/O | `/proc/<pid>/io` (root, `su -c`, with `--root --processes`) |
| Video decoder component/MIME/resolution/HDR format, hardware vs software | `dumpsys media.metrics` (codec session records) |
| Display brightness, HDR capability + active HDR | `dumpsys display`, `dumpsys SurfaceFlinger` (layer dataspaces) |
| Disk throughput, IOPS, busy time, latency | `/proc/diskstats` (delta between 1 Hz polls) |
| I/O pressure | `/proc/pressure/io` (PSI avg10) |
| Manufacture date | `getprop ril.manufacturedate` (`YYYYMMDD`) |
| Region / sales code / locale | `mdc.country_code`, `mdc.countryiso_code`, `ro.csc.sales_code`, `persist.sys.locale` |
| Measured IPD + eye/face calibration dates | OpenPX calibration files (root, read-only) + calibration settings |
| Guardian/boundary state | secure `guardian_*` + system `guardian_*` / `toggle_guardian` settings |
| Approximate first setup date | earliest mtime of user settings markers (root, read-only) |

### Findings index

Each topic links to tests/results first, then the digestible findings and full details.

> **Hardware state cutoff:** Runs before **2026-11-01** are from the **stock, unmodified** SM-I610. Runs from **2026-11-01 onward** (the in-between and after runs) are from the **SoC thermal-modded** headset (phase-change pads + copper shims). Thermal status 4 was only observed on the stock unit. Every topic page repeats its own `Hardware state` label at the top.

| Topic | Covers |
|---|---|
| [Device identity & boundary](gxr-findings/device.md) | build, region/CSC, manufacture, first setup, IPD/calibration, guardian |
| [Thermal, throttling & fan](gxr-findings/thermal.md) | temperature sources, CPU caps, GPU clock, fan, throttle ladder |
| [Thermal mod before/after](gxr-findings/thermal-mod.md) | phase-change pads + copper shims on the SoC: 7 paired tests, status-4 removal, performance gains and limits |
| [Thermal caps & fan steps](gxr-findings/thermal-caps-fan.md) | AP/LRP/CPU/GPU roles, status thresholds, CPU/camera caps, fan curve, where limits were hit |
| [Power rails & battery drain](gxr-findings/power.md) | rail voltage/current/power/energy, battery rate |
| [Cameras, perception & controllers](gxr-findings/tracking.md) | CIB streams, service rates, hand tracking, controller state |
| [Display, media & passthrough](gxr-findings/display-media.md) | decoders, HDR/color/bit depth, panel, passthrough |
| [Audio](gxr-findings/audio.md) | speaker/mic paths, latency, spatializer, codecs |
| [Bluetooth & location](gxr-findings/radios.md) | BLE-on quirk, A2DP, location modes |
| [Wi-Fi & standby](gxr-findings/wifi.md) | throughput, link rate, RSSI and retries after standby |
| [Storage I/O](gxr-findings/storage.md) | diskstats, pressure, per-process I/O |
| [CPU & memory](gxr-findings/cpu-memory.md) | meminfo, zram/swap, per-core utilisation |
| [Power modes & battery](gxr-findings/modes.md) | Battery Saver, hand tracking, battery/AC A/B |
| [Standby & wake](gxr-findings/standby.md) | rest/standby recovery, short vs long gap, status-3 re-entry |
| [Root](gxr-findings/root.md) | KernelSU reads, fan, calibration, limits |
| [Measurement coverage](gxr-findings/coverage.md) | captured, opt-in, available, unavailable |
| [Cross-run analysis](gxr-findings/cross-run.md) | 35-run correlations: thermal stages, fan curve, HDR, Wi-Fi, passthrough, process load |
| [Process offenders](gxr-findings/processes.md) | idle/active CPU, camera/perception cost, WiFi test client, YouTube/Chronolink, profiler overhead |
| [Background processes & debloat](gxr-findings/debloat.md) | controller HAL, hand tracking, profiler overhead, package cleanup |

### Key findings

- **The GPU clock is workload/display-state dependent, not fixed at 421 MHz.** Normal 72 Hz SRGB loads cluster at 421 MHz, but 8K/HDR at 90 Hz used 492-640 MHz, and after that session idle stayed at 545 MHz until a later run returned to 421 ([cross-run](gxr-findings/cross-run.md)). `gpu_clock_stats` still explains why ordinary 72 Hz loads look static at 421.
- **Thermal status 3 halves head/hand camera rates** (60 -> 30, raw 480/360 -> 240/180) after a 3-18 s lag, with `psm=0` and unchanged display rate ([cross-run](gxr-findings/cross-run.md)).
- **Thermal stage and fan step are separate ladders.** The stage tracked LRP (status 4 at LRP
>= 65 C); the fan tracked AP/GPU across steps 1-7 (~3.6k-5.9k RPM). Status 3 also correlates with the 1.92 GHz CPU cap. See [thermal caps & fan steps](gxr-findings/thermal-caps-fan.md).
- **The SoC thermal mod removed status 4 and cut CPU/GPU temperatures by 5-15 C.** Loaded CPU mean fell 7.8-14.9 C and GPU mean 5.3-10.1 C; AP fell 3.1-7.9 C and the power-path (LRP) sensor 0.7-6.7 C. The idle floor was essentially unchanged. 8K HDR still reaches status 3 and fan 7, and the untouched WIFI/DDR sensors remain the hottest under streaming/HDR (75-78 C / 69-74 C). See [thermal mod before/after](gxr-findings/thermal-mod.md).
- **No Wi-Fi thermal throttle is exposed at status 4.** WIFI has no HAL hot-throttling thresholds and status 4 tracked the LRP power-path trip (65 C); the only status-4 network-throughput run held ~498 Mbps with zero drops/errors. See [thermal mod before/after](gxr-findings/thermal-mod.md#status-4-and-wi-fi).
- **8K HDR at 90 Hz is GPU-bound**: 92-99% busy, ~70 fps against 90, fan step 7, CPU capped to 1.65-1.92 GHz ([cross-run](gxr-findings/cross-run.md)).
- **Process offenders**: SystemUI and SurfaceFlinger are the active-XR baseline; camera provider and perceptionhost dominate passthrough; `adbd` is profiler overhead, not a device workload ([processes](gxr-findings/processes.md)).
- **Throttling ladder** (idle -> OS -> OS+controllers -> VRChat): `thermal_status` 0->1->2, `fan_step` 1->3->6->7, and CPU `scaling_max_freq` only caps under the heaviest load (controllers briefly to 1.65 GHz; VRChat pinned both clusters at 1.92 GHz for 100% of the run). GPU clock stayed on the 421 MHz floor throughout that 72 Hz ladder.
- **Power saving does not reduce CPU frequency caps**; it mainly reduces display/XR to 60 Hz and halves the head/hand camera pipeline. See [Power modes & battery](gxr-findings/modes.md). Thermal status 3 can produce a similar camera halving without `psm`.
- **Low/critical battery did not add a battery-specific throttle.** Down to 3%, VRChat ran at the same thermal status-3 caps, `psm=0`, 72 Hz and 421 MHz GPU, with no shutdown. See [the battery follow-up](gxr-findings/modes.md#low--critical-battery-follow-up-2026-10-31).
- **An immediate standby wake is genuinely cold.** Straight from desk to head after ~18 min, the device started at status 0, AP 45 C, fan 1 and the 2.36 GHz CPU cap, with CPU utilisation starting low (core0 53%) and ramping as the workload loaded. It reached status 3 only after 277 s. Earlier after-standby recordings had already warmed during 1-2 min of use; a 3.7 min gap plus use re-entered status 3 within 35 s. See [standby & wake](gxr-findings/standby.md).
- **Wi-Fi throughput did not collapse after standby.** Two 60 s standby runs and a 5 min immediate-wake run sustained ~1.27 Gbps Rx with zero drops/errors and normal link-rate adaptation. The early "42.5% retry" in the immediate-wake run is a low-TX denominator artifact (3 pps TX), settling to ~5% once TX ramped. Latency/jitter was not measured. See [Wi-Fi & standby](gxr-findings/wifi.md).
- **Max Wi-Fi throughput reached ~2.17 Gbps** on a 2.5 GbE speedtest, about 87% of line rate, with the camera already thermally halved. The earlier 900 Mbps test was not link-limited: link rate was slightly higher there, so the old client/server path was the ceiling. 1.6 Gbps is a plausible upper cap at good orientation; 1.3-1.4 Gbps is safer with movement/body blocking. See [Wi-Fi & standby](gxr-findings/wifi.md).
- **The power-rail monitor adds a shell-readable 15 V rail, not battery power.** Rail 1 read about 15 V and 0.6-1.0 W while idle/unplugged; rail 2 was zero. Battery voltage/current/power remain `0`, and the rail labels are not exposed. See [power rails](gxr-findings/power.md).
- **The controller HAL is the biggest reducible background CPU cost.** With controllers active, `vendor.samsung.hardware.secxrcontroller@1.0-service` averaged ~27-35% CPU in Chronolink runs and dropped to 0 in controller-idle runs. Hand tracking costs ~5-10 CPU points in perception/camera and ~2 GPU points; most Samsung/Google app bloat was not actually running. See [background processes & debloat](gxr-findings/debloat.md).
- **Disabling hand tracking is a suspend, not a teardown** - small thermal benefit. See [Power modes & battery](gxr-findings/modes.md).
