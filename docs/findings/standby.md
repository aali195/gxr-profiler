# Standby, wake & thermal recovery

[Findings index](../README.md) | [Commands](../COMMANDS.md) | [Power modes & battery](modes.md)

Three VRChat-on-SteamVR ASTC runs immediately after the low/critical battery session, all plugged in
and with hand tracking off/no active media. Two were 60 s runs started after the headset had been put
on and used for a minute or two; the third was a 5 min run started right from the desk to the head.

- Long rest before a 60 s run: ~31.5 min since the previous recording ended.
- Short rest before a 60 s run: ~3.7 min.
- Immediate-wake run: ~18.0 min rest, then straight from the desk onto the head.

## Tests & results

| Run | Rest before | Battery | Thermal status | AP start -> end | GPU start -> end | Fan | XR fps | Head camera | Result |
|---|---|---:|---|---:|---:|---|---:|---:|---|
| after-standby-1 | ~31.5 min | 52 -> 53% | 2 | 70.0 -> 72.0 C | 71.1 -> 73.4 C | 5 -> 6 | 71.8 | 60 | stayed status 2 |
| after-standby-2-short | ~3.7 min | 58 -> 59% | 2 -> 3 at 35 s | 71.6 -> 73.0 C | 72.4 -> 73.4 C | 5 -> 6 at 4 s | 70.1 | 60 -> 56.6 -> 30 | crossed to status 3 |
| after-standby-2-long-from-put-on | ~18.0 min | 85 -> 90% | 0 -> 1 at 32 s -> 2 at 137 s -> 3 at 277 s | 45.5 -> 72.0 C | 44.4 -> 73.1 C | 1 -> 6 | 71.5 | 11.4 -> 60 -> 30 | true cold wake, full 5 min ramp |

The two 60 s runs held CPU caps **1.92 / 1.92 GHz**, GPU **421 MHz**, `g_throttling=0`, `psm=0`,
display **72 Hz** and `passthrough=0`. The 5 min run started at the **2.36 GHz** cap and dropped to
1.92 GHz by 5 s, then stayed there. Battery temperature was 37-38 C for the 60 s runs and 41-40 C
for the 5 min run. CIB head was ~480 fps while status 2; it fell to ~240 fps once status 3 arrived.

### Immediate wake (5 min run)

This is the first run that starts at the actual wake instead of after a minute or two of use.

| elapsed | event |
|---:|---|
| 0-5 s | status 0, AP 45.5 C, GPU 44.4 C, fan 1, CPU cap 2.36 GHz, GPU busy 0 |
| 5 s | GPU busy 38%, XR 70.1 fps, head camera 11.4 fps |
| 6 s | CIB head ~479 fps, eye 2.8 fps, WiFi link 3459 Mbps |
| 11 s | TX ramps to ~249 pps; retry settles to ~5.3% |
| 15 s | head camera 60 fps |
| 16 s | eye camera 30.1 fps |
| 22 s | fan step 2 |
| 32 s | thermal status 1 |
| 42 s | fan step 3 |
| 83 s | fan step 4 |
| 137 s | thermal status 2 |
| 153 s | fan step 5 |
| 210 s | fan step 6 |
| 277 s | thermal status 3 |
| 295 s | head camera falls to 30 fps |

CPU utilisation also ramps with the workload rather than starting high:

| elapsed | CPU |
|---:|---|
| 0 s | core0 53%, core2 34%, load1 1.7, 3 runnable |
| 5-10 s | core0 81-85%, load1 1.9-2.7; runnable spikes to 23 at 10 s |
| 30 s | core0 94%, load1 5.4 |
| 60 s | core0 74%, load1 6.4 |
| 5 min | core0 mean 82%, cores2-5 mean 58-63%, load1 8-10 |

## Findings

- **An immediate wake is genuinely cold.** After ~18 min on the desk, the headset restarted at
  thermal status 0, AP 45.5 C, GPU 44.4 C, fan 1 and the full 2.36 GHz CPU cap. The earlier 60 s
  after-standby runs were recorded after 1-2 min of use and had already warmed to status 2/AP ~70 C;
  that was pre-recording heat, not evidence that standby failed to cool the device.
- **CPU use is not higher because of standby.** The immediate-wake run started *lower*: core0 53%,
  core2 34% and load1 1.7, then ramped as Chronolink, perception and the compositor started. Its
  first-10-s core0 mean was 64.6%, versus 81-84% in the 60 s after-standby runs that were already in
  use. The 5 min run's higher whole-run mean (81.6% core0) is sustained workload, not a standby
  penalty; no extra background CPU state was visible.
- **Rest length and pre-recording use matter more than "standby" itself.** With a 3.7 min gap plus
  1-2 min of use, the next run re-entered status 3 within 35 s. With an ~18 min gap and an immediate
  start, it took **277 s** to reach status 3.
- **The cold-start thermal ladder is gradual.** Status went 0 -> 1 at 32 s, 1 -> 2 at 137 s and
  2 -> 3 at 277 s; fan climbed 1 -> 2 -> 3 -> 4 -> 5 -> 6 at 22/42/83/153/210 s.
- **The camera pipeline wakes more slowly than CIB telemetry.** Head camera was 11.4 fps until 15 s,
  eye was 2.8 fps until 16 s, then both jumped to 60/30 fps. CIB head was already ~479 fps by 6 s.
  Part of this may be recorder/media-state settling rather than the device, but the intermediate
  rates are real in the row data.
- **Frame pacing was normal after wake:** 70.1 fps for the first 5 s, then 71.9/71.5 fps against a
  72 fps target, with `xr_drops=0`.
- **Wi-Fi throughput did not collapse.** Both 60 s post-standby runs and the 5 min immediate-wake
  run held ~1.27 Gbps Rx with zero loss/drops/errors. The apparent 42.5% retry at the start of the
  5 min run is a low-TX denominator artifact (3 pps TX, 1.28 retry pps); once TX ramped to ~249 pps
  the retry rate was ~5.3%. See [Wi-Fi & standby](wifi.md).
- **No Wi-Fi restart was needed in these recordings.** RSSI was a few dB weaker in the first seconds
  after wake but recovered as the headset was worn; link rate adapted normally.

## Caveats

- Three runs, all plugged, sequential and not temperature-matched.
- "Rest before" is measured from the previous recording's end, not the actual standby/doze entry
  time. The 60 s runs include 1-2 min of pre-recording use; the 5 min run does not.
- No ambient temperature, no pre-run thermal snapshot, and no Android doze/suspend logs were
  captured. The exact standby depth is unknown.
- Hand tracking was off and the Chronolink/VRChat workload was effectively identical.
- The Wi-Fi retry percentage becomes misleading at very low TX packet rates; use retry pps with it.

## Useful next experiments

1. Log `dumpsys thermalservice` and battery/charging state before and after known standby intervals
   (5, 10, 20, 40 min) without launching VRChat.
2. Repeat the paired rest test with matched starting AP/GPU temperatures and randomised rest order.
3. Capture Android suspend/doze state (`dumpsys power`, `dumpsys deviceidle`) at wake to separate
   display-off idle from true suspend.
4. Repeat the immediate-wake run with ping/iPerf or streaming-latency capture to test whether the
   early retry/link changes are perceptible.
