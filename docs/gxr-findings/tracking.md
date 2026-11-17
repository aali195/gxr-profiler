# Cameras, perception & controllers

[Findings index](../README.md) | [Commands](../COMMANDS.md)

> **Hardware state: STOCK.** All runs on this page are from the unmodified headset, before 2026-11-01. No thermal mod.

All camera/tracking attribution is by named CIB stream or perception service, not by a physical sensor ID. Controllers are delivered through Samsung XR services, not Linux joystick devices.

## In plain terms

- Head tracking runs fastest, then hand and eye tracking, with depth tracking slowest.
- With power saving on, raw head and hand camera rates are halved, so fast movement is tracked less smoothly.
- There is no separate hand camera; hand tracking shares the main tracking cameras.
- The rear ambient-light sensor drives the IR illuminators: brightness 50-60 below about 7 lx, and off in brighter rooms.
- A controller showing as connected is not necessarily in use; tracking state shows that.
- Both controllers had full battery and were tracked during the test.

## Tests & results

Probed 2026-10-21 while idle and in XR apps.

| Probe | Observed result |
|---|---|
| CIB `client_state` stream names | `HT`/`P-HT` ~240 fps, `Hat`/`P-Hat` ~180, `EyeT`/`P-EyeT` ~120, `DepthTOF` 10, `DepthInput` ~120 |
| `XrHeartbeat` ingest rates | head 60, hand 60, eye 30; `IRLedController` control loop 30 Hz |
| physical stream IDs | 4 `trackingA..D_curved`, 2 `rgb-*`, 1 `d-depth` |
| controllers | both connected, battery 100%, pose status 2/quality 1, inputs received |
| suspended controller | still reports connected; pose/tracking distinguishes use |

## Findings

- No dedicated hand camera; `Hat` is a consumer of the shared world-facing array.
- Stream-to-sensor routing is not exposed; only stream/service rates are reportable.
- IR illuminators are low-light assist for the world-facing tracking cameras and eye cameras, not eye-only.
- IR output is gated by the STK6D2X rear ALS: 60 below 2 lx, 50 up to about 7 lx, off above about 8 lx.
- Controllers are XR input services, not `/dev/input`.
- Connection state alone is not "in use"; use tracking/pose state.
- Power saving halves raw head/hand and service ingest rates.

## Details

### Camera & tracking attribution

Attribution is by **named stream / service**, never by physical sensor ID:

- **CIB stream names** (logcat `client_state.cc`): `HT`/`P-HT` = head (~240 fps), `Hat`/`P-Hat` = hand (~180 fps), `EyeT`/`P-EyeT` = eye (~120 fps), `DepthTOF` 10 fps, `DepthInput` ~120 fps. (With power saving on, the head/hand rates halve.)
- **Service heartbeats** (logcat `XrHeartbeat`) give the rates each perception service ingests: eye ~30 fps, head ~60 fps, hand ~60 fps. `SXR/IRLedController` is a ~30 Hz control loop, not an emitter strobe rate. These are recorded as `cam_*_fps` and `irled_fps`.
- Physical stream IDs seen separately: `trackingA..D_curved` (4 tracking cameras), `rgb-left_curved` / `rgb-right_curved` (2 passthrough RGB), `d-depth` (ToF).
- **No dedicated hand-tracking camera**: `Hat` is a CIB *consumer* fed from the shared world-facing camera array (the same bundle head tracking uses). Depth has its own ToF. Stream-to-sensor routing is not exposed to user-visible logs, so gxr-profiler reports stream/service rates, not per-sensor rates.

### Ambient light & IR illuminator

- The rear ALS is an STK6D2X at `/sys/class/sensors/als_rear` (`lux`, `als_data`, `als_enable`); userspace reads it through `SensorsFlicker` and `QVRFlickerSensorReader`, and `IRLedController` logs it as `flickerSensorLux`.
- `/vendor/etc/sxr/irled_control_config.json` sets a 30 Hz control loop and two brightness bands: `lux < 2` -> 60, `lux < 7` -> 50, with hysteresis (`>= 6` exits 60; `>= 8` for 200 ms exits 50). With no matching band, brightness is 0.
- The QVR camera config shows the world-facing `s5k931_stereo` tracking cameras using `flash_sequence_cfg` / `illumination_ramptime_ns_cfg`, and the eye cameras using `torch`; the IR illuminator is therefore shared low-light assist, not eye-tracking-only.
- Lifecycle: `IRLedController` resumes with the perception host when the display wakes/headset is worn and suspends about 8-10 s after an off-body screen-off. The emitter writer only starts in the 50/60 bands, so a worn headset in a bright room runs the controller with the emitters off.
- The ALS sysfs files are SELinux-protected for `shell` and are invalid while asleep (`als_enable=0`); logcat `flickerSensorLux` is the usable non-root source while the headset is awake.

### Controllers

- Samsung's controller stack runs as `vendor.samsung.hardware.secxrcontroller@1.0-service`, `com.sec.android.secxrcontrollerservice`, and the `xrcontrollertracking` system service. They do not appear as Linux `/dev/input` joysticks; input is delivered through the XR input service.
- Useful read-only logcat sources:
- `SXRC_TSVC`: `updateDeviceState hand_controller_left/right: state=connected, battery=N`,
    plus trigger, squeeze, grip, thumbstick, and firmware fields.
- `SXRC_POSE`: per-controller pose with `status:2` and `quality:1` when tracked.
- `CpmInput`: `XRInputConnection: start tracking for hand_controller_*` and
    `XRControllerDevice: stop tracking ...`.
- `SXRC_SVC`: `OnControllerDeviceStatusChange` with `2(CONNECTED)` / `3(SUSPENDED)`.
- Live check on 2026-10-21: both controllers connected, battery 100%, pose status 2 / quality 1, with trigger, squeeze, grip, and thumbstick input events. A suspended controller still reports `connected`; use tracking/pose state for "in use".
- gxr-profiler records `ctrl_left/right_connected`, `ctrl_left/right_track`, `ctrl_left/right_battery`, and `ctrl_active`, and tags runs with a controllers/no-controllers badge from start/end state when active.
