# CLI reference

[Documentation home](README.md) | [Profiler guide](PROFILER.md) | [Manager guide](MANAGER.md) | [Commands](COMMANDS.md)

GXR Tools ships two terminal builds: `gxr-profiler-cli.exe` and `gxr-manager-cli.exe`. After
`pip install -e .` the commands are `gxr-profiler` and `gxr-manager`.

## GXR Profiler CLI

From a source checkout without installing:

```powershell
python -m gxr_tools.profiler --help
```

### Commands

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

### `record` flags

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

Ctrl-C stops a recording cleanly. Media/audio/display is sampled every 30 s by default. Run
`gxr-profiler <command> --help` for the complete current flag list.

### Capture profiles

The UI exposes Standard, Detailed and Everything presets plus per-option overrides. Profile
defaults, cadence details and measured overhead are documented in
[capture profiles & overhead](PROFILER.md#capture-profiles--overhead).

## GXR Manager CLI

The manager has a small CLI for opening the UI and checking the connection state:

```powershell
gxr-manager-cli.exe ui        # open the manager UI
gxr-manager-cli.exe status    # devices + whether the profiler is recording
```

From a source checkout: `python -m gxr_tools.manager.cli.app ui` or
`python -m gxr_tools.manager.cli.app status`.

The manager UI commands are intentionally not exposed as terminal actions; device changes still
require the local UI confirmation flow. See [device-change safety](MANAGER.md#device-change-safety).

## Device selection

**No `--serial` is needed** once the headset is paired. Both apps auto-select a single device,
collapsing duplicate TCP and mDNS transports of the same headset. Pass `--serial <id>` or set
`ANDROID_SERIAL` only if multiple devices are connected. The adb executable is taken from `ADB`, then
`adb(.exe)` next to the executable, then `platform-tools/adb(.exe)`, then `PATH`. After a wireless ADB
reconnect, `record` waits up to 30 seconds for the headset to return to the `device` state (5-second
polling).
