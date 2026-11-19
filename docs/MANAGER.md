# GXR Manager guide

[Documentation home](README.md) | [GXR Profiler](PROFILER.md) | [CLI](CLI.md#gxr-manager-cli) | [Apps & installer](APPS.md) | [Settings](SETTINGS.md) | [Diagnostics](DIAGNOSTICS.md)

**GXR Manager** is the device-tools app in [GXR Tools](../README.md). It opens its own local window
and handles everything that reads or changes headset state outside a recording. **GXR Profiler** stays
focused on recording, runs, comparison and reports.

## Tabs

| Tab | Purpose | Changes the headset? |
|---|---|---|
| [Diagnostics](DIAGNOSTICS.md) | Crash, boot/rescue, Dropbox, thermal and exit-info snapshots. | No |
| [Apps](APPS.md) | List packages, inspect details, run confirmed package actions and Game Mode overrides. | Yes, after confirmation |
| [Installer](APPS.md#installing-apks-and-obb-data) | Stage and install APK, OBB and XAPK files after command review. | Yes, after confirmation |
| [Settings](SETTINGS.md) | Reversible device settings, including advanced and testing-only keys. | Yes, after confirmation |

## When to use the manager

- After an unexpected restart, crash or hang: **Diagnostics**.
- To inspect, disable, remove, restore or uninstall a package: **Apps**.
- To apply a per-app FPS cap or render scale on a supported title: **Apps > package detail > Performance overrides**.
- To install or update an app: **Installer**.
- To change XR, display, update or testing settings: **Settings**.

Use **GXR Profiler** instead when you want a timed recording, a before/after comparison or a shareable
HTML report.

## Running both apps

Keep `gxr-profiler.exe`, `gxr-manager.exe` and their CLI companions in the same folder. The profiler
writes a small `recording.json` heartbeat while a run is active; the manager reads it and blocks
device-changing actions in Apps, Installer and Settings while the profiler records. The manager shows a
red banner while the profiler is recording.

Both apps use ADB independently. The manager handles device-changing actions; the profiler only reads
telemetry, so they can run together safely.

If you move one executable elsewhere, set `GXR_STATE_DIR` to a shared folder for both processes so
the recording lock still works.

## Device-change safety

- Apps, Installer and Settings only run after an explicit action in the local UI, with the local API
  token and a confirmation flag in the request.
- Every action is blocked while GXR Profiler is recording.
- Critical system packages cannot be installed over, disabled, removed for user 0 or uninstalled.
  Stock packages are removed for user 0 only; the system image is never edited.
- Package IDs and setting IDs are validated against built-in definitions. There are no free-form
  shell commands in the UI or API.
- Actions are appended to `reports/apps/app-actions.jsonl`; setting changes to
  `reports/settings/setting-actions.jsonl`. Neither file is included in exported HTML reports, and
  manager tools are not available in offline reports.
- Diagnostics is read-only. Root extras use `su -c` reads and may prompt.

See [Apps safety](APPS.md#safety), [Settings safety](SETTINGS.md#safety) and
[Diagnostics](DIAGNOSTICS.md) for tool-specific notes.

## Manager CLI

```powershell
gxr-manager-cli.exe ui        # open the manager UI
gxr-manager-cli.exe status    # devices + whether the profiler is recording
```

Device changes stay in the UI confirmation flow; they are intentionally not exposed as terminal
commands. See the [CLI reference](CLI.md#gxr-manager-cli).

## Detailed guides

- [Diagnostics](DIAGNOSTICS.md)
- [Apps, installer & services](APPS.md)
- [Settings](SETTINGS.md)
- [Hidden and experimental ADB settings](HIDDEN_ADB_SETTINGS.md)
- [Background processes & debloat](gxr-findings/debloat.md)
