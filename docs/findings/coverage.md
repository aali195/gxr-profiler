# Measurement coverage

[Findings index](../README.md) | [Commands](../COMMANDS.md)

What gxr-profiler records, what is opt-in, and what remains unavailable.

## Tests & results

Coverage status as of the current schema/build.

| Area | Status |
|---|---|
| Temps, throttle, clocks, XR/CPU/GPU/RAM, cameras, controllers, passthrough, display, battery, network, device snapshot | Captured |
| Fan RPM/PWM | `--root` |
| Measured IPD/calibration dates, first setup | `--root` |
| Android SensorService summary | `--sensors` |
| Per-process snapshot | `--processes`; disk I/O adds `--root --process-io` |
| Regulator rail voltages, modeled power | Available, not captured |
| Real SoC power/battery current, NPU/DSP utilisation, sensor-level camera rates | Not available |

## Findings

- Core 1 Hz telemetry and one-time device metadata are always captured.
- Fan, per-process I/O, calibration dates and first setup are root opt-ins.
- Process snapshots and sensor-service summaries are separate opt-ins.
- Power, NPU/DSP and physical camera routing remain unavailable.
- Existing runs are not backfilled when new fields are added.

## Details

**Captured** (1 Hz poll + event stream):
- Temps: HAL named set (CPU0-5, GPU0-7, nsp0-2, AP, skin, WIFI, LRP, BAT, CHG, USB) +
  `sec-*-thermistor`.
- Throttle/caps: global thermal status, per-sensor severity, CPU `scaling_max_freq` caps, GPU
  throttling, thermal thresholds; fan step.
- Clocks: CPU per-core, GPU clock (`kgsl`) + residency (`gpu_clock_stats`).
- Performance: XR fps/target/drops, CPU/GPU/RAM util, GPU busy %, load, mem.
- Cameras: raw CIB streams (`HT`/`Hat`/`EyeT`/`Depth`), perception ingest rates, IR LED.
- Controllers: per-side connection, tracking, pose status, battery, trigger/squeeze/grip/thumbstick events.
- Passthrough: requested mode, running flag, camera state.
- Display: refresh Hz + power-save state.
- Battery: temp, capacity, charge counter, status, health, AC online.
- Network: link Tx/Rx, RSSI, band, retries/loss.
- Device/build/region/manufacture/Wi-Fi/panel/audio snapshot once per run
  (`meta.json -> device_info`).
- Current IPD/calibration status and guardian/boundary state once per run (no root).

**Captured opt-in:**
- **Fan RPM/PWM** with `--root`.
- **Measured IPD, eye/face calibration file dates and approximate first setup date** with
  `--root` (read-only OpenPX files and user-settings mtimes).
- **Android sensor-service summary** with `--sensors`: `sensors_total`, `sensors_running`,
  `sensors_disabled_clients`, `sensors_active`, `sensor_conns`, `sensor_rate_min_ms`,
  `sensor_max_hz`. Note: **XR IMUs bypass Android SensorService** (consumed directly by the
  perception host), so this reflects only Android sensor clients - typically just the
  offbody/proximity sensor at ~5 Hz.
- **Per-process snapshot** with `--processes`: all non-kernel processes (optional `--processes-kernel`),
  current CPU, RSS, GPU memory, disk/network rates, package/system type and OOM class per PID;
  with `--root`, cumulative disk bytes and read/write rates per PID.

**Available but not captured yet:**
- **Regulator rail voltages** - `/sys/class/regulator/*/microvolts` (many rails; no current).
- **Modeled power** - `dumpsys batterystats` "Estimated power use (mAh)" (a model, not a
  measurement).

**Not available, even with root:**
- **Real SoC power / battery current/voltage** - `battery` reports
  `VOLTAGE_NOW = CURRENT_NOW = POWER_NOW = 0`, `charge_counter` is static,
  `cmd powerstats` = "No shell command implementation", debugfs is not mounted.
- **NPU/DSP utilisation** - `/sys/devices/soc0/npu` is `0x0`; tracefs events need writes.
- **Sensor-level camera rates** - only CIB/perception stream rates are exposed.
