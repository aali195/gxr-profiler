# Thermal, throttling & fan

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Temperature, thermal-status and fan findings from the 1 Hz poll plus event-driven logcat.
`gxr-profiler` treats the HAL poll as authoritative and logcat as supplementary.

## Tests & results

Probed 2026-10-20 to 2026-10-24 during idle, OS, controllers, VRChat and HDR runs.

| Probe | Observed result |
|---|---|
| `thermal_changed` vs `dumpsys thermalservice` at steady temp | logcat silent; HAL continues at 1 Hz |
| logcat `-s` vs `-e` | `-s` misses colon tags such as `SSRM:Temperature`; `-e` matches messages |
| fan step vs fan RPM | step only in `SSRM:w`; RPM/PWM are root-only sysfs |
| `scaling_max_freq` policy0/policy2 | 1.92/1.92 GHz idle; caps only under heaviest load |
| AP vs skin vs `sec_ap` | identical to 0.1 C - same physical sensor |
| GPU clock, 72 Hz vs 90 Hz | 421 MHz common at 72 Hz; 492-640 MHz in 90 Hz HDR; 545 MHz idle after HDR |
| idle -> OS -> controllers -> VRChat | thermal status 0/1/2; fan step 1/3/6/7 |

## Findings

- HAL temperatures are primary; `thermal_changed` is event-only.
- Fan step is logcat-only; fan RPM/PWM require root.
- CPU caps come from live `scaling_max_freq`; Dcvsh is event-only.
- GPU load usually shows as `g_busy` at 72 Hz, but the clock is not globally fixed: 90 Hz HDR
  and post-HDR idle can raise it. See [cross-run analysis](cross-run.md).
- AP, skin and `sec_ap` are the same sensor.
- Throttling escalates through status and fan step before CPU caps.

## Details

- logcat `-s` does exact tag matching, so it **misses** colon tags like `SSRM:Temperature`;
  `-e` matches the **message**, not the tag. The tool streams unfiltered with `-T 1` and filters
  by tag in Python.
- `thermal_changed` fires **only on change/threshold crossings** (`[NAME,TYPE,VALUE,sev,hot]`) -
  at a steady temperature it stays silent, so it cannot be the primary temp source. Per-core /
  GPU / NPU / skin temps come from the 1 Hz `dumpsys thermalservice` HAL poll instead.
- Thermal CPU caps are captured two ways: every tick from `scaling_max_freq` for policy0/policy2
  (`cpu_max0/2`, the live cap) and event-driven from the `ThermalManagerService` Dcvsh log
  (`dcvsh_*`). The poll is reliable; the Dcvsh log only fires on change. The live TUI shows
  `CAPPED` when either policy drops below 2.36 GHz.
- `SSRM:Temperature` gives a ~3.5 s snapshot (CHG/SUBBAT/BAT/USB/WIFI/AP/LRP).
- Global thermal status appears in `DynamicPolicyManager` (~15 s JSON blob).
- **Fan step is logcat-only** - `/sys/class/sec_fan/fan` is root-only.
- `/sys/class/kgsl/kgsl-3d0/gpuclk` and `devfreq/cur_freq` are permission-denied to shell; GPU
  clock comes from `clock_mhz` (`g_devfreq` is derived from it).
- Battery current/voltage are not exposed (`0`), even with root; `dumpsys battery` gives
  temp/level/AC.
- Two CPU clusters: policy0 = cores 0-1, policy2 = cores 2-5 (2.3616 GHz max;
  `scaling_max_freq` drops when capped).
- `t_AP`, `t_skin` and `sec_ap` are **the same physical sensor** (the HAL reads
  `/sys/class/sec/sec-ap-thermistor/temperature` for both AP and skin) - they track identically
  to 0.1 C.
