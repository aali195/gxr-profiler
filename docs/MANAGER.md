# GXR Manager guide

[Back to README](../README.md) | [Apps & installer](APPS.md) | [Settings](SETTINGS.md) | [Diagnostics](DIAGNOSTICS.md)

**GXR Manager** is the device-tools companion to **GXR Profiler**. It opens its own local window and
provides four tabs:

| Tab | Purpose |
|---|---|
| Diagnostics | Read-only crash, boot/rescue, Dropbox, thermal and exit-info snapshots. |
| Apps | List packages, inspect details and perform confirmed package actions or Game Mode overrides. |
| Installer | Stage and install APK, OBB and XAPK files after command review. |
| Settings | Reversible device settings, including advanced/testing keys. |

The profiler remains focused on recording, runs, comparison and HTML reports. It is read-only on the
device.

## Running both apps

Keep `gxr-profiler.exe`, `gxr-manager.exe` and their CLI companions in the same folder. The profiler
writes a small `recording.json` heartbeat while a run is active; the manager reads it and blocks
device-changing actions in Apps, Installer and Settings while the profiler records. The manager shows a
red banner while the profiler is recording.

Both apps use ADB independently. The manager handles device-changing actions; the profiler only reads
telemetry, so they can run together safely.

If you move one executable elsewhere, set `GXR_STATE_DIR` to a shared folder for both processes so
the recording lock still works.

## Detailed guides

- [Apps, installer & services guide](APPS.md)
- [Settings](SETTINGS.md)
- [Diagnostics](DIAGNOSTICS.md)
- [Background processes & debloat](gxr-findings/debloat.md)
