# 2026-11-17 - two Beat Saber soft reboots: SystemUI HWUI animation race

[Findings index](../../README.md#findings-index) | [Crash & soft-reboot logs](../../crash-logs.md) | [Thermal mod before/after](../../thermal-mod.md)

> **Hardware state: MODDED.** SoC thermal-modded SM-I610 (phase-change pads + copper shims,
> post-2026-11-01). This page covers two unexpected soft reboots observed while running the
> GXR-converted Beat Saber APK.

## Summary

Two framework soft reboots occurred during Beat Saber at 90 Hz. Both were caused by
**`com.android.systemui` native crashes in Android's HWUI animation code**:

- Event 1: SystemUI main thread `SIGABRT`, abort message
  `sp<> assignment detected data race`, in `PropertyValuesAnimatorSet::start` via
  `AnimatedVectorDrawable` / `ProgressBar$CircleAnimationCallback`.
- Event 2: SystemUI `RenderThread` `SIGSEGV`, null dereference in the
  `PropertyValuesAnimatorSet` set insertion path via
  `AnimationContextBridge::startFrame`.

Beat Saber is the trigger, not the crashing process. The device stayed on the kernel; only
`system_server`/SystemUI restarted. There is no evidence of a thermal shutdown, GPU fault, kernel
panic, power fault, root-exploit crash or thermal-mod failure in these two events.

The second attempt was made after deliberately dimming the room; the first event was captured
before that dimming. Dim lighting can worsen tracking and make SystemUI's tracking/poor-condition
overlays appear; the logs show the XR overlay layers `DWELL_PANEL`, `POOR_CONDITION_DIALOG` and
`ACCESSIBILITY_FLOATING_MENU` around the crashes. This is a plausible frequency modifier, not a
proven root cause.

## Conditions

| Item | Value |
|---|---|
| Device | Samsung Galaxy XR (SM-I610) |
| Build | `I610UEU2AZF3` / `UML2.260301.001` |
| Android | 14 |
| Hardware | SoC thermal-modded (phase-change pads + copper shims) |
| Workload | GXR-converted Beat Saber, 90 Hz |
| Lighting | First event not instrumented; second event after deliberately dimming the room |
| Root | KernelSU/DFroot active; root initialisation uses a soft reboot |
| Root soft reboots | Expected and separate from these events |

The headset had already soft-rebooted to initialise the KernelSU root modules before the capture.
The two events below are not that routine reboot.

## Timeline

Times are device-local UTC from logcat.

| Time | Event |
|---|---|
| 00:32:50 | Host-side full `logcat -b all` capture started |
| 00:41:36-00:41:49 | Beat Saber rendering; `CPM` client 7 CPU ~12-14 ms, GPU ~15-21 ms |
| 00:41:47.751 | SystemUI main thread aborts (`SIGABRT`) |
| 00:41:49.143 | `ActivityManager`: `Process com.android.systemui (pid 11754) has died: pers PER` |
| 00:41:49.192 | `ActivityManager`: scheduling restart of `com.android.systemui/.SystemUIService` |
| 00:41:49 | Dropbox records `SYSTEM_TOMBSTONE` (matches `tombstone_13`) |
| 00:41:51 | ADB/logcat connection drops |
| 00:42:02 | New `system_server`; SystemUI restarts as pid 611 |
| ~00:42:04 | `boot_progress_enable_screen`; kernel uptime is continuous (soft reboot) |
| 00:42:20 | Dropbox records `SYSTEM_RESTART` |
| 00:51:23-00:51:35 | Beat Saber second song; SystemUI XR overlays active |
| 00:51:35.813 | SystemUI `RenderThread` `SIGSEGV` (pid 611) |
| 00:51:36.975 | `ActivityManager`: `Process com.android.systemui (pid 611) has died: pers PER` |
| 00:51:49 | ADB/logcat connection drops |
| 00:52:03 | Dropbox records `SYSTEM_RESTART` |
| ~00:51:50+ | New `system_server`; replacement SystemUI logs repeated OpenXR swapchain errors |

Kernel `/proc/uptime` continued across both events, so these were framework/system_server restarts,
not full power cycles. `sys.boot.reason` was `reboot,rescueparty_warm_reboot`; the rescue/boot-count
properties are live, but DFroot's routine soft reboot can look similar and must be separated by
timestamp.

## Crash evidence

### Event 1 - SystemUI main-thread data race

```text
11-17 00:41:48.881 31700 31700 F DEBUG   : Timestamp: 2026-11-17 00:41:47.751068593+0000
11-17 00:41:48.881 31700 31700 F DEBUG   : Process uptime: 1860s
11-17 00:41:48.881 31700 31700 F DEBUG   : Cmdline: com.android.systemui
11-17 00:41:48.881 31700 31700 F DEBUG   : pid: 11754, tid: 11754, name: ndroid.systemui  >>> com.android.systemui <<<
11-17 00:41:48.881 31700 31700 F DEBUG   : signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------
11-17 00:41:48.881 31700 31700 F DEBUG   : Abort message: 'sp<> assignment detected data race'
11-17 00:41:48.882 31700 31700 F DEBUG   :       #05 pc ... /system/lib64/libhwui.so (android::uirenderer::PropertyValuesAnimatorSet::start(...)+160)
11-17 00:41:48.882 31700 31700 F DEBUG   :       #07 pc ... /system/framework/arm64/boot-framework.oat (android.graphics.drawable.AnimatedVectorDrawable$VectorDrawableAnimatorRT.startAnimation+156)
11-17 00:41:48.882 31700 31700 F DEBUG   :       #08 pc ... /system/framework/arm64/boot-framework.oat (android.graphics.drawable.AnimatedVectorDrawable$VectorDrawableAnimatorRT.start+436)
11-17 00:41:48.882 31700 31700 F DEBUG   :       #09 pc ... /system/framework/arm64/boot-framework.oat (android.graphics.drawable.AnimatedVectorDrawable.start+224)
11-17 00:41:48.882 31700 31700 F DEBUG   :       #10 pc ... /memfd:jit-cache (android.widget.ProgressBar$CircleAnimationCallback$1.run+280)
```

This is a **circular `ProgressBar` animation** starting an `AnimatedVectorDrawable` on SystemUI's
main thread. libutils detected two threads assigning the same strong pointer and intentionally
aborted the process. That is a software refcount race.

### Event 2 - SystemUI RenderThread null dereference

```text
11-17 00:51:36.747  6866  6866 F DEBUG   : Timestamp: 2026-11-17 00:51:36.070078941+0000
11-17 00:51:36.747  6866  6866 F DEBUG   : Process uptime: 578s
11-17 00:51:36.747  6866  6866 F DEBUG   : Cmdline: com.android.systemui
11-17 00:51:36.747  6866  6866 F DEBUG   : pid: 611, tid: 980, name: RenderThread  >>> com.android.systemui <<<
11-17 00:51:36.747  6866  6866 F DEBUG   : signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0000000000000002
11-17 00:51:36.747  6866  6866 F DEBUG   : Cause: null pointer dereference
11-17 00:51:36.748  6866  6866 F DEBUG   :       #00 pc ... /system/lib64/libhwui.so (...set<...PropertyValuesAnimatorSet...>::insert...+344)
11-17 00:51:36.748  6866  6866 F DEBUG   :       #01 pc ... /system/lib64/libhwui.so (android::uirenderer::AnimationContextBridge::startFrame(...)+196)
11-17 00:51:36.748  6866  6866 F DEBUG   :       #02 pc ... /system/lib64/libhwui.so (android::uirenderer::renderthread::CanvasContext::prepareTree(...)+276)
11-17 00:51:36.748  6866  6866 F DEBUG   :       #03 pc ... /system/lib64/libhwui.so (...DrawFrameTask::postAndWait()...+744)
11-17 00:51:36.748  6866  6866 F DEBUG   :       #04 pc ... /system/lib64/libhwui.so (android::uirenderer::WorkQueue::process()+608)
11-17 00:51:36.748  6866  6866 F DEBUG   :       #05 pc ... /system/lib64/libhwui.so (android::uirenderer::renderthread::RenderThread::threadLoop()+408)
```

This is the same animation subsystem: a `PropertyValuesAnimatorSet` is inserted into an animation
set while the RenderThread starts a frame. The fault address `0x2` and the null-deref cause are
consistent with a dead/null animator state rather than a hardware memory error.

## SystemUI overlay context

Around the crashes the renderer logged buffers for these XR SystemUI layers:

```text
com.android.systemui.xr.DWELL_PANEL
com.android.systemui.xr.POOR_CONDITION_DIALOG
com.android.systemui.xr.DWELL_MENU
com.android.systemui.xr.ACCESSIBILITY_FLOATING_MENU
com.android.systemui/.xr.wm.SysUiVisibilityBarrier
```

Relevant settings at capture time:

```text
enabled_dwell=0
accessibility_enabled=0
animator_duration_scale=0.0
window_animation_scale=0.0
transition_animation_scale=0.0
```

So dwell/accessibility was not enabled and Android's global animation scales were already zero. The
crashing animation is therefore likely an indeterminate/SystemUI-owned animation (circular
`ProgressBar`/`AnimatedVectorDrawable`) tied to an XR overlay or system-UI transition, not a
user-enabled dwell ring. The dim-room correlation remains a hypothesis: poor lighting/tracking can
make tracking/poor-condition overlays appear more often.

## Thermal and power context

Both events happened at thermal status 3 with the fan at step 7. The SoC sensors were hot but the
device was not in a thermal shutdown or status 4:

| Event | AP | WIFI | LRP | Status | Fan |
|---|---:|---:|---:|---:|---:|
| 1 (00:41:45-48) | 74.2-74.4 C | 78.0-78.2 C | 62.4 C | 3 | 7 |
| 2 (00:51:30-36) | 74.8-75.0 C | 78.6-78.8 C | 61.2-61.3 C | 3 | 7 |

This matches the documented post-mod behaviour for heavy workloads: WIFI/DDR are untouched and
remain the hottest named sensors, and heavy VR can still reach status 3/fan 7. There is no status 4,
no thermal-critical trip and no power-rail/battery anomaly in the captured window.

## Interpretation

- **Not Beat Saber's renderer.** The crashing process is `com.android.systemui`; Beat Saber kept
  rendering until the framework restart.
- **Not a kernel/GPU/power fault.** No kernel panic, `kgsl` fault, GPU reset, thermal shutdown or
  power-rail error was found. The same two HWUI stacks repeat.
- **Not the root exploit.** Root was active, but the crash is in stock SystemUI animation code. The
  same class of restart was reported before the mod and occurs across multiple payloads.
- **Not the thermal mod failing.** The mod is doing its job: the headset is hot under Beat Saber but
  stays at status 3 instead of the stock status-4 cases. A cooling-mod fault would not produce a
  deterministic `sp<>` race in libhwui.
- **Likely trigger:** a SystemUI XR overlay/system-UI animation during Beat Saber. Dim light and
  poor tracking are plausible frequency modifiers; they do not change the crash mechanism.

## Historical tombstone sweep (later follow-up)

A later Diagnostics root sweep read all 15 text tombstones then present, covering 2026-10-18 to
2026-11-17. It found more than the two events above. The full sweep is documented in
[historical tombstone sweep](2026-11-17-historical-tombstones.md):

- 12 `com.android.systemui` tombstones with the same HWUI race signature.
- 2 `android.hardware.perceptionhost` SIGABRTs:
  `Head tracking failed to initialize the internal MotionTrackingAdapter component.`
- 1 `com.google.android.apps.immersiveviewxr` SIGSEGV.

This is useful for two reasons. First, the SystemUI issue is not a one-off; it has recurred across
multiple days. Second, the parser/UI handles a **new** native process generically: the perceptionhost
and immersiveviewxr crashes appear as their own findings rather than being forced into the SystemUI
classification. The two perceptionhost failures are a separate head-tracking initialization issue and
should not be blamed on the thermal mod without their own investigation.

## Caveats

- Only two events; this is a signature, not a rate or a complete trigger list.
- The first manual `/data/tombstones` and `/data/system/dropbox` reads returned permission denied.
  A later Diagnostics root probe read `tombstone_13` / `tombstone_14` and the Dropbox
  `SYSTEM_TOMBSTONE` entry at 00:41:49, so this report uses the logcat `F DEBUG` blocks plus the
  retained Dropbox tombstone. If root access is blocked on another boot, use `adb bugreport`.
- `dumpsys activity exit-info` did not list these SystemUI native crashes. The initial Dropbox read
  showed only `SYSTEM_RESTART`; the later probe also showed `SYSTEM_TOMBSTONE` and two more
  `SYSTEM_RESTART` entries at 00:42:20 and 00:52:03.
- The room lighting was not measured. Only the second event followed a deliberate dimming; the
  dim/bright correlation was observed by the user, not instrumented.
- DFroot's routine soft reboot can also produce `rescueparty_warm_reboot` and increment
  `sys.rescue_boot_count`; the counters alone do not prove a bug.
- The raw capture is large (~329 MB) and stays local; it is not committed. Only sanitized excerpts
  are in this report.

## Suggested next steps

1. Compare `tombstone_13` / `tombstone_14` and the Dropbox `SYSTEM_TOMBSTONE` body with the
   `F DEBUG` blocks above; capture a full `adb bugreport` after the next event if access changes.
2. Repeat with bright, even lighting and compare SystemUI overlay activity and crash frequency.
3. Check for a SystemUI/system update before attributing the signature to the hardware.
4. After the planned factory reset, repeat the same Beat Saber workload and collect a Diagnostics
   snapshot to see whether the signature disappears.
5. Report the `libhwui` stack to Samsung/Google; the retained Dropbox `SYSTEM_TOMBSTONE` and
   `tombstone_13`/`tombstone_14` already match the build and crash signature (`I610UEU2AZF3`).
