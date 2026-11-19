# Black level floor

[Findings index](../README.md#findings-index) | [Profiler guide](../../PROFILER.md) | [Commands](../../COMMANDS.md)

> **Hardware state: MODDED.** SoC thermal-modded headset (phase-change pads + copper shims); tests on 2026-11-19.

Investigation of the Galaxy XR micro-OLED black floor. The panel can show true black at boot, but after Android/XR takes over the black field is slightly lifted. This page records the read-only probes, the panel gamma/ELVSS experiments, and what was ruled out.

## In plain terms

- The active panel is a Sony ECX344A micro-OLED rated at 100,000:1, so true black is expected.
- The XR compositor is sending pure black (`0,0,0`) for a black Chrome tab; the lift is after the compositor.
- The boot logos are true black. The lift appears when the normal Android/XR display state takes over.
- The exposed panel gamma tables (`B4`, `D1`) and the ELVSS toggle did not change the actual black floor.
- The only effective software control found is overall brightness/dimming. Lower brightness makes the whole image dimmer and the black field look darker, but does not improve contrast.
- The `D1` `BB` block is per-panel calibration. Changing it produced ring artifacts, so it must not be touched.

## Tests & results

Probed 2026-11-19 on `I610UEU2AZF3`, KernelSU root, display at maximum brightness (`Display Brightness=1.0`, `screen_brightness=255`).

| Probe                                    | Observed result                                                       |
| ---------------------------------------- | --------------------------------------------------------------------- |
| active panel                             | `XR2_SONY_ECX344A` (`SONY_e34400`), both eyes                         |
| Sony ECX344A spec                        | 1,000 nits at 20% duty, 100,000:1 contrast                            |
| DT `qcom,mdss-dsi-panel-blackness-level` | `0x17F6` -> 6134 -> **0.6134 nits**                                   |
| DT peak / average brightness             | `0x561AF8` -> **564.4 nits**; `0x1E8480` -> **200 nits**              |
| DT HDR primaries                         | match the Qualcomm Sharp reference DTSI, not measured for this panel  |
| QDCM `PostBlendGC` / `PostBlendIGC`      | both map input `0` -> output `0`                                      |
| XR compositor capture, black Chrome tab  | 2880x2880, every pixel `0`                                            |
| Chrome layer                             | `BT709 sRGB Full range`, identity color transform                     |
| SurfaceFlinger color                     | `ColorMode::SRGB (7)`, identity transform                             |
| boot logos                               | pure black                                                            |
| after boot / in apps                     | black field slightly lifted, panel edges visible                      |
| brightness dependence                    | lift decreases with brightness, residual remains at minimum           |
| `B4` at max brightness                   | `bl_level 255, idx 7, WRDISBV ff`; value `33 23 32`                   |
| `B4 28 E2 8E`                            | slight overall dimming; no black-floor change                         |
| `B4 1E A1 EA`                            | everything dimmer; apparent black floor lower proportional to dimming |
| `D1` first byte `0D` -> `00`             | no visible change                                                     |
| `D1` `BB` byte `0D` -> `00`              | ring layers, different per panel, dark-blue thick rings; restored     |
| ELVSS toggle `1`                         | `ss_brightness_dcs` re-sent; no visible change                        |
| `read_mtp` (`CA/C8/C9/B3/B4/D1`)         | 20 zero bytes each                                                    |
| `gamma_flash` / `gamma_check`            | empty                                                                 |

## Findings

- The XR compositor output for a pure black tab is `0,0,0`; the lift is not in the app or compositor color math.
- QDCM and SurfaceFlinger are full-range and map 0 to 0; there is no software black offset in the color pipeline.
- The panel is rated 100,000:1. The DT `blackness-level` is a copied reference value and is not the panel's real limit.
- The boot logos prove the panel and early display path can do true black; the lift appears after the normal Android/XR display state is applied.
- `B4` is an overall gamma/brightness reference. It dims/brightens the whole image, including the black floor, but does not change contrast.
- `D1` first byte `0D` is not the black level; changing it had no visible effect.
- `D1` `BB` is per-panel calibration/uniformity data. Changing it created ring artifacts, so it must not be modified.
- The `set_elvss` sysfs node is a boolean override, not a voltage. The toggle re-sent the brightness/ELVSS path but produced no visible change.
- The MTP read helper is a placeholder on this panel. `samsung,mtp_read_sysfs_rx_cmds_revA` reads command `0x00`; it returns zeros even with the panel on.
- No exposed software control changed the actual black floor. The remaining causes are panel ELVSS/internal black-level programming or optical/lens glare.
- The only safe software lever is brightness. Lower brightness makes the black field look darker but reduces overall luminance and does not improve contrast.

## Details

### Display path

The black-level complaint was checked at three layers:

1. **App/compositor**: `dumpsys SurfaceFlinger` showed the Chrome layer as `BT709 sRGB Full range` with an identity `colorTransform`. The XR compositor capture for a full-screen black tab was 2880x2880 and every sampled pixel was `0,0,0`.
2. **Framework color**: `dumpsys display` reported `ColorMode::SRGB (7)`, `Display Brightness=1.0`, `mAppliedDimming=false`.
3. **Panel/DT**: the QDCM gamma tables (`PostBlendGC`, `PostBlendIGC`) both map input `0` to output `0`.

So the lift is after the compositor, in the panel/display path or optics.

The CPM config at `/product/etc/xr/device_config.json` has `local_tone_mapping=true` and `background_box_filter=true`, but the `libvulkan_compositor` shader names containing `local_tone_mapping` are all `passthrough_*`. That path is passthrough-camera related, not the rendered scene.

### Panel identity and HDR metadata

The active panel is selected at boot by `lcd_id`:

```text
msm_drm.dsi_display0=XR2_SONY_ECX344A:
msm_drm.dsi_display1=XR2_SONY_ECX344A_SUB:
lcd_type=SONY_e34400
```

The DT panel node is:

```text
/proc/device-tree/soc/qcom,mdss_mdp@ae00000/XR2_SONY_ECX344A
```

HDR metadata in that node:

```text
qcom,mdss-dsi-panel-blackness-level = 0x17F6  -> 6134 -> 0.6134 nits
qcom,mdss-dsi-panel-peak-brightness  = 0x561AF8 -> 564.4 nits
qcom,mdss-dsi-panel-average-brightness = 0x1E8480 -> 200 nits
```

The HDR primaries (`14880 15935 32435 16555 14945 30910 7790 3415`) and the blackness value match Qualcomm's generic Sharp reference panel DTSI. They are not measured values for the Sony ECX344A. The Sony datasheet gives 100,000:1 contrast and 1,000 nits at 20% duty, so the DT 0.6134-nit value is not the panel's real limit.

### Panel gamma path

`XR2_SONY_ECX344A_init` points the active panel at the `.9729` variant of `ss_brightness_gamma_mode2`. That function loads a 3-byte value from `.rodata` at `0x6d998` by brightness index and writes it 20 times into the panel `B4` gamma packet.

Table:

| index | raw value | bytes written to `B4` |
|---:|---:|---|
| 0 | `0x1EA1EA` | `1E A1 EA` |
| 1 | `0x28E28E` | `28 E2 8E` |
| 2-7 | `0x332332` | `33 23 32` |

At maximum brightness the driver logs:

```text
ss_brightness_gamma_mode2 : bl_level: 255, idx = 7, WRDISBV: ff
```

so the active `B4` value is `33 23 32`.

The `B4` test sequence was sent over debugfs DCS:

```text
/sys/kernel/debug/dri/0/DSI-1/tx_cmd   # left
/sys/kernel/debug/dri/1/DSI-2/tx_cmd   # right
```

The sequence was the stock `51 FF`, unlock, `B4`, lock. Results:

- `28 E2 8E` (index 1): slight overall dimming, no black-floor change.
- `1E A1 EA` (index 0): everything dimmer; the black floor looked lower, but proportionally to the dimming.
- Stock `33 23 32` restored after each test.

### D1 table

The `display_on` command contains a 177-byte `D1` table:

```text
D1: 0D FF 00 FF 00 03 0C 1E 38 5B 89 C0 FF ...
```

Two targeted tests were run, restoring the stock table after each:

- First byte `0D` -> `00`: no visible change.
- `BB` block byte `0D` -> `00` (payload index 172): produced ring-shaped layers, positioned differently on each eye, plus two thick dark-blue rings. This is consistent with per-panel calibration/uniformity data, not a black-level control. Restored immediately.

Do not modify the `D1` `BB` block.

### ELVSS

`/sys/devices/virtual/lcd/panel/set_elvss` and `/sys/devices/virtual/lcd/panel1/set_elvss` are write-only. The driver's `ss_set_elvss_store` parses an integer, sets an override flag, and conditionally re-sends the brightness/ELVSS path.

Writing `1` produced:

```text
ss_set_elvss_store : (1)
ss_brightness_gamma_mode2 : bl_level: 255, idx = 7, WRDISBV: ff
ss_brightness_dcs : level:255 candela:1000CD hbm:0 acl:(0|0) itp:TABLE
```

There was no visible black-floor change. Writing `0` cleared the flag; the panel was already off, so the driver logged `Panel is not ready. Panel State(0)` and did not re-send the packet. The flag is `0`, and the next panel-on or reboot reinitializes stock.

### MTP read path

`/sys/devices/virtual/lcd/panel/read_mtp` is a read trigger in the form:

```text
echo <addr> <offset> <len> > read_mtp
```

The DT read command is:

```text
samsung,mtp_read_sysfs_rx_cmds_revA = 06 01 00 00 00 00 01 00 00 00
```

That is a DCS read of command `0x00` with length 1. The address/offset are only passed as parameters. Reads of `CA`, `C8`, `C9`, `B3`, `B4`, and `D1` all returned 20 zero bytes, even with the panel on. `gamma_flash` and `gamma_check` were empty. The MTP helper is a placeholder on this panel and cannot read the gamma table.

## Reproduce

Read-only probes:

```bash
adb shell "dumpsys display | grep -E 'Display Brightness|mActiveColorMode|mAppliedDimming'"
adb shell "dumpsys SurfaceFlinger | grep -E 'Current color mode|dataspace=|colorTransform'"
adb shell "su -c 'grep -o dsi_display0=[^:]* /proc/cmdline; cat /sys/class/lcd/panel/lcd_type'"
adb shell "su -c 'od -An -tx1 -v /proc/device-tree/soc/qcom,mdss_mdp@ae00000/XR2_SONY_ECX344A/qcom,mdss-dsi-panel-blackness-level'"
adb shell "su -c 'dmesg | grep -E \"ss_brightness_gamma_mode2|ss_set_elvss_store|ss_brightness_dcs\"'"
```

The XR compositor capture used by the profiler is 2880x2880; a `screencap` of a full-screen black tab is all zero.

The `B4` and `D1` write sequences are not read-only. They were sent to the debugfs `tx_cmd` nodes and restored from the stock DT command bytes.

## Caveats

- All black-floor observations are visual. No camera or colorimeter measurement was made, so "lower/higher" is subjective.
- Tests were at maximum brightness unless noted. The panel's brightness index changes the `B4` value, so compare at a fixed brightness.
- `screencap` captures the compositor/CPM capture, not the photons reaching the eye.
- The `B4`/`D1` writes are runtime DCS only. No MTP, flash, partition, or original file was written.
- Stock `B4` and `D1` were re-sent after each test. A full reboot is the guaranteed reset.
- The `D1` `BB` block is per-panel calibration; it must not be changed.
- The DT `blackness-level` is a reference copy, not a measurement of this unit.

## Next experiments

1. Measure a pure black pattern with a camera/colorimeter at 100%, 50%, and 20% brightness. This separates panel emission from lens glare/ambient light.
2. Compare a pure black 2D image with the XR home environment to confirm whether the home scene's sky/background contributes.
3. If a panel datasheet or Sony/Samsung service source becomes available, identify a real ELVSS or black-level register. Do not guess at the `D1` calibration block.
4. If a module is built now, restrict it to a brightness cap. It is safe, boot-scoped, and reversible, but it only reduces the brightness-dependent part.

## Module implications

- Do not ship a `B4` or `D1` "black level" patch. `B4` changes overall gamma/brightness; `D1` `BB` is calibration data.
- A `gxr-black-level` prototype should be brightness-only:
  - boot-scoped `service.sh` apply
  - `action.sh on/off/status`
  - `uninstall.sh` restore
  - no MTP/flash/partition writes
  - reboot as the last resort
- If a safe ELVSS/black-level command is found later, use runtime DCS via `tx_cmd`, keep the exact stock command bytes, and restore on `off`/uninstall.
