# Thermal caps, fan steps & throttle conditions

[Findings index](../README.md) | [Thermal, throttling & fan](thermal.md) | [Thermal mod before/after](thermal-mod.md)

> **Hardware state: MIXED - STOCK BEFORE 2026-11-01, MODDED AFTER.** Runs before 2026-11-01 are from the unmodified headset. Runs from 2026-11-01 onward, including the in-between and after runs, are from the SoC thermal-modded headset (phase-change pads + copper shims). Thermal status 4 was only observed on the stock unit.

This page collects the sensor roles, global thermal status ladder, CPU/camera caps and fan-step mapping in one place, then shows where those limits were hit before the SoC thermal mod and where the mod reduced or failed to reduce them.

## In plain terms

- **Status 3 is the tracking-camera cap:** head/hand tracking falls from 60 to 30 fps. That can make fast hand movement and controller tracking feel rougher, even though the screens keep their refresh rate.
- **Status 4 is the worst stage** and was only reached on the stock unit in pre-mod 8K HDR/Virtual Desktop runs. It came from the board power-path sensor, not the Wi-Fi sensor.
- **Status 3 still happens after the mod**, especially in 8K HDR; the mod removes status 4 but not the status-3 camera cap.
- **The fan is stepped, not smooth:** step 1 is quiet idle, step 7 is the loudest and is common in HDR/heavy streaming. A temperature drop only helps when it crosses a step boundary.
- **CPU/GPU temperatures are the real SoC measure.** AP/LRP are board-level indicators. The mod cut CPU/GPU much more than AP/LRP.
- **Charging can raise the fan a step** without adding a separate CPU/GPU cap.

## Tests & results

### Sensor roles

| Name | What it is | Notes |
|---|---|---|
| **AP** | Application-processor/board thermistor | Same physical sensor as `skin` and `sec_ap`; board-level, not a CPU core. |
| **LRP** | Power-path thermistor | Board power-delivery path, **not RAM**. It matched the status-4 trip. |
| **CPU** | Six HAL CPU sensors (`CPU0`-`CPU5`) | CPU mean is the average of the six; CPU peak is the hottest one. |
| **GPU** | Eight HAL GPU sensors (`GPU0`-`GPU7`) | GPU mean is the average of the eight; GPU peak is the hottest one. |
| **NPU** | Three HAL NPU sensors (`nsp0`-`nsp2`) | Included for completeness. |
| **DDR** | Kernel `ddr` thermal zone | Actual DRAM temperature. Not the same as LRP. |
| **WIFI** | HAL WIFI sensor | Not the WLAN RF chip sensor; no hot-throttling thresholds are set. |

### Observed global thermal status

Medians from the local run library, with representative conditions:

| Status | Hardware seen | Observed when | Samples | AP median | LRP median | CPU median | GPU median | Fan median | CPU cap median |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | stock + modded | idle on desk | 1,504 | 44.0 C | 42.0 C | 47.4 C | 45.5 C | 1 | 2.36 GHz |
| 1 | stock + modded | light passthrough/hands, light video | 1,552 | 64.4 C | 52.0 C | 69.7 C | 66.0 C | 3 | 2.36 GHz |
| 2 | stock + modded | moderate VR, 4K video, light streaming | 1,627 | 70.8 C | 59.9 C | 76.2 C | 71.1 C | 5 | 1.92 GHz |
| 3 | stock + modded | heavy VR/streaming; camera halving | 1,018 | 73.0 C | 61.0 C | 79.1 C | 73.9 C | 7 | 1.92 GHz |
| 4 | **stock only** | pre-mod 8K HDR / Virtual Desktop worst case | 240 | 77.0 C | 65.0 C | 85.9 C | 80.2 C | 7 | 1.38 GHz |

Status 4 only appeared before the SoC mod. After the mod the highest stage observed was 3, and only in 8K HDR. Status 2 and 3 overlap in the raw data, so the stage is not a strict temperature lookup.

### HAL hot thresholds

Read from `dumpsys thermalservice` on 2026-11-07:

| Sensor | Hot thresholds by stage 0-6 (C) |
|---|---|
| AP | 50 / 58 / 69 / 73 / 80 / - / - |
| LRP (power path) | 49 / 53 / 57 / 62 / 65 / 67 / 80 |
| CPU / GPU / NPU | - / - / - / 95 / - / - / 115 |
| WIFI, CHG, BAT, USB, skin | no hot threshold set |

The global stage tracked **LRP**, not the CPU/GPU sensors. Every status-4 sample had LRP >= 65 C, the LRP stage-4 threshold, while AP stayed at 76.9-78.7 C, below its 80 C stage-4 threshold. CPU/GPU/NPU only trip at 95/115 C, which these runs did not reach. WIFI has no thresholds, so status 4 is not a Wi-Fi throttle.

### CPU, camera and display caps

| Signal | Status 0-1 | Status 2-3 | Status 4 (pre-mod worst case) |
|---|---|---|---|
| CPU `scaling_max_freq` median | 2.36 GHz | 1.92 GHz | 1.38 GHz |
| Head/hand camera | 60 fps | 60 -> 30 fps at status 3 | 30 fps |
| Raw CIB head/hand | ~480 / ~360 fps | ~240 / ~180 fps at status 3 | ~240 / ~180 fps |
| Eye camera | 30 fps | 30 fps | 30 fps |
| Display refresh | 72/90 Hz as selected | unchanged at status 3 | 72 Hz target recorded in the status-4 VD/HDR runs; possible stage-4 clamp (unconfirmed) |
| `psm` | 0 | 0 | 0 |

The camera halving is a **status-3 policy effect**, not a battery or Wi-Fi effect. Display refresh was unchanged at status 3. In test 6, Virtual Desktop was set to 90 Hz for both runs, but the status-4 before run recorded a 72 Hz target; that is consistent with a stage-4 target clamp but is not proven because status 4 was already active when recording started.

### Fan steps

The fan uses seven discrete programmed steps, not a continuous curve. Approximate observed mapping:

| Fan step | AP median (range) | GPU median | PWM | RPM | Typical status |
|---:|---|---:|---:|---:|---:|
| 1 | 33.4 C (28-55) | 35.7 C | 85 | 3,575 | 0 |
| 2 | 56.0 C (55-59) | 57.3 C | 90 | 3,957 | 0 |
| 3 | 63.0 C (59.8-64.9) | 64.3 C | 95 | 4,213 | 1 |
| 4 | 66.5 C (64-70) | 67.0 C | 100 | 4,366 | 1 |
| 5 | 70.8 C (69.2-71.9) | 71.4 C | 110 | 4,792 | 2 |
| 6 | 72.9 C (72-73.5) | 73.4 C | 120 | 5,181 | 3 |
| 7 | 72.6 C (68-74.1) | 75.5 C | 140 | 5,893 | 3 |

Step 7 can fire at AP ~68 C when the GPU is already 75+ C. The AP ranges overlap, so these are rough triggers, not strict thresholds. Fan step and global status are separate ladders driven by temperature; status is not a direct fan command.

### Where the caps were hit and reduced in the mod runs

| Test | Before: stage / fan mean (max) / CPU cap / camera | After: stage / fan mean (max) / CPU cap / camera | What changed |
|---:|---|---|---|
| 1 | 1 / 3.5 (4) / 2.36 GHz / 60 fps | 1 / 2.9 (3) / 2.36 GHz / 60 fps | fan step 4 avoided |
| 2 | 0 / 1.0 (1) / 2.36 GHz / idle | 0 / 1.0 (1) / 2.36 GHz / idle | unchanged |
| 3 | 0 -> 1 / 2.7 (3) / 2.36 GHz / 60 fps | 0 / 1.0 (1) / 2.36 GHz / 60 fps | status 1 and fan step 3 avoided |
| 4 | 1 -> 2 / 4.3 (5) / 2.36 GHz / 60 fps | 1 / 3.4 (4) / 2.36 GHz / 60 fps | status 2 and fan step 5 avoided |
| 5 | 4 / 7.0 (7) / 1.38 GHz / 30 fps | 3 / 7.0 (7) / 1.92 GHz / 30 fps | stage 4 -> 3, CPU cap raised; fan still max, camera still halved |
| 6 | 4 / 7.0 (7) / 1.38 GHz / 30 fps | 2 / 7.0 (7) / 1.92 GHz / 60 fps | stage 4 -> 2, cap raised, camera restored; fan still max |
| 7 | 3 / 7.0 (7) / 1.92 GHz / 30 fps | 2 / 5.0 (5) / 1.92 GHz / 60 fps | stage, fan and camera all improved |

## Findings

- **AP and LRP are board-level indicators, not the SoC.** The CPU/GPU sensors showed the largest mod gains: CPU mean fell 7.8-14.9 C and GPU mean 5.3-10.1 C in loaded tests. AP fell 3.1-7.9 C and LRP 0.7-6.7 C.
- **The global thermal stage follows LRP in these runs.** Status 4 was an LRP >= 65 C event, not an AP 80 C event and not a Wi-Fi event. After the mod, status 4 disappeared.
- **Status 3 is the camera-cap stage.** Head/hand camera falls 60 -> 30 fps and raw CIB falls ~480/360 -> ~240/180 fps, while display refresh and `psm` stay unchanged.
- **The CPU cap follows the stage in the observed runs.** Median cap was 2.36 GHz at status 0-1, 1.92 GHz at status 2-3 and 1.38 GHz in the pre-mod status-4 HDR/VD runs.
- **The fan is a separate seven-step ladder.** It tracked AP/GPU temperature, not the global stage directly. Step 7 can occur at AP ~68 C when the GPU is already 75+ C.
- **The mod reduced the fan only when it crossed a step boundary.** Tests 1, 3, 4 and 7 dropped a fan step; tests 5 and 6 stayed at step 7, and HDR stayed at status 3.
- **Charging can add a fan step without adding a SoC cap.** Plugged low-battery runs used fan 7 versus fan 6 unplugged, with no extra CPU/GPU/display limit. Battery temperature rose about 0.75-1 C.
- **Daytime/brighter content adds a small ambient/load offset.** The daytime VD run was ~1.5-1.8 C warmer at the same 500 Mbps and 90 Hz, not a separate thermal cap.

## Details

### What raises the status

- Sustained VR compositing, passthrough + hand tracking, video decode, streaming decode and 8K HDR all raise AP/CPU/GPU and therefore LRP.
- The platform escalates the global stage before the CPU cap deepens: status 1-2 still ran 2.36 GHz or 1.92 GHz; only the pre-mod status-4 HDR/VD runs sat at 1.38 GHz.
- The camera pipeline drops to 30 fps when status 3 is reached, after a 3-18 s lag in the runs where the transition was captured.
- Wi-Fi load adds heat and CPU work, but no Wi-Fi sensor threshold is configured; the radio itself is not part of the Android thermal-stage ladder.

### What raises the fan

- Light load: fan 1 at idle/desk.
- Passthrough or light VR: fan 3-4, driven by AP/CPU rather than GPU busy.
- Moderate VR/video: fan 5.
- Heavy VR/streaming/HDR: fan 6-7; step 7 can be GPU-led.
- Plugged charging can move the same thermal state up one fan step.
- The fan is discrete, so a temperature drop only helps when it crosses a step boundary. This is why test 7 fell from 7 to 5 while test 5 and test 6 stayed at 7 despite lower temperatures.

### Caveats

- The status tables are medians across the local run library, not controlled thresholds.
- The fan AP/GPU values overlap between steps; treat them as approximate triggers.
- No ambient temperature or matched starting temperature was recorded.
- Status is a platform stage, not the maximum per-sensor severity.
- Wi-Fi latency/jitter was not recorded.
