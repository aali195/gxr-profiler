# Wi-Fi performance & standby

[Findings index](../README.md) | [Commands](../COMMANDS.md) | [Standby & wake](standby.md)

The recent low/critical battery and post-battery runs were all taken from the same position in the
same session. Seven were normal hot runs and three followed a desk standby: ~31.5 min (60 s run),
~3.7 min (60 s run), and ~18 min with the 5 min recording started **immediately** after putting the
headset on. All three standby runs were plugged in and used the same VRChat/SteamVR ASTC workload.

## Tests & results

### Whole-run Wi-Fi metrics

| Run | Battery / AC | Rx mean | Tx mean | Link mean | RSSI mean | Retry | Loss/drops/errors |
|---|---|---:|---:|---:|---:|---:|---|
| run-20 | 20%, off | 1288 Mbps | 3.87 Mbps | 3.64 Gbps | -25.5 dBm | 4.65% | 0 |
| run-17 | 16%, off | 1295 Mbps | 3.87 Mbps | 3.24 Gbps | -25.6 dBm | 4.31% | 0 |
| run-13 | 13%, off | 1281 Mbps | 3.88 Mbps | 3.79 Gbps | -26.0 dBm | 4.68% | 0 |
| run-8 | 8%, off | 1281 Mbps | 3.88 Mbps | 4.05 Gbps | -26.6 dBm | 4.80% | 0 |
| run-4 | 4%, off | 1281 Mbps | 3.88 Mbps | 3.51 Gbps | -27.8 dBm | 4.98% | 0 |
| run-4 plugged | 3%, on | 1275 Mbps | 3.91 Mbps | 3.11 Gbps | -27.0 dBm | 4.51% | 0 |
| run-16 plugged | 16%, on | 1273 Mbps | 3.88 Mbps | 3.16 Gbps | -27.3 dBm | 4.31% | 0 |
| after-standby-1 | 52%, on | 1279 Mbps | 3.84 Mbps | 3.51 Gbps | -31.2 dBm | 5.33% | 0 |
| after-standby-2-short | 58%, on | 1274 Mbps | 3.85 Mbps | 3.09 Gbps | -31.9 dBm | 5.25% | 0 |
| after-standby-2-long (immediate wake) | 85%, on | 1264 Mbps | 3.82 Mbps | 3.55 Gbps | -27.1 dBm | 5.30%* | 0 |

\* Mean includes the first-5-s low-TX artifact below; steady-state retry is ~4.6%.

All runs were on channel/frequency **6295 MHz**, Wi-Fi standard **8** (Wi-Fi 7), with max
supported Tx/Rx link **5764 Mbps**. `wifi_rx_drops`, `wifi_tx_drops`, `wifi_rx_errors`,
`wifi_tx_errors` and `wifi_lost_pps` stayed at **0** for every run.

### First 10 s vs the rest

The first 10 s were checked separately in case standby left a short re-association/rate-control
transient.

| Run | Window | Rx mean | Link mean | RSSI | Retry |
|---|---|---:|---:|---:|---:|
| run-16 (pre-standby) | first 10 s | 1343 Mbps | 2.26 Gbps | -33.0 dBm | 4.41% |
| | rest | 1259 Mbps | 3.34 Gbps | -26.2 dBm | 4.29% |
| after-standby-1 | first 10 s | 1317 Mbps | 2.13 Gbps | -31.2 dBm | **7.54%** |
| | rest | 1271 Mbps | 3.79 Gbps | -31.2 dBm | 4.88% |
| after-standby-2-short | first 10 s | 1319 Mbps | 3.00 Gbps | -28.4 dBm | 5.74% |
| | rest | 1265 Mbps | 3.11 Gbps | -32.6 dBm | 5.15% |
| after-standby-2-long (immediate) | first 10 s | 1358 Mbps | 2.54 Gbps | -30.4 dBm | 25.5%* |
| | rest | 1261 Mbps | 3.59 Gbps | -27.0 dBm | 4.61% |

\* Low-TX artifact: only 1.9 TX pps and 0.77 retry pps over that window; once TX ramped to 249-435
pps the retry rate was ~4.6-5.3%.

### Max-throughput test (2026-10-31)

A 60 s run with Chrome open on an OpenSpeedTest server hosted by the PC; the PC has a **2.5 GbE**
NIC connected to the router. The headset was at 100%, plugged, thermal status 3, with the camera
already thermally halved to 30 fps.

| Test | Demand / setting | Rx mean | Rx p50 | Rx steady max | Link mean | RSSI | Retry | Drops/errors |
|---|---|---:|---:|---:|---:|---:|---:|---|
| max-wifi-test | 2.5 GbE speedtest | **2190 Mbps** | 2185 Mbps | 2369 Mbps | 3.83 Gbps | -28.6 dBm | 3.09% | 0 |
| wifi-4-vr-900 | 900 Mbps | 876 Mbps | 872 Mbps | 1320 Mbps | 4.16 Gbps | -31.4 dBm | 3.29% | 0 |
| wifi-4-vr-600 | 600 Mbps | 632 Mbps | 629 Mbps | 999 Mbps | 3.91 Gbps | -33.8 dBm | 2.28% | 0 |
| wifi-4-vr-300 | 300 Mbps | 320 Mbps | 319 Mbps | 515 Mbps | 3.83 Gbps | -34.1 dBm | 2.29% | 0 |

The first sample reported **3038 Mbps**, but excluding it the sustained mean is **2175 Mbps** and
the steady maximum is **2369 Mbps**. That is about **87% of 2.5 GbE line rate**. Link rate, Wi-Fi
7 (`std=8`) and the 6295 MHz channel were unchanged from the older tests; max supported Tx/Rx
remained 5764 Mbps. Lost packets, drops and errors were zero throughout.

## Findings

- **No considerable Wi-Fi throughput degradation after standby.** Rx stayed around **1.26-1.28
  Gbps** and Tx around **3.8-3.9 Mbps** in every run, including the immediate-wake 5 min run. There
  was no sustained low-throughput or stuck-low-link-rate period.
- **The headset can sustain ~2.17 Gbps.** The 2.5 GbE speedtest run held ~2.19 Gbps (p50 2185,
  ~2.17 Gbps excluding the first sample), about 87% of 2.5 GbE line rate. The old 900 Mbps test was
  therefore not limited by the Wi-Fi link: its link rate was actually slightly higher (4.16 vs
  3.83 Gbps mean), so the ceiling was the old test/client/server setup, not the radio.
- **The 3038 Mbps first sample is a start-of-run artifact.** Excluding it, the steady maximum was
  2369 Mbps. Treat the first rate sample after recording starts cautiously on saturated links.
- **Thermal status 3 did not reduce network throughput.** The max test ran at status 3 with the
  camera already at 30 fps, yet held 2.19 Gbps with retry around 3.1% and zero drops/errors.
- **No packet loss at the measured layer.** Lost packets, netdev drops and errors were all zero.
- **The scary-looking 42.5% retry at immediate wake is a denominator artifact.** For the first 5 s
  the platform reported only **3.02 TX pps** and **1.28 retry pps**, producing a meaningless 42.5%
  ratio. TX then sat at 0.33 pps for 5 s, and by 11 s had ramped to **249 pps** with retry around
  **5.3%**. Actual retry pps in steady state was 18-24/s.
- **RSSI is a few dB weaker in the first seconds after wake**, improving from about -32 dBm to -28
  dBm by 6 s and -21 dBm later. The headset was being put on, so position/orientation is a
  confounder.
- **Link rate adapted normally.** Link speed varied from about 1.7 to 5.2 Gbps; there was no
  persistent low-rate state. Max supported Tx/Rx remained 5764 Mbps.
- **No restart appeared necessary.** The headset sustained the same ~1.27 Gbps receive stream
  through the immediate-wake period and both later standby runs.

The immediate-wake run covers the first moments after standby, but the profiler records link rate,
RSSI and packet counters, not ping, jitter or SteamVR transport latency. A short post-wake
latency/jitter spike could still exist without showing up here.

### Practical bitrate guidance

- The measured max is **~2.17 Gbps** at **-28.6 dBm** line-of-sight, so **1.6 Gbps is ~74% of the
  observed ceiling** and about **37-42% of the 3.8-4.3 Gbps link rate** in good conditions. That is
  a reasonable ceiling when sitting at the desk/couch facing the router.
- Normal VRChat/SteamVR play in these runs used **~1.17-1.29 Gbps**, with retry **4-6%** and zero
  lost packets/drops/errors.
- At lower RSSI during movement/occlusion (-34 to -43 dBm), retry rose to **6-11%** and link rate
  occasionally fell to **1.9-2.3 Gbps**, still without packet loss at ~1.2 Gbps demand.
- At a 1.9-2.3 Gbps link, a 1.6 Gbps stream would use **70-84% of the link rate**. That leaves much
  less margin for turning around, body blocking or retries than the current ~1.27 Gbps play load.
- **Recommendation:** treat **1.3-1.4 Gbps** as the comfortable everyday cap if you want margin
  while moving/turning. **1.6 Gbps is a plausible upper test cap** at good orientation, but I would
  not assume it is movement-safe without testing the worst body/shadowing orientation.
- The dedicated 6 GHz band removes contention, but 6 GHz is more body/line-of-sight sensitive than
  5 GHz. Wi-Fi 7/MLO can help capacity, but these runs do not expose MLO state.

## Caveats

- The max test is from a different day than the 300/600/900 runs, though the channel, Wi-Fi
  standard and max link rate match. The PC 2.5 GbE NIC/router/OpenSpeedTest server can limit the
  result. The max run was 60 s; the older 300/600/900 runs were 120 s.
- Three standby runs, all plugged, sequential and not temperature-matched.
- "Rest before" is measured from the previous recording's end, not the actual standby/doze entry
  time.
- Same physical spot, but headset orientation/body position can change RSSI by several dB.
- `wifi_retry_pct` is derived from the platform's retried-Tx packets per second and is unreliable
  when TX pps is very low; use retry pps with it.
- The first rate sample after recording starts can be inflated; steady-state values are more useful.
- No ping, iPerf, jitter or SteamVR streaming-latency samples were captured.

## Useful next experiments

1. Start a recording **immediately** at wake and compare the first 60 s with a pre-standby run.
2. Run a continuous ping/iPerf or SteamVR streaming-latency test across standby; throughput alone
   will not show latency spikes.
3. Log `dumpsys wifi`, `cmd wifi status` and the Wi-Fi driver state at wake to catch reassociation
   or power-save transitions.
4. Repeat with a fixed headset position and matched start temperature to separate RSSI/position
   effects from standby.
5. Repeat the max test with a 10 GbE host/router path and iperf3 to find the headset radio ceiling
   rather than the PC/NIC ceiling.
