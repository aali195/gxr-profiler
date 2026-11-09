# Thermal, throttling & fan

[Findings index](../README.md) | [Commands](../COMMANDS.md) | [Thermal caps & fan steps](thermal-caps-fan.md) | [Thermal mod before/after](thermal-mod.md)

> **Hardware state: MIXED - STOCK BEFORE 2026-11-01, MODDED AFTER.** Runs before 2026-11-01 are from the unmodified headset. Runs from 2026-11-01 onward, including the in-between and after runs, are from the SoC thermal-modded headset (phase-change pads + copper shims). Thermal status 4 was only observed on the stock unit.

Temperature, thermal-status and fan findings from the 1 Hz poll plus event-driven logcat. `gxr-profiler` treats the HAL poll as authoritative and logcat as supplementary.

## In plain terms

- When **thermal status 3** is reached, head and hand tracking cameras drop from 60 to 30 fps. Fast hand movement and controller tracking can feel worse; the display refresh rate stays the same.
- The fan has seven fixed steps. Light VR is usually quiet; 8K HDR and heavy streaming can pin it at the loudest step.
- Status 4 was only seen on the stock unit in the pre-mod worst cases. Normal use mostly stays at status 0-3.
- Status 3 still occurs **after** the mod, especially in 8K HDR. The mod lowers the temperature and removes status 4, but it does not stop the status-3 camera cap.
- Passthrough, 8K HDR, 90 Hz and long streaming sessions are the biggest heat sources. Charging while playing can add a fan step.

## Tests & results

Probed 2026-10-20 to 2026-11-07 during idle, OS, controllers, VRChat, HDR and before/after mod runs.

| Probe | Observed result |
|---|---|
| `thermal_changed` vs `dumpsys thermalservice` at steady temp | logcat silent; HAL continues at 1 Hz |
| logcat `-s` vs `-e` | `-s` misses colon tags such as `SSRM:Temperature`; `-e` matches messages |
| fan step vs fan RPM | step only in `SSRM:w`; RPM/PWM are root-only sysfs |
| `scaling_max_freq` policy0/policy2 | 1.92/1.92 GHz idle; caps only under heaviest load |
| AP vs skin vs `sec_ap` | identical to 0.1 C - same physical sensor |
| GPU clock, 72 Hz vs 90 Hz | 421 MHz common at 72 Hz; 492-640 MHz in 90 Hz HDR; 545 MHz idle after HDR |
| kernel `ddr` thermal zone | `thermal_zone15` readable by shell (~43.9 C), absent from the HAL named set |
| raw thermal zones (idle) | `video` ~35.7 C, `camera-0/1` ~35.0/35.3 C, `aoss-0/1` ~35.5/35.7 C, `cpuss-0/1` ~35.8 C, 12 `cpu-*` zones; none are in the HAL named set |
| idle -> OS -> controllers -> VRChat | thermal status 0/1/2; fan step 1/3/6/7 |
| global thermal status 4 | observed only on the pre-mod runs (AP 76.9-78.7 C, LRP 65.0-66.3 C) |
| HAL hot thresholds | AP 50/58/69/73/80 C; LRP 49/53/57/62/65/67/80 C; CPU/GPU/NPU 95/115 C; WIFI/CHG/BAT/USB/skin none |

## Findings

- HAL temperatures are primary; `thermal_changed` is event-only.
- Fan step is logcat-only; fan RPM/PWM require root.
- CPU caps come from live `scaling_max_freq`; Dcvsh is event-only.
- GPU load usually shows as `g_busy` at 72 Hz, but the clock is not globally fixed: 90 Hz HDR and post-HDR idle can raise it. See [cross-run analysis](cross-run.md).
- AP, skin and `sec_ap` are the same sensor. `skin` and `sec_ap` stay in the raw CSV for fallback/diagnostics but are not charted separately.
- DDR/RAM temperature exists as a separate kernel thermal zone (`ddr`), but is not in the HAL named-temperature set.
- The raw thermal-zone set adds video, camera, AOSS/CPUSS and per-core CPU sensors that the HAL does not expose. AOSS/CPUSS and raw CPU zones are kept under **Extra -> Raw thermal**.
- Throttling escalates through status and fan step before CPU caps.
- The global status ladder tracks the **LRP (power path)** thresholds in the local runs: status 4 only appeared with LRP >= 65 C, while AP stayed below its 80 C stage-4 threshold. WIFI has no hot-throttling thresholds, so no Wi-Fi thermal throttle is exposed at status 4. See [thermal mod before/after](thermal-mod.md).
- The phase-change/copper SoC mod cut loaded CPU mean by 7.8-14.9 C and GPU mean by 5.3-10.1 C, and lowered AP/LRP enough to remove status 4; 8K HDR still reaches status 3. See [thermal mod before/after](thermal-mod.md).

## Details

- logcat `-s` does exact tag matching, so it **misses** colon tags like `SSRM:Temperature`; `-e` matches the **message**, not the tag. The tool streams unfiltered with `-T 1` and filters by tag in Python.
- `thermal_changed` fires **only on change/threshold crossings** (`[NAME,TYPE,VALUE,sev,hot]`) - at a steady temperature it stays silent, so it cannot be the primary temp source. Per-core / GPU / NPU / skin temps come from the 1 Hz `dumpsys thermalservice` HAL poll instead.
- Thermal CPU caps are captured two ways: every tick from `scaling_max_freq` for policy0/policy2 (`cpu_max0/2`, the live cap) and event-driven from the `ThermalManagerService` Dcvsh log (`dcvsh_*`). The poll is reliable; the Dcvsh log only fires on change. The live TUI shows `CAPPED` when either policy drops below 2.36 GHz.
- `SSRM:Temperature` gives a ~3.5 s snapshot (CHG/SUBBAT/BAT/USB/WIFI/AP/LRP).
- Global thermal status appears in `DynamicPolicyManager` (~15 s JSON blob).
- **Fan step is logcat-only** - `/sys/class/sec_fan/fan` is root-only.
- `/sys/class/kgsl/kgsl-3d0/gpuclk` and `devfreq/cur_freq` are permission-denied to shell; GPU clock comes from `clock_mhz`.
- Battery current/voltage are not exposed (`0`), even with root; `dumpsys battery` gives temp/level/AC.
- Two CPU clusters: policy0 = cores 0-1, policy2 = cores 2-5 (2.3616 GHz max; `scaling_max_freq` drops when capped).
- `t_AP`, `t_skin` and `sec_ap` are **the same physical sensor** (the HAL reads `/sys/class/sec/sec-ap-thermistor/temperature` for both AP and skin) - they track identically to 0.1 C.
- `/sys/class/thermal/thermal_zone15/temp` is the kernel `ddr` zone (millidegrees C). If that path is absent or is no longer type `ddr`, gxr-profiler falls back to the thermal zone whose type is `ddr`. It is shell-readable but does not appear in `dumpsys thermalservice`, so it is polled separately as `ddr_temp`. `LRP` is the power path, not RAM.
- The raw-zone poll matches zone `type` names rather than fixed indices: `video`, `camera-0/1`, `aoss-0/1`, `cpuss-0/1`, and `cpu-0-*`/`cpu-1-*`. PMIC zones (`pmxr2230_tz`, `pm8550*`) return no valid temperature, and `sys-therm-*` is not used because several entries are invalid or implausible (for example `sys-therm-2` ~66.8 C at idle). The `ac`, `battery`, `pogo` and `usb` zones duplicate HAL `BAT`/`CHG`/`USB` readings or return invalid values, so they are not recorded separately.
- The full HAL threshold, status-by-status median and fan-step reference is in [thermal caps & fan steps](thermal-caps-fan.md). Status 4 in the local library only occurred with LRP 65.0-66.3 C and AP 76.9-78.7 C, consistent with the LRP stage-4 trip.
