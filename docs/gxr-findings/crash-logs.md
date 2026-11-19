# Crash, soft-reboot & error logs

[Findings index](README.md#findings-index) | [Profiler guide](../PROFILER.md) | [Diagnostics guide](../DIAGNOSTICS.md) | [Commands](../COMMANDS.md) | [Thermal, throttling & fan](thermal.md) | [Soft-reboot report](reports/soft-reboots/2026-11-17-systemui-hwui-beatsaber.md)

> **Hardware state: MIXED.** Log format is device-wide. The first recorded crash investigation
> (2026-11-17) was on the SoC thermal-modded headset; it was not a thermal event.

How the SM-I610 reports native crashes, Java crashes, ANRs, framework soft reboots and Android
RescueParty state. This is the reference page for the **GXR Manager > Diagnostics** view and for reading a capture
after a reboot.

## In plain terms

- A **native crash** appears in the `crash` logcat buffer as an `F DEBUG` block with a process
  name, signal, abort message and backtrace. `logcat -b crash` is the first place to look.
- A **java/ANR** event appears as `FATAL EXCEPTION` / `ANR in` in the app's log, and as
  `am_crash` / `am_anr` in the `events` buffer.
- A **framework soft reboot** restarts `system_server` while the kernel keeps running. Look for a
  new `system_server` PID and `boot_progress_*` lines while `/proc/uptime` continues.
- A **kernel reboot/panic** resets uptime; use `sys.boot.reason`, `ro.boot.bootreason`, `dmesg`
  (root) and `/proc/last_kmsg` / pstore if available.
- **Do not trust one source.** `dumpsys dropbox` can be empty, `exit-info` can miss native SystemUI
  crashes, and `/data/tombstones` can be blocked even with KernelSU root.
- **Thermal is context, not proof.** A hot headset at thermal status 3 can still have a software
  crash. Keep the temperature evidence separate from the crash stack.

## Tests & results

Probed from logcat, dropbox, exit-info and thermal polling during the 2026-11-17 Beat Saber
soft-reboot investigation.

| Probe | What it showed | Caveat |
|---|---|---|
| `logcat -d -b crash -v time` | Full SystemUI `F DEBUG` blocks with `Cmdline`, signal, abort message and backtrace | Ring buffer only; collect soon after the event |
| `logcat -d -b events -v time` | `rescue_note`, `boot_progress_*`, `am_crash`, `am_anr`, `am_proc_died` | Event values are compact; look up tags in AOSP |
| `logcat -d -b system -v time` | `SystemServer`, `SYSTEM_SERVER_START`, boot phases, SystemUI death/restart | Large; use `-t` and filter |
| `logcat -d -b main -v time` | App/runtime logs such as `AndroidRuntime`, `ActivityManager`, `PackageWatchdog` | Very large; use `-t` and keywords |
| `dumpsys dropbox --print` | `SYSTEM_RESTART`; may include `system_server_crash`, `SYSTEM_TOMBSTONE`, `data_app_crash` | This unit only had 8 entries and no crash entries |
| `dumpsys activity exit-info` | Historical process exits with `reason=...` / `subreason=...` | It did **not** list the SystemUI native crashes |
| `/data/tombstones` | Native tombstone files, usually written by `crash_dump64` | Root/SELinux can block; see below |
| `/data/system/dropbox` | Persisted dropbox files | Root/SELinux can block; same data as `dumpsys dropbox` |
| `/data/anr` | ANR traces | Root-only; one old ANR existed, none for the crashes |
| `getprop` boot/rescue keys | Boot reason, RescueParty count, mitigation state | Does not identify a user-initiated reboot by itself |
| `dumpsys thermalservice` + battery | AP/WIFI/LRP, status, battery, fan context | Correlation only, not a crash source |

## Findings

### Native crash block

A native crash is written by `debuggerd`/`crash_dump64` into the `crash` buffer. The useful fields
are:

```text
F DEBUG   : *** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
F DEBUG   : Timestamp: 2026-11-17 00:41:47.751068593+0000
F DEBUG   : Process uptime: 1860s
F DEBUG   : Cmdline: com.android.systemui
F DEBUG   : pid: 11754, tid: 11754, name: ndroid.systemui  >>> com.android.systemui <<<
F DEBUG   : signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------
F DEBUG   : Abort message: 'sp<> assignment detected data race'
F DEBUG   : backtrace:
F DEBUG   :       #00 pc ... /apex/com.android.runtime/lib64/bionic/libc.so (abort+168)
F DEBUG   :       #05 pc ... /system/lib64/libhwui.so (PropertyValuesAnimatorSet::start(...)+160)
```

Key fields:

- `Cmdline` — the crashing process. This is more useful than the logcat tag.
- `pid`/`tid`/`name` — process and crashing thread; the thread name is often the subsystem.
- `signal` — `SIGABRT` is an intentional abort, often from a CHECK/assert. `SIGSEGV` is a memory
  fault. `SIGILL`/`SIGBUS` are also possible.
- `Abort message` — the exact assertion. `sp<> assignment detected data race` is libutils
  detecting two threads racing on a strong pointer; it is a software race, not a thermal event.
- `Cause` — for `SIGSEGV`, e.g. `null pointer dereference`.
- `backtrace` — the first few frames identify the library and function. The top frame is not always
  the root cause; use the whole stack.

`Fatal signal ...` lines from `libc` usually appear immediately before the `F DEBUG` block. The
`F DEBUG` block is the readable one.

### Java crash and ANR

Java crashes appear as `E AndroidRuntime` lines with `FATAL EXCEPTION` and a `Process:` line, and
as `am_crash` in the events buffer. ANRs appear as `ANR in <package>` in the main/system buffers
and as `am_anr` in `events`.

A Java/ANR crash is linked to an app process. A native `F DEBUG` block can come from a system
process or native service and does not necessarily produce a Java stack.

### Framework soft reboot vs kernel reboot

A **framework soft reboot** restarts `system_server` while the kernel (and often SurfaceFlinger,
perception and other native services) keeps running:

- `/proc/uptime` **continues increasing**.
- A new `system_server` PID appears.
- `boot_progress_start`, `boot_progress_system_run`, `boot_progress_enable_screen` appear again.
- `logcat` may disconnect/reconnect even though the device did not power-cycle.
- `sys.boot.reason` can be `reboot,rescueparty_warm_reboot`; `ro.boot.bootreason` may still show the
  previous kernel-boot reason.

A **full kernel reboot** resets `/proc/uptime`; `crash_dump64` and tombstones may be lost from the
current buffers. Use `sys.boot.reason`, `ro.boot.bootreason`, pstore/last_kmsg and boot-phase logs
to separate them.

### RescueParty and the boot counter

`PackageWatchdog.noteBoot()` increments `sys.rescue_boot_count` and writes an event:

```text
rescue_note: [0,2,79837]
```

The fields are `uid, boot_count, window_ms` (`EventLogTags.writeRescueNote(ROOT_UID, count, window)`).
The count is the number of system_server boots inside the rolling window, not the rescue level.
At the AOSP default, five system_server boots in ten minutes triggers boot-loop mitigation; the
rescue levels then escalate through settings resets and eventually a warm reboot/factory-reset
prompt.

Related keys:

```text
sys.boot.reason                  # reason for the current framework boot
sys.boot.reason.last             # previous framework boot reason
ro.boot.bootreason               # bootloader reason for the current kernel boot
sys.rescue_boot_count            # system_server boots in the current window
sys.rescue_boot_start            # window start (uptime ms)
sys.boot_mitigation_count        # boot-loop mitigation attempts
sys.boot_mitigation_start        # mitigation window start
sys.max_rescue_level_attempted   # highest rescue level applied
sys.attempting_reboot            # set while a rescue reboot is being requested
sys.attempting_factory_reset     # set while a factory reset is being requested
persist.sys.last_factory_reset   # last factory-reset request time
```

**Important:** A DFroot/KernelSU "soft reboot to initialise root" can also change these values and
produce a `rescueparty_warm_reboot`-style boot reason. Do not call every rescue note a bug. Compare
timestamps with the user's root routine and with actual crash blocks.

### Dropbox, tombstones and exit-info

- `dumpsys dropbox --print` lists `SYSTEM_RESTART` and, if present, crash/ANR/tombstone tags. On
  the morning of the 2026-11-17 crashes it still had only 8 entries, but by the later Diagnostics
  probe it held `SYSTEM_TOMBSTONE` at 00:41:49 and `SYSTEM_RESTART` at 00:42:20 and 00:52:03.
  Dropbox can lag the crash or rotate; do not treat an empty first read as conclusive.
- `/data/system/dropbox` holds the persisted files. It is normally `system:system 0700`; the
  KernelSU root context may receive `Permission denied` on some commands.
- `/data/tombstones` holds native tombstones. `crash_dump64` may run seconds after the crash; the
  file is not instantly visible. On this unit the first manual `su -c ls` was denied, but a later
  root probe read `tombstone_13` / `tombstone_14` and Dropbox held the first `SYSTEM_TOMBSTONE`.
  Treat root access as best-effort, not a guarantee.
- `NativeTombstoneManager` ignores tombstones with invalid SELinux labels and tombstones whose UID
  is 1000, so a native system-process crash may never appear in Dropbox.
- `dumpsys activity exit-info` is useful for app crashes (`reason=5 (APP CRASH(NATIVE))`,
  `reason=6 (ANR)`, `reason=2 (SIGNALED)`, `reason=3 (LOW_MEMORY)`), but it did not record the
  SystemUI native crashes here.
- If root cannot read tombstone/dropbox paths, try `adb bugreport` (which runs `dumpstate` with
  broader privileges) or read the files with a root file manager. Do **not** use `logcat -c`,
  `setprop`, or any write as a workaround.

### Thermal context

Keep thermal and power readings separate from crash classification:

- The 2026-11-17 SystemUI crashes happened at AP ~74-75 C, WIFI ~78 C, LRP ~61-62 C, thermal
  status 3, fan 7. The device was hot, but the stack is a software race in `libhwui`, not a
  thermal shutdown.
- Thermal status 3, fan 7 and WIFI/DDR being hottest are expected post-mod behaviour under heavy
  VR loads. They do not explain an `sp<>` race.

## Details

### Quick triage after a reboot

```sh
# 1. Was it a framework restart or a kernel reboot?
adb shell 'date; cat /proc/uptime; getprop sys.boot.reason; getprop sys.boot.reason.last; \
getprop ro.boot.bootreason; getprop sys.rescue_boot_count; getprop sys.boot_mitigation_count'

# 2. Native and Java crashes
adb shell 'logcat -d -b crash -v time -t 2000'

# 3. Boot and rescue events
adb shell 'logcat -d -b events -v time -t 2000 | grep -E "rescue_note|boot_progress|am_crash|am_anr|am_proc_died"'

# 4. System and app context
adb shell 'logcat -d -b system -v time -t 1500 | grep -iE "system_server|SystemUI|Watchdog|PackageWatchdog|RescueParty|fatal|died"'
adb shell 'logcat -d -b main -v time -t 1500 | grep -iE "FATAL EXCEPTION|AndroidRuntime|ANR in|systemui|watchdog|rescue"'

# 5. Dropbox and process exits
adb shell 'dumpsys dropbox --print'
adb shell 'dumpsys activity exit-info'

# 6. Root-only context, if available
adb shell su -c 'ls -lt /data/tombstones | head; ls -lt /data/system/dropbox | head; ls -lt /data/anr | head'
adb shell su -c 'dmesg | tail -500'
```

### Reading a native crash

1. Open the newest `F DEBUG` block in `logcat -b crash`.
2. Record `Cmdline`, `pid/tid/name`, `signal`, `Abort message`/`Cause` and the first 10-15 frames.
3. Match the process against the workload: SystemUI, SurfaceFlinger, perceptionflinger, camera,
   media/codec, a HAL, or the app.
4. Look for the same signature in the other buffer (e.g. `ActivityManager: Process ... has died`,
   `StatusBarManagerService: binder died`, `Scheduling restart of crashed service`).
5. Check whether `system_server` restarted; if so, it was a framework soft reboot.
6. Only then look at temperatures/power and note them as context.

### Known signatures

| Signature | What it means | Typical next step |
|---|---|---|
| `Abort message: 'sp<> assignment detected data race'` + `libhwui` `PropertyValuesAnimatorSet` | Android HWUI animation refcount race; software | Check for a SystemUI/system update; avoid the overlay trigger; report the stack |
| `AnimationContextBridge::startFrame` SIGSEGV in `libhwui` | Same animation subsystem, null/dead animator state | Same as above |
| `Process com.android.systemui ... has died: pers PER` | SystemUI died; framework may schedule its service restart | Check whether system_server also restarted |
| `rescue_note` / `sys.rescue_boot_count` | Boot-loop/rescue accounting | Compare with DFroot routine and crash timestamps |
| `Fatal signal 11` in `kgsl` / GPU driver | GPU fault | Check `dmesg`, GPU clock/busy, app workload |
| `ANR in` / `am_anr` | App main thread blocked | Read ANR trace and blocking binder/syscall |
| `Kernel panic` / `BUG:` / `watchdog` in `dmesg` | Kernel fault | Full reboot/pstore; not a framework-only issue |
| `avc: denied` | SELinux denial | Check the source/target context; do not weaken SELinux as a first step |

### Observed historical set

The 2026-11-17 Diagnostics sweep of the 15 retained tombstones (2026-10-18 to 2026-11-17) found:

- 12 SystemUI HWUI animation-race tombstones.
- 2 `android.hardware.perceptionhost` SIGABRTs, both reporting
  `Head tracking failed to initialize the internal MotionTrackingAdapter component.`
- 1 `com.google.android.apps.immersiveviewxr` SIGSEGV.

The perceptionhost and immersiveviewxr crashes are separate signatures. GXR Manager > Diagnostics now
gives each one a dedicated title, explanation and next step, and still falls back to a generic
native crash entry for unknown processes. See the
[historical tombstone sweep](reports/soft-reboots/2026-11-17-historical-tombstones.md).

## Caveats

- The logcat buffers are ring buffers. A busy device can rotate the crash out quickly. Collect
  immediately after a reboot; GXR Manager > Diagnostics is a snapshot, not a permanent recorder.
- The `crash` buffer can contain duplicate blocks after a logcat reconnect because a new `-b all`
  dump starts from the whole buffer.
- `dumpsys dropbox` may be empty or incomplete. `exit-info` may not include system-process native
  crashes. Absence of evidence in one source is not absence of a crash.
- KernelSU root is not the same as an `adb root`/system context. Expect SELinux denials on
  `/data/tombstones` and `/data/system/dropbox`.
- A DFroot soft reboot and a crash-triggered rescue reboot can both look like a warm boot. Use
  timestamps, the user's root routine and the crash blocks to tell them apart.
- Two crashes are not a statistical sample. The 2026-11-17 report shows a repeatable signature, not
  a proven rate or a complete list of triggers.

## Useful next experiments

1. Repeat a soft reboot with bright, even room lighting and compare the SystemUI overlay/animation
   activity; the dim-room correlation is suggestive, not proven.
2. Capture a tombstone via `adb bugreport` or a root context that can read `/data/tombstones` and
   compare it with the `F DEBUG` block.
3. After the planned factory reset, repeat the same Beat Saber workload and collect a Diagnostics
   snapshot; compare crash signature, boot reason and rescue counts.
4. Check whether a newer SystemUI/system build changes the `libhwui` stack before attributing it to
   the headset hardware.
