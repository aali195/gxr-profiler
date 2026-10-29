# Cameras, perception & controllers

[Findings index](../README.md) | [Commands](../COMMANDS.md)

All camera/tracking attribution is by named CIB stream or perception service, not by a physical
sensor ID. Controllers are delivered through Samsung XR services, not Linux joystick devices.

## Tests & results

Probed 2026-10-21 while idle and in XR apps.

| Probe | Observed result |
|---|---|
| CIB `client_state` stream names | `HT`/`P-HT` ~240 fps, `Hat`/`P-Hat` ~180, `EyeT`/`P-EyeT` ~120, `DepthTOF` 10, `DepthInput` ~120 |
| `XrHeartbeat` ingest rates | head 60, hand 60, eye 30, IR LED 30 fps |
| physical stream IDs | 4 `trackingA..D_curved`, 2 `rgb-*`, 1 `d-depth` |
| controllers | both connected, battery 100%, pose status 2/quality 1, inputs received |
| suspended controller | still reports connected; pose/tracking distinguishes use |

## Findings

- No dedicated hand camera; `Hat` is a consumer of the shared world-facing array.
- Stream-to-sensor routing is not exposed; only stream/service rates are reportable.
- Controllers are XR input services, not `/dev/input`.
- Connection state alone is not "in use"; use tracking/pose state.
- Power saving halves raw head/hand and service ingest rates.

## Details

### Camera & tracking attribution

Attribution is by **named stream / service**, never by physical sensor ID:

- **CIB stream names** (logcat `client_state.cc`): `HT`/`P-HT` = head (~240 fps),
  `Hat`/`P-Hat` = hand (~180 fps), `EyeT`/`P-EyeT` = eye (~120 fps), `DepthTOF` 10 fps,
  `DepthInput` ~120 fps. (With power saving on, the head/hand rates halve.)
- **Service heartbeats** (logcat `XrHeartbeat`) give the rates each perception service ingests:
  eye ~30 fps, head ~60 fps, hand ~60 fps; `SXR/IRLedController` = IR LEDs ~30 fps. These are
  recorded as `cam_*_fps` / `irled_fps`.
- Physical stream IDs seen separately: `trackingA..D_curved` (4 tracking cameras),
  `rgb-left_curved` / `rgb-right_curved` (2 passthrough RGB), `d-depth` (ToF).
- **No dedicated hand-tracking camera**: `Hat` is a CIB *consumer* fed from the shared
  world-facing camera array (the same bundle head tracking uses). IR LEDs are dedicated to eye
  tracking; depth has its own ToF. Stream-to-sensor routing is not exposed to user-visible logs,
  so gxr-profiler reports stream/service rates, not per-sensor rates.

### Controllers

- Samsung's controller stack runs as `vendor.samsung.hardware.secxrcontroller@1.0-service`,
  `com.sec.android.secxrcontrollerservice`, and the `xrcontrollertracking` system service. They do
  not appear as Linux `/dev/input` joysticks; input is delivered through the XR input service.
- Useful read-only logcat sources:
  - `SXRC_TSVC`: `updateDeviceState hand_controller_left/right: state=connected, battery=N`,
    plus trigger, squeeze, grip, thumbstick, and firmware fields.
  - `SXRC_POSE`: per-controller pose with `status:2` and `quality:1` when tracked.
  - `CpmInput`: `XRInputConnection: start tracking for hand_controller_*` and
    `XRControllerDevice: stop tracking ...`.
  - `SXRC_SVC`: `OnControllerDeviceStatusChange` with `2(CONNECTED)` / `3(SUSPENDED)`.
- Live check on 2026-10-21: both controllers connected, battery 100%, pose status 2 / quality 1,
  with trigger, squeeze, grip, and thumbstick input events. A suspended controller still reports
  `connected`; use tracking/pose state for "in use".
- gxr-profiler records `ctrl_left/right_connected`, `ctrl_left/right_track`,
  `ctrl_left/right_battery`, and `ctrl_active`, and tags runs with a controllers/no-controllers
  badge from start/end state when active.
