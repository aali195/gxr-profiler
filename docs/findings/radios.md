# Bluetooth & location

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Radio state and capture limits.

## Tests & results

Probed 2026-10-20 to 2026-10-21.

| Probe | Observed result |
|---|---|
| Bluetooth off | `bluetooth_on=0`, `enabled: false`, adapter `BLE_ON`, GATT registered, since boot |
| A2DP | offload enabled, max 1 device, no device connected |
| location | mode 0 (off); master/providers read; no per-app requests captured |

## Findings

- Bluetooth "off" leaves the BLE adapter on.
- No Bluetooth audio codec was exercised without a paired device.
- Location capture is master state only; per-app requests are not tracked.

## Details

- **Bluetooth "off" is not fully off.** With `settings get global bluetooth_on=0` and
  `dumpsys bluetooth_manager` reporting `enabled: false`, the adapter sits in `state: BLE_ON`
  (`curState=BleOnState`, `time since enabled` ~8h20m, i.e. since boot). The enable log says
  `Enabled due to APPLICATION_REQUEST by android`, GattService is registered, and the BLE scanner
  ran once after boot (13:46:10-13:49:12, ~182 s, BALANCED) with ServiceDataUuid
  `0000fe2c-...` (the Fast Pair service UUID) before stopping. The user toggle is off, but a
  BLE-only stack remains up - track both `bt_on` and `bt_state`.
- **No Bluetooth state command.** `cmd bluetooth_manager get-state` returns
  `Unknown command: get-state`; use `settings get global bluetooth_on` plus
  `dumpsys bluetooth_manager`.
- **A2DP offload is enabled:** `A2dpOffloadEnabled: true`, `MaxConnectedAudioDevices: 1`,
  `A2DP Source/Sink State: Disabled` while no device is connected. No BT device was paired, so the
  A2DP codec (SBC/AAC/aptX/LDAC) is not captured.
- **Location off still has providers registered.** `location_mode=0`,
  `location_providers_allowed=null`, `cmd location is-location-enabled=false`, yet
  `dumpsys location` lists `network` and `fused` providers with `ProviderRequest[OFF]` and
  identities/attribution tags from `com.google.android.gms` (plus a low-power
  `com.google.android.as` request with a 6 h interval, inactive). Location is off, but the
  provider plumbing remains.
- **Modes:** 0=off, 1=device only (sensors), 2=battery saving, 3=high accuracy. Captured as
  `loc_mode` / `loc_mode_name`, with `loc_providers`. We could not toggle location on (read-only
  test), so the enabled paths use Android's documented semantics rather than an on-device A/B.
- **No per-app location requests tracked yet.** `dumpsys location` exposes active/inactive
  requests (e.g. `ProviderRequest[OFF]`, `(inactive)`), but gxr-profiler records only the master
  on/off/mode/providers.
