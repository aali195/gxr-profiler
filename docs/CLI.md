# CLI reference

[Back to README](../README.md) | [Development](DEVELOPMENT.md) | [Commands](COMMANDS.md)

The CLI is available as `gxr-profiler-cli.exe` in the release, as `gxr-profiler` after
`pip install -e .`, or as `python -m gxr_profiler` from a source checkout.

## Commands

```powershell
# packaged app: double-click gxr-profiler.exe, or:
gxr-profiler-cli.exe ui

# installed command / source checkout
gxr-profiler ui
gxr-profiler ui --browser

# record runs
gxr-profiler record --name before --duration 900 --cooldown 37
gxr-profiler record --name after  --duration 900 --cooldown 37

# compare runs -> reports/before_vs_after.html next to the exe
gxr-profiler report before after

gxr-profiler runs
gxr-profiler devices
```

With an editable install use `gxr-profiler`; without installing use
`python -m gxr_profiler ...`.

## Manager CLI

The device-tools app has its own small CLI:

```powershell
gxr-manager-cli.exe ui        # open the manager UI
gxr-manager-cli.exe status    # devices + whether the profiler is recording
```

The manager UI commands are intentionally not exposed as terminal actions; device changes
still require the local UI confirmation flow.

## Device selection

**No `--serial` is needed** once the headset is paired. The tool auto-selects a single device,
collapsing duplicate TCP and mDNS transports of the same headset. Pass `--serial <id>` or set
`ANDROID_SERIAL` only if multiple devices are connected. The adb executable is taken from `ADB`, then `adb(.exe)` next to the executable, then `platform-tools/adb(.exe)`, then `PATH`. After a wireless ADB reconnect, `record` waits up to 30 seconds for the headset to return to the `device` state (5-second polling).

## `record` flags

| Flag | Meaning |
|---|---|
| `--interval` | Core poll interval in seconds (default `1`) |
| `--cooldown <C>` | Wait until the selected sensor is at or below this temperature before starting |
| `--sensor <id>` | Cooldown sensor: `AP`, `CPU0..5`, `GPU0..7`, `nsp0..2`, `skin`, `WIFI`, `LRP`, `BAT`, `CHG`, `USB`, `DDR` (default `AP`) |
| `--cooldown-max-wait <s>` | Maximum cooldown wait; `0` waits indefinitely |
| `--notes <text>` | Attach notes to the run |
| `--root` | Read fan RPM/PWM, active panel and calibration metadata via read-only `su -c` |
| `--process-io` | Per-process disk I/O; requires `--root` and process sampling |
| `--sensors` / `--sensors-interval` | Enable the SensorService summary and set its cadence |
| `--processes` / `--no-processes` | Capture all non-kernel processes (default on) |
| `--processes-interval` | Process snapshot cadence |
| `--processes-top <N>` | Cap the process list; `0` captures all |
| `--processes-kernel` | Include kernel threads |
| `--media-interval` | Media/audio/display cadence |
| `--state-interval` | Battery/Wi-Fi/thermal state cadence |
| `--radio-interval` | Bluetooth/location/storage-capacity cadence |
| `--no-logcat` | Disable the logcat event stream |

Ctrl-C stops a recording cleanly. Media/audio/display is sampled every 30 s by default.
Run `gxr-profiler <command> --help` for the complete current flag list.

## Capture profiles

The UI exposes Standard, Detailed and Everything presets plus per-option overrides. Profile
defaults, cadence details and measured overhead are documented in
[capture profiles & overhead](README.md#capture-profiles--overhead).


