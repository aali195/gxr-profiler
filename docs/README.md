# GXR Tools documentation

[Back to project README](../README.md)

GXR Tools is two apps over one shared core. Start with the app you need.

| | **GXR Profiler** | **GXR Manager** |
|---|---|---|
| Purpose | Record, preview, compare and export runs. | Diagnose, install and change device settings. |
| Device access | Read-only. | Changes the headset only after confirmation. |
| GUI | `gxr-profiler.exe` | `gxr-manager.exe` |
| CLI | `gxr-profiler-cli.exe` | `gxr-manager-cli.exe` |
| Guide | [Profiler guide](PROFILER.md) | [Manager guide](MANAGER.md) |

## GXR Profiler

- [Profiler guide](PROFILER.md) - capture profiles, output/schema, data sources, safety and fair runs.
- [CLI: profiler](CLI.md#gxr-profiler-cli) - `ui`, `record`, `report`, `runs`, `devices`.
- [Capture commands and polling cadence](COMMANDS.md)
- [Research & findings](gxr-findings/README.md) - measurements, thermal-mod comparisons and crash investigations.

## GXR Manager

- [Manager guide](MANAGER.md) - tabs, recording lock and device-change safety.
- [Diagnostics](DIAGNOSTICS.md) - crash, soft-reboot, boot/rescue and thermal snapshots.
- [Apps, installer & services](APPS.md) - package actions, Game Mode overrides, APK/OBB/XAPK installs.
- [Settings](SETTINGS.md) - reversible device settings exposed in the app.
- [Hidden and experimental ADB settings](HIDDEN_ADB_SETTINGS.md) - research notes and unexposed keys.
- [CLI: manager](CLI.md#gxr-manager-cli) - `ui` and `status`.

## Shared reference

- [Development, tests and packaging](DEVELOPMENT.md)
- [CLI reference](CLI.md) - profiler and manager CLIs, plus device selection.
- [Examples](examples/README.md) - sanitized snippets and device quirks.
- [Exported reports](gxr-findings/reports/README.md) - thermal-mod and soft-reboot investigations.

## Safety at a glance

- **GXR Profiler** is read-only: recording, preview and export use `cat`, `getprop`, `dumpsys`,
  `logcat` and `ps`. `--root` adds read-only `su -c` reads. See
  [profiler safety](PROFILER.md#safety--fair-runs).
- **GXR Manager** only changes the headset after an explicit confirmation in the local UI and with the
  local API token. Actions are blocked while the profiler records. See
  [device-change safety](MANAGER.md#device-change-safety).
