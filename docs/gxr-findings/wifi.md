# Wi-Fi performance & standby

[Findings index](../README.md) | [Commands](../COMMANDS.md) | [Standby & wake](standby.md) | [Thermal mod before/after](thermal-mod.md)

> **Hardware state: STOCK.** All runs on this page are from the unmodified headset, before 2026-11-01. No thermal mod.

The recent low/critical battery and post-battery runs used the same position and session. Seven were normal hot runs; three followed a desk standby: ~31.5 min (60 s run), ~3.7 min (60 s run), and ~18 min with the 5 min recording started **immediately** after putting the headset on. All three standby runs were plugged in and used the same VRChat/SteamVR ASTC workload.

## In plain terms

- Wi-Fi stays stable after standby. There is no slowdown or stuck-low-speed period, and no restart is needed.
- Normal VRChat/SteamVR play used about 1.2-1.3 Gbps with no lost packets, drops or errors.
- The headset can reach about 2.17 Gbps at best on a good 2.5 GbE setup.
- 1.3-1.4 Gbps is the safer everyday choice if you move around; 1.6 Gbps needs good line of sight.
- 6 GHz Wi-Fi is less crowded but more sensitive to your body blocking the signal.

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

\* Mean includes the first-5-s low-TX artifact; steady-state retry is ~4.6%.

All runs were on channel/frequency **6295 MHz**, Wi-Fi standard **8** (Wi-Fi 7), with max supported Tx/Rx link **5764 Mbps**. `wifi_rx_drops`, `wifi_tx_drops`, `wifi_rx_errors`, `wifi_tx_errors` and `wifi_lost_pps` stayed at **0** for every run.

### First 10 s vs the rest

The first 10 s were checked separately for a short standby re-association/rate-control transient.

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

\* Low-TX artifact: only 1.9 TX pps and 0.77 retry pps over that window; once TX ramped to 249-435 pps the retry rate was ~4.6-5.3%. `wifi_retry_pct` is derived from retried-Tx packets per second and is unreliable at very low TX pps; read retry pps alongside it.

### Max-throughput test (2026-10-31)

A 60 s run with Chrome open on an OpenSpeedTest server hosted by the PC; the PC has a **2.5 GbE** NIC connected to the router. The headset was at 100%, plugged, thermal status 3, with the camera already thermally halved to 30 fps.

| Test | Demand / setting | Rx mean | Rx p50 | Rx steady max | Link mean | RSSI | Retry | Drops/errors |
|---|---|---:|---:|---:|---:|---:|---:|---|
| max-wifi-test | 2.5 GbE speedtest | **2190 Mbps** | 2185 Mbps | 2369 Mbps | 3.83 Gbps | -28.6 dBm | 3.09% | 0 |
| wifi-4-vr-900 | 900 Mbps | 876 Mbps | 872 Mbps | 1320 Mbps | 4.16 Gbps | -31.4 dBm | 3.29% | 0 |
| wifi-4-vr-600 | 600 Mbps | 632 Mbps | 629 Mbps | 999 Mbps | 3.91 Gbps | -33.8 dBm | 2.28% | 0 |
| wifi-4-vr-300 | 300 Mbps | 320 Mbps | 319 Mbps | 515 Mbps | 3.83 Gbps | -34.1 dBm | 2.29% | 0 |

The first sample reported **3038 Mbps**; excluding it, the sustained mean is **2175 Mbps** and the steady maximum **2369 Mbps** - about **87% of 2.5 GbE line rate**. Link rate, Wi-Fi 7 (`std=8`) and the 6295 MHz channel were unchanged from the older tests; max supported Tx/Rx remained 5764 Mbps. Lost packets, drops and errors were zero throughout.

## Findings

- **No throughput degradation after standby.** Rx stayed ~**1.26-1.28 Gbps** and Tx ~**3.8-3.9 Mbps** in every run, including immediate wake. No sustained low-throughput or stuck-low-rate period; the same ~1.27 Gbps stream continued through both later standby runs and no restart was needed.
- **The headset can sustain ~2.17 Gbps.** The 2.5 GbE speedtest held ~2.19 Gbps (p50 2185, ~2.17 Gbps excluding the first sample), ~87% of line rate. The old 900 Mbps test was not radio-limited: its link rate was slightly higher (4.16 vs 3.83 Gbps mean), so the ceiling was the test/client/server setup. Thermal status 3 did not reduce throughput: the max test ran at status 3 with the camera already at 30 fps, yet held 2.19 Gbps at ~3.1% retry with zero drops/errors.
- **No packet loss at the measured layer**, and no Wi-Fi speed lock at thermal status 4: WIFI has no HAL hot-throttling thresholds; status 4 aligned with the LRP power-path trip (65 C). The only status-4 run held ~498 Mbps (p5 474, p95 523) at 1.72% retry, zero drops/errors. That run was on the **stock, pre-mod** unit ([thermal mod](thermal-mod.md#status-4-and-wi-fi)).
- **The 42.5% retry at immediate wake is the low-TX denominator artifact.** The first 5 s had only **3.02 TX pps** and **1.28 retry pps**; TX sat at 0.33 pps for 5 s, then ramped to **249 pps** with retry ~**5.3%** by 11 s. Steady-state retry was 18-24 pps.
- **Link rate adapted normally; RSSI dips briefly at wake.** Link speed varied ~1.7-5.2 Gbps without a persistent low-rate state (max Tx/Rx 5764 Mbps); RSSI improved from ~-32 dBm to -28 dBm by 6 s and -21 dBm later, confounded by position/orientation.

The immediate-wake run covers the first moments after standby, but the profiler records link rate, RSSI and packet counters, not ping, jitter or SteamVR transport latency, so a short post-wake spike could still exist unnoticed.

### Practical bitrate guidance

- Measured max **~2.17 Gbps** at **-28.6 dBm** line-of-sight: **1.6 Gbps is ~74% of that ceiling** and ~**37-42% of the 3.8-4.3 Gbps link rate** in good conditions, reasonable when facing the router.
- Normal VRChat/SteamVR play used **~1.17-1.29 Gbps**, retry **4-6%**, zero lost packets/drops/errors; at lower RSSI (-34 to -43 dBm) retry rose to **6-11%** and link occasionally fell to **1.9-2.3 Gbps**, still lossless at ~1.2 Gbps demand.
- On a 1.9-2.3 Gbps link, a 1.6 Gbps stream uses **70-84% of the link rate**, leaving less margin for turning, body blocking or retries than the current ~1.27 Gbps load.
- **Recommendation:** use **1.3-1.4 Gbps** as the comfortable everyday cap for margin while moving/turning; **1.6 Gbps is a plausible upper test cap** at good orientation, but is not movement-safe without testing the worst body/shadowing orientation.
- Dedicated 6 GHz removes contention but is more body/line-of-sight sensitive than 5 GHz; Wi-Fi 7/MLO can help capacity, but these runs do not expose MLO state.

## Caveats

- The max test is from a different day than the 300/600/900 runs, though channel, Wi-Fi standard and max link rate match. The PC 2.5 GbE NIC/router/OpenSpeedTest server can limit the result; the max run was 60 s and the older runs 120 s.
- Three standby runs, all plugged, sequential and not temperature-matched.
- "Rest before" is measured from the previous recording's end, not the actual standby/doze entry.
- Same physical spot, but headset orientation/body position can change RSSI by several dB; no ping, iPerf, jitter or SteamVR streaming-latency samples were captured.

## Useful next experiments

1. Start a recording **immediately** at wake and compare the first 60 s with a pre-standby run.
2. Run continuous ping/iPerf or SteamVR streaming-latency across standby; throughput alone will not show latency spikes.
3. Log `dumpsys wifi`, `cmd wifi status` and Wi-Fi driver state at wake to catch reassociation or power-save transitions.
4. Repeat with a fixed headset position and matched start temperature to separate RSSI/position effects from standby.
5. Repeat the max test with a 10 GbE host/router path and iperf3 to find the headset radio ceiling rather than the PC/NIC ceiling.
