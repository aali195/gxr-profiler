# 2026-10-18 to 2026-11-17 - historical tombstone sweep

[Findings index](../../README.md#findings-index) | [Diagnostics guide](../../../DIAGNOSTICS.md) | [Crash & soft-reboot logs](../../crash-logs.md) | [SystemUI HWUI report](2026-11-17-systemui-hwui-beatsaber.md)

> **Hardware state: MIXED.** This sweep spans the stock unit (2026-10-18 and 2026-10-28) and the
> thermal-modded unit (2026-11-06 onward). The dates matter: the SystemUI HWUI and perceptionhost
> signatures both appear **before** the mod, so the mod is not their origin.

The Diagnostics root sweep read all 15 text tombstones retained on 2026-11-17. It found three
distinct native crash signatures, not just the two Beat Saber soft reboots already documented.

## Summary

| Signature | Count | First seen | Last seen | Meaning |
|---|---:|---|---|---|
| SystemUI HWUI animation race | 12 | 2026-10-18 (stock) | 2026-11-17 (modded) | Android HWUI animation/data-race crash |
| Perception head-tracking initialisation failure | 2 | 2026-10-28 (stock) | 2026-11-06 (modded) | Native perception host cannot initialise MotionTrackingAdapter |
| Immersive View XR Vulkan/foveation crash | 1 | 2026-11-08 (modded) | 2026-11-08 (modded) | Unity app crashes in Android foveation Vulkan layer/Adreno driver |

The SystemUI signature remains the best-understood issue. The other two are now recognised by the
Diagnostics tab with their own titles, explanations and next steps.

## Tombstone index

| Tombstone | Timestamp (UTC) | Process | Signature |
|---|---|---|---|
| `tombstone_00` | 2026-10-18 13:25 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_01` | 2026-10-28 02:47 | `android.hardware.perceptionhost` | Perception head-tracking init |
| `tombstone_02` | 2026-11-06 23:13 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_03` | 2026-11-06 23:17 | `android.hardware.perceptionhost` | Perception head-tracking init |
| `tombstone_04` | 2026-11-07 00:25 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_05` | 2026-11-07 00:32 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_06` | 2026-11-08 00:42 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_07` | 2026-11-08 20:50 | `com.google.android.apps.immersiveviewxr` | Immersive View XR foveation |
| `tombstone_08` | 2026-11-13 02:23 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_09` | 2026-11-13 02:55 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_10` | 2026-11-16 22:34 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_11` | 2026-11-16 22:35 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_12` | 2026-11-16 22:45 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_13` | 2026-11-17 00:41 | `com.android.systemui` | SystemUI HWUI animation race |
| `tombstone_14` | 2026-11-17 00:51 | `com.android.systemui` | SystemUI HWUI animation race |

`tombstone_00` is timestamped `+0100`; the others are `+0000`. The table normalises the first entry
to UTC.

## 1. SystemUI HWUI animation race

This is the issue already covered in the
[2026-11-17 report](2026-11-17-systemui-hwui-beatsaber.md). The historical sweep adds two useful
facts:

- It appears **before** the thermal mod: `tombstone_00` is dated 2026-10-18, on the stock unit.
- It is recurrent: 12 of the 15 retained tombstones carry the same SystemUI HWUI signature across
  multiple days and boots.

The stack remains the `libhwui` `PropertyValuesAnimatorSet` / `AnimationContextBridge` path, with
`sp<> assignment detected data race` or a null animator. The Diagnostics tab groups these historical
entries under **Historical SystemUI HWUI animation race** instead of creating a dozen duplicate
findings.

## 2. Perception head-tracking initialisation failure

Two tombstones have an identical stack:

```text
Cmdline: /vendor/bin/hw/android.hardware.perceptionhost
pid: 11930, tid: 12131, name: read_factory_ca  >>> /vendor/bin/hw/android.hardware.perceptionhost <<<
signal 6 (SIGABRT), code -1 (SI_QUEUE)
Abort message: '... world_sense_session.cc:271] [XrHealthEvent|XrLifecycle][HeadTracking] Head tracking
failed to initialize the internal MotionTrackingAdapter component.'
```

Backtrace:

```text
#00 libc.so (abort+168)
#01-#06 libperception_head_tracking_host_plugin.so
#07 libc.so (__pthread_start)
#08 libc.so (__start_thread)
```

The crash is inside the vendor perception head-tracking host plugin, on a thread named
`read_factory_ca`, while bringing up the internal `MotionTrackingAdapter`. The process aborts
deliberately after the initialisation failure.

What it likely means:

- The head-tracking service could not initialise its camera/IMU/calibration pipeline. This is a
  **tracking-service startup failure**, not an app crash and not the SystemUI animation race.
- It happened on **2026-10-28 (stock)** and **2026-11-06 (modded)** with the same stack, so the
  thermal mod is not required for it to occur.
- The stack alone cannot tell us whether the trigger was a camera/IMU resource conflict, a service
  restart/standby transition, a calibration read failure, or a transient hardware/driver issue.

Practical next steps:

1. Note what happened just before the failure: standby/wake, camera or passthrough use, a specific
   app, or a headset reboot.
2. If it repeats, collect `adb bugreport` while it is fresh and keep the full tombstone.
3. Check for a system/perception update before treating it as hardware.
4. If it correlates with a specific app or passthrough/camera path, test that path separately.

The Diagnostics tab titles this **Perception head-tracking initialisation failure** and recommends
checking standby/wake, camera use and a system update.

## 3. Immersive View XR Vulkan/foveation crash

One tombstone:

```text
Cmdline: com.google.android.apps.immersiveviewxr
pid: 27825, tid: 27950, name: Thread-24
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x00ffffffffffffff
```

Backtrace:

```text
#00 /vendor/lib64/hw/vulkan.adreno.so (vkCreateImage+328)
#01 /vendor/lib64/hw/vulkan.adreno.so (qglinternal::vkCreateImage(...))
#02 /system/lib64/vulkan/libVkLayer_android_foveation.so (foveation_layer::ShiftedFDM::Initialize(...))
#03 /system/lib64/vulkan/libVkLayer_android_foveation.so (ShiftedFDMFramebuffer::Initialize(...))
#04 /system/lib64/vulkan/libVkLayer_android_foveation.so (AlignFDMCreateFramebuffer(...))
#05 /system/lib64/vulkan/libVkLayer_android_foveation.so (InterceptCreateFramebuffer(...))
#06-#14 libunity.so
```

The app is **Immersive View XR** version **1.0.1118** (last updated 2026-10-31). It is a Unity app
crashing while creating a Vulkan image/framebuffer through Android's foveation Vulkan layer and the
Adreno driver. The fault address is a non-canonical sentinel (`0x00ffffffffffffff`), consistent with
a bad/corrupted Vulkan handle rather than a thermal event.

This is most likely an app/content + foveation/driver interaction. It is **not** the SystemUI HWUI
race and there is no evidence that the thermal mod caused it.

Practical next steps:

1. Update the app and the headset system; re-test the same content.
2. If the app exposes a foveation/rendering setting, try disabling it.
3. Record the app version and the exact content being opened.
4. If it repeats, capture a bugreport with the app version and the full tombstone.

The Diagnostics tab titles this **Immersive View XR Vulkan/foveation crash** and recommends updating
the app/system and trying different content or foveation settings.

## How the Diagnostics tab handles this now

- Known native signatures get a dedicated title, summary and recommendation in the **Crashes** and
  **Tombstones (history)** cards.
- Historical tombstones are grouped by signature, so 12 SystemUI entries become one finding rather
  than 12 duplicate cards.
- Unknown native crashes still appear generically with process, signal, abort/cause and top frame;
  a new reason does not need a hand-written rule to be visible.
- Historical entries are labelled as history and may predate the current issue.

## Caveats

- This is a tombstone-only sweep. The original logcat context for the October/early-November events
  has rotated out, so the trigger/workload for each event is unknown.
- `tombstone_07`'s app version is the version installed on 2026-11-17; the app may have been updated
  since 2026-11-08.
- The perceptionhost stack identifies the failing service and the deliberate abort, but not the
  underlying camera/IMU/calibration condition.
- The tombstones do not prove hardware health. They show what Android recorded; use `adb bugreport`,
  system updates and controlled re-tests for a full diagnosis.
- Raw tombstones are not committed. Only sanitized excerpts are included here.

## Suggested next steps

1. Treat the perceptionhost failures as a separate tracking-service issue; collect context if they
   recur.
2. Update/re-test Immersive View XR with and without foveation.
3. Keep the SystemUI HWUI report and this historical sweep separate: they are different signatures.
4. After the planned factory reset, collect a new GXR Manager > Diagnostics snapshot and compare whether
   any of these signatures return.
