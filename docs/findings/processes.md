# Process offenders

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Process analysis across the run library. `cpu_now_pct` is the interval CPU delta; `cpu_pct` is
Android's ~5-minute sliding value. Unless stated otherwise, values below are the maximum
`cpu_now_pct` seen in a process snapshot, and are **per process, not additive**. GPU memory and
RSS are maxima.

## Tests & results

### True idle / no active XR app

These runs had no head/hand camera activity and no foreground XR app:

| Run | Top current CPU consumers |
|---|---|
| `wifi-0-idle-headset-on-my-desk` | `adbd` 5.2%, SurfaceFlinger 3.4%, systemui 2.3%, system_server 1.7%; camera provider/perception <0.5% |
| `runidle` | `adbd` 8.4%, system_server 5.7%, SurfaceFlinger 4.3%, systemui 2.4% |
| `idle-processes` | `adbd` 7.4%, system_server 5.9%, SurfaceFlinger 4.4%, systemui 2.2% |
| `idle-processes-2` | `adbd` 7.8%, system_server 5.2%, SurfaceFlinger 4.3%, systemui 2.2% |

`adbd` is the capture transport, not a device workload. In true idle the remaining system load is
low.

### XR home or browser active

| Run | Scene | Top current CPU consumers | GPU busy |
|---|---|---|---:|
| `run-idle-meta` | XR home, no foreground app | systemui 47.7%, perceptionhost 45.5%, camera provider 44.6%, SurfaceFlinger 34.5%, XR home 8.9% | 36% |
| `wifi-3...dark-seaside-vr` | browser VR, no passthrough | systemui 59.4%, camera provider 46.5%, perceptionhost 42.2%, SurfaceFlinger 32.7%, Chrome 6.6% | 43% |
| `wifi-4...day-mountain-vr` | browser VR, no passthrough | systemui 57.9%, camera provider 46.6%, perceptionhost 35.4%, SurfaceFlinger 32.5%, Chrome 7.0% | 35% |
| `wifi-1...passthrough` | browser + passthrough | camera provider 64.4%, perceptionhost 54.2%, systemui 53.3%, SurfaceFlinger 33.6%, controller service 16.7%, Chrome 7.6% | 40% |
| `wifi-2-300-browser` | passthrough + 300 Mbps | camera provider 53.9%, perceptionhost 43.4%, Chrome 92.7% total, systemui 40.6%, SurfaceFlinger 40.2% | 40% |
| `wifi-4-vr-900...` | Chrome test client + 900 Mbps | Chrome 113.3% total, systemui 43.1%, SurfaceFlinger 40.8%, camera provider 36.5%, perceptionhost 33.5% | 38% |

`run-idle-meta` is a useful correction: the XR home is **not** idle. It still runs systemui,
perceptionhost and the camera provider at roughly 45% each.

### HDR and SteamVR

| Run | Scene | Top current CPU consumers | GPU busy |
|---|---|---|---:|
| `run-youtube-hdr` | 8K HDR YouTube, 90 Hz | YouTube XR 85.3%, systemui 58.1%, perceptionhost 50.0%, camera provider 39.0%, SurfaceFlinger 32.9%, media.hwcodec 15.2%, audioserver 7.0% | 99% |
| `for-chronos...` | SteamVR / Chronolink | Chronolink client 50.0%, perceptionhost 31.0%, SurfaceFlinger 27.0%, camera provider 23.0%, controller service 18.0%, systemui 13.0% | 52% |

### GPU memory and RSS

| Process | Max GPU memory | Max RSS | Notes |
|---|---:|---:|---|
| `com.android.systemui` | 1.85 GB | 0.97 GB | large in every active XR session |
| `surfaceflinger` | 1.82 GB | 0.71 GB | stable across 120 s runs |
| `android.hardware.perceptionhost` | n/a | 0.93 GB | higher with passthrough/depth |
| `vendor.qti.camera.provider@2.7-service_64` | n/a | 0.25 GB | passthrough |
| `com.google.android.apps.youtube.xr` | 0.31 GB | 0.62 GB | RSS grew 426 -> 615 MB during 30 s of 8K HDR |
| `com.android.chrome` | 0.13 GB | 0.48 GB | WiFi test client; CPU is mostly download/payload handling |
| `dev.chronolink.client` | 0.20 GB | 0.22 GB | SteamVR streaming client |

GPU memory is shared accounting; do not add systemui and SurfaceFlinger together as if they were
independent.

### Profiler overhead

| Process | Observed current CPU | What it is |
|---|---:|---|
| `adbd` | 5-8% true idle; up to 15.8% in active runs | ADB transport for the poll/shell commands |
| `logcat` | 0.1-2.3% | logcat capture |
| `logd` | 0.2-7.2% | logging daemon, including captured log volume |
| `sh` | 0.9-1.7% | adb shell commands |

This overhead is not part of the headset's normal workload. Exclude it before comparing small
process deltas.

### Sliding-window warning

`cpu_pct` is a ~5-minute value and lags the present. In `run-idle-again`, shortly after the HDR
run, `cpu_pct` still showed YouTube 26%, systemui 27% and SurfaceFlinger 15%, while `cpu_now_pct`
was only 3.7%, 2.4% and 3.9%. Use `cpu_now_pct` for immediate state and `cpu_pct` for sustained
history.

## Findings

- **The biggest recurring active-XR CPU consumers are SystemUI and SurfaceFlinger**, each around
  30-60% depending on scene. They are low in true idle. This looks like baseline XR compositor/UI
  cost, not a runaway app.
- **Camera provider and perceptionhost are the passthrough offenders.** They rise from about
  46%/35-42% without passthrough to 64%/54% with it, and passthrough also activates the depth
  streams. This is the main reason passthrough is expensive despite little GPU change.
- **Chrome is the configured WiFi test client, not a general browser offender.** At 900 Mbps the
  three Chrome processes totaled ~113% CPU, but 300 -> 600 -> 900 Mbps only moved that total
  ~101 -> 110 -> 113 points while GPU stayed ~38%. That is consistent with the browser handling
  the fast download/payload, not UI rendering; do not treat this as normal Chrome overhead.
- **YouTube XR is the HDR offender**: 85% CPU, 15% media.hwcodec, 58% systemui, 50%
  perceptionhost and 39% camera provider alongside 99% GPU.
- **The Chronolink client is the SteamVR workload**: 50% CPU, with perceptionhost, SurfaceFlinger
  and camera provider still significant.
- **`adbd` is the largest apparent idle CPU consumer, but it is the profiler.** True idle is
  otherwise light: system_server ~2-6%, SurfaceFlinger ~3-4%, systemui ~2%.
- **The XR home is not idle.** With no foreground app it still held systemui ~48%, perceptionhost
  ~46%, camera provider ~45% and SurfaceFlinger ~35%.
- **No obvious runaway process or monotonic CPU leak.** RSS was broadly stable over 120 s;
  systemui/SurfaceFlinger changed only a few MB. YouTube HDR RSS grew 426 -> 615 MB during 30 s,
  which is most likely decoder/compositor buffering and needs a longer run to classify as a leak.
- **The controller service is material in controller-heavy sessions** (~17-18% in passthrough and
  Chronolink), but not in controller-free browser runs.
- **Google Play services can appear in idle** (`gms.persistent` ~5% in one plugged-idle sample),
  but the sample is short and not a sustained offender.

## Details

### Method

- Process snapshots from the 26 current-layout runs plus the legacy Chronolink run.
- Current snapshots contain `cpu_now_pct` (interval delta) and `cpu_pct` (5-minute sliding).
  Legacy runs only have the latter, so they were not used for instantaneous comparisons unless
  noted.
- `processes_top=0` in the current runs captures all non-kernel processes; older runs captured the
  top 15 only.
- Process names are matched exactly; Chrome totals include main, sandboxed and privileged
  processes.
- Network values are per UID, so Chrome processes share the same network counters.

### Caveats

- Process snapshots are sparse: 3-12 snapshots per 30-120 s run, so maxima are not long-term
  averages.
- `cpu_pct` can carry the previous workload for up to 5 minutes.
- GPU memory may double-count shared graphics allocations.
- The profiler itself changes the system load (`adbd`, `logcat`, `sh`, `logd`).
- Many runs started hot; process CPU is not independent of thermal state.
- `run-idle-meta` is an active XR home, not a doffed headset; `run-idle-again` is post-HDR idle
  and shows stale 5-minute values.

### What to optimize first

1. Treat SystemUI + SurfaceFlinger as the active-XR baseline, not as app bugs.
2. For thermal tests, avoid passthrough unless it is the subject; camera provider + perceptionhost
   add ~18/12 CPU points and activate depth.
3. For network tests, treat Chrome CPU as part of the download harness and compare it at the same
   bitrate; exclude `adbd`/`logcat` overhead.
4. For HDR, test 8K versus 4K and 90 Hz versus 72 Hz separately; YouTube HDR combines all three.
5. For leak questions, run 10-30 minutes, not 30-120 seconds.
