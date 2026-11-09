# Power modes & battery

[Findings index](../README.md) | [Commands](../COMMANDS.md)

> **Hardware state: STOCK.** All runs on this page are from the unmodified headset, before 2026-11-01. No thermal mod.

Power-saving, hand-tracking and battery/AC A/B tests. All runs were 60 s, hot-started and idle unless noted; the battery tests used ASTC.

## In plain terms

- Battery Saver drops the display to 60 Hz and roughly halves camera and hand/head tracking rates, with lower GPU use and fan speed.
- Turning hand tracking off saves only a little: about 1-2 C cooler and a couple of GPU points.
- Low battery (even 3-4%) does not switch on Battery Saver or shut the headset down by itself.
- Heat, not battery level, is what usually slows the headset: hot runs cut the head camera to 30 fps and cap CPU.
- Plugging in while hot mostly just raises fan speed; it does not lift the performance caps.

## Tests & results

Probed 2026-10-20 to 2026-10-31.

| Test | Observed result |
|---|---|
| idle, normal vs Battery Saver | 72 -> 60 Hz; raw CIB head/hand 480/360 -> 240/180; ingest 60/60 -> 30/30; GPU 35% -> 23%; fan 4 -> 3; CPU caps unchanged |
| idle, hand on vs hand off | hand CIB/ingest absent; head/eye/IR unchanged; GPU 35% -> 33%; 1-2 C cooler |
| 4x ASTC 14-45%, AC on/off | same caps 1.92 GHz, 72 Hz, 421 MHz, fan 5, status 2, ~40% GPU |
| charging | pack +0.75-1 C; no SoC profile change |
| 7x VRChat ASTC, 20% -> 3% | no battery-triggered throttle; thermal status 3 caps CPU 1.92 GHz, head camera 30 fps, fan 6; plugged runs raised fan to 7 without an extra SoC/display cap |

## Findings

- Power saving caps display/XR at 60 Hz and halves head/hand camera rates; CPU caps stay.
- Thermal status 3 produces a similar camera halving without `psm`; see [cross-run analysis](cross-run.md).
- Hand tracking is suspended, not torn down; an idle context thread and registration remain.
- Neither low (14-16%) nor critical (3-4%) battery enabled Battery Saver, added a lower cap, or shut the headset down during the 60 s runs. The observed limits were thermal status 3.
- Plugged low-battery runs used fan step 7, but added no extra CPU, GPU or display limit; AC did not raise caps/clocks in these thermally saturated runs.

## Details

Two on-device toggles were profiled on the OS (60 s runs, hot-started, idle headset).

### Power saving (Battery Saver)

| metric | normal | power saving |
|---|---|---|
| display Hz / XR target | 72 / 72 | **60 / 60** |
| raw CIB `HT` / `Hat` fps | 480 / 360 | **240 / 180** |
| head / hand service ingest fps | 60 / 60 | **30 / 30** |
| eye / IR LED fps | 120 / 30 | 120 / 30 |
| GPU busy (avg) | 35% | **23%** |
| peak AP / CPU / GPU (C) | 67 / 77 / 71 | **63 / 71 / 65** |
| fan step | 4 | 3 |
| CPU `scaling_max_freq` | uncapped | uncapped |

Effects: caps display + XR to 60 Hz, sets CPU/GPU perf votes to `POWER_SAVING`, disables the passthrough denoiser (`PassthroughDenoiser` 2 -> 0 in `DynamicPolicyManager`), and **halves the head/hand camera pipeline**; `scaling_max_freq` stays uncapped. Captured as `psm` + `disp_hz`.

### Hand tracking disabled (Power + Volume Up + Volume Down)

Genuinely **suspends** hand tracking - it does **not** keep running in the background.

| metric | hand on | hand off |
|---|---|---|
| `cib_hat_fps` (raw hand) | 360 (PSM off) / 180 (PSM on) | **absent** |
| `cam_hand_fps` (ingest) | 60 / 30 | **absent** |
| `cib_ht_fps` (raw head) | 480 / 240 | 480 / 240 (**unchanged**) |
| eye / IR LED fps | 120 / 30 | 120 / 30 |
| GPU busy | 35% | 33% |
| peak AP / CPU / GPU (C) | 67 / 77 / 71 | 65 / 76 / 69 |

Only the hand stream disappears; head/eye/IR are unchanged, GPU busy is ~2 pts lower, ~1-2 C cooler, with no fan/status/cap change. Captured as the *absence* of the two hand fps keys.

### Perception services (hand on vs off)

Inspect with `adb shell dumpsys com.google.xr.frameworks.perception.IPerceptionLifecycleManager/default`. Active services with **hand on** (id -> service): HeadTracking 65537, Depth 131073, Spaces 196609, MapAnnotations 327681, HandJointTracking 393217, HandGestureTracking 458753, HandSurfaceTracking 524289, EyeTracking 655361, Calibration 786433, HeadTrackingData 1703937.

With **hand off**, the three Hand* services drop out, plus the `HandJoints_*`, `CPM_HandTrackingConnection`, `CPM_HandMesh` and `OpenPxBridge_Hand` clients; all other services remain active.

Logcat at the toggle:
```
I/CpmInput: OpenPXHandTrackingConnection: stop tracking called
[PerceptionLifecycleManager] removing ... service_id=(HandJointTracking)
[HandJointsService] suspend called. / stopped adapter / suspend success.
[HaT] Stop() called.
```

### What hand-off stops vs. leaves behind (thread/CPU A/B)

Measured inside `android.hardware.perceptionhost` (pid 12004):

| | hand on | hand off |
|---|---|---|
| CIB `Hat` / `P-Hat` stream | ~360 fps | **gone** |
| Lifecycle Hand* services | 3 | **0** |
| hand worker threads (`HaT_hand_tracker`, `HaT_online_cali`, `HaT_telemetry_l`) | present | **gone** |
| `HaT-Context` thread | ~100 ticks / 6 s (~17% of a core), exists | **0 ticks / 6 s (idle); still exists (residual)** |
| `PerceptionDataMonitor` | tracks `HandJointTracking` | still registers it: `Skipping ..., since it is not resumed` |
| prop `persist.cpm.hand.openpx_post_processing` | `true` | `true` (residual) |
| camera provider CPU (`vendor.qti.camera@2.7-service`) | ~56% | ~58% (unchanged) |

The toggle **suspends** hand tracking - stream, services, worker threads and context CPU all stop - but does **not** fully tear it down: an idle `HaT-Context` thread, the `PerceptionDataMonitor` registration and one prop persist. Since head tracking drives the same cameras at full rate, camera-provider CPU is unchanged - hence only ~2 pts GPU / 1-2 C.

### NPU and the hand model

The SoC NPU is Qualcomm **Hexagon**, used two ways: **HTP** (tensor) for head tracking (`MTC_HTP_To_CPU_` thread in perceptionhost) and **CDSP** (compute DSP) for QNN inference (`adsprpc: ... libqnn_service_skel.so ... _dom=cdsp`).

Hand tracking runs a real DNN (`[HaT] Run detector model` + joint/gesture/surface stages) in a large plugin. Sizes: face_parameter_tracking 571 MB, **hand_joint_tracking 202 MB**, object_tracking 117 MB, fittracker/scene_understanding 67/66 MB, depth_estimation 54 MB, head_tracking 35 MB, eye_tracking 21 MB.

Hand on vs off:

| metric | hand ON | hand OFF |
|---|---|---|
| `[HaT] Run detector model` | every ~3 s | none |
| `HaT-Context` thread CPU | 333 ticks / 20 s (~17% of a core) | 0 |
| hand worker threads | present | gone |
| perceptionhost RSS | 642 MB | 573 MB (-70 MB) |
| NPU/DSP hand inference | runs | stops |

The model is **not small**; while on it costs ~17% of a core (orchestration; heavy inference is offloaded to the NPU/DSP), ~70 MB RSS, and NPU/DSP slice time. It self-throttles when idle (`idle_mode_config.fps_throttle_factor`). System-wide delta stays small because the cameras plus the head/eye/depth DNNs keep running and dominate.

Config: `/vendor/etc/perception/host_config.json`, `/vendor/etc/hand_tracking_aggressive_mode_override.textproto`, `/vendor/etc/opx/opx_manifest_gg_hand_*.json`.

### Battery level & charging

Goal: does battery level or AC state put the headset into a **different performance profile**? Four 60 s ASTC runs (power save off, hand tracking on) varied only battery/AC: low-batt 16%, low-batt plugged 14%, 38%, 45% plugged. All were hot-started (thermal status 2).

Profile signals were identical: CPU caps policy0/policy2 (`cpu_max0/2`) 1.92/1.92 GHz, all-core 1.92 GHz (mean=max), display 72/72 Hz, `psm` off, GPU 421 MHz, fan 5, thermal status 2, camera ingest 60/60/30/30 fps, raw CIB `HT`/`Hat`/`EyeT` 480/360/120 fps. Only the averages moved: GPU busy 40.8/41.4/40.8/40.3%, XR fps 72.7/72.2/72.1/72.1.

**Result: identical across 14-45% and AC on/off.** Low battery (14-16%) did **not** enable Battery Saver (`psm` stayed 0) or add a lower CPU cap, and plugging in did **not** raise caps, clocks or fps or change fan step. The camera pipeline was unchanged; low battery did **not** trigger the power-saving halving (only Battery Saver does). The only consistent battery-related change was pack temperature **+0.75 to 1.0 C when charging** (37 -> 38 C), with no SoC profile change.

Depth streams (`DepthInput` / `DepthTOF`) were not emitted during these ASTC/VRChat runs, so those columns are blank; this is workload-dependent, not battery/AC related.

**Caveat:** every run started thermally saturated (status 2, both clusters pinned at 1.92 GHz for 100% of the run), so this rules out a battery/AC profile *below* the thermal cap and shows low battery did not trigger power saving, but cannot reveal whether AC allows extra boost when not thermally limited. Better experiment: cool to the same starting temperature, run the same workload for >=5-10 min at matched battery levels, then compare unplugged vs plugged at ~50% and at <10%.

### Low / critical battery follow-up (2026-10-31)

Seven 60 s VRChat-on-SteamVR ASTC runs at night, hand tracking off, no active media, 72 Hz target. Battery fell from 20% to 3%; the 3% and 16% points were repeated while charging. All runs were hot-started: the 20% run began at thermal status 2 and crossed to 3 at 16 s; the rest were already at status 3.

| run | battery | AC | thermal status | AP mean | GPU max | fan | head cam | batt temp |
|---|---|---:|---|---:|---:|---|---:|---:|
| run-20 | 20 -> 19% | off | 2 -> 3 | 72.8 C | 75.8 C | 6 | 38.6* | 29 C |
| run-17 | 16 -> 16% | off | 3 | 72.1 C | 75.8 C | 6 | 30 | 30-31 C |
| run-13 | 13 -> 12% | off | 3 | 72.4 C | 76.1 C | 6 | 30 | 32 C |
| run-8 | 8 -> 7% | off | 3 | 72.9 C | 76.8 C | 6-7 | 30 | 33-34 C |
| run-4 | 4 -> 3% | off | 3 | 72.8 C | 76.5 C | 6 | 30 | 34 C |
| run-4 plugged | 3 -> 3% | on | 3 | 71.9 C | 74.8 C | 7 | 30 | 34-35 C |
| run-16 plugged | 16 -> 17% | on | 3 | 73.0 C | 76.5 C | 6-7 | 30 | 32 C |

\* run-20 camera was 60 fps until 8 s, 44.7 fps at 18 s, then 30 fps from 28 s.

Across all seven runs:

- CPU caps were **1.92 / 1.92 GHz**, GPU clock **421 MHz**, `g_throttling=0`, `psm=0` and display **72 Hz**; none changed at 3-4% battery.
- The head camera was **30 fps** in every status-3 run. run-20 shows the transition (status 3 at 16 s, 44.7 fps at 18 s, 30 fps from 28 s) - the same thermal camera throttle, not a battery threshold.
- Fan step was **6** unplugged, **7** at 3% plugged and **6 -> 7** at 16% plugged.
- At 4 -> 3% the headset kept running the full 60 s with no shutdown, Battery Saver, lower CPU cap or display drop. Battery fell about **1%/min** under this workload.
- Pack temperature rose from **29 C at 20%** to **34 C at 3%** unplugged, and **34-35 C** when charging at 3%; this tracks session heat and charging, not a battery threshold.

The earlier 14-45% test remains a useful baseline: at thermal status 2, low battery alone kept 72 fps, 60 fps cameras, `psm=0` and the normal thermal cap; the low/critical runs are dominated by status 3, so they do not show a separate battery throttle.

**Caveats.** Sequential hot-start runs, no cooldown or ambient control, only two low-battery plugged runs; hand tracking was off and the Chronolink workload was effectively identical. The standby follow-up pair is in [standby & wake](standby.md).
