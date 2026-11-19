# Hidden and experimental ADB settings

[Back to README](../README.md) | [Settings guide](SETTINGS.md) | [Commands](COMMANDS.md)

This page records hidden Android XR settings found on the **Samsung Galaxy XR (SM-I610)**, including
settings exposed in **GXR Manager > Settings** and candidates that are deliberately not exposed. It is a
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
| **Exposed** | Appears in **GXR Manager > Settings**. |
| **Documented only** | Recorded here but not exposed in the app. |
| **Observed** | Value read from this build during the read-only pass. |
| **Inferred** | Behavior or numeric mapping inferred from labels/code, not verified by changing it. |
| **Untested** | No write was performed; expect possible differences or resets. |
| **Persistent** | Stored in Android SettingsProvider and normally survives a reboot. |

The generic manual form is `adb shell settings --user 0 <get|put|delete> <namespace> <key> [value]`.
The app uses the same command without the leading `adb shell`.

## Exposed in GXR Manager > Settings

This page records the research behind each exposed key: what the firmware calls it, what value was
observed on this build, and what remains inferred. Behaviour, warnings, defaults and the exact
commands are in the [Settings guide](SETTINGS.md).

### XR controls

| Setting | Key(s) | Observed | Research note |
|---|---|---:|---|
| Android XR performance metrics | `toggle_xr_perf_metrics` | `0` | Google-documented overlay control. The overlay is static, so it can cause OLED burn-in if left on. |
| Aiming method | `natural_input_mode`, `input_pointer` | `6` | `6` hand + eye, `5` eye only, `1` hand only. Hidden `7` is HMD fallback (head + touchpad, no hand tracking). |
| Hands breakthrough | `toggle_hands_breakthrough` | `0` | Shows hands through content; adds a small GPU cost. |
| Touch on everything | `enable_touch_on_everything` | `1` | Enables direct touch/poke instead of a gesture. |
| Guardian safety boundary | `toggle_guardian` | `0` | Disabling removes a collision warning; the app asks for confirmation. |
| Boundary size | `guardian_radius` | `1` | `0/1` mapping is inferred: `0` Small, `1` Large. |
| Auto-spatialization preference | `auto_spatialization_settings` | `0` | Saved Labs preference only; it does not force windows into 3D. |

### Advanced

| Setting | Key(s) | Observed | Research note |
|---|---|---:|---|
| Disable child-process restrictions | `settings_enable_monitor_phantom_procs` | unset | Global resource-limit change, not an FPS tweak. |
| Stay awake while charging | `stay_on_while_plugged_in` | `0` | Bitmask: `1` AC, `2` USB, `4` wireless; `7` covers all. |
| Disable heads-up notifications | `heads_up_notifications_enabled` | `1` | Hides pop-ups; the notification shade still works. |
| Disable always-on Wi-Fi/BLE scanning | `wifi_scan_always_enabled`, `ble_scan_always_enabled` | `0`, `0` | May affect location accuracy and nearby-device features. |

### Testing - untested

| Setting | Key(s) | Observed | Research note |
|---|---|---:|---|
| Disable performance optimization policy | `enable_dynamic_policy` | `false` | Root required; SurfaceFlinger transaction `1044` plus a DeviceConfig property. |
| Disable UI animations | `window_animation_scale`, `transition_animation_scale`, `animator_duration_scale` | `0.0` | Already disabled on this headset before the research pass. |
| Reduce transparency/window blur | `accessibility_reduce_transparency`, `disable_window_blurs` | unset | Support varies; may have no visible effect. |
| Disable Samsung Game Optimizing Service | `com.samsung.android.game.gos` | enabled | Reversible, but unverified on Galaxy XR. |
| Disable fixed Home Space Mode display rate | `fixed_hsm_display_rate` | `true` | Root required; SurfaceFlinger transaction `1043` plus a DeviceConfig property. |

### Research notes

- **Disable performance optimization policy** is the string
  `disable_application_dynamic_policy_title`. The Settings controller is
  `com.android.settings.xr.development.DisableAppDynamicPolicyPreferenceController`; it checks
  `com.android.xr.flags.enable_dynamic_policy`, calls SurfaceFlinger transaction `1044`, and writes
  the matching DeviceConfig property. Framework strings describe jank detection and an open-app
  limit ("Too many apps are open", apps "placed in the background due to poor performance"). It is
  not a CPU/GPU boost. The `shell` ADB user gets `Operation not permitted`; rooted `su` succeeds.
- **Disable fixed Home Space Mode display rate** is the string
  `disable_fixed_hsm_display_rate_title`. The controller is
  `com.android.settings.xr.development.DisableFixedHSMDisplayRatePreferenceController`; it checks
  `com.android.xr.flags.fixed_hsm_display_rate`, calls SurfaceFlinger transaction `1043`, and writes
  the matching DeviceConfig property.
- **Aiming method** is also set by the firmware gesture Volume Down + Volume Up + the headset
  action button, which switches to hidden mode `7`. Set both `natural_input_mode` and
  `input_pointer` to the same value.

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
partially exposed through **GXR Manager > Apps**; the rest are documented for future work.

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

### Per-app Game Mode interventions (partially exposed in GXR Manager > Apps)

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
