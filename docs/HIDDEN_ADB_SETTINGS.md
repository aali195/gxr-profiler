# Hidden and experimental ADB settings

[Back to README](../README.md) | [Settings guide](SETTINGS.md) | [Commands](COMMANDS.md)

This page records hidden Android XR settings found on the **Samsung Galaxy XR (SM-I610)**, including
settings exposed in **Tools > Settings** and candidates that are deliberately not exposed. It is a
research document, not a promise that every key works on every firmware.

> **Status:** most values here are **untested**. The only operations performed while compiling this
> page were read-only: `settings list`, `settings get`, package queries and APK/resource inspection.
> No setting was changed on the headset.

## Device and method

- Device: Samsung Galaxy XR, `SM-I610`
- Android 14 / SDK 34
- Build: `UML2.260301.001.I610UEU2AZF3`
- Discovered with:

```sh
adb shell settings list system
adb shell settings list secure
adb shell settings list global
adb shell settings get <system|secure|global> <key>
adb shell pm list packages
```

The firmware's Settings app (`/system_ext/priv-app/SecSettings/SecSettings.apk`) and XR SystemUI
(`/system_ext/priv-app/XrSystemUI/XrSystemUI.apk`) were also inspected read-only to recover labels,
preference keys and command relationships.

No serials, Bluetooth addresses, account IDs, Wi-Fi names or other personal identifiers are recorded
here.

## Legend

| Label | Meaning |
|---|---|
| **Exposed** | Appears in **Tools > Settings**. |
| **Documented only** | Recorded here but not exposed in the app. |
| **Observed** | Value read from this build during the read-only pass. |
| **Inferred** | Behavior or numeric mapping inferred from labels/code, not verified by changing it. |
| **Untested** | No write was performed; expect possible differences or resets. |
| **Persistent** | Stored in Android SettingsProvider and normally survives a reboot. |

The generic manual form is `adb shell settings --user 0 <get|put|delete> <namespace> <key> [value]`.
The app uses the same command without the leading `adb shell`.

## Exposed in Tools > Settings

### XR controls

| Setting | Key | Observed | Status |
|---|---|---:|---|
| Android XR performance metrics | `toggle_xr_perf_metrics` | `0` | Documented by Google; write untested |
| Hands breakthrough | `toggle_hands_breakthrough` | `0` | Small GPU cost |
| Touch on everything | `enable_touch_on_everything` | `1` | Direct touch/poke |
| Guardian safety boundary | `toggle_guardian` | `0` | Inferred/untested; safety-critical |
| Boundary size | `guardian_radius` | `1` | Inferred/untested; `1` appears to mean Large |
| Auto-spatialization preference | `auto_spatialization_settings` | `0` | Existing setting |

#### Android XR performance metrics

```sh
settings --user 0 get system toggle_xr_perf_metrics
settings --user 0 put system toggle_xr_perf_metrics 1
settings --user 0 put system toggle_xr_perf_metrics 0
```

Google's Android XR Engine Hub documents this key as the remote “Show XR performance data overlay”
control. The firmware labels are “Android XR Performance Metrics” and “Enable Android XR Performance
Metrics”; the summary says the metrics are overlaid on top.

**Warning:** the overlay is static. Leave it off when you are not profiling; long sessions can cause
OLED burn-in. Reverting is a normal settings write and does not require root.

#### Hands breakthrough

```sh
settings --user 0 get system toggle_hands_breakthrough
settings --user 0 put system toggle_hands_breakthrough 1
settings --user 0 put system toggle_hands_breakthrough 0
```

Shows your hands through content instead of only their outlines. The feature adds a small GPU cost
while it is active.

#### Touch on everything

```sh
settings --user 0 get system enable_touch_on_everything
settings --user 0 put system enable_touch_on_everything 1
settings --user 0 put system enable_touch_on_everything 0
```

The firmware label is “Enable touch on everything”. It likely enables direct hand touch/poke
interaction with UI elements instead of requiring a pinch/gesture. The exact interaction behavior is
inferred, not verified.

#### Guardian safety boundary

```sh
settings --user 0 get system toggle_guardian
settings --user 0 put system toggle_guardian 1
settings --user 0 put system toggle_guardian 0
```

`1` enables the boundary; `0` disables it. AndroidX/SystemUI use this key as the “boundary enabled in
developer options” flag. The observed value was `0`, so the boundary is currently disabled on this
headset.

**Safety:** disabling the boundary removes a collision warning. Use it only in a clear, safe space.
The app shows a confirmation modal before turning it off.

#### Boundary size

```sh
settings --user 0 get system guardian_radius
settings --user 0 put system guardian_radius 0
settings --user 0 put system guardian_radius 1
```

Firmware labels are “Boundary size”, “Small” and “Large”; `guardian_toggle_radius_available=1`.
The observed value `1` appears to mean **Large**. The `0/1` mapping is inferred and untested.

#### Auto-spatialization preference

```sh
settings --user 0 get system auto_spatialization_settings
settings --user 0 put system auto_spatialization_settings 1
settings --user 0 put system auto_spatialization_settings 0
```

This is the saved Labs preference. It does not force every window into 3D or bypass thermal/content
restrictions. If the KernelSU auto-spatialization module is installed, it will set the value back to
`1` at boot.

#### Aiming method (`natural_input_mode`)

```sh
settings --user 0 get system natural_input_mode
settings --user 0 get system input_pointer
settings --user 0 put system natural_input_mode <value>
settings --user 0 put system input_pointer <value>
```

The firmware UI exposes 6 = hand and eye aiming, 5 = eye aiming only, and 1 = hand aiming only.

Mode `3` is head direction + finger gesture click; hand tracking stays on, so it is not exposed.
Hidden mode `7` is HMD fallback: head direction + touchpad click with no hand tracking. Enable it
with Volume Down + Volume Up + the headset action button. Set both `natural_input_mode` and
`input_pointer`.

`natural_input_mode` indexes the `ComputerEvents.InputModeType` enum; `input_pointer` maps to
`android.graphics.CPM.InputMode`:

| Value | Input mode type | CPM enum |
|---:|---|---|
| `0` | `UNKNOWN` | `INVALID` |
| `1` | `RAYCAST_HANDS` | `HAND` |
| `2` | `CONTROLLER` | `CONTROLLER` |
| `3` | `HEAD_WITH_HANDS` | `HEAD` |
| `4` | `MOUSE` | `MOUSE` |
| `5` | `EYE_WITH_HANDS` | `EYE` |
| `6` | `AUTO` | `AUTO` |
| `7` | `HMD_FALLBACK` | `HMD_FALLBACK` |
| `8` | `DWELL_WITH_HEAD` | `DWELL_WITH_HEAD` |
| `9` | `DWELL_WITH_EYE` | `DWELL_WITH_EYE` |
| `10` | `HAND_GESTURE_CONTROL` | `HAND_GESTURE_CONTROL` |
| `11` | `DIRECT_HANDS` | `DIRECT_HAND` |

Only `1`, `5`, `6` and `7` are exposed here.

The separate Labs switch "Eyes only" is not part of this enum. Its app key is
`toggle_experimental_eyes_only_input`; observed behavior is head aiming with hand clicks for
selection.

### UI settings (moved to Testing — untested)

| Setting | Keys | Observed | Notes |
|---|---|---:|---|
| Disable UI animations | `window_animation_scale`, `transition_animation_scale`, `animator_duration_scale` | `0.0`, `0.0`, `0.0` | Already disabled on this headset |
| Reduce transparency/window blur | `accessibility_reduce_transparency`, `disable_window_blurs` | unset | Support varies |

#### Disable UI animations

```sh
settings --user 0 get global window_animation_scale
settings --user 0 get global transition_animation_scale
settings --user 0 get global animator_duration_scale

settings --user 0 put global window_animation_scale 0
settings --user 0 put global transition_animation_scale 0
settings --user 0 put global animator_duration_scale 0

settings --user 0 delete global window_animation_scale
settings --user 0 delete global transition_animation_scale
settings --user 0 delete global animator_duration_scale
```

Reverting deletes the keys rather than assuming `1.0`; this lets Android restore its configured
defaults. The current `0.0` values were already present before this work.

#### Reduce transparency and window blur

```sh
settings --user 0 get global accessibility_reduce_transparency
settings --user 0 get global disable_window_blurs

settings --user 0 put global accessibility_reduce_transparency 1
settings --user 0 put global disable_window_blurs 1

settings --user 0 delete global accessibility_reduce_transparency
settings --user 0 delete global disable_window_blurs
```

Both keys were unset on this build. Either may be ignored by a particular app or OEM build. These
settings are exposed under **Testing — untested** because they may have no visible effect.

### Advanced

#### Disable performance optimization policy

```sh
getprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy
su -c 'service call SurfaceFlinger 1044 i32 0'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy false'
su -c 'service call SurfaceFlinger 1044 i32 1'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.enable_dynamic_policy true'
```

This is the developer-option string `disable_application_dynamic_policy_title` ("Disable performance
optimization policy"). The Settings controller is
`com.android.settings.xr.development.DisableAppDynamicPolicyPreferenceController`; it checks the
`com.android.xr.flags.enable_dynamic_policy` flag, calls SurfaceFlinger transaction `1044`, and writes
the DeviceConfig property above.

The policy is not a CPU/GPU boost. Framework strings describe jank detection and an open-app limit:
"Too many apps are open", apps "placed in the background due to poor performance", and apps "closed
due to poor performance". Disabling it removes those interventions.

Observed: `false`, meaning the policy is already disabled and the Settings row shows **On**. The `shell`
ADB user gets `Operation not permitted` for transaction `1044` and cannot set the persistent property;
rooted `su` succeeds. Requires root. Re-enabling writes `true` and transaction `1044 i32 1`.

#### Disable child-process restrictions

```sh
settings --user 0 get global settings_enable_monitor_phantom_procs
settings --user 0 put global settings_enable_monitor_phantom_procs false
settings --user 0 delete global settings_enable_monitor_phantom_procs
```

Observed unset, so Android uses its default monitoring. Setting `false` disables the phantom-process
monitor's limits on child processes; useful for Termux, emulators and similar apps that spawn many
children. It is a global resource-limit change, not a general FPS tweak. Persistent and no root;
deleting the key restores the default.

#### Stay awake while charging

```sh
settings --user 0 get global stay_on_while_plugged_in
settings --user 0 put global stay_on_while_plugged_in 7
settings --user 0 put global stay_on_while_plugged_in 0
```

Observed: `0`. The value is a bitmask: `1` AC, `2` USB, `4` wireless; `7` covers all. This matches the
Android XR Engine Hub's "Stay awake while charging (even when doffed)" option. Persistent and no root.

#### Disable heads-up notifications

```sh
settings --user 0 get global heads_up_notifications_enabled
settings --user 0 put global heads_up_notifications_enabled 0
settings --user 0 put global heads_up_notifications_enabled 1
```

Observed: `1`. Setting it to `0` hides pop-up alerts but leaves notifications in the shade. Persistent
and no root.

#### Disable always-on Wi-Fi/BLE scanning

```sh
settings --user 0 get global wifi_scan_always_enabled
settings --user 0 get global ble_scan_always_enabled

settings --user 0 put global wifi_scan_always_enabled 0
settings --user 0 put global ble_scan_always_enabled 0

settings --user 0 delete global wifi_scan_always_enabled
settings --user 0 delete global ble_scan_always_enabled
```

Observed: both `0`, so always-on scanning is already disabled. Reverting deletes the keys so the
platform can restore defaults. May affect location accuracy and nearby-device features.

### Testing — untested

These entries are exposed in the testing section.

#### Disable Samsung Game Optimizing Service

```sh
pm list packages com.samsung.android.game.gos
pm list packages -d com.samsung.android.game.gos
pm disable-user --user 0 com.samsung.android.game.gos
pm enable --user 0 com.samsung.android.game.gos
```

Observed: installed and enabled. Disabling it is reversible, but it may affect Samsung game/thermal
behavior. This is not verified on Galaxy XR and is not the same as a thermal override.

#### Disable fixed Home Space Mode display rate

```sh
getprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate
su -c 'service call SurfaceFlinger 1043 i32 0'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate false'
su -c 'service call SurfaceFlinger 1043 i32 1'
su -c 'setprop persist.device_config.com_android_xr.com.android.xr.flags.fixed_hsm_display_rate true'
```

This is the developer option `disable_fixed_hsm_display_rate_title`. The controller is
`com.android.settings.xr.development.DisableFixedHSMDisplayRatePreferenceController`; it checks the
`com.android.xr.flags.fixed_hsm_display_rate` flag, calls SurfaceFlinger transaction `1043`, and writes
the DeviceConfig property above. Observed `true`, meaning the fixed Home Space Mode rate is enabled and
the Settings row shows **Off**. Requires root; unverified on this build.


## Documented but not exposed

These were investigated but deliberately left out of the app.

### Passthrough window availability

```sh
settings --user 0 get system passthrough_window_available
settings --user 0 get system toggle_passthrough_window
```

Observed: `passthrough_window_available=0`; `toggle_passthrough_window` is `null`.

The Settings app has a “Passthrough window” screen and strings such as “Create a new passthrough
window or adjust your current one.” `passthrough_window_available` looks like a state/capability flag,
not a simple switch. The companion `toggle_passthrough_window` key exists but was unset. Neither is
exposed because the write semantics are not understood.

### Theater mode

```sh
settings --user 0 get global theater_mode_on
settings --user 0 put global theater_mode_on 1
settings --user 0 put global theater_mode_on 0
```

AOSP defines `Settings.Global.THEATER_MODE_ON` as “Whether Theater Mode is on”. On Wear OS it can put
the display to sleep and limit/mute notifications. XR behavior is not documented here and is not
exposed; changing it may make the headset difficult to wake or dismiss.

### Mute when off body

```sh
settings --user 0 get global obtain_mute_when_off_body
settings --user 0 put global obtain_mute_when_off_body 1
settings --user 0 put global obtain_mute_when_off_body 0
```

AOSP defines `MUTE_WHEN_OFF_BODY_ENABLED` as “If the device should be muted when off body”. Observed
`1`. It may require a reboot to take effect and is not exposed.

## Additional candidates not exposed

These are useful or interesting but were not fully added to the app. The per-app Game Mode entry is
partially exposed through **Tools > Apps**; the rest are documented for future work.

### Private DNS

```sh
settings --user 0 get global private_dns_mode
settings --user 0 get global private_dns_specifier

settings --user 0 put global private_dns_mode hostname
settings --user 0 put global private_dns_specifier one.one.one.one

settings --user 0 delete global private_dns_specifier
settings --user 0 delete global private_dns_mode
```

Persistent, no root. A bad hostname can break all DNS/network access, so this needs validated presets
rather than a simple switch.

### Captive-portal detection

```sh
settings --user 0 get global captive_portal_mode
settings --user 0 put global captive_portal_mode 0
settings --user 0 delete global captive_portal_mode
```

Useful for clean LAN/PCVR networks; public Wi-Fi sign-in pages may stop opening automatically.

### Show touch points and pointer location

```sh
settings --user 0 put system show_touches 1
settings --user 0 put system show_touches 0
settings --user 0 put system pointer_location 1
settings --user 0 put system pointer_location 0
```

Useful for demos/debugging; visual clutter only.

### Per-app Game Mode interventions (partially exposed in Tools > Apps)

```sh
device_config get game_overlay <PACKAGE_NAME>
cmd game list-modes <PACKAGE_NAME>
cmd game mode [standard|performance|battery|custom] <PACKAGE_NAME>
cmd game set --fps [30|45|60|90|disable] --downscale [0.5..0.9|disable] <PACKAGE_NAME>
cmd game reset <PACKAGE_NAME>
```

Google documents these as the Game Mode intervention test commands. `cmd game mode` switches the
OEM-provided mode; `cmd game set` applies custom FPS/downscale interventions and normally needs an app
restart. On this build, Beat Saber, Moonlight XR, NBA 2K and Suzerain report `standard`/`custom`
support; most other XR apps report no game modes.

The app exposes **FPS cap** and **render scale** for packages that report `custom` support. The
underlying Game Mode config also contains `useAngle` and `loadingBoost` fields, but `cmd game set`
does not provide flags for them, so they remain undocumented/unexposed.

### Display mode and refresh presets

```sh
cmd display get-user-preferred-display-mode
cmd display set-user-preferred-display-mode 3552 1920 90
cmd display clear-user-preferred-display-mode
```

`dumpsys display` reports twelve modes: `7104x3840`, `4736x2560`, `3552x1920` and `2368x1280`, each at
60, 72 and 90 Hz. The current mode is the native `7104x3840` at 72 Hz. The app briefly exposed native
72/90 presets, but they were removed: while wearing the headset, the display manager accepted a 90 Hz
preference and the fixed-HSM flag was disabled, yet Home Space kept actively rendering at 72 Hz. A
`dumpsys SurfaceFlinger` frequency log showed only a short 90 Hz period before returning to 72 Hz. The
90 Hz mode is available to apps that request it, but these commands do not force Home Space to use it.
Lower resolutions remain unexposed because they may break XR composition or reduce clarity.

### Disable App Standby

```sh
settings get global app_standby_enabled
settings put global app_standby_enabled 0
settings put global app_standby_enabled 1
```

Observed `1`. App Standby throttles background apps based on usage; disabling it may keep companion or
streaming apps responsive but increases background battery/heat. It is not exposed.

### Fixed-performance mode

```sh
cmd power set-fixed-performance-mode-enabled true
cmd power set-fixed-performance-mode-enabled false
```

Runtime-only. Google documents this as a lower, sustainable operating point, not maximum performance.
Useful for repeatable benchmark runs; no obvious documented read command.

### Dropbox crash/ANR retention

Observed secure values:

```text
dropbox:data_app_anr=disabled
dropbox:data_app_crash=disabled
dropbox:data_app_wtf=disabled
```

These look like useful Diagnostics levers, but the correct way to re-enable them is untested. Do not
change them without verifying the expected value and effect.

### Other observed keys

```text
sleep_timeout=-1
theater_mode_on=0
obtain_mute_when_off_body=1
hmd_don_sound=/product/media/audio/ui/HmdDon.ogg
hmd_doff_sound=/product/media/audio/ui/HmdDoff.ogg
one_handed_mode_enabled=0
```

These are not exposed. `sleep_timeout`, the HMD sounds and one-handed mode need more validation before
they are safe or useful toggles.

## Do not use

Avoid these unless you are deliberately testing recovery:

- `cmd thermalservice override-status ...`
- `settings put secure game_auto_temperature_control 0`
- `settings put global debug.sys.thermal.protection 0`
- disabling package/ADB verifiers
- changing `adb_enabled` or `development_settings_enabled`
- `debug.hwui.*` / `debug.sf.*` props
- guardian/boundary changes outside a safe play area

They can hide thermal problems, weaken security, break ADB or make rendering unstable.

## Read-only discovery results

The pass found no other `xr_*` keys in `system` or `global`. The most useful new system keys were:

```text
toggle_xr_perf_metrics=0
toggle_hands_breakthrough=0
enable_touch_on_everything=1
toggle_guardian=0
guardian_radius=1
passthrough_window_available=0
```

## Validation checklist

Before treating any write as supported:

1. Read the key before changing it.
2. Change one key at a time.
3. Read it back and verify the displayed effect.
4. Revert or delete the key and verify the default.
5. Reboot and check whether it survived.
6. For XR behavior, test in Home Space and Full Space separately.
7. Do not test boundary changes in a cluttered or unsafe space.
