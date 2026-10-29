# Display, media & passthrough

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Decoder, display/HDR, panel and passthrough findings. Capability is not the same as active state:
read the compositor layers and latest codec record, not only advertised flags.

## Tests & results

Probed 2026-10-21 during YouTube XR 1080p SDR playback; the 8K HDR result is from 2026-10-24.

| Probe | Observed result |
|---|---|
| `dumpsys media.metrics` | YouTube XR 1080p AV1 with `c2.qti.av1.decoder`, HDR format 0 |
| `dumpsys media.codec` | empty on this build |
| active display | 7104x3840 @ 72 Hz; per-eye candidates include 3552x1920 |
| SDR YouTube layers | `BT709`/`V0_SRGB`, `RGBA_8888`, 8-bit, `hdr_active=0` |
| display vs SurfaceFlinger color | display reports NATIVE; SurfaceFlinger reports SRGB (7) / DISPLAY_P3 (9) |
| mode IDs | display `modeId 2` vs SF `DisplayMode id=1`, both 72 Hz |
| panel identification | candidates Sony/Samsung/BOE; active Sony ECX344A |
| passthrough | `Home`, `requestEnabled=true`, `running=1`, camera state 4, occlusion 20-82% |
| 8K HDR playback | 7680x4320 AV1, 10-bit, 90 Hz, GPU 92-99%, 70/90 fps, `media_hdr_format=0` |

## Findings

- `media.metrics` is cumulative since boot; track both the latest session and the set of codecs.
- Advertised HDR/10-bit support is not active HDR/10-bit output.
- Use SurfaceFlinger dataspaces for active HDR and color mode.
- Trust SurfaceFlinger color mode over `mActiveColorMode`.
- One wide 7104x3840 canvas is exposed, not one display per eye.
- Active panel is Sony ECX344A; EDID PNP `QCM` is the Qualcomm bridge, not the panel vendor.
- Passthrough mode comes from `PassthroughStateManager`, not a simple settings flag.
- 8K HDR at 90 Hz is GPU-bound (the GPU clock itself rises to 492-640 MHz); codec
  `media_hdr_format` can read 0 while active HDR and 10-bit layers are present.
  See [cross-run analysis](cross-run.md).

## Details

### Media & display state

- **Decoder sessions** live in `dumpsys media.metrics`; there is no `media.codec` service on this
  build (`dumpsys media.codec` is empty). Each `{codec, ...}` record is one MediaCodec session:
  ```
  {codec, (10-19 21:23:48.290), (com.google.android.youtube, 0, 12345),
   (android.media.mediacodec.codec=c2.qti.av1.decoder,
    android.media.mediacodec.mime=video/av01,
    android.media.mediacodec.mode=video, android.media.mediacodec.hdr-format=0,
    android.media.mediacodec.width=1920, android.media.mediacodec.height=1080,
    android.media.mediacodec.profile=1)}
  ```
- Naming tells you the path: `c2.qti.*` / `OMX.qcom.*` = Qualcomm hardware,
  `c2.android.*` / `OMX.google.*` = software. Observed: YouTube AV1 →
  `c2.qti.av1.decoder` (hardware), HEVC → `c2.qti.hevc.decoder`, Vorbis audio →
  `c2.android.vorbis.decoder`.
- Each record also names the decoding process (`media_app`); during testing YouTube's XR app
  (`com.google.android.apps.youtube.xr`) used `c2.qti.av1.decoder` for 1080p AV1.
- `media.metrics` is cumulative since boot and expires old records, so gxr-profiler tracks the set of
  decoder names seen during a run **and** the latest video session (component, process, MIME,
  resolution, profile, HDR format).
- **Brightness**: `dumpsys display` → `Display Brightness=1.0`, `Display SdrBrightness=1.0`
  (normalized 0-1). `settings get system screen_brightness` reads 255 at maximum.
- **HDR**: the panel is HDR-capable (`mSupportedHdrTypes=[2, 3]`, `mMaxLuminance=500`), but that is
  not the same as HDR being used. Active HDR is detected from SurfaceFlinger layer dataspaces
  (`V0_BT2020_PQ`, `ST2084`, `HLG`). On a 1080p SDR YouTube stream the dataspaces were
  `BT709`/`V0_SRGB` and the codec reported `hdr-format=0` → `hdr_active=0`.
- **10-bit**: the display advertises HDR10/HLG and Display P3, and
  `ro.surface_flinger.has_HDR_display` / `has_wide_color_display` are `true`, so the panel/pipeline
  is 10-bit capable. Active output is whatever the composer uses: during YouTube every layer was
  `RGBA_8888_UBWC` → **8-bit active**, with color mode SRGB or DISPLAY_P3 depending on content.
  For HDR/wide-color content look for `RGBA_1010102`/`P010` formats; gxr-profiler records
  `disp_bit_depth` (8/10) and `disp_color_mode`.
- Stream depth is inferred from the codec profile (`video/hevc` Main10, `video/av01` Main10,
  `video/x-vnd.on2.vp9` Profile 2/3, `video/avc` High10). YouTube AV1 profile 1 = **8-bit**.
- Color modes: NATIVE (0), SRGB (7), DISPLAY_P3 (9); the current mode is in
  `dumpsys SurfaceFlinger` and can switch between SRGB (UI/SDR) and DISPLAY_P3 (wide-color
  content) during the same app session.
- Active panel mode while testing: 7104×3840 @ 72 Hz. `device_info.display` records the active
  mode, HDR types (HDR10 + HLG), 500-nit max luminance, normalized brightness range
  (0-1, default 0.425), color modes (NATIVE/SRGB/DISPLAY_P3), 10-bit capability, and ALLM /
  game-content flags.

#### Display quirks (unadvertised / surprising)

- **Two sources disagree about color mode.** `dumpsys display` reports `mActiveColorMode=0`
  (NATIVE) and `mDefaultDisplayDefaultColorMode=0`, while `dumpsys SurfaceFlinger` reports the
  actual mode: `ColorMode::SRGB (7)` for SDR/UI and `ColorMode::DISPLAY_P3 (9)` while a wide-color
  video was playing. gxr-profiler uses the SurfaceFlinger value; do not trust `mActiveColorMode`.
- **The mode changes with content, not a user setting.** The same YouTube session was observed in
  SRGB and later in DISPLAY_P3, while composition stayed `RGBA_8888_UBWC` (8-bit). Wide gamut is
  not the same as 10-bit or HDR.
- **Framework and SurfaceFlinger use different mode IDs.** `DisplayDeviceInfo` says `modeId 2`,
  `renderFrameRate 72.00001`; `mActiveSfDisplayMode` says `DisplayMode{id=1,
  refreshRate=72.00001}`. Both are the active 72 Hz mode - do not join on the ID.
- **One wide canvas, not one display per eye.** The built-in display is exposed as 7104×3840.
  Per-eye modes are 3552×1920 (plus 4736×2560 and 2368×1280), each with 90/72/60 Hz variants.
  The active mode was 7104×3840 @ 72 Hz.
- **HDR conversion is system-owned.** `mHdrConversionMode=HDR_CONVERSION_SYSTEM`,
  `PreferredHdrOutputType=HDR_TYPE_INVALID`; the panel advertises HDR10 + HLG at
  `mMaxLuminance=500` (no Dolby Vision). `hdrSdrRatio` is `NaN` even in SDR, so it is not a
  usable HDR-active signal - use layer dataspaces or the codec's `hdr-format`.
- **Brightness is normalized, not nits.** `Display Brightness=1.0` / `SdrBrightness=1.0`,
  `brightnessDefault=0.425197`, `brightnessMinimum=0.0`, `brightnessMaximum=1.0`;
  `settings get system screen_brightness` is 0-255. There is no nits readback.
- **Unadvertised SurfaceFlinger props** (relevant to PCVR/capture): `has_HDR_display=true`,
  `has_wide_color_display=true`, `use_color_management=true`,
  `wcg_composition_dataspace=143261696`, `max_virtual_display_dimension=4096`,
  `force_hwc_copy_for_virtual_displays=true`, `enable_frame_rate_override=false`,
  `supports_background_blur=0`. The 4096 virtual-display cap and forced HWC copy are practical
  limits for streaming/capture.
- **XR embedding allowlist:** `ro.xr.wm.allowlisted_spatial_embedding_package=com.android.vending`
  - on this build only the Play Store is allowlisted for spatial embedding.

Reproduce:

```bash
adb shell "dumpsys display | grep -E 'DisplayDeviceInfo|mActiveColorMode|mActiveSfDisplayMode|mHdrConversionMode'"
adb shell "dumpsys SurfaceFlinger | grep -E 'Current color mode|dataspace=|format:' | sort -u"
adb shell "getprop | grep -E 'surface_flinger|wcg|virtual_display|frame_rate'"
```

### Panel identification

The firmware ships **three** device-specific XR2 panel calibrations:

| panel | calibration file |
|---|---|
| Sony ECX344A | `qdcm_calib_data_XR2_SONY_ECX344A.json` (+ `_SUB`) |
| Samsung S6E8JN0 / AMM130GZ01 | `qdcm_calib_data_XR2_S6E8JN0_AMM130GZ01.json` (+ `_SUB`) |
| BOE VX135KDP | `qdcm_calib_data_XR2_BOE_VX135KDP.json` (+ `_SUB`) |

The active panel is selected at boot by `lcd_id`. The unit used here is **Sony ECX344A**
(`dsi_display0=XR2_SONY_ECX344A`, `lcd_type=SONY_e34400`, second eye `..._SUB`).

**Identify (no root - shows candidates):**
```bash
adb shell "ls /vendor/etc/display | grep XR2"
```

**Identify (root - shows the active panel):**
```bash
adb shell "su -c 'echo TYPE:; cat /sys/class/lcd/panel/lcd_type; echo CMDLINE:; grep -o dsi_display0=[^:]* /proc/cmdline; echo EDID:; strings /sys/class/drm/card0-DSI-1/edid | grep XR2'"
```

Caveats:
- EDID's manufacturer PNP ID is **`QCM` (Qualcomm display bridge)**, not the panel vendor - do not
  use it to identify the panel.
- `lcd_type` may report a short driver code (`SONY_e34400`) while `/proc/cmdline` reports the full
  model (`XR2_SONY_ECX344A`); both refer to the same panel.
- Presence of a calibration file only means the firmware *supports* that panel, not that it is
  installed.

### Passthrough

- `PassthroughStateManager` in XrSystemUI logs the computed requested mode, e.g.
  `Home(requestEnabled=true)`, `Window(requestEnabled=false)`, `SpatialApi`, `Disabled`,
  `Lockscreen`, `BoundarySetup`. This is the best live signal for whether the user sees passthrough.
- `dumpsys cpm` exposes `XrPassthroughController: passthroughRunning: 1/0` plus
  `passthroughCameraState` and the current `"Passthrough occlusion %"`.
- The CPM scene also has `Passthrough node (Left/Right)` nodes (`type=PASSTHROUGH`,
  1500x1500 buffers) under `Passthrough Root`; these are compositor layers, not a simple mode flag.
- Live check on 2026-10-21: mode `Home`, `requestEnabled=true`, `passthroughRunning=1`,
  camera state 4, occlusion around 20-82%. gxr-profiler records `passthrough` (0/1) and
  `passthrough_mode`, and tags runs with a passthrough badge when active.
