# Research & findings

[Documentation home](../README.md) | [Profiler guide](../PROFILER.md) | [Commands](../COMMANDS.md) | [Exported reports](reports/README.md)

Measurement findings for the **Samsung Galaxy XR (SM-I610)**, collected with the read-only
recorder. Each topic page is self-contained: a plain-language summary, the tests and results, the
short findings, then the full details.

## How to read a topic page

Most pages follow the same order:

1. **In plain terms** - what the result means without the numbers.
2. **Tests & results** - what was measured, on which runs.
3. **Findings** - the conclusions, one line each.
4. **Details** - commands, tables and per-test breakdowns.

A few pages finish with **Caveats**, **next experiments** or commands instead of **Details**.

## Hardware state

The label at the top of each page uses one of four values. Read it before comparing numbers.

| Label | Meaning |
|---|---|
| **STOCK** | Unmodified headset; runs before 2026-11-01. |
| **MODDED** | SoC thermal-modded headset (phase-change pads + copper shims); 2026-11-01 onward. |
| **MIXED** | Both: stock before 2026-11-01, modded after (including the in-between and after runs). |
| **REFERENCE** | Describes coverage, format or method, not one hardware state. |

Thermal status 4 was only observed on the stock unit. See
[thermal mod before/after](thermal-mod.md) for the paired stock-vs-modded tests.

## Findings index

| Topic | Covers |
|---|---|
| [Device identity & boundary](device.md) | build, region/CSC, manufacture, first setup, IPD/calibration, guardian |
| [Thermal, throttling & fan](thermal.md) | temperature sources, CPU caps, GPU clock, fan, throttle ladder |
| [Thermal mod before/after](thermal-mod.md) | phase-change pads + copper shims on the SoC: 7 paired tests, status-4 removal, performance gains and limits |
| [Thermal caps & fan steps](thermal-caps-fan.md) | AP/LRP/CPU/GPU roles, status thresholds, CPU/camera caps, fan curve, where limits were hit |
| [Power rails & battery drain](power.md) | rail voltage/current/power/energy, battery rate |
| [Cameras, perception & controllers](tracking.md) | CIB streams, service rates, hand tracking, controller state |
| [Display, media & passthrough](display-media.md) | decoders, HDR/color/bit depth, panel, passthrough |
| [Audio](audio.md) | speaker/mic paths, latency, spatializer, codecs |
| [Bluetooth & location](radios.md) | BLE-on quirk, A2DP, location modes |
| [Wi-Fi & standby](wifi.md) | throughput, link rate, RSSI and retries after standby |
| [Storage I/O](storage.md) | diskstats, pressure, per-process I/O |
| [CPU & memory](cpu-memory.md) | meminfo, zram/swap, per-core utilisation |
| [Power modes & battery](modes.md) | Battery Saver, hand tracking, battery/AC A/B |
| [Standby & wake](standby.md) | rest/standby recovery, short vs long gap, status-3 re-entry |
| [Root](root.md) | KernelSU reads, fan, calibration, limits |
| [Crash & soft-reboot logs](crash-logs.md) | crash/events/system buffers, dropbox, tombstones, exit-info, rescue/boot props, root/SELinux limits |
| [Measurement coverage](coverage.md) | captured, opt-in, available, unavailable |
| [Cross-run analysis](cross-run.md) | 35-run correlations: thermal stages, fan curve, HDR, Wi-Fi, passthrough, process load |
| [Process offenders](processes.md) | idle/active CPU, camera/perception cost, WiFi test client, YouTube/Chronolink, profiler overhead |
| [Background processes & debloat](debloat.md) | controller HAL, hand tracking, profiler overhead, package cleanup |
| [Black level floor](root-research/black-level-floor.md) | panel black level, compositor/QDCM checks, B4/D1 gamma tests, ELVSS, MTP read limits |

## Key findings

- **GPU clock is workload and display-state dependent, not fixed at 421 MHz.** Normal 72 Hz SRGB
  loads cluster at 421 MHz, 8K/HDR at 90 Hz used 492-640 MHz, and post-HDR idle stayed at 545 MHz
  ([cross-run](cross-run.md)).
- **Thermal status 3 halves head/hand camera rates** from 60 to 30 fps (raw 480/360 to 240/180)
  after a 3-18 s lag, with `psm=0` and an unchanged display rate ([cross-run](cross-run.md)).
- **Thermal stage and fan step are separate ladders.** The stage tracked LRP (status 4 at LRP
  >= 65 C); the fan tracked AP/GPU across steps 1-7. Status 3 also correlates with the 1.92 GHz CPU
  cap ([thermal caps & fan steps](thermal-caps-fan.md)).
- **The SoC thermal mod removed status 4 and cut CPU/GPU temperatures by 5-15 C.** Loaded CPU mean
  fell 7.8-14.9 C and GPU mean 5.3-10.1 C; 8K HDR still reaches status 3 and fan 7
  ([thermal mod before/after](thermal-mod.md)).
- **No Wi-Fi thermal throttle is exposed at status 4.** WIFI has no HAL hot-throttling thresholds;
  the only status-4 network run held ~498 Mbps with zero drops/errors
  ([thermal mod before/after](thermal-mod.md#status-4-and-wi-fi)).
- **8K HDR at 90 Hz is GPU-bound**: 92-99% busy, ~70 fps against 90, fan step 7, CPU capped to
  1.65-1.92 GHz ([cross-run](cross-run.md)).
- **Process offenders**: SystemUI and SurfaceFlinger are the active-XR baseline; camera provider
  and perceptionhost dominate passthrough; `adbd` is profiler overhead, not a device workload
  ([processes](processes.md)).
- **The throttling ladder** (idle to OS to controllers to VRChat) raised `thermal_status` 0->1->2
  and `fan_step` 1->3->6->7; CPU caps appeared only under the heaviest load, and the GPU stayed at
  421 MHz. See [thermal caps & fan steps](thermal-caps-fan.md).
- **Power saving does not reduce CPU frequency caps.** It mainly drops display/XR to 60 Hz and
  halves the head/hand camera pipeline ([Power modes & battery](modes.md)).
- **Low/critical battery added no battery-specific throttle.** Down to 3%, VRChat kept the same
  status-3 caps, `psm=0`, 72 Hz and 421 MHz GPU, with no shutdown
  ([battery follow-up](modes.md#low--critical-battery-follow-up-2026-10-31)).
- **An immediate standby wake is genuinely cold.** After ~18 min on a desk the device started at
  status 0, AP 45 C, fan 1 and the 2.36 GHz cap, and reached status 3 only after 277 s
  ([standby & wake](standby.md)).
- **Wi-Fi throughput did not collapse after standby.** Standby and immediate-wake runs sustained
  ~1.27 Gbps Rx with zero drops/errors; the early "42.5% retry" was a low-TX denominator artifact
  ([Wi-Fi & standby](wifi.md)).
- **Max Wi-Fi throughput reached ~2.17 Gbps** on a 2.5 GbE speedtest, about 87% of line rate.
  1.3-1.4 Gbps is the safer expectation with movement or body blocking
  ([Wi-Fi & standby](wifi.md)).
- **The power-rail monitor is a shell-readable 15 V rail, not battery power.** Rail 2 was zero, and
  battery voltage/current/power remain `0` ([power rails](power.md)).
- **The controller HAL is the biggest reducible background CPU cost.** It averaged ~27-35% CPU in
  Chronolink runs and dropped to 0 when controllers were idle; hand tracking costs ~5-10 CPU points
  in perception/camera ([debloat](debloat.md)).
- **Two Beat Saber soft reboots were SystemUI HWUI animation races, not thermal or hardware.** The
  headset was hot (AP ~74-75 C, WIFI ~78 C, status 3, fan 7) but did not reach status 4
  ([crash logs](crash-logs.md) and the
  [2026-11-17 report](reports/soft-reboots/2026-11-17-systemui-hwui-beatsaber.md)).
- **Disabling hand tracking is a suspend, not a teardown**, so the thermal benefit is small
  ([Power modes & battery](modes.md)).
- **The micro-OLED black floor is not in the exposed gamma tables.** The compositor outputs
  true black, QDCM maps 0 to 0, and `B4` only dims the whole image; `D1` `BB` is per-panel
  calibration. The remaining floor is panel/optical; the only safe software lever is brightness
  ([black level floor](root-research/black-level-floor.md)).

## Exported reports

Dated, sanitized HTML comparisons and investigation notes are indexed in
[reports/](reports/README.md).
