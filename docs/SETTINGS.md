# Settings guide

[Back to README](../README.md) | [Commands](COMMANDS.md) | [Hidden/experimental research](HIDDEN_ADB_SETTINGS.md) | [Apps & services](APPS.md) | [Diagnostics](DIAGNOSTICS.md)

The **GXR Manager > Settings** tab contains grouped, reversible device settings that are not tied to a run.
Every row shows its current status, default label, persistence and any warning. Advanced and testing
sections are always shown. Press **Load settings** when ADB is ready; after the first load the button
becomes **Refresh**.

> Settings changes are optional writes to the headset. Recording, preview, diagnostics and report
> export remain read-only.

> **Recommended:** start with **Hide recording indicator (green dot)** under Privacy indicators.
> Several XR controls are experimental or marked **Test only**. Read the warning on each row before
> using it. The detailed command and research notes are in
> [Hidden and experimental ADB settings](HIDDEN_ADB_SETTINGS.md).

## XR controls

### Enable Android XR performance metrics

Shows the Android XR on-device performance metrics overlay.

Status read:
```sh
settings --user 0 get system toggle_xr_perf_metrics
```

Apply:
```sh
settings --user 0 put system toggle_xr_perf_metrics 1
```

Disable:
```sh
settings --user 0 put system toggle_xr_perf_metrics 0
```

**Turn this off when finished.** The overlay is static and can cause OLED burn-in if left on for long
periods. The app shows the warning on the row and reminds you after enabling it.

### Aiming method (`natural_input_mode`)

```sh
settings --user 0 get system natural_input_mode
settings --user 0 get system input_pointer
settings --user 0 put system natural_input_mode <value>
settings --user 0 put system input_pointer <value>
```

The firmware UI exposes three values:

| Value | Label |
|---:|---|
| `6` | Hand and eye aiming |
| `5` | Eye aiming only |
| `1` | Hand aiming only |

Hidden mode `7` is HMD fallback: head direction + touchpad click with no hand tracking. Enable it
with Volume Down + Volume Up + the headset action button. Set both `natural_input_mode` and
`input_pointer` to `7`. Changing this changes how you aim and select.

### Enable hands breakthrough

Shows your hands through content instead of only their outlines. The feature adds a small GPU cost
while it is active.

```sh
settings --user 0 get system toggle_hands_breakthrough
settings --user 0 put system toggle_hands_breakthrough 1
settings --user 0 put system toggle_hands_breakthrough 0
```

### Enable touch on everything

Enables direct hand touch/poke interaction with elements instead of requiring a gesture.

```sh
settings --user 0 get system enable_touch_on_everything
settings --user 0 put system enable_touch_on_everything 1
settings --user 0 put system enable_touch_on_everything 0
```

### Guardian safety boundary

`On` enables the boundary; `Off` disables it. Disabling the boundary opens a confirmation modal.

```sh
settings --user 0 get system toggle_guardian
settings --user 0 put system toggle_guardian 1
settings --user 0 put system toggle_guardian 0
```

Only disable the boundary in a clear, safe space. It is a safety feature, not just a display effect.

### Boundary size

Choose **Small** or **Large**.

```sh
settings --user 0 get system guardian_radius
settings --user 0 put system guardian_radius 0  # inferred: Small
settings --user 0 put system guardian_radius 1  # inferred: Large
```

The `0/1` mapping is inferred. The observed value on the reference headset was `1` (Large).

### Enable auto-spatialization preference

Turns on the saved Labs `auto_spatialization_settings` preference. This does not force every window
into 3D, change per-window choices, or bypass content/thermal restrictions.

Status read:
```sh
settings --user 0 get system auto_spatialization_settings
```

Apply:
```sh
settings --user 0 put system auto_spatialization_settings 1
```

Disable:
```sh
settings --user 0 put system auto_spatialization_settings 0
```

If the KernelSU auto-spatialization module is installed, it will set the preference back to `1` at
boot. Disable or remove that module before relying on this toggle.

## Privacy indicators

### Hide recording indicator (green dot)

Android shows a green dot when an app is using the microphone or camera. This setting hides that
indicator and keeps the change across reboots by disabling DeviceConfig syncing.

Status is read when you press **Load settings**, after each change, and when you press
**Refresh**. It is not polled continuously.

| Status | Meaning |
|---|---|
| **On** | Indicator hidden and DeviceConfig persistence enabled |
| **Off** | Indicator shown and DeviceConfig syncing normal |
| **Needs reapply** | Only part of the setting is applied; use **Reapply** |
| **Unknown** | The headset did not return a recognized value |

Android updates, resets or future builds may restore the dot. Open Settings and use **Reapply** if
the status becomes partial.

Commands:

```sh
cmd device_config get privacy camera_mic_icons_enabled
cmd device_config get_sync_disabled_for_tests
cmd device_config put privacy camera_mic_icons_enabled false default
cmd device_config set_sync_disabled_for_tests persistent
cmd device_config put privacy camera_mic_icons_enabled true default
cmd device_config set_sync_disabled_for_tests none
```

The `persistent` mode stops DeviceConfig from being overwritten and survives reboots. Returning it
to `none` may require a reboot before normal syncing resumes.

## Software updates

Samsung updates can replace the current build or patch the root exploit. These controls reduce
automatic update paths, but they also stop security updates. They do **not** remove an update that is
already downloaded or prepared, so check the headset's Software Update screen before rebooting if
retaining root matters.

Samsung does not fully document how its update packages divide the work. The package descriptions
below are inferred from package labels and observed behaviour.

### Disable Samsung update client (com.wssyncmldm)

```sh
pm list packages com.wssyncmldm
pm list packages -d com.wssyncmldm
pm disable-user --user 0 com.wssyncmldm
pm enable --user 0 com.wssyncmldm
```

### Disable Samsung update agent (com.sec.android.soagent)

```sh
pm list packages com.sec.android.soagent
pm list packages -d com.sec.android.soagent
pm disable-user --user 0 com.sec.android.soagent
pm enable --user 0 com.sec.android.soagent
```

### Disable automatic OTA scheduling

```sh
settings get global ota_disable_automatic_update
settings put global ota_disable_automatic_update 1
settings delete global ota_disable_automatic_update
```

Package settings show **On**, **Off**, **Not installed**, or **Unknown**.

## Advanced

### Disable child-process restrictions

```sh
settings --user 0 get global settings_enable_monitor_phantom_procs
settings --user 0 put global settings_enable_monitor_phantom_procs false
settings --user 0 delete global settings_enable_monitor_phantom_procs
```

This disables Android's phantom-process monitor restrictions on child processes. It helps apps that
spawn many child processes, such as Termux or emulators. It is not a general FPS tweak. Deleting the
key restores Android's default monitoring.

### Stay awake while charging

```sh
settings --user 0 get global stay_on_while_plugged_in
settings --user 0 put global stay_on_while_plugged_in 7
settings --user 0 put global stay_on_while_plugged_in 0
```

`7` is the bitmask for AC, USB and wireless charging. This matches the Android XR Engine Hub
"Stay awake while charging (even when doffed)" mode. It increases heat and OLED burn-in risk if left
on, so turn it off between sessions.

### Disable heads-up notifications

```sh
settings --user 0 get global heads_up_notifications_enabled
settings --user 0 put global heads_up_notifications_enabled 0
settings --user 0 put global heads_up_notifications_enabled 1
```

Notifications still appear in the notification shade; only the pop-up heads-up alerts are hidden.

### Disable always-on Wi-Fi/BLE scanning

```sh
settings --user 0 get global wifi_scan_always_enabled
settings --user 0 get global ble_scan_always_enabled

settings --user 0 put global wifi_scan_always_enabled 0
settings --user 0 put global ble_scan_always_enabled 0

settings --user 0 delete global wifi_scan_always_enabled
settings --user 0 delete global ble_scan_always_enabled
```

May affect location accuracy and nearby-device features. Reverting deletes the keys so Android can
restore its defaults.

## Testing - untested

These controls are exposed for local testing. Some may have no effect or unverified behavior on this
build.

### Disable performance optimization policy

Turns off Android XR's SurfaceFlinger app dynamic policy. The policy watches for jank, limits how many
apps stay open, and can background or close apps to recover performance. Disabling it removes that
intervention; it is not a guaranteed FPS boost and may let apps run past the system limit.

**Root required.** The `shell` ADB user cannot perform the SurfaceFlinger transaction or set the
persistent property.

Read:
```sh
getprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy
```

Disable policy:
```sh
su -c 'service call SurfaceFlinger 1044 i32 0'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy false'
```

Re-enable policy:
```sh
su -c 'service call SurfaceFlinger 1044 i32 1'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy true'
```

`false` means the policy is disabled and the Settings row shows **On**.

### Disable UI animations

```sh
settings --user 0 get global window_animation_scale
settings --user 0 get global transition_animation_scale
settings --user 0 get global animator_duration_scale

settings --user 0 put global window_animation_scale 0
settings --user 0 put global transition_animation_scale 0
settings --user 0 put global animator_duration_scale 0
```

Reverting deletes the three keys so Android restores its configured defaults:
```sh
settings --user 0 delete global window_animation_scale
settings --user 0 delete global transition_animation_scale
settings --user 0 delete global animator_duration_scale
```

This may have no visible effect on this build.

### Reduce transparency and window blur

```sh
settings --user 0 get global accessibility_reduce_transparency
settings --user 0 get global disable_window_blurs

settings --user 0 put global accessibility_reduce_transparency 1
settings --user 0 put global disable_window_blurs 1
```

Revert:
```sh
settings --user 0 delete global accessibility_reduce_transparency
settings --user 0 delete global disable_window_blurs
```

This may do nothing on this build.

### Disable Samsung Game Optimizing Service

```sh
pm list packages com.samsung.android.game.gos
pm list packages -d com.samsung.android.game.gos
pm disable-user --user 0 com.samsung.android.game.gos
pm enable --user 0 com.samsung.android.game.gos
```

Reversible, but unverified on Galaxy XR. It may change gaming/thermal behavior.

### Disable fixed Home Space Mode display rate

This is the firmware developer option of the same name. It calls SurfaceFlinger transaction `1043` and
clears the `fixed_hsm_display_rate` DeviceConfig flag.

Read:
```sh
getprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate
```

Disable the fixed rate:
```sh
su -c 'service call SurfaceFlinger 1043 i32 0'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate false'
```

Restore the fixed rate:
```sh
su -c 'service call SurfaceFlinger 1043 i32 1'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate true'
```

**Root required.** Untested on this headset; it may change refresh rate, frame pacing or power use.

## Defaults

| Setting | Default |
|---|---|
| Android XR performance metrics | **Off** |
| Aiming method | **Hand and eye aiming** |
| Hands breakthrough | **Off** |
| Touch on everything | **On** |
| Guardian safety boundary | **On** |
| Boundary size | **Unknown** (observed Large) |
| Auto-spatialization preference | **Off** |
| Hide recording indicator | **Off** (indicator shown) |
| Disable Samsung update client | **Off** (package enabled) |
| Disable Samsung update agent | **Off** (package enabled) |
| Disable automatic OTA scheduling | **Off** (automatic scheduling enabled) |
| Disable performance optimization policy | **Off** (policy active; requires root) |
| Disable child-process restrictions | **Off** |
| Stay awake while charging | **Off** |
| Disable heads-up notifications | **Off** |
| Disable always-on Wi-Fi/BLE scanning | **Unknown** |
| Disable UI animations (testing) | **Off** |
| Reduce transparency/window blur (testing) | **Off** |
| Disable Samsung Game Optimizing Service (testing) | **Off** |
| Disable fixed Home Space Mode display rate (testing) | **Off** (fixed rate active; requires root) |

## Persistence labels

Every setting row shows how long the change is expected to last:

| Label | Meaning |
|---|---|
| **Survives reboots** | Stored by Android PackageManager, SettingsProvider or DeviceConfig and survives a normal reboot |
| **Until reboot** | Runtime-only change; reapply after a reboot or root restart |
| **Requires module/service** | Needs a KernelSU module or background daemon, not a standalone setting |

The current Settings entries are persistent. Only **Disable performance optimization policy** and
**Disable fixed Home Space Mode display rate** require root; the rest need no root. KernelSU modules
that use sysfs, system properties, memory patches, debugfs or background daemons are intentionally not
represented as Settings toggles; they need their module/service after each rooted startup.

## Module-only features

These local KernelSU modules are not suitable replacements for Settings toggles:

- Fan control: needs a root daemon to hold `/sys/class/sec_fan/fan/step` away from SSRM.
- No low-light toast: sets a non-persistent SystemUI property read at class init.
- Mic gain boost: needs an event-driven audio daemon and affects the shared mic path.
- Passthrough Anywhere: needs a root daemon, logcat watcher and compositor access.
- Camera WebStream: needs a native root camera daemon.
- Display-off on eye loss: needs a root watcher and debugfs DSI commands.
- Hand-tracking toggle: live-patches `surfaceflinger` memory and resets on reboot.
- ADB port publisher: needs a root watcher to report the changing port.
- USB NCM/AOA: needs early boot/configfs/overlay handling.
- Xbox unknown-key recovery: needs a root input-event watcher.
- Window curvature: needs a Frida/agent/SystemUI integration.
- Face tracking relay: needs a root relay daemon.

## Safety

- Changes are blocked while a recording runs, require the local API token, and are appended to
  `reports/settings/setting-actions.jsonl`. Settings are not available in offline HTML reports.
  See [safety & fair runs](README.md#safety--fair-runs).
- Settings use normal shell commands; only the performance-policy and fixed Home Space Mode rate
  toggles require root, through `su -c`.
- Setting IDs are validated against built-in definitions; there are no free-form commands.
- Hiding the indicator does not change which apps can use the microphone or camera. It only hides
  the indicator.
- The performance overlay warning is not optional: turn it off when finished to avoid OLED burn-in.
- Disabling the guardian boundary is safety-related and requires confirmation.
- `passthrough_window_available`, `theater_mode_on` and `obtain_mute_when_off_body` are documented
  but not exposed in the UI.

## Troubleshooting

| Symptom | What to try |
|---|---|
| `no adb device` | Reconnect wireless ADB; see [device selection](CLI.md#device-selection). |
| Status is **Unknown** | Press **Refresh**. Check that the matching `settings get` command works in `adb shell`. |
| Status is **Needs reapply** | Press **Reapply** to set all required keys. |
| Dot returns after a reboot or update | Open Settings, check the status and reapply. |
| Change fails with an error | Android may have blocked the write in a newer build. The App/Diagnostics tabs remain usable. |
| XR control does nothing | The key is undocumented; check [Hidden and experimental ADB settings](HIDDEN_ADB_SETTINGS.md) and test one key at a time. |
