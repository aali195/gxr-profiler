# Thermal mod: phase-change pads + copper shims (SoC only)

[Findings index](../README.md) | [Thermal, throttling & fan](thermal.md) | [Thermal caps & fan steps](thermal-caps-fan.md) | [Wi-Fi & standby](wifi.md)

> **Hardware state: MIXED - STOCK BEFORE 2026-11-01, MODDED AFTER.** Runs before 2026-11-01 are from the unmodified headset. Runs from 2026-11-01 onward, including the in-between and after runs, are from the SoC thermal-modded headset (phase-change pads + copper shims). Thermal status 4 was only observed on the stock unit.

The original SoC thermal solution was replaced with phase-change pads and copper shims on the SoC. The DRAM and Wi-Fi chips were deliberately left untouched. Seven numbered scenarios were recorded before and after the mod on the same SM-I610 (build `I610UEU2AZF3`), plus a set of in-between runs while the assembly settled.

- Before: 2026-10-31 20:20-23:44 UTC.
- In-between: 2026-11-01 04:03 to 2026-11-02 04:05 UTC.
- After: 2026-11-06 22:01 to 2026-11-07 02:36 UTC.
- All comparison runs are 120 s.
- Cooldown between tests: headset put down until the CPU was around 50 C.
- Room temperature reading: **~25 C before**, **~24 C after**. These are rough, uncalibrated readings, not lab-grade ambient measurements.

This page separates what the run data shows from what it cannot show. The short version: the mod is effective on the SoC and power path, removes thermal status 4, and unlocks sustained performance. It does not fix HDR, it does not stop the fan reaching step 7 under the heaviest loads, and it does not cool the untouched Wi-Fi/DRAM hotspots much.

## In plain terms

- **Normal VR should run cooler and hold performance longer.** CPU was 8-15 C cooler and GPU 5-10 C cooler in loaded tests; thermal status 4 disappeared.
- **In practice:** Virtual Desktop/Chronolink kept full 60 fps tracking cameras instead of dropping to 30, and Chronolink dropped from fan 7 to fan 5. Light VR/passthrough was quieter too.
- **Still demanding:** 8K HDR remains status 3 with fan 7 and about 73 fps against 90. Virtual Desktop can still reach fan 7, and HDR still halves the tracking camera to 30 fps.
- **Idle is unchanged**, and the untouched Wi-Fi/DRAM chips still get hot. This is a SoC cooling upgrade, not a whole-headset fix.
- The before/after tests were not perfectly matched (some after runs used 90 Hz due to lack of thermal throttling), so treat the exact deltas as directional, not laboratory-controlled.

## Runs used

| Test | Before run | After run |
|---:|---|---|
| 1 | `before-1-idle-passthrough-hands` | `after-1-idle-passthrough-hands` |
| 2 | `before-2-idle-on-desk` | `after-2-idle-on-desk` |
| 3 | `before-3-idle-hands-vr` | `after-3-idle-hands-vr` |
| 4 | `before-4-youtube-no-hdr-hand-vr` | `after-4-youtube-no-hdr-hand-vr` |
| 5 | `before-5-youtube-hdr-hand-vr` | `after-5-youtube-hdr-hand-vr` |
| 6 | `before-6-virtualdesktop-h264-rampage-controllers-vrchat-fish-world-night` | `after-6-virtualdesktop-h264-rampage-controllers-vrcjat-fish-night-500mbps` |
| 7 | `before-7-chronolink-astc-controllers-vrchat-fish-world-night` | `after-7-chronolink-astc-controllers-vrchat-fish-world-night` |

The in-between runs are not used in the before/after tables. For test 6 the table uses the final clean 500 Mbps repeat (the directory name contains the `vrcjat` typo); the other Virtual Desktop after-run variants are compared in [Virtual Desktop and day/night runs](#virtual-desktop-and-daynight-runs).

## Exported reports

Each test has a self-contained `gxr-profiler` HTML report with both runs embedded. GitHub shows the
HTML source in its file viewer rather than rendering it; use **Preview** for a rendered view or
**HTML** to download/open locally. The report index and labels are in
[reports/thermal-mod/README.md](reports/thermal-mod/README.md).

| Test | Scenario | Report |
|---:|---|---|
| 1 | idle + passthrough + hands | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-1-idle-passthrough-hands-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-1-idle-passthrough-hands-stock-vs-mod.html) |
| 2 | idle on desk | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-2-idle-on-desk-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-2-idle-on-desk-stock-vs-mod.html) |
| 3 | idle + hands, VR | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-3-idle-hands-vr-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-3-idle-hands-vr-stock-vs-mod.html) |
| 4 | YouTube 4K SDR | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-4-youtube-4k-sdr-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-4-youtube-4k-sdr-stock-vs-mod.html) |
| 5 | YouTube 8K HDR | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-5-youtube-8k-hdr-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-5-youtube-8k-hdr-stock-vs-mod.html) |
| 6 | Virtual Desktop H.264, ~500 Mbps | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-6-virtual-desktop-500mbps-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-6-virtual-desktop-500mbps-stock-vs-mod.html) |
| 7 | Chronolink/SteamVR ASTC | [Preview](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-7-chronolink-astc-stock-vs-mod.html) / [HTML](reports/thermal-mod/test-7-chronolink-astc-stock-vs-mod.html) |

## Headline findings

- **The SoC itself is substantially cooler under load.** Across loaded tests 1 and 3-7, the CPU sensor mean fell **7.8-14.9 C** and the GPU mean fell **5.3-10.1 C**. CPU peak fell 8.8-15.2 C and GPU peak fell 7.7-12.1 C. The idle-on-desk baseline was unchanged (CPU 47.0 -> 44.7 C, GPU 45.0 -> 44.0 C, AP 43.3 -> 42.6 C), which is exactly what a cooling mod should look like.
- **Board/power-path sensors improved less than the SoC.** AP fell 3.1-7.9 C and LRP fell 0.7-6.7 C (2.7-6.7 C in the heavier tests 3-7). The CPU/GPU data is the direct measure of the mod; AP/LRP are secondary board-level indicators.
- **Global thermal status dropped in every loaded test.** Test 4 went from 1->2 to 1, test 5 from 4 to 3, test 6 from 4 to 2, and test 7 from 3 to 2. **Status 4 was not observed at all after the mod.**
- **It buys performance, not just lower temperatures.** Test 5 went from 53.1 fps against a 72 Hz target to 73.2 fps against 90 Hz, with the CPU cap rising from 1.38 to 1.92 GHz. Test 6 went 79.4 -> 85.3 fps, test 7 went 87.6 -> 90.4 fps, and the head camera stayed at 60 fps in tests 6/7 instead of being halved to 30 fps by status 3.
- **The fan is lower only in light/moderate workloads.** It dropped in tests 1, 3, 4 and 7, but still reached step 7 in 8K HDR and Virtual Desktop.
- **It did not fix the other hotspots.** In streaming/HDR workloads the WIFI sensor remained the hottest named sensor at 75-78 C, DDR sat at 69-74 C, and 8K HDR still hit status 3, fan 7, ~99% GPU busy and ~73 fps against 90.
- **There is no evidence that status 4 limits Wi-Fi speed.** The Wi-Fi sensor has no HAL hot-throttling thresholds. Status 4 lined up with the LRP power-path threshold (65 C), and the only status-4 streaming run held ~498 Mbps with zero drops/errors. See [status 4 and Wi-Fi](#status-4-and-wi-fi).

## Summary

All temperatures are C. CPU mean is the average of the six HAL CPU sensors over the run; CPU peak is the hottest single CPU sensor. GPU mean/peak use the eight HAL GPU sensors the same way.

### SoC thermal summary

| Test | Scenario                   | Status before (start -> end; peak) | Status after (start -> end; peak) | CPU mean before -> after (delta) | CPU peak before -> after | GPU mean before -> after (delta) | GPU peak before -> after |
| ---: | -------------------------- | ---------------------------------- | --------------------------------- | -------------------------------- | ------------------------ | -------------------------------- | ------------------------ |
|    1 | idle + passthrough + hands | 1 -> 1 (1)                         | 1 -> 1 (1)                        | 70.9 -> 63.1 (-7.8)              | 75.7 -> 66.9             | 66.6 -> 61.2 (-5.3)              | 70.7 -> 63.0             |
|    2 | idle on desk               | 0 -> 0 (0)                         | 0 -> 0 (0)                        | 47.0 -> 44.7 (-2.3)              | 53.8 -> 52.1             | 45.0 -> 44.0 (-0.9)              | 48.2 -> 47.1             |
|    3 | idle + hands, VR           | 0 -> 1 (1)                         | 0 -> 0 (0)                        | 64.9 -> 53.7 (-11.2)             | 68.0 -> 57.1             | 61.3 -> 52.4 (-8.9)              | 63.7 -> 54.2             |
|    4 | YouTube 4K SDR             | 1 -> 2 (2)                         | 1 -> 1 (1)                        | 74.8 -> 65.7 (-9.1)              | 80.8 -> 69.7             | 71.3 -> 64.1 (-7.1)              | 74.8 -> 65.7             |
|    5 | YouTube 8K HDR             | 4 -> 4 (4)                         | 3 -> 3 (3)                        | 84.3 -> 74.6 (-9.7)              | 87.6 -> 77.1             | 81.9 -> 73.3 (-8.6)              | 84.6 -> 74.8             |
|    6 | Virtual Desktop H.264      | 4 -> 4 (4)                         | 1 -> 2 (2)                        | 86.4 -> 71.5 (-14.9)             | 88.6 -> 73.4             | 79.2 -> 69.1 (-10.1)             | 82.2 -> 70.1             |
|    7 | Chronolink/SteamVR ASTC    | 3 -> 3 (3)                         | 2 -> 2 (2)                        | 81.2 -> 70.6 (-10.6)             | 84.2 -> 72.0             | 76.3 -> 68.6 (-7.7)              | 79.2 -> 69.7             |

### Power and performance summary

| Test | Scenario | AP mean before -> after (delta) | LRP mean before -> after (delta) | Fan step before -> after | XR fps / target before -> after |
|---:|---|---|---|---|---|
| 1 | idle + passthrough + hands | 64.1 -> 61.0 C (-3.1) | 53.1 -> 52.4 C (-0.7) | 3.5 -> 2.9 | 72.0 / 72 -> 72.0 / 72 |
| 2 | idle on desk | 43.3 -> 42.6 C (-0.7) | 42.4 -> 42.5 C (+0.1) | 1.0 -> 1.0 | 72.0 / 72 -> 71.9 / 72 |
| 3 | idle + hands, VR | 59.8 -> 51.9 C (-7.9) | 50.8 -> 44.1 C (-6.7) | 2.7 -> 1.0 | 72.0 / 72 -> 72.0 / 72 |
| 4 | YouTube 4K SDR | 68.2 -> 63.9 C (-4.3) | 57.6 -> 54.4 C (-3.2) | 4.3 -> 3.4 | 72.0 / 72 -> 90.0 / 90* |
| 5 | YouTube 8K HDR | 77.6 -> 73.6 C (-4.0) | 65.5 -> 61.6 C (-3.9) | 7.0 -> 7.0 | 53.1 / 72 -> 73.2 / 90* |
| 6 | Virtual Desktop H.264 | 76.9 -> 70.1 C (-6.9) | 65.0 -> 61.0 C (-4.0) | 7.0 -> 7.0 | 79.4 / 72 -> 85.3 / 90* |
| 7 | Chronolink/SteamVR ASTC | 74.4 -> 69.9 C (-4.5) | 62.0 -> 59.2 C (-2.7) | 7.0 -> 5.0 | 87.6 / 90 -> 90.4 / 90 |

\* Tests 4-6 ran at 90 Hz after the mod but 72 Hz before it, so the after run is doing more GPU work. Test 5 also changed media format between runs; see the per-test notes.

### Wi-Fi and memory summary

| Test | Scenario | WIFI mean before -> after | DDR mean after (before not recorded) | Wi-Fi Rx mean before -> after (p5-p95) | Retry before -> after |
|---:|---|---:|---:|---|---:|
| 1 | idle + passthrough + hands | 66.2 -> 64.0 C | 62.1 C | 0.3 -> 0.2 Mbps (0.2-0.3) | 5.33 -> 5.86% |
| 2 | idle on desk | 45.5 -> 45.6 C | 44.3 C | 0.1 -> 0.1 Mbps (0.1-0.2) | 9.11 -> 14.91% |
| 3 | idle + hands, VR | 61.3 -> 54.9 C | 53.1 C | 0.2 -> 0.2 Mbps (0.2-0.3) | 6.72 -> 5.31% |
| 4 | YouTube 4K SDR | 70.0 -> 67.3 C | 64.9 C | 3.6 -> 8.1 Mbps (0.3-54.4) | 4.22 -> 5.01% |
| 5 | YouTube 8K HDR | 79.7 -> 78.3 C | 73.8 C | 51.0 -> 55.5 Mbps (19.3-75.7) | 4.17 -> 4.66% |
| 6 | Virtual Desktop H.264 | 79.0 -> 75.0 C | 70.2 C | 497.6 -> 495.4 Mbps (467.0-516.7) | 1.72 -> 2.04% |
| 7 | Chronolink/SteamVR ASTC | 78.3 -> 76.4 C | 69.3 C | 1,138.7 -> 1,217.0 Mbps (1,149.0-1,263.9) | 7.46 -> 5.25% |

Tests 1-5 are not network-throughput tests, so their Wi-Fi Rx is mostly idle/video traffic. Test 6 is a ~500 Mbps stream and test 7 a ~1.2 Gbps stream. Retry % is unreliable at very low TX pps; all runs had zero drops/errors.

## Test 1 - idle + passthrough + hands

Both 120 s, 72 Hz, unplugged, hands and passthrough active.

| Metric                                     | Before             | After              | Change              |
| ------------------------------------------ | ------------------ | ------------------ | ------------------- |
| Global thermal status (start -> end; peak) | 1 -> 1 (1)         | 1 -> 1 (1)         | same stage          |
| CPU mean / peak                            | 70.9 / 75.7 C      | 63.1 / 66.9 C      | -7.8 / -8.8 C       |
| GPU mean / peak                            | 66.6 / 70.7 C      | 61.2 / 63.0 C      | -5.3 / -7.7 C       |
| AP mean / max                              | 64.1 / 66.1 C      | 61.0 / 62.6 C      | -3.1 / -3.5 C       |
| LRP mean / max                             | 53.1 / 55.0 C      | 52.4 / 54.0 C      | -0.7 / -1.0 C       |
| WIFI sensor mean / max                     | 66.2 / 68.9 C      | 64.0 / 65.7 C      | -2.2 / -3.2 C       |
| DDR mean / max                             | not recorded       | 62.1 / 63.6 C      | n/a                 |
| Fan step mean / max; RPM mean              | 3.5 / 4; 4,285     | 2.9 / 3; 4,169     | -0.6 step; -116 RPM |
| CPU cap policy0 / policy2                  | 2.36 / 2.36 GHz    | 2.36 / 2.36 GHz    | same                |
| GPU clock / busy                           | 421 MHz / 34.8%    | 421 MHz / 37.4%    | +2.6 pts busy       |
| XR fps / target; drops/s                   | 72.0 / 72; 0       | 72.0 / 72; 0       | same                |
| Head camera fps                            | 60                 | 60                 | same                |
| Wi-Fi Rx mean (p5-p95)                     | 0.3 Mbps (0.2-0.3) | 0.2 Mbps (0.2-0.3) | -0.1 Mbps           |
| Wi-Fi retry mean; drops/errors             | 5.33%; 0           | 5.86%; 0           | 0 drops/errors      |
| Battery / AC                               | 96% / off          | 94% / off          | -                   |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-1-idle-passthrough-hands-stock-vs-mod.html)

The after run was slightly busier on the GPU but the CPU was 7.8 C and the GPU 5.3 C cooler, and it stayed at fan step 3 instead of touching step 4.

## Test 2 - idle on desk

Both 120 s, 72 Hz, unplugged, device on the desk. This is the ambient/cold baseline, not a load test.

| Metric | Before | After | Change |
|---|---|---|---|
| Global thermal status (start -> end; peak) | 0 -> 0 (0) | 0 -> 0 (0) | same |
| CPU mean / peak | 47.0 / 53.8 C | 44.7 / 52.1 C | -2.3 / -1.7 C |
| GPU mean / peak | 45.0 / 48.2 C | 44.0 / 47.1 C | -0.9 / -1.1 C |
| AP mean / max | 43.3 / 45.0 C | 42.6 / 45.0 C | -0.7 / 0.0 C |
| LRP mean / max | 42.4 / 43.2 C | 42.5 / 43.9 C | +0.1 / +0.7 C |
| WIFI sensor mean / max | 45.5 / 46.4 C | 45.6 / 47.1 C | +0.1 / +0.7 C |
| DDR mean / max | not recorded | 44.3 / 48.0 C | n/a |
| Fan step mean / max; RPM mean | 1.0 / 1; 3,535 | 1.0 / 1; 3,513 | same |
| CPU cap policy0 / policy2 | 2.36 / 2.36 GHz | 2.36 / 2.36 GHz | same |
| GPU clock / busy | 421 MHz / 0% | 421 MHz / 0% | same |
| XR fps / target; drops/s | 72.0 / 72; 0 | 71.9 / 72; 0 | same |
| Head camera fps | not active | not active | - |
| Wi-Fi Rx mean (p5-p95) | 0.1 Mbps (0.1-0.1) | 0.1 Mbps (0.1-0.2) | same |
| Wi-Fi retry mean; drops/errors | 9.11%; 0 | 14.91%; 0 | 0 drops/errors |
| Battery / AC | 94% / off | 92% / off | - |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-2-idle-on-desk-stock-vs-mod.html)

The before run carried a `passthrough=1` event while on the desk, but GPU stayed at 0% and no camera streams were active, so it is treated as the same no-load baseline. CPU/GPU barely moved, which is the useful result: the mod does not lower the cold/idle floor.

## Test 3 - idle + hands, VR

Both 120 s, 72 Hz, unplugged, hands on, no passthrough.

| Metric | Before | After | Change |
|---|---|---|---|
| Global thermal status (start -> end; peak) | 0 -> 1 (1) | 0 -> 0 (0) | no longer crosses to 1 |
| CPU mean / peak | 64.9 / 68.0 C | 53.7 / 57.1 C | -11.2 / -10.9 C |
| GPU mean / peak | 61.3 / 63.7 C | 52.4 / 54.2 C | -8.9 / -9.5 C |
| AP mean / max | 59.8 / 61.2 C | 51.9 / 54.0 C | -7.9 / -7.2 C |
| LRP mean / max | 50.8 / 52.3 C | 44.1 / 46.0 C | -6.7 / -6.3 C |
| WIFI sensor mean / max | 61.3 / 62.8 C | 54.9 / 57.0 C | -6.4 / -5.8 C |
| DDR mean / max | not recorded | 53.1 / 54.8 C | n/a |
| Fan step mean / max; RPM mean | 2.7 / 3; 4,133 | 1.0 / 1; 3,670 | -1.7 step; -463 RPM |
| CPU cap policy0 / policy2 | 2.36 / 2.36 GHz | 2.36 / 2.36 GHz | same |
| GPU clock / busy | 421 MHz / 36.3% | 421 MHz / 38.1% | +1.8 pts busy |
| XR fps / target; drops/s | 72.0 / 72; 0 | 72.0 / 72; 0 | same |
| Head camera fps | 60 | 60 | same |
| Wi-Fi Rx mean (p5-p95) | 0.2 Mbps (0.2-0.3) | 0.2 Mbps (0.2-0.3) | same |
| Wi-Fi retry mean; drops/errors | 6.72%; 0 | 5.31%; 0 | 0 drops/errors |
| Battery / AC | 89% / off | 91% / off | - |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-3-idle-hands-vr-stock-vs-mod.html)

The before run started warmer (AP 56.7 vs 49.0 C), so the size of the delta is not a controlled measurement, but the after run stayed at status 0 and fan step 1 for the whole run. The CPU mean was still 11.2 C lower and the GPU 8.9 C lower.

## Test 4 - YouTube 4K SDR + hands, VR

Both 120 s, unplugged, 4K AV1 8-bit YouTube. The before run was 72 Hz; the after run was 90 Hz.

| Metric | Before | After | Change |
|---|---|---|---|
| Global thermal status (start -> end; peak) | 1 -> 2 (2) | 1 -> 1 (1) | no longer crosses to 2 |
| CPU mean / peak | 74.8 / 80.8 C | 65.7 / 69.7 C | -9.1 / -11.1 C |
| GPU mean / peak | 71.3 / 74.8 C | 64.1 / 65.7 C | -7.1 / -9.1 C |
| AP mean / max | 68.2 / 70.0 C | 63.9 / 65.3 C | -4.3 / -4.7 C |
| LRP mean / max | 57.6 / 58.6 C | 54.4 / 55.5 C | -3.2 / -3.1 C |
| WIFI sensor mean / max | 70.0 / 71.6 C | 67.3 / 68.9 C | -2.7 / -2.7 C |
| DDR mean / max | not recorded | 64.9 / 66.3 C | n/a |
| Fan step mean / max; RPM mean | 4.3 / 5; 4,486 | 3.4 / 4; 4,255 | -0.9 step; -231 RPM |
| CPU cap policy0 / policy2 | 2.36 / 2.36 GHz | 2.36 / 2.36 GHz | same |
| GPU clock / busy | 421 MHz / 57.3% | 421 MHz / 66.3% | +9.0 pts busy |
| XR fps / target; drops/s | 72.0 / 72; 0 | 90.0 / 90; 0 | +18 fps, higher target |
| Head camera fps | 60 | 60 | same |
| Wi-Fi Rx mean (p5-p95) | 3.6 Mbps (0.2-23.0) | 8.1 Mbps (0.3-54.4) | +4.5 Mbps |
| Wi-Fi retry mean; drops/errors | 4.22%; 0 | 5.01%; 0 | 0 drops/errors |
| Battery / AC | 80% / off | 82% / off | - |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-4-youtube-4k-sdr-stock-vs-mod.html)

This is a clean media comparison (same 4K AV1 8-bit stream) except for refresh rate. The after run did ~9 GPU-busy points more work at 90 Hz and still ran 9.1 C cooler on CPU and 7.1 C cooler on GPU. The before run crossed to status 2 and fan step 5; the after run stayed at status 1 and fan step 4, so both limits were avoided.

## Test 5 - YouTube 8K HDR + hands, VR

Both 120 s, unplugged. **This is not a clean content comparison.** The before run recorded 7680x4320 10-bit media at 72 Hz; the after run recorded 7680x4320 8-bit media at 90 Hz. GPU busy was ~99% in both.

| Metric                                     | Before                    | After                       | Change                   |
| ------------------------------------------ | ------------------------- | --------------------------- | ------------------------ |
| Global thermal status (start -> end; peak) | 4 -> 4 (4)                | 3 -> 3 (3)                  | stage 4 -> 3             |
| CPU mean / peak                            | 84.3 / 87.6 C             | 74.6 / 77.1 C               | -9.7 / -10.5 C           |
| GPU mean / peak                            | 81.9 / 84.6 C             | 73.3 / 74.8 C               | -8.6 / -9.8 C            |
| AP mean / max                              | 77.6 / 78.7 C             | 73.6 / 74.6 C               | -4.0 / -4.1 C            |
| LRP mean / max                             | 65.5 / 66.3 C             | 61.6 / 62.3 C               | -3.9 / -4.0 C            |
| WIFI sensor mean / max                     | 79.7 / 80.5 C             | 78.3 / 78.8 C               | -1.4 / -1.7 C            |
| DDR mean / max                             | not recorded              | 73.8 / 75.4 C               | n/a                      |
| Fan step mean / max; RPM mean              | 7.0 / 7; 5,859            | 7.0 / 7; 5,834              | same                     |
| CPU cap policy0 / policy2                  | 1.38 / 1.38 GHz           | 1.92 / 1.92 GHz (mean 1.97) | +0.54 GHz                |
| GPU clock / busy                           | 421 MHz (max 456) / 98.9% | 599 MHz (max 690) / 98.5%   | higher clock, same busy  |
| XR fps / target; drops/s                   | 53.1 / 72; 2.02           | 73.2 / 90; 1.93             | +20.1 fps, higher target |
| Head camera fps                            | 30                        | 30                          | same                     |
| Wi-Fi Rx mean (p5-p95)                     | 51.0 Mbps (0.2-75.9)      | 55.5 Mbps (19.3-75.7)       | +4.5 Mbps                |
| Wi-Fi retry mean; drops/errors             | 4.17%; 0                  | 4.66%; 0                    | 0 drops/errors           |
| Battery / AC                               | 71% / off                 | 78% / off                   | -                        |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-5-youtube-8k-hdr-stock-vs-mod.html)

The mod moved HDR from status 4 to status 3 and cut CPU mean by 9.7 C and GPU mean by 8.6 C, but HDR still sits at status 3, fan 7, ~99% GPU busy and 73 fps against 90. The fan remained pinned at step 7 and the camera remained halved at 30 fps, so this is only a partial cap reduction. The media format difference means the delta should not be read as a pure mod effect.

## Test 6 - Virtual Desktop H.264 -> VRChat, controllers, night

The after column uses the final clean night run at a locked 500 Mbps. The before run was 72 Hz and unplugged; the after run was 90 Hz and plugged. The six Virtual Desktop variants are compared separately under [Virtual Desktop and day/night runs](#virtual-desktop-and-daynight-runs).

| Metric | Before | After | Change |
|---|---|---|---|
| Global thermal status (start -> end; peak) | 4 -> 4 (4) | 1 -> 2 (2) | stage 4 -> 2 |
| CPU mean / peak | 86.4 / 88.6 C | 71.5 / 73.4 C | -14.9 / -15.2 C |
| GPU mean / peak | 79.2 / 82.2 C | 69.1 / 70.1 C | -10.1 / -12.1 C |
| AP mean / max | 76.9 / 77.2 C | 70.1 / 70.7 C | -6.9 / -6.5 C |
| LRP mean / max | 65.0 / 65.3 C | 61.0 / 61.2 C | -4.0 / -4.1 C |
| WIFI sensor mean / max | 79.0 / 79.1 C | 75.0 / 75.2 C | -4.0 / -3.9 C |
| DDR mean / max | not recorded | 70.2 / 70.7 C | n/a |
| Fan step mean / max; RPM mean | 7.0 / 7; 5,852 | 7.0 / 7; 5,834 | same |
| CPU cap policy0 / policy2 | 1.38 / 1.38 GHz | 1.92 / 1.92 GHz | +0.54 GHz |
| GPU clock / busy | 421 MHz / 42.7% | 421 MHz / 55.3% | +12.6 pts busy |
| XR fps / target; drops/s | 79.4 / 72; 0 | 85.3 / 90; 0 | +5.9 fps, higher target |
| Head camera fps | 30 | 60 | no longer halved |
| Wi-Fi Rx mean (p5-p95) | 497.6 Mbps (474.2-523.2) | 495.4 Mbps (467.0-516.7) | -2.2 Mbps |
| Wi-Fi retry mean; drops/errors | 1.72%; 0 | 2.04%; 0 | 0 drops/errors |
| Battery / AC | 53% / off | 87% / on | - |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-6-virtual-desktop-500mbps-stock-vs-mod.html)

The head camera staying at 60 fps is the clearest functional win: the before run was already status 4 with the camera halved, while the after run stayed at status 2 and full camera rate. The CPU mean was 14.9 C lower and the GPU 10.1 C lower. The fan still reached step 7. The after run was plugged, so the battery/charging difference is not attributable to the mod. An unplugged after run at the default 600 Mbps also gave status 2 and AP 71.1 C, so the result is not a plugged-run artifact. Wi-Fi throughput and the labelled latency issue are covered in [Virtual Desktop and day/night runs](#virtual-desktop-and-daynight-runs).

## Test 7 - Chronolink/SteamVR ASTC -> VRChat, controllers, night

Both 120 s, 90 Hz, unplugged, no active media, identical VRChat/Chronolink workload. This is the cleanest performance comparison because refresh rate and workload match.

| Metric | Before | After | Change |
|---|---|---|---|
| Global thermal status (start -> end; peak) | 3 -> 3 (3) | 2 -> 2 (2) | stage 3 -> 2 |
| CPU mean / peak | 81.2 / 84.2 C | 70.6 / 72.0 C | -10.6 / -12.2 C |
| GPU mean / peak | 76.3 / 79.2 C | 68.6 / 69.7 C | -7.7 / -9.5 C |
| AP mean / max | 74.4 / 75.2 C | 69.9 / 70.8 C | -4.5 / -4.4 C |
| LRP mean / max | 62.0 / 62.7 C | 59.2 / 60.0 C | -2.8 / -2.7 C |
| WIFI sensor mean / max | 78.3 / 78.8 C | 76.4 / 77.0 C | -1.9 / -1.8 C |
| DDR mean / max | not recorded | 69.3 / 70.0 C | n/a |
| Fan step mean / max; RPM mean | 7.0 / 7; 5,846 | 5.0 / 5; 4,758 | -2.0 step; -1,088 RPM |
| CPU cap policy0 / policy2 | 1.92 / 1.92 GHz | 1.92 / 1.92 GHz | same |
| GPU clock / busy | 421 MHz / 65.9% | 421 MHz / 66.8% | +0.9 pts busy |
| XR fps / target; drops/s | 87.6 / 90; 0 | 90.4 / 90; 0 | +2.8 fps |
| Head camera fps | 30 | 60 | no longer halved |
| Wi-Fi Rx mean (p5-p95) | 1,138.7 Mbps (1,061.3-1,198.6) | 1,217.0 Mbps (1,149.0-1,263.9) | +78.3 Mbps |
| Wi-Fi retry mean; drops/errors | 7.46%; 0 | 5.25%; 0 | 0 drops/errors |
| Battery / AC | 92% / off | 90% / off | - |

[Preview this test's before/after report](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-7-chronolink-astc-stock-vs-mod.html)

The after run is 10.6 C cooler on CPU and 7.7 C cooler on GPU, two fan steps lower, holds the 90 fps target instead of 87.6, and keeps the head camera at 60 fps. Wi-Fi was also stable: 1,139 -> 1,217 Mbps mean, retry 7.46 -> 5.25%, zero drops/errors. This is the strongest evidence that the mod changed the sustained thermal/performance state rather than just moving a number.

## Where the caps and fan steps were hit and reduced

| Test | Before: stage / fan mean (max) / CPU cap / camera | After: stage / fan mean (max) / CPU cap / camera | Result |
|---:|---|---|---|
| 1 | 1 / 3.5 (4) / 2.36 GHz / 60 fps | 1 / 2.9 (3) / 2.36 GHz / 60 fps | fan step 4 avoided |
| 2 | 0 / 1.0 (1) / 2.36 GHz / idle | 0 / 1.0 (1) / 2.36 GHz / idle | unchanged |
| 3 | 0 -> 1 / 2.7 (3) / 2.36 GHz / 60 fps | 0 / 1.0 (1) / 2.36 GHz / 60 fps | status 1 and fan step 3 avoided |
| 4 | 1 -> 2 / 4.3 (5) / 2.36 GHz / 60 fps | 1 / 3.4 (4) / 2.36 GHz / 60 fps | status 2 and fan step 5 avoided |
| 5 | 4 / 7.0 (7) / 1.38 GHz / 30 fps | 3 / 7.0 (7) / 1.92 GHz / 30 fps | stage 4 -> 3 and CPU cap raised; fan still max, camera still halved |
| 6 | 4 / 7.0 (7) / 1.38 GHz / 30 fps | 2 / 7.0 (7) / 1.92 GHz / 60 fps | stage 4 -> 2, CPU cap raised, camera restored; fan still max |
| 7 | 3 / 7.0 (7) / 1.92 GHz / 30 fps | 2 / 5.0 (5) / 1.92 GHz / 60 fps | stage, fan and camera all improved |

The full sensor/status/fan reference is in [thermal caps, fan steps & throttle conditions](thermal-caps-fan.md).

## In-between (settle) runs

The in-between recordings were made while the assembly was settling. They are not part of the main tables, but they show no large drift relative to the final after state.

| Run | Workload | Status | CPU mean | GPU mean | Fan | XR fps / target | Result |
|---|---|---|---|---:|---:|---|---|
| `inbetween-idle-on-desk` | desk, 72 Hz | 0 | 44.3 C | 43.2 C | 1 | 71.9 / 72 | same as before/after baseline |
| `inbetween-idle-on-desk-2` | desk, 72 Hz | 0 | 37.0 C | 36.4 C | 1 | 72.0 / 72 | cold room/start, not comparable |
| `inbetween-youtube-no-hdr-hand-vr` | YouTube 4K, 90 Hz | 0 -> 1 | 61.1 C | 59.6 C | 2.5 | 90.0 / 90 | cooler than the final after run (CPU 65.7 C) but different ambient/start |
| `inbetween-youtube-hdr-hand` | YouTube 8K, 90 Hz | 3 | 75.4 C | 73.9 C | 7 | 76.9 / 90 | essentially the final after result (CPU 74.6 C / status 3) |
| `inbetween-astc-72fps` | ASTC/VRChat, 72 Hz | 1 | 68.4 C | 66.6 C | 4 | 73.7 / 72 | consistent with the after-state |
| `inbetween-astc-72fps-2` | ASTC/VRChat, 72 Hz | 2 | 69.6 C | 67.8 C | 4 | 72.2 / 72 | consistent with the after-state |
| `inbetween-astc-72fps-3` | ASTC/VRChat, 72 Hz | 2 | 69.2 C | 67.4 C | 5 | 72.0 / 72 | consistent with the after-state |

There was no temporary "wearing in" improvement followed by a regression. The HDR in-between run was already at the after result (CPU 75.4 C / status 3) and well below the before run (CPU 84.3 C / status 4). The only outlier is the second desk run at 37.0 C CPU, which is a cold-start/ambient difference, not a mod effect.

The out-of-order `after-3-idle-hands-vr-wrong-order-did-first` run is excluded from the main comparison. It was test 3 recorded first in the sequence and matched the real after-3 result (CPU 54.2 C mean, status 0, fan 1), so it does not change the conclusion.

## Status 4 and Wi-Fi

Status 4 was an **LRP/power-path** stage, not a Wi-Fi stage. Every status-4 sample had LRP >= 65 C while AP stayed at 76.9-78.7 C, below its 80 C stage-4 threshold. WIFI has no HAL hot-throttling thresholds, the WLAN temperature node is not a thermal zone, and `thermal-engine.conf` is empty. The full threshold/status tables are in [thermal caps & fan steps](thermal-caps-fan.md).

No Wi-Fi speed lock was observed. The only status-4 network-throughput run (`before-6`) held **497.6 Mbps mean** (p5 474, p95 523), 1.72% retry and zero drops/errors, with a ~3.0 Gbps link. The max-throughput test also sustained ~2.19 Gbps at status 3. Status 4 disappeared after the mod, so a controlled status-4 stress plus iperf/ping was not possible here.

## Virtual Desktop and day/night runs

Test 6 produced several runs because of the labelled problems. They are all 120 s, 90 Hz, same H.264 1408x1536 stream, same VRChat world, controllers active. All had zero drops/errors.

| Run                         | Bitrate / control      | AC / battery |       Status |     AP |    DDR | WiFi Rx mean (p5-p95) | Retry | XR / target |
| --------------------------- | ---------------------- | ------------ | -----------: | -----: | -----: | --------------------- | ----: | ----------- |
| `before-6`                  | default, night         | off / 53%    |            4 | 76.9 C |    n/a | 498 (474-523) Mbps    | 1.72% | 79.4 / 72   |
| `after-6` night, default    | unlocked ~600 Mbps     | off / 53%    |            2 | 71.1 C | 71.2 C | 593 (528-644) Mbps    | 1.88% | 87.2 / 90   |
| `after-6` night, locked 500 | 500 Mbps               | off / 37%    |            2 | 71.0 C | 71.1 C | 510 (472-542) Mbps    | 2.18% | 87.2 / 90   |
| `after-6` night, fixed 600  | 600 Mbps, no dashboard | on / 70%     | 2 (mean 1.5) | 70.8 C | 70.3 C | 618 (588-647) Mbps    | 1.89% | 85.3 / 90   |
| `after-6` night, final 500  | 500 Mbps               | on / 87%     | 2 (mean 1.4) | 70.1 C | 70.2 C | 495 (467-517) Mbps    | 2.04% | 85.3 / 90   |
| `after-6` day, fixed 500    | 500 Mbps, day          | on / 74%     | 2 (mean 1.4) | 71.8 C | 71.9 C | 496 (457-522) Mbps    | 2.00% | 85.3 / 90   |
|                             |                        |              |              |        |        |                       |       |             |

What the labelled runs show:

- **The before run's ~500 Mbps was not a thermal Wi-Fi limit.** `before-6` measured 497.6 Mbps (p5 474, p95 523), almost exactly the 500 Mbps lock used later, with lower retry (1.72%), a ~3.0 Gbps link and zero drops/errors. Its extra heat and status 4 were not accompanied by a collapsed link.
- **The unlocked 600 Mbps run was the least stable.** Its 1 s Rx standard deviation was ~46 Mbps and the largest one-second swing was ~385 Mbps, versus ~26-29 Mbps standard deviation and ~217-250 Mbps swings in the locked 500/600 runs. Locking the bitrate visibly smoothed throughput. That is consistent with the "network jumping" label, although latency itself was not captured.
- **The dashboard issue looks external to the headset.** The run without the dashboard ("fixed 600") held a stable 618 Mbps mean with 1.89% retry and zero drops. The profiler cannot prove the labelled "jumping to 120" latency events, but the throughput data does not show a headset-side collapse.
- **Day vs night is a small ambient/content effect.** Comparing the two plugged 500 Mbps runs, the daytime run was ~1.5-1.8 C warmer on AP, DDR and WIFI, and ~1.3 GPU-busy points higher. The display brightness fields read 1.0 in both, so the brighter daytime scene is not captured as a display-setting change. It is not evidence of a mod regression.
- **Wi-Fi was not faster after the mod in this test.** 495-510 Mbps after versus 498 Mbps before, with retry 1.9-2.2% versus 1.7%. The value is in the thermal/performance state, not throughput.

## What the mod did not fix

After-mod residual temperatures show where the remaining heat is. These zones are after-only: the before runs use schema 6 and do not record DDR/video/camera/CPUSS.

| Sensor (mean C) | Test 5 - 8K HDR | Test 6 - Virtual Desktop | Test 7 - Chronolink |
|---|---:|---:|---:|
| CPU (6 sensors) | 74.6 | 71.5 | 70.6 |
| GPU (8 sensors) | 73.3 | 69.1 | 68.6 |
| NPU (3 sensors) | 72.8 | 69.3 | 68.7 |
| AP | 73.6 | 70.1 | 69.9 |
| LRP (power path) | 61.6 | 61.0 | 59.2 |
| DDR | 73.8 | 70.2 | 69.3 |
| WIFI | 78.3 | 75.0 | 76.4 |
| video | 72.9 | 69.1 | 68.1 |
| camera-0 / camera-1 | 71.6 / 72.2 | 68.2 / 68.6 | 67.4 / 67.7 |
| CPUSS-0 / CPUSS-1 | 75.0 / 75.1 | 72.2 / 72.1 | 71.1 / 71.0 |

- **8K HDR is still thermally limited.** Status 3, fan 7, ~99% GPU busy, ~73 fps against 90, CPU mean 74.6 C and GPU mean 73.3 C. The mod lowers temperature and raises the CPU cap but cannot make the HDR workload fit the 90 Hz budget.
- **The fan still maxes under the heaviest loads.** HDR is pinned at step 7 and Virtual Desktop still reaches it. Light/moderate runs improve (test 3: 3 -> 1, test 7: 7 -> 5).
- **The untouched hotspots remain hot.** WIFI is 75-78 C and DDR 69-74 C in streaming/HDR; WIFI is the hottest named sensor in tests 6/7. The DRAM and Wi-Fi chips were not touched.
- **The idle floor is unchanged.** Test 2 was ~43 C AP, CPU 47.0 -> 44.7 C, GPU 45.0 -> 44.0 C. The 15 V rail is after-only, so it cannot show an efficiency gain.

## Caveats

- No ambient temperature, controlled cool-down or matched starting temperature. The before and after sessions were different days; several runs were sequential and carried heat forward.
- Tests 4-6 used 90 Hz after the mod but 72 Hz before. That makes the after workload heavier, so the thermal improvement is not a like-for-like magnitude.
- Test 5 changed media format between runs (10-bit before, 8-bit after). Treat it as a direction, not a clean A/B.
- Test 's after run is plugged while the before run is unplugged, and battery levels differ.
- Before runs use schema 6 and do not have DDR, raw thermal zones or rail power. DDR and rail rows are therefore after-only.
- The fan step is a discrete logcat value; RPM/PWM are root-only. The fan still uses the stock curve, so a lower temperature only helps if it crosses a step boundary.
- Wi-Fi latency/jitter was not recorded. The profiler records throughput, retries, RSSI and packet counters, so it cannot prove or disprove the labelled "jumping to 120" latency events.
- The global thermal stage is a platform stage, not the maximum per-sensor severity. The LRP table above is a strong correlation, not a confirmed code path.

## Useful next experiments

1. Cool-start, temperature-matched before/after runs would turn the CPU/GPU deltas into controlled measurements.
2. Repeat tests 4-6 at the same refresh rate and same content/bitrate.
3. Run 5-10 min HDR and Virtual Desktop sessions to see whether the after state holds or slowly drifts toward status 3/4.
4. Deliberately reach status 4 (if still possible on another unit or with a hotter workload) and run iperf/ping alongside it. This is the only way to fully rule out firmware-level Wi-Fi thermal mitigation.
5. Capture latency/jitter (ping or SteamVR transport stats) during the Virtual Desktop runs to verify the labelled "jumping to 120" behaviour.
6. Repeat the day/night pair with measured ambient temperature and a logged scene brightness, not just `disp_brightness`.
7. If the WIFI/DDR hotspots matter, apply pads/shims to those chips next; the SoC mod alone leaves them as the remaining high-temperature sensors.
