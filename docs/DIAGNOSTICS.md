# Diagnostics guide

[Documentation home](README.md) | [Manager guide](MANAGER.md) | [Profiler](PROFILER.md) | [Commands](COMMANDS.md) | [Crash & soft-reboot log reference](gxr-findings/crash-logs.md)

The **GXR Manager > Diagnostics** tab is a one-click, read-only health snapshot for the headset. Use it after
an unexpected restart, a crash, a hang, or any time the headset behaves strangely and you want to know
what Android recorded.

It does not record continuously and does not create a run. Every snapshot is saved locally as JSON
and Markdown under `reports/debug/` next to the exe.

## When to use it

- The headset **soft-rebooted** (screen restarted but the device did not power off).
- An app **crashed**, froze, or disappeared.
- Tracking, passthrough, or the UI started behaving oddly.
- You want to check whether the headset is in a **rescue / boot-loop** state.
- You are about to report a problem and need evidence.

Collect soon after the event. Android's logcat buffers are rings and can rotate quickly. Dropbox and
tombstones often survive longer, but they are not guaranteed.

## Quick start

1. Connect the headset over ADB. The UI needs a single paired device, or pass `--serial`.
2. Open **GXR Manager**, then **Diagnostics**.
3. Choose the options you need:
   - **Root extras** - asks `su` for data that normal shell cannot read. It may prompt.
   - **Read tombstone / ANR files** - reads recent native crash and ANR files. Requires root.
   - **Kernel log / pstore** - reads `dmesg`, `last_kmsg`, and the pstore listing. Requires root.
   - **Log lines per buffer** - how much recent logcat to include. The default is 1500; higher values
     capture more history but make the saved report larger.
4. Press **Collect snapshot**.
5. Wait for the status badge to change from `running` to `done`. A normal unrooted snapshot takes a
   few seconds; root and tombstone reads can take longer.
6. Read **Findings** first. Expand **Raw sections** only when you need the original log lines.

## What the cards mean

### Findings

Plain-language issues ordered by severity:

| Severity | Meaning |
|---|---|
| **Critical** | Strong evidence of a crash, rescue escalation, or a known serious signature. Act on it first. |
| **Warning** | A crash/ANR or suspicious condition that needs investigation. |
| **Info** | Useful context, or a historical record. It may not be related to the current problem. |
| **OK** | No recognized crash signature was found in the collected data. |

The analyzer is conservative. It can say "this is a native crash in process X" without claiming why
it crashed. A new crash reason is still shown with its process, signal, abort message, and stack; it
does not need a special rule in the code.

### Crashes

Crash blocks found in the current logcat crash buffer or Dropbox. Each item shows the process, native
or Java/ANR type, signal, abort/cause, and the top frames. Expand it for the full captured excerpt.

### Tombstones (history)

Recent files from `/data/tombstones` when root/tombstone reading is enabled. This is the best source
for crashes that have already rotated out of logcat. The current build reads the newest 20 text
tombstones and the first part of each file, which is enough for the process, signal, abort message
and backtrace.

Historical entries may be days or weeks old. Always check the timestamp and tombstone file name
before treating one as the cause of the current problem.

Known signatures get a dedicated title, explanation and next step in the expanded entry. Current
examples include the SystemUI HWUI animation race, the perception head-tracking initialisation
failure, and the Immersive View XR Vulkan/foveation crash. Unknown native crashes still show their
process, signal, abort/cause and top frames.

### Process exits (history)

The latest 20 ActivityManager exit records. This is useful for **silent** failures that do not leave
a normal crash block, especially:

- `APP CRASH(NATIVE)` / `APP CRASH(JAVA)`
- `ANR`
- `LOW_MEMORY`

Some of these records can be old. The latest records are shown first.

### Boot & rescue

Shows the current boot reason, the previous reason, RescueParty boot count, mitigation state, and
recent `rescue_note` events. A rescue/warm-boot state can come from a crash loop, or from the
DFroot/KernelSU soft reboot used to initialise root. Check the timestamp and the crash entries to
tell them apart.

### Thermal context

Current thermal status, AP/WIFI/LRP temperatures, fan step, battery, DDR and GPU values. These are
**context**, not proof that heat caused a crash. A hot headset can still have a software crash, and
a cool headset can still have a kernel fault.

### Root evidence

Shows whether root was available and whether tombstone, Dropbox, ANR, dmesg and watchdog paths were
readable. KernelSU does not guarantee access: its SELinux context may be denied on some paths. The
snapshot reports the denial instead of failing the whole collection.

### Raw sections

The untrimmed captured text for crash, events, system, main, Dropbox, exit-info, dmesg, pstore and
other root sections. Use this when a finding needs the exact surrounding lines.

## What is picked up automatically

The snapshot currently looks for:

- Native crashes in `logcat -b crash` (`F DEBUG`, `Fatal signal`, abort message, backtrace).
- Java crashes and ANRs in the main/system logs and events (`am_crash`, `am_anr`).
- Dropbox crash, tombstone, system_server and app crash/ANR tags.
- Tombstone files and ANR files when root reading is enabled.
- ActivityManager exit records, including silent low-memory app kills.
- RescueParty/boot-loop state and recent rescue notes.
- High-signal system/watchdog/low-memory lines in the system and main buffers.
- Kernel panic/GPU/OOM/watchdog lines when **Kernel log / pstore** is enabled.
- Known signatures with a richer explanation:
  - SystemUI HWUI animation race.
  - Perception head-tracking initialisation failure
    (`android.hardware.perceptionhost`, `MotionTrackingAdapter`).
  - Immersive View XR Vulkan/foveation crash
    (`com.google.android.apps.immersiveviewxr`, `libVkLayer_android_foveation`).
- Thermal and power context.

A **new** native crash process is shown as a generic native crash with its stack. It will not be
misclassified as the known SystemUI issue just because it is also a native crash.

## What it cannot pick up

- **Kernel faults without root** - `dmesg` and pstore are root-only. Without root, a silent kernel
  issue may leave no evidence in the normal logcat buffers.
- **Anything that left no record** - if an app/service crashes without a tombstone, Dropbox entry,
  exit record, or log line, the snapshot has nothing to show.
- **Very old logcat** - the buffers rotate. Use tombstone history, Dropbox, or `adb bugreport` for
  older events.
- **Full tombstones** - the snapshot keeps the first 30 KB of each recent tombstone. Use
  `adb bugreport` or read the file directly for the complete tombstone.
- **Root-denied paths** - if SELinux denies `/data/tombstones` or `/data/system/dropbox`, the UI
  reports the denial. Try `adb bugreport` or a root file manager with a suitable context.
- **Hardware health** - this is a log snapshot, not a hardware diagnostic. It cannot prove the
  battery, power rails, memory, or SoC are healthy.

## Saved reports and privacy

Each collection writes:

```text
reports/debug/diagnostics-<timestamp>.json
reports/debug/diagnostics-<timestamp>.md
```

The JSON contains the parsed findings, crashes, history and raw sections. The Markdown is a short
human-readable summary. **Download JSON** uses the in-memory snapshot.

These files are local and are not redacted like the shareable HTML run reports. Check the raw log
sections for account names, package names, device identifiers, or other personal data before
sharing. Prefer the Markdown summary plus the relevant finding excerpts for a bug report.

## Troubleshooting

| Symptom | What to try |
|---|---|
| `no adb device` | Reconnect wireless ADB; see [device selection](CLI.md#device-selection). |
| `su` prompt or root unavailable | Re-enable DFroot/KernelSU, then collect again. |
| Tombstones say `Permission denied` | Use **Root extras**, or collect `adb bugreport` and inspect its tombstone section. |
| No crashes found | The crash may have rotated; enable tombstone reading and check Dropbox/exit history. |
| Everything is historical | Check the timestamps in the cards. Collect immediately after the next event. |
| Thermal values look high | Treat them as context, not a cause. Check the crash stack and boot reason first. |
| Rescue count keeps rising | Avoid repeated reproduction; the rescue path can escalate to settings resets. |
| Snapshot takes a long time | Root/tombstone/dmesg reads are slower. Reduce log lines or disable root extras. |

## For deeper analysis

- [Crash & soft-reboot log reference](gxr-findings/crash-logs.md) - exact buffers, fields, commands and
  known signatures.
- [2026-11-17 SystemUI HWUI investigation](gxr-findings/reports/soft-reboots/2026-11-17-systemui-hwui-beatsaber.md) -
  a worked example involving Beat Saber.
- [Every headset command](COMMANDS.md) - the Diagnostics commands and cadences.
