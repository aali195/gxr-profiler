# Audio

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Speaker/microphone paths, routing and codec findings. Output is PCM; source codecs can be stale
and are reported only when recent.

## Tests & results

Probed 2026-10-21 during YouTube XR playback.

| Probe | Observed result |
|---|---|
| `media.audio_flinger` active output | XR_SPATIALIZER, 48 kHz stereo, `PCM_8_24_BIT`, speaker, underruns 0 |
| write latency | ~134 ms on deep-buffer output |
| `media.audio_policy` | speaker PCM16 + PCM_8_24 @ 48 kHz; mic PCM16 8-48 kHz |
| `dumpsys audio` | YouTube XR AudioTrack 48 kHz stereo; `STREAM_MUSIC` 9/15 |
| codec age | `media.metrics` records can be hours stale; `media.codec` is empty |

## Findings

- Speaker output is 24-bit; the source AudioTrack can still be 16-bit.
- Spatialization happens in the mixer, below the AudioTrack.
- Media uses deep buffer (~110 ms advertised, ~134 ms measured), not low latency.
- Speaker is 48 kHz only; mic capture is PCM16 only.
- Source codecs are shown only when the record is <=300 s old.
- Dolby DAP, Fluence, dynamics/loudness and other DSP blocks are loaded but mostly inactive.

## Details

- **Speaker**: `dumpsys media.audio_flinger` shows the active output thread (XR_SPATIALIZER):
  48 kHz, stereo, HAL format `AUDIO_FORMAT_PCM_8_24_BIT` (24-bit in a 32-bit container), device
  `AUDIO_DEVICE_OUT_SPEAKER`, master volume 1.0, underruns 0. Idle output threads are 16-bit
  (VOIP/telephony).
- **Latency**: `Threadloop write latency stats` averaged ~134 ms on the active deep-buffer output.
  This is the buffer write path, not end-to-end latency.
- **Playback**: the `dumpsys audio` focus stack names the app (YouTube XR); `players:` lists one
  started AudioTrack at 48 kHz stereo; `STREAM_MUSIC` volume was 9/15 (60%), not muted.
- **Mic**: `dumpsys audio` reports `mic mute FromSwitch/Restrictions/Api/system` (all false when
  unmuted); `media.audio_flinger` has no input thread while idle. When active, the input thread
  gives device (`AUDIO_DEVICE_IN_BUILTIN_MIC` / `BACK_MIC`), source (`MIC`, `CAMCORDER`, ...),
  PCM format, rate and channels.
- **Capabilities** (`dumpsys media.audio_policy`): Speaker PCM_16_BIT + PCM_8_24_BIT @ 48 kHz
  stereo; Built-In Mic / Back Mic PCM_16_BIT at 8-48 kHz. No Bluetooth/A2DP device was connected
  during testing, so Bluetooth codecs (SBC/AAC/aptX/LDAC) are not captured.
- **Codecs**: `dumpsys media.metrics` audio records (e.g. `c2.android.vorbis.decoder`,
  `audio/vorbis`, 48 kHz, 2 ch) can be stale; gxr-profiler records the newest record's age and the UI
  shows a source codec only if it was seen within 5 minutes. Output is always PCM (uncompressed).

### Audio quirks (unadvertised / surprising)

- **24-bit is the output pipe, not the source.** The speaker HAL runs `PCM_8_24_BIT` (24-bit in a
  32-bit container), while the active AudioTrack is `PCM_16_BIT` (format 0x1). `audio_out_bits`
  (24) and the player/source format (16) are different things - do not report them as one number.
- **All output threads are XR_SPATIALIZER.** `AudioOut_D`, `AudioOut_15`, `AudioOut_1D` and
  `AudioOut_25` all report `type 9 (XR_SPATIALIZER)`, including the VOIP/telephony threads. The
  active media thread is `AudioOut_D` with
  `AUDIO_OUTPUT_FLAG_PRIMARY|AUDIO_OUTPUT_FLAG_DEEP_BUFFER`.
- **The player says it is not spatialized, but the mixer is.** The started AudioTrack reports
  `FormatInfo{isSpatialized=false, channelMask=0x3, sampleRate=48000}`, while the output thread
  lists `XrSpatialMixer tracks` and the flinger log receives `setXrSpatialAudioEnabledApp` and
  `setMasterBalance`. Spatialization happens below the AudioTrack, not in the player.
- **Unadvertised DSP stack.** `media.audio_flinger` loads Dolby DAP (`object_dap`, `dap`,
  `HMD_1.0.0.0_r1`), Qualcomm Fluence noise suppression + AEC, dynamics processing, loudness
  enhancer, downmix, visualizer and reverb. Flags: `mDsEnable=0`, `mDsProfile=-1`,
  `mDlbGameEnable=0`, `mDlbContentProcEnabled=1` (content processing enabled, no Dolby profile).
- **Media uses deep buffer, not low-latency.** The policy advertises `deep_buffer` with
  `Latency: 110`; flinger measured ~134 ms threadloop write latency. `direct_pcm` and
  `hifi_playback` profiles exist but were unused. AAudio MMAP is enabled
  (`aaudio.mmap_policy=1`, `aaudio.mmap_exclusive_policy=1`) and `tunnel.audio.encode=true`; an
  app can still choose a different path.
- **Speaker is 48 kHz only.** The speaker profile supports PCM_16_BIT and PCM_8_24_BIT at 48 kHz
  stereo; there is no 44.1 kHz speaker profile. Mic inputs (Built-In + Back) are PCM_16_BIT only,
  8-48 kHz - there is no 24-bit capture path.
- **XR mic denoiser allowlist.** `persist.audio.xrdenoiser.list=com.google.costar_helper,
  com.google.android.googlequicksearchbox` - an unadvertised per-app denoiser list.
- **Audio routing/mute knobs.** `audio.sys.mute.latency.factor=2`,
  `audio.sys.routing.latency=0`, `audio.sys.offload.pstimeout.secs=3`,
  `audio.sys.noisy.broadcast.delay=500`, and `media.stagefright.audio.deep=false` (despite the
  active deep_buffer output).
- **Codec records can be hours stale.** There is no `media.codec` service on this build
  (`dumpsys media.codec` is empty); audio/video codec records live in `media.metrics` and are
  emitted on release/expiry. gxr-profiler stores the record age and shows a source codec only if it is
  <= 300 s old.

Reproduce:

```bash
adb shell "dumpsys media.audio_flinger | grep -E 'Output thread|HAL format|Threadloop write latency|XrSpatialMixer|mDs|mDlb|Library'"
adb shell "dumpsys media.audio_policy | grep -E 'deep_buffer|direct_pcm|hifi_playback|Built-In Mic|sampling rates'"
adb shell "dumpsys audio | grep -E 'players:|AudioPlaybackConfiguration|mic mute|STREAM_MUSIC|streamVolume'"
adb shell "getprop | grep -E 'aaudio|tunnel.audio|audio.sys|xrdenoiser|surface_flinger'"
```
