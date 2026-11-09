# Thermal mod comparison reports

Self-contained `gxr-profiler` HTML reports for the seven before/after tests in
[thermal mod before/after](../../thermal-mod.md).

- **Before** runs are from the **stock, unmodified** headset (2026-10-31).
- **After** runs are from the **SoC thermal-modded** headset (phase-change pads + copper shims,
  2026-11-06/07).
- Between tests the headset was put down to cool until the CPU was around **50 C**.
- Room-temperature readings were **~25 C before** and **~24 C after**; these are rough,
  uncalibrated readings.
- Each report contains both runs, all charts/tables, and the process data inlined. No internet or
  Python is needed after download.
- Exported reports redact common Wi-Fi/device identifiers.

## Open a report

GitHub does **not** render HTML files in the repository file viewer; clicking an `.html` file shows
its source. Use one of these instead:

- **Rendered (external preview):** click the `Rendered` link in the table below.
- **Local:** download the `.html` file and open it in a browser (fully offline).

| Test | Scenario | Before (stock) | After (modded) | Report |
|---:|---|---|---|---|
| 1 | idle + passthrough + hands | `before-1-idle-passthrough-hands` | `after-1-idle-passthrough-hands` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-1-idle-passthrough-hands-stock-vs-mod.html) / [HTML](test-1-idle-passthrough-hands-stock-vs-mod.html) |
| 2 | idle on desk | `before-2-idle-on-desk` | `after-2-idle-on-desk` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-2-idle-on-desk-stock-vs-mod.html) / [HTML](test-2-idle-on-desk-stock-vs-mod.html) |
| 3 | idle + hands, VR | `before-3-idle-hands-vr` | `after-3-idle-hands-vr` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-3-idle-hands-vr-stock-vs-mod.html) / [HTML](test-3-idle-hands-vr-stock-vs-mod.html) |
| 4 | YouTube 4K SDR | `before-4-youtube-no-hdr-hand-vr` | `after-4-youtube-no-hdr-hand-vr` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-4-youtube-4k-sdr-stock-vs-mod.html) / [HTML](test-4-youtube-4k-sdr-stock-vs-mod.html) |
| 5 | YouTube 8K HDR | `before-5-youtube-hdr-hand-vr` | `after-5-youtube-hdr-hand-vr` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-5-youtube-8k-hdr-stock-vs-mod.html) / [HTML](test-5-youtube-8k-hdr-stock-vs-mod.html) |
| 6 | Virtual Desktop H.264, ~500 Mbps | `before-6-virtualdesktop-h264-rampage-controllers-vrchat-fish-world-night` | `after-6-virtualdesktop-h264-rampage-controllers-vrcjat-fish-night-500mbps` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-6-virtual-desktop-500mbps-stock-vs-mod.html) / [HTML](test-6-virtual-desktop-500mbps-stock-vs-mod.html) |
| 7 | Chronolink/SteamVR ASTC | `before-7-chronolink-astc-controllers-vrchat-fish-world-night` | `after-7-chronolink-astc-controllers-vrchat-fish-world-night` | [Rendered](https://htmlpreview.github.io/?https://github.com/aali195/gxr-profiler/blob/main/docs/gxr-findings/reports/thermal-mod/test-7-chronolink-astc-stock-vs-mod.html) / [HTML](test-7-chronolink-astc-stock-vs-mod.html) |

The `Rendered` links use `htmlpreview.github.io`. If that service is unavailable, download the
matching HTML file and open it locally.
