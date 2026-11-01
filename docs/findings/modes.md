# Power modes & battery

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Power-saving, hand-tracking and battery/AC A/B tests. All runs were 60 s, hot-started and idle
unless noted; the battery tests used ASTC.

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
- Thermal status 3 produces a similar camera halving without `psm`; see
  [cross-run analysis](cross-run.md).
- Hand tracking is suspended, not torn down; residual context thread and registration remain.
- Low battery (14-16%) did not enable Battery Saver or add a lower cap.
- Critical battery (3-4%) also did not add a battery-specific cap, enable Battery Saver, or shut
  down during the 60 s runs. The observed CPU/camera/fan limits were thermal status 3.
- Plugged low-battery runs used fan step 7, but did not add an extra CPU, GPU or display limit.
- AC did not raise caps/clocks in these thermally saturated runs.
- Battery/AC conclusions are limited by every run starting thermally saturated (status 2 in the
  first test, status 3 in the low/critical follow-up).

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

Effects: caps display + XR to 60 Hz, sets CPU/GPU perf votes to `POWER_SAVING`, disables the
passthrough denoiser (`PassthroughDenoiser` 2 -> 0 in `DynamicPolicyManager`), and **halves the
head/hand camera pipeline** (raw `HT`/`Hat` and ingest). It does **not** cap
`scaling_max_freq`. Captured as `psm` + `disp_hz`.

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

Only the hand stream disappears (raw + ingest); head/eye/IR are unchanged. GPU busy ~-2 pts,
~1-2 C cooler, no fan/status/cap change. Captured as the *absence* of `cib_hat_fps` /
`cam_hand_fps`.

### Perception services (hand on vs off)

Inspect:
```
adb shell dumpsys com.google.xr.frameworks.perception.IPerceptionLifecycleManager/default
```

Active services with **hand on** (service_id -> clients):

| id | service | clients |
|---|---|---|
| 65537 | HeadTracking | DepthEstimation_HeadTracking, CPM_HeadTracking_0/1/2, `HandJoints_HeadTracking`, OpenPxBridge_Head |
| 131073 | Depth | CPM_Passthrough, CPM_DepthTracker |
| 196609 | Spaces | DepthEstimation_Spaces, CPM_SpaceManager |
| 327681 | MapAnnotations | DepthEstimation_MapAnnotations |
| **393217** | **HandJointTracking** | `CPM_HandTrackingConnection`, `OpenPxBridge_Hand` |
| **458753** | **HandGestureTracking** | `CPM_HandTrackingConnection`, `OpenPxBridge_Hand` |
| **524289** | **HandSurfaceTracking** | `CPM_HandMesh`, `OpenPxBridge_Hand` |
| 655361 | EyeTracking | CPM_EyeTrackingConnection, OpenPxBridge_Eye |
| 786433 | Calibration | `HandJoints_Calibration`, CPM_DepthTracker, EyeTracking_Calibration, XRInputManager, ... |
| 1703937 | HeadTrackingData | DepthEstimation_HeadTrackingData |

With **hand off**, these drop out: services **HandJointTracking**, **HandGestureTracking**,
**HandSurfaceTracking**, plus the `HandJoints_*`, `CPM_HandTrackingConnection`, `CPM_HandMesh` and
`OpenPxBridge_Hand` clients. HeadTracking, Depth, Spaces, MapAnnotations, EyeTracking,
Calibration and HeadTrackingData remain active.

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
| `HaT-Context` thread CPU | ~100 ticks / 6 s (~17% of a core) | **0 ticks / 6 s (idle)** |
| `HaT-Context` thread exists | yes | **yes (residual, idle)** |
| `PerceptionDataMonitor` | tracks `HandJointTracking` | still registers it: `Skipping ..., since it is not resumed` |
| prop `persist.cpm.hand.openpx_post_processing` | `true` | `true` (residual) |
| camera provider CPU (`vendor.qti.camera@2.7-service`) | ~56% | ~58% (unchanged) |

The toggle **suspends** hand tracking - stream, services, worker threads and context CPU all stop -
but it does **not** fully tear it down: an idle `HaT-Context` thread, the `PerceptionDataMonitor`
registration and one prop persist. Because head tracking drives the same world-facing cameras at
full rate, camera-provider CPU is unchanged - hence only ~2 pts GPU / 1-2 C.

### NPU and the hand model

The SoC NPU is Qualcomm **Hexagon**, used two ways:
- **HTP** (tensor): head tracking (`MTC_HTP_To_CPU_` thread in perceptionhost).
- **CDSP** (compute DSP): QNN inference (`adsprpc: ... libqnn_service_skel.so ... _dom=cdsp`).

Hand tracking runs a real DNN (`[HaT] Run detector model` + joint/gesture/surface stages),
embedded in a large plugin:

| perception host plugin | size |
|---|---|
| face_parameter_tracking | 571 MB |
| **hand_joint_tracking** | **202 MB** |
| object_tracking | 117 MB |
| fittracker / scene_understanding | 67 / 66 MB |
| depth_estimation | 54 MB |
| head_tracking | 35 MB |
| eye_tracking | 21 MB |

Hand on vs off:

| metric | hand ON | hand OFF |
|---|---|---|
| `[HaT] Run detector model` | every ~3 s | none |
| `HaT-Context` thread CPU | 333 ticks / 20 s (~17% of a core) | 0 |
| hand worker threads | present | gone |
| perceptionhost RSS | 642 MB | 573 MB (-70 MB) |
| NPU/DSP hand inference | runs | stops |

The model is **not small**; while on it costs ~17% of a core (orchestration; heavy inference is
offloaded to the NPU/DSP), ~70 MB RSS, and NPU/DSP slice time. It self-throttles when idle
(`idle_mode_config.fps_throttle_factor`). System-wide delta stays small because the cameras plus
the head/eye/depth DNNs keep running and dominate.

Config: `/vendor/etc/perception/host_config.json`,
`/vendor/etc/hand_tracking_aggressive_mode_override.textproto`,
`/vendor/etc/opx/opx_manifest_gg_hand_*.json`.

### Battery level & charging

Goal: does battery level or AC state put the headset into a **different performance profile**?

Four 60 s ASTC runs (power save off, hand tracking on), varying only battery/AC.
All were hot-started (thermal status 2).

| profile signal | low-batt 16% | low-batt plugged 14% | 38% | 45% plugged |
|---|---|---|---|---|
| CPU cap policy0 / policy2 (`cpu_max0/2`) | 1.92 / 1.92 GHz | same | same | same |
| all-core current freq | 1.92 GHz (mean=max) | same | same | same |
| display Hz / XR target | 72 / 72 | 72 / 72 | 72 / 72 | 72 / 72 |
| power save (`psm`) | off | off | off | off |
| GPU clock | 421 MHz | 421 | 421 | 421 |
| fan step | 5 | 5 | 5 | 5 |
| thermal status | 2 | 2 | 2 | 2 |
| GPU busy (avg) | 40.8% | 41.4% | 40.8% | 40.3% |
| XR fps (avg) | 72.7 | 72.2 | 72.1 | 72.1 |
| camera ingest head / hand / eye / IR | 60 / 60 / 30 / 30 fps | same | same | same |
| raw CIB HT / Hat / EyeT | 480 / 360 / 120 fps | same | same | same |

**Result: the performance profile was identical across 14-45% and AC on/off.** Specifically:
- Low battery (14-16%) did **not** enable Battery Saver (`psm` stayed 0) and did **not** add a
  lower CPU cap.
- Plugging in did **not** raise caps, clocks or fps, and did not change fan step.
- **The camera pipeline was also unchanged**: head/hand ingest 60 fps, eye 30, IR LED 30;
  raw CIB `HT` ~480, `Hat` ~360, `EyeT` ~120. Low battery did **not** trigger the power-saving
  camera halving (that only happens with Battery Saver on).
- The only consistent battery-related change was pack temperature **+0.75 to 1.0 C when charging**
  (37 -> 38 C), with no corresponding SoC profile change.

Note: depth streams (`DepthInput` / `DepthTOF`) were not emitted during these ASTC/VRChat runs, so
those columns are blank for all four; this is workload-dependent, not battery/AC related.

**Caveat:** every run started already thermally saturated (status 2, both clusters pinned at
1.92 GHz for 100% of the run). This rules out a battery/AC profile *below* the thermal cap and
shows low battery didn't trigger power saving - but it cannot reveal whether AC allows extra boost
when the device is not thermally limited.

**Better experiment for the boost/headroom question:** cool to the same starting temperature,
same workload for >=5-10 min, matched battery levels, then compare unplugged vs plugged at ~50%
and again at <10% (critical).

### Low / critical battery follow-up (2026-10-31)

Seven 60 s VRChat-on-SteamVR ASTC runs at night, hand tracking off, no active media, 72 Hz target.
Battery fell from 20% to 3% across the session; the 3% and 16% points were repeated while charging.
All runs were hot-started: the 20% run began at thermal status 2 and crossed to 3 at 16 s; the rest
were already at status 3.

| run | battery | AC | thermal status | AP mean | GPU max | fan | head cam | batt temp |
|---|---:|---:|---|---:|---:|---|---:|---:|
| run-20 | 20 -> 19% | off | 2 -> 3 | 72.8 C | 75.8 C | 6 | 38.6* | 29 C |
| run-17 | 16 -> 16% | off | 3 | 72.1 C | 75.8 C | 6 | 30 | 30-31 C |
| run-13 | 13 -> 12% | off | 3 | 72.4 C | 76.1 C | 6 | 30 | 32 C |
| run-8 | 8 -> 7% | off | 3 | 72.9 C | 76.8 C | 6-7 | 30 | 33-34 C |
| run-4 | 4 -> 3% | off | 3 | 72.8 C | 76.5 C | 6 | 30 | 34 C |
| run-4 plugged | 3 -> 3% | on | 3 | 71.9 C | 74.8 C | 7 | 30 | 34-35 C |
| run-16 plugged | 16 -> 17% | on | 3 | 73.0 C | 76.5 C | 6-7 | 30 | 32 C |

\* run-20 camera was 60 fps until 8 s, 44.7 fps at 18 s, then 30 fps from 28 s.

Across all seven runs:

- CPU caps were **1.92 / 1.92 GHz**, GPU clock **421 MHz**, `g_throttling=0`, `psm=0` and display
  **72 Hz**. None of those changed at 3-4% battery.
- The head camera was **30 fps** in every status-3 run. run-20 shows the thermal transition:
  status 3 at 16 s, camera 44.7 fps at 18 s, 30 fps from 28 s. This is the same thermal camera
  throttle already seen at status 3, not a battery threshold.
- Fan step was **6** unplugged, but **7** in the 3% plugged run and **6 -> 7** in the 16% plugged
  run.
- At 4 -> 3% the headset kept running for the full 60 s with no shutdown, Battery Saver, lower
  CPU cap or display drop. Battery fell about **1%/min** under this workload.
- Pack temperature rose from **29 C at 20%** to **34 C at 3%** unplugged, and **34-35 C** when
  charging at 3%. That tracks session heat and charging, not the battery threshold itself.

The earlier 14-45% test remains a useful baseline: at thermal status 2, low battery alone kept
72 fps, 60 fps cameras, `psm=0` and the normal thermal cap. The new low/critical runs are
dominated by status 3, so they do not show a separate battery throttle.

**Caveats.** Sequential hot-start runs, no cooldown or ambient control, and only two low-battery
plugged runs. Hand tracking was off and the Chronolink workload was effectively identical. The
standby follow-up pair is in [standby & wake](standby.md).
