# Cross-run analysis

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Analysis of the full local run library: **35 unique recordings** from 43 files (8 duplicate
copies), recorded 2026-10-19 to 2026-10-25 on the same SM-I610. This file separates observed
results from interpretation and from the caveats that limit both.

## Tests & results

### Global thermal status, fan and camera

- 1,711 one-second samples from the 26 current-layout runs.
- `thermal_status` is the platform's staged thermal state; `thermal_max_sev` is the maximum
  per-sensor severity and is not always the same number. One legacy YouTube run had
  `thermal_status=3` with `maxsev=0`, so the two fields must not be treated as interchangeable.

| Global status | AP median | GPU median | Fan step median | Head camera median |
|---|---:|---:|---:|---:|
| 0 | 45.0 C | 46.1 C | 1 | 60 fps |
| 1 | 64.0 C | 65.7 C | 3 | 60 fps |
| 2 | 70.8 C | 71.4 C | 5 | 60 fps |
| 3 | 73.0 C | 73.4 C | 6 | **30 fps** |

Camera response at status 3:

| Run | Status 3 first seen | Camera half first seen | Delay | `psm` | Display |
|---|---:|---:|---:|---:|---:|
| `wifi-2-300-browser` | 34 s | 41 s | 7 s | 0 | 72 Hz |
| `run-youtube-hdr` | 16 s | 28 s | 12 s | 0 | 90 Hz |
| `youtube` (legacy) | 28 s | 46 s | 18 s | 0 | 72 Hz |
| `for-chronos...` | 0 s | 3 s | 3 s | 0 | 72 Hz |

In `wifi-2` the camera change was 60 -> 31.8 fps for head, 60 -> 31.5 fps for hand, raw CIB
480/360 -> 240/180, eye 30 fps, while XR frame rate stayed 72 fps and `psm` stayed 0.

### Fan curve

Values are medians across the 1,693 current-layout rows where fan step and AP were both present.
`fan_pwm` and RPM are discrete fan-program levels, not a continuously controlled curve.

| Fan step | AP median (min-max) | GPU median | Fan PWM median | Fan RPM median | Status median |
|---:|---|---:|---:|---:|---:|
| 1 | 33.4 C (28-55) | 35.7 C | 85 | 3,575 | 0 |
| 2 | 56.0 C (55-59) | 57.3 C | 90 | 3,957 | 0 |
| 3 | 63.0 C (59.8-64.9) | 64.3 C | 95 | 4,213 | 1 |
| 4 | 66.5 C (64-70) | 67.0 C | 100 | 4,366 | 1 |
| 5 | 70.8 C (69.2-71.9) | 71.4 C | 110 | 4,792 | 2 |
| 6 | 72.9 C (72-73.5) | 73.4 C | 120 | 5,181 | 3 |
| 7 | 72.6 C (68-74.1) | 75.5 C | 140 | 5,893 | 3 |

Fan step 7 at AP 68 C was the HDR run, where GPU was already 71-78 C. AP alone does not explain
the highest fan step.

### HDR, display rate and GPU clock

| Run | Display | Active media | GPU clock | GPU busy | FPS / target | Frame drops | AP / GPU | Fan |
|---|---|---|---:|---:|---:|---:|---|---:|
| `run-youtube-hdr` | 90 Hz | 7680x4320 AV1, 10-bit, HDR active | 492-640 MHz | 99% | 70.1 / 90 | 1.6/s | 72 / 75 C | 7 |
| `youtube` (legacy) | 72 Hz | 1920x1080 / 3840x2160 AV1, 8-bit | 421-788 MHz | 44% | 71.9 / 72 | 0.4/s | 72 / 74 C | 5-6 |
| `run-idle-meta` | 72 Hz | none | 421 MHz | 36% | 72 / 72 | 0 | 43 / 44 C | 1 |
| `run-idle-again` | 72 Hz | no active media; stale 8K record | 545 MHz | 0% | 73.4 / 72 | 0 | 45 / 48 C | 1 |
| `run-metadatyaa` | 72 Hz | no active media; stale 8K record | 545 MHz | 0% | 73.4 / 72 | 0 | 36 / 39 C | 1 |
| `run-aaa` | 72 Hz | no active media | 421 MHz | 32% | 72 / 72 | 0 | 41 / 43 C | 1 |
| `for-chronos...` | 72 Hz | 3072x2944 AV1, 8-bit | 421 MHz | 52% | 71.9 / 72 | 0.04/s | 73 / 73 C | 6-7 |

HDR details from `run-youtube-hdr`:

| Signal | Value |
|---|---|
| Media | `video/av01`, 7680x4320, profile 1, `c2.qti.av1.decoder` |
| HDR/layers | `hdr_active=1`, 10-bit active, DISPLAY_P3 |
| Codec HDR field | `media_hdr_format=0` (does not match active HDR) |
| CPU cap | 1.65-1.92 GHz (`cpu_max0/2`), vs 2.36 GHz normally |
| `psm` | 0 |

### Wi-Fi receive and passthrough

Same 120 s, 72 Hz, `psm=0`, Chrome/browser scenario unless noted. `wifi-*` starts are sequential
and began progressively warmer.

| Run | Scene | Wi-Fi Rx | AP start -> end | Fan start -> end | Status max | Camera |
|---|---|---:|---|---|---:|---|
| `wifi-3...dark-seaside-vr` | dark VR, no pass | 0.2 Mbps | 50.7 -> 56.0 C | 1 -> 2 | 0 | 60 fps |
| `wifi-4...day-mountain-vr` | bright VR, no pass | 0.2 Mbps | 53.8 -> 56.4 C | 1 -> 2 | 0 | 60 fps |
| `wifi-1...passthrough` | passthrough | 0.2 Mbps | 60.1 -> 65.1 C | 2.9 -> 4 | 1 | 60 fps |
| `wifi-2-300-browser` | passthrough + 300 | 320 Mbps | 69.9 -> 73.0 C | 4.9 -> 6 | 3 | 30 after 41 s |
| `wifi-4-vr-300...` | VR + 300 | 320 Mbps | 60.3 -> 66.0 C | 3 -> 4 | 1 | 60 fps |
| `wifi-4-vr-600...` | VR + 600 | 632 Mbps | 61.2 -> 69.1 C | 3 -> 4 | 2 | 60 fps |
| `wifi-4-vr-900...` | VR + 900 | 876 Mbps | 63.4 -> 71.0 C | 3 -> 5 | 2 | 60 fps |
| `for-chronos...` | SteamVR streaming | 1,037 Mbps | 72.9 -> 73.3 C | 6 -> 7 | 3 | 30 fps |

Network context from the `wifi-4` sequence: 6.295 GHz, Wi-Fi 7 (`std=8`), link rate ~3.8-4.2
Gbps, RSSI -34 to -31 dBm, retry 2.3-3.3%, no lost packets.

Passthrough also activated depth streams:

| Run | Passthrough | DepthInput | DepthTOF |
|---|---:|---:|---:|
| `wifi-1` | 1 | 143.9 fps | 10.0 fps |
| `wifi-2` | 1 | 143.2 fps | 10.0 fps |
| `wifi-3` | 0 | not present | not present |
| `wifi-4` | 0 | not present | not present |

### Process attribution

Max per-process CPU seen in a snapshot, not additive. Chrome is the sum of its main, sandboxed
and privileged processes where present. Full offender breakdown: [processes](processes.md).

| Run | Dominant CPU consumers | GPU busy |
|---|---|---:|
| `wifi-1` passthrough | camera provider 64%, perceptionhost 54%, systemui 53%, SurfaceFlinger 34%, Chrome 8% | 40% |
| `wifi-3` dark VR | systemui 59%, camera provider 46%, perceptionhost 42%, SurfaceFlinger 33%, Chrome 7% | 43% |
| `wifi-4` bright VR | systemui 58%, camera provider 47%, perceptionhost 35%, SurfaceFlinger 33%, Chrome 7% | 35% |
| `wifi-4-vr-900` | Chrome test client ~113% total, systemui 43%, SurfaceFlinger 41%, camera provider 36%, perceptionhost 34% | 38% |
| `run-youtube-hdr` | YouTube 85%, systemui 58%, perceptionhost 50%, camera provider 39%, SurfaceFlinger 33%, media.hwcodec 15% | 99% |
| `for-chronos...` | Chronolink client 50%, perceptionhost 31%, SurfaceFlinger 27%, camera provider 23%, controller service 18% | 52% |

GPU memory was dominated by system UI and SurfaceFlinger in these snapshots (~1.5-1.8 GB each),
not by the foreground app (YouTube ~0.3 GB, Chrome ~0.35 GB, Chronolink ~0.2 GB).

### Battery and AC

Four 60 s ASTC runs, `psm=0`, 72 Hz, status 2:

| Run | Battery | AC | AP mean | Fan | GPU busy | CPU cap |
|---|---:|---:|---:|---:|---:|---:|
| `low-batt-astc` | 16% | off | 71.4 C | 5 | 40.8% | 1.92 GHz |
| `low-batt-plugged-astc` | 14% | on | 70.7 C | 5 | 41.5% | 1.92 GHz |
| `38-bat-astc` | 38% | off | 70.6 C | 5 | 40.8% | 1.92 GHz |
| `44-bat-plugged-astc` | 45% | on | 70.7 C | 5 | 40.3% | 1.92 GHz |

`crit-batt-youtube` at 7% battery also stayed at `psm=0`, 72 Hz and 2.36 GHz cap.

## Findings

- **Thermal status 3 triggers a camera-pipeline throttle.** Head/hand camera rates fall 60 ->
  ~30 fps, raw CIB falls 480/360 -> 240/180, while eye remains 30 fps, display rate is unchanged
  and `psm` remains 0. It appears 3-18 s after status 3 in the runs where the transition was
  captured, and preserved 72 fps in `wifi-2`.
- **Global thermal status and per-sensor severity are separate signals.** A legacy YouTube run
  reached global status 3 while its recorded max sensor severity was 0; use status for the
  platform stage and max-severity for sensor attribution.
- **The fan uses seven discrete programmed steps.** The observed mapping is about 3.6k -> 5.9k
  RPM and 85 -> 140 PWM from step 1 to 7; AP thresholds are roughly 55, 60, 64, 69, 72 C, but
  step 7 can fire at AP 68 C when GPU is already 75+ C.
- **The GPU clock is not fixed at 421 MHz.** Normal 72 Hz/SRGB workloads cluster at 421 MHz,
  HDR/8K at 90 Hz used 492-640 MHz, and idle runs immediately after the HDR session stayed at
  545 MHz at 0% busy. A later idle run returned to 421 MHz. 421 is a common floor, not a global
  invariant.
- **8K HDR at 90 Hz is GPU-bound on this unit.** It ran 66.8-75.3 fps against a 90 fps target
  (mean 70.1, ~1.6 drops/s) with 92-99% GPU busy, AP/GPU 68-78 C, fan step 7 and CPU capped to
  1.65-1.92 GHz. The codec record still said `media_hdr_format=0` while active HDR and 10-bit
  layers were present, so codec HDR metadata alone is not a reliable active-HDR signal.
- **Wi-Fi receive load adds heat without moving GPU load.** In the sequential 300/600/900
  browser runs, GPU stayed ~37-38% busy and cameras stayed 60 fps, while AP end temperature rose
  66.0 -> 69.1 -> 71.0 C, fan rose 4 -> 4 -> 5, and Chrome CPU rose with throughput. Chrome was
  deliberately used as the download client, so that CPU is mostly the fast-download/payload
  workload, not browser UI rendering. The runs were sequential, so some of the rise is thermal
  carryover; the direction is consistent but the slope is not a controlled measurement.
- **Passthrough is a camera/perception workload, not primarily a GPU workload.** Pass-through
  activated `DepthInput` (~144 fps) and ToF (10 fps), raised camera-provider CPU from ~46% to
  ~64% and perceptionhost from ~35-42% to ~54%, and raised AP from ~54-56 C to ~65 C at the same
  light Chrome load. GPU busy was not higher. The pass-through run started warmer, so the exact
  temperature delta is not clean.
- **Passthrough plus network load compounds.** `wifi-2` (passthrough + 320 Mbps) reached 73 C,
  fan step 6 and status 3, while the no-passthrough 300 Mbps run ended at 66 C, fan 4, status 1.
  Again, the pass-through run started ~70 C, so treat the size of the gap as indicative, not
  controlled.
- **The software workload is broader than the foreground app.** System UI and SurfaceFlinger
  consume substantial CPU/GPU memory in every XR session; camera provider and perceptionhost
  dominate passthrough; Chrome is the deliberate network test client and its CPU tracks the fast
  download; YouTube HDR is CPU/GPU heavy even with the hardware AV1 decoder; SteamVR streaming is
  led by the Chronolink client.
- **Battery/AC state still shows no performance profile change.** Low battery, high battery,
  plugged and unplugged ASTC runs all held the same caps, clock, display mode, fan and GPU load.
  Charging added ~0.75-1 C to pack temperature only.
- **Stale media records can mislead.** Several idle runs still carry an 8K AV1 record while
  `media_active=0`; use `media_active` and record age, not the presence of a codec record.

## Details

### Scope and method

- 26 current-layout directories + 17 legacy flat runs = 43 recorded files.
- Eight CSV files are byte-identical duplicates between the two layouts; analysis uses 35 unique
  recordings.
- Schemas range from 2 to 6 and column counts from 119 to 218. Metrics absent from older runs
  were treated as missing, not zero.
- All statistics are per-row aggregates over the run; the tests above use start/end means where
  warm-up matters.
- `run-youtube` was excluded from YouTube comparisons because `media_active=0` throughout; it is
  not an active-playback run.
- `run-aaa` is only 10 s and `run-test` is 5-7 s; neither is steady state.

### Run inventory

| Group | Runs |
|---|---|
| Battery / ASTC | `low-batt-astc`, `low-batt-plugged-astc`, `38-bat-astc`, `44-bat-plugged-astc` |
| YouTube | `youtube`, `youtube-2`, `crit-batt-youtube`, `run-youtube-hdr`; `run-youtube` inactive |
| Idle / desktop | `runidle`, `idle`, `idle-2`, `run` (current), `run1`, `run-3`, `run-idle-meta`, `run-idle-again`, `run-metadatyaa`, `run-aaa`, `idle-processes`, `idle-processes-2`, `crit-plugged-idle`, `wifi-0-idle...` |
| Browser / Wi-Fi | `wifi-1` passthrough, `wifi-2` 300 passthrough, `wifi-3` dark VR, `wifi-4` bright VR, `wifi-4-vr-300/600/900` |
| SteamVR | `for-chronos-in-steamvr-void-astc-balanced-hitching-and-stream-lost` |
| Other / short | `run` (legacy), `run-test`, `rundfg`, `rundfgfg` |

### Caveats

- No ambient temperature, controlled workload, or cool-down was recorded. Absolute temperatures
  are not comparable across sessions; many runs started at status 1-3.
- Several comparisons were recorded sequentially (300/600/900, passthrough vs dark) and carry
  heat forward. The direction is useful; the magnitude is not controlled.
- HDR, 8K, 10-bit, 90 Hz and P3 changed together in `run-youtube-hdr`; this suite cannot separate
  their individual costs.
- Camera halving is correlated with status 3 and a short lag, but the exact trigger source was not
  logged. It is a thermal/perception policy observation, not a confirmed code path.
- Short runs (5-30 s) are dominated by warm-up and should not be used for steady-state claims.
- The profiler itself adds ADB/logcat load (`adbd` often 13-16% CPU, `logcat` 2-3%); the smallest
  effects should be treated as within measurement overhead.

### Useful next experiments

1. Cool-start HDR matrix: 1080p / 4K / 8K, SDR / HDR, 72 / 90 Hz, matched brightness and duration.
2. Sustained status-3 test with `DynamicPolicyManager` and camera lifecycle logs to confirm the
   camera-throttle trigger and release hysteresis.
3. Randomised 300/600/900 Wi-Fi runs with a cooldown between runs, same scene and no passthrough.
4. Passthrough on/off with identical scene, brightness and starting temperature, plus depth-stream
   counts, to isolate the ISP/perception cost.
5. GPU-clock recovery timeline after an HDR session: sample `g_clock` and `gpu_clock_stats` at idle
   until it returns to 421 MHz, and test whether a reboot is required.
6. Long HDR playback with CPU/GPU caps and dropped-frame counters to see whether 90 Hz is ever
   sustainable.
