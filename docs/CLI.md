# CLI reference

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

## Device selection

**No `--serial` is needed** once the headset is paired. The tool auto-selects a single device,
collapsing duplicate TCP and mDNS transports of the same headset. Pass `--serial <id>` or set
`ANDROID_SERIAL` only if multiple devices are connected.

## `record` flags

| Flag | Meaning |
|---|---|
| `--interval` | Core poll interval in seconds (default `1`) |
| `--cooldown <C>` | Wait until the selected sensor is at or below this temperature before starting |
| `--sensor <id>` | Cooldown sensor: `AP`, `CPU0..5`, `GPU0..7`, `nsp0..2`, `skin`, `WIFI`, `LRP`, `BAT`, `CHG`, `USB` (default `AP`) |
| `--cooldown-max-wait <s>` | Maximum cooldown wait; `0` waits indefinitely |
| `--notes <text>` | Attach notes to the run |
| `--root` | Read fan RPM/PWM and active panel via read-only `su -c` |
| `--process-io` | Per-process disk I/O; requires `--root` |
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
