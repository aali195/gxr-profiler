# Display, media & passthrough

[Findings index](../README.md) | [Commands](../COMMANDS.md)

> **Hardware state: STOCK.** All runs on this page are from the unmodified headset, before 2026-11-01. No thermal mod.

Decoder, display/HDR, panel and passthrough findings. Capability is not the same as active state: read the compositor layers and latest codec record, not only advertised flags.

## In plain terms

- The headset supports HDR and 10-bit, but that does not mean video is using them; normal 1080p YouTube played as standard 8-bit SDR.
- 8K HDR at 90 Hz is heavy: the GPU runs near full load and frame rate can drop below the target.
- The display is one wide canvas for both eyes, not two separate screens.
- Passthrough is costly because it runs the cameras and perception pipeline; expect more heat and shorter battery life.
- Brightness is reported on a 0-1 scale, not in nits, so it is not a direct measure of screen brightness.

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
- Advertised HDR/10-bit support is not active output. Use SurfaceFlinger layer dataspaces and color mode, not `mActiveColorMode` or the codec's `hdr-format` alone.
- One wide 7104x3840 canvas is exposed, not one display per eye. The active panel is Sony ECX344A; EDID PNP `QCM` is the Qualcomm bridge, not the panel vendor.
- Passthrough mode comes from `PassthroughStateManager`, not a simple settings flag.
- 8K HDR at 90 Hz is GPU-bound (GPU clock rises to 492-640 MHz); codec `media_hdr_format` can read 0 while active HDR/10-bit layers are present. See [cross-run analysis](cross-run.md).

## Details

### Media & display state

- **Decoder sessions** live in `dumpsys media.metrics`; there is no `media.codec` service on this build (`dumpsys media.codec` is empty). Each `{codec, ...}` record is one MediaCodec session:
  ```
  {codec, (10-19 21:23:48.290), (com.google.android.youtube, 0, 12345),
   (android.media.mediacodec.codec=c2.qti.av1.decoder, android.media.mediacodec.mime=video/av01,
    android.media.mediacodec.mode=video, android.media.mediacodec.hdr-format=0,
    android.media.mediacodec.width=1920, android.media.mediacodec.height=1080, android.media.mediacodec.profile=1)}
  ```
- Naming tells you the path: `c2.qti.*` / `OMX.qcom.*` = Qualcomm hardware, `c2.android.*` / `OMX.google.*` = software. Observed: YouTube AV1 -> `c2.qti.av1.decoder` (hardware), HEVC -> `c2.qti.hevc.decoder`, Vorbis audio -> `c2.android.vorbis.decoder`. Each record also names the decoding process (`media_app`); the YouTube XR app (`com.google.android.apps.youtube.xr`) used `c2.qti.av1.decoder` for 1080p AV1.
- Records expire, so gxr-profiler tracks the set of decoder names seen during a run **and** the latest video session (component, process, MIME, resolution, profile, HDR format).
- **Brightness**: `dumpsys display` -> `Display Brightness=1.0`, `Display SdrBrightness=1.0` (normalized 0-1). `settings get system screen_brightness` reads 255 at maximum.
- **HDR/10-bit**: the panel is HDR-capable (`mSupportedHdrTypes=[2, 3]`, `mMaxLuminance=500`) and 10-bit capable (`ro.surface_flinger.has_HDR_display` / `has_wide_color_display` are `true`), but that is capability, not active state. Active HDR is detected from SurfaceFlinger layer dataspaces (`V0_BT2020_PQ`, `ST2084`, `HLG`); active depth from layer formats (`RGBA_1010102`/`P010` vs `RGBA_8888_UBWC` = 8-bit). On 1080p SDR YouTube the dataspaces were `BT709`/`V0_SRGB`, every layer was `RGBA_8888_UBWC` -> **8-bit active**, `hdr-format=0` -> `hdr_active=0`, with color mode SRGB or DISPLAY_P3 depending on content. gxr-profiler records `disp_bit_depth` (8/10) and `disp_color_mode`.
- Stream depth is inferred from the codec profile (`video/hevc` Main10, `video/av01` Main10, `video/x-vnd.on2.vp9` Profile 2/3, `video/avc` High10). YouTube AV1 profile 1 = **8-bit**.
- Active panel mode while testing: 7104×3840 @ 72 Hz. `device_info.display` records the active mode, HDR types (HDR10 + HLG), 500-nit max luminance, normalized brightness range (0-1, default 0.425), color modes (NATIVE/SRGB/DISPLAY_P3), 10-bit capability, and ALLM / game-content flags.

#### Display quirks (unadvertised / surprising)

| quirk | detail |
|---|---|
| Color mode is compositor-owned, not user-set | `dumpsys display` reports `mActiveColorMode=0` (NATIVE) and `mDefaultDisplayDefaultColorMode=0`; `dumpsys SurfaceFlinger` reports the actual mode: `ColorMode::SRGB (7)` for SDR/UI, `ColorMode::DISPLAY_P3 (9)` for wide-color video. The same YouTube session switched modes while composition stayed `RGBA_8888_UBWC` (8-bit); wide gamut is not 10-bit or HDR. Use the SurfaceFlinger value. |
| Framework and SurfaceFlinger use different mode IDs | `DisplayDeviceInfo` says `modeId 2`, `renderFrameRate 72.00001`; `mActiveSfDisplayMode` says `DisplayMode{id=1, refreshRate=72.00001}`. Both are the active 72 Hz mode; do not join on the ID. |
| One wide canvas, not one display per eye | The built-in display is exposed as 7104×3840. Per-eye modes are 3552×1920 (plus 4736×2560 and 2368×1280), each with 90/72/60 Hz variants. Active mode was 7104×3840 @ 72 Hz. |
| HDR conversion is system-owned | `mHdrConversionMode=HDR_CONVERSION_SYSTEM`, `PreferredHdrOutputType=HDR_TYPE_INVALID`; the panel advertises HDR10 + HLG at `mMaxLuminance=500` (no Dolby Vision). `hdrSdrRatio` is `NaN` even in SDR, so it is not a usable HDR-active signal - use layer dataspaces or the codec's `hdr-format`. |
| Brightness is normalized, not nits | `Display Brightness=1.0` / `SdrBrightness=1.0`, `brightnessDefault=0.425197`, `brightnessMinimum=0.0`, `brightnessMaximum=1.0`; `settings get system screen_brightness` is 0-255. There is no nits readback. |
| Unadvertised SurfaceFlinger props | `has_HDR_display=true`, `has_wide_color_display=true`, `use_color_management=true`, `wcg_composition_dataspace=143261696`, `max_virtual_display_dimension=4096`, `force_hwc_copy_for_virtual_displays=true`, `enable_frame_rate_override=false`, `supports_background_blur=0`. The 4096 virtual-display cap and forced HWC copy limit streaming/capture. |
| XR embedding allowlist | `ro.xr.wm.allowlisted_spatial_embedding_package=com.android.vending` - on this build only the Play Store is allowlisted for spatial embedding. |

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

The active panel is selected at boot by `lcd_id`; this unit is **Sony ECX344A** (`dsi_display0=XR2_SONY_ECX344A`, `lcd_type=SONY_e34400`, second eye `..._SUB`).

**Identify (no root - shows candidates):**
```bash
adb shell "ls /vendor/etc/display | grep XR2"
```

**Identify (root - shows the active panel):**
```bash
adb shell "su -c 'echo TYPE:; cat /sys/class/lcd/panel/lcd_type; echo CMDLINE:; grep -o dsi_display0=[^:]* /proc/cmdline; echo EDID:; strings /sys/class/drm/card0-DSI-1/edid | grep XR2'"
```

Caveats:
- EDID's manufacturer PNP ID is **`QCM` (Qualcomm display bridge)**, not the panel vendor.
- `lcd_type` may show a short driver code (`SONY_e34400`) while `/proc/cmdline` shows the full model (`XR2_SONY_ECX344A`); both refer to the same panel.
- A calibration file only means the firmware *supports* that panel, not that it is installed.

### Passthrough

- `PassthroughStateManager` in XrSystemUI logs the computed requested mode (`Home(requestEnabled=true)`, `Window(requestEnabled=false)`, `SpatialApi`, `Disabled`, `Lockscreen`, `BoundarySetup`) - the best live signal for whether the user sees passthrough. `dumpsys cpm` exposes `XrPassthroughController: passthroughRunning: 1/0`, `passthroughCameraState` and `"Passthrough occlusion %"`.
- The CPM scene has `Passthrough node (Left/Right)` nodes (`type=PASSTHROUGH`, 1500x1500 buffers) under `Passthrough Root`; these are compositor layers, not a simple mode flag.
- Live check on 2026-10-21: mode `Home`, `requestEnabled=true`, `passthroughRunning=1`, camera state 4, occlusion around 20-82%. gxr-profiler records `passthrough` (0/1) and `passthrough_mode`, and tags runs with a passthrough badge when active.
