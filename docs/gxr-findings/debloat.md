# Background processes & debloat

[Findings index](../README.md) | [Commands](../COMMANDS.md) | [Process offenders](processes.md) | [Power modes](modes.md)

> **Hardware state: STOCK.** All runs on this page are from the unmodified headset, before 2026-11-01. No thermal mod.

Reducing CPU/GPU load while using Chronolink/SteamVR is not about typical Samsung bloat. The expensive work is the **XR compositor, camera/perception pipeline, controller HAL and the streaming client itself**.

> Debloat actions are optional manual operations. They modify the headset and are not part of gxr-profiler's read-only capture path.

## In plain terms

- The biggest easy saving is controllers: leaving them on costs about a third of a CPU core; turning them off drops it to zero.
- Keeping hand tracking off helps a little (roughly 17% of a core), but it is a smaller win than controllers.
- Passthrough and the cameras are expensive; expect more heat and lower battery life when they run.
- The headset's own UI and compositor are a normal baseline cost, not runaway bloat.
- Removing Bixby, Samsung apps and most Google apps saves storage and RAM but will not fix CPU/GPU load.

## Tests & results

### Chronolink: where the CPU goes

Five-minute VRChat/SteamVR run, hand tracking **on**, controllers active, passthrough off. Values are `cpu_now_pct` averaged over the run; per-process, not additive.

| Process | Avg current CPU | Peak | Role |
|---|---:|---:|---|
| `dev.chronolink.client` | **50.4%** | 52.2% | streaming client |
| `android.hardware.perceptionhost` | **38.2%** | 57.0% | head/hand/eye perception |
| `vendor.samsung.hardware.secxrcontroller@1.0-service` | **34.9%** | 38.1% | controller HAL |
| `vendor.qti.camera.provider@2.7-service_64` | **32.1%** | 34.7% | camera pipeline |
| `surfaceflinger` | 22.6% | 25.5% | XR compositor |
| `adbd` | 12.7% | 14.3% | **profiler overhead** |
| `[dp_refill_threa]` | 12.1% | 12.6% | display pipeline |
| `logd` | 10.2% | 12.0% | **profiler/log volume** |
| `com.android.systemui` | 10.1% | 21.2% | system UI |
| `[dp_rx_thread_0]` | 10.1% | 12.3% | display pipeline |
| `[kxr-spi-xfer]` | 10.0% | 10.5% | sensor/SPI |
| `com.samsung.android.app.xr.home` | 4.3% | 4.6% | XR home/launcher |
| `com.sec.android.secxrcontrollerservice` | 2.7% | 2.9% | controller app service |
| `system_server` | 2.8% | 8.7% | Android system |

The same run spent roughly **27% combined in `adbd` + `logd` + `logcat` + `sh`** because the profiler was recording with processes/root/logcat/sensors enabled. That CPU is not useful while playing.

### Controllers are a large, reducible cost

| State | Vendor controller HAL avg CPU | Example runs |
|---|---:|---|
| Controllers active | **27-35%** | recent battery/Chronolink runs |
| Controllers idle/off | **0%** | `idle-processes`, `run`, desk-idle runs |

The vendor HAL (`vendor.samsung.hardware.secxrcontroller@1.0-service`) runs even when the user-level `com.sec.android.secxrcontrollerservice` is only ~3%. If you are not using the controllers, turning them off is the single biggest background CPU reduction available in these runs.

### Hand tracking on vs off

The five-minute run had hand tracking **on again** (`cam_hand_fps` present, raw CIB hand ~359 fps); the preceding battery/standby runs had it off.

| State | Perceptionhost avg CPU | Camera provider avg CPU | GPU busy |
|---|---:|---:|---:|
| Hand off battery/standby runs | 18-34% | 20-32% | ~54% |
| Hand on five-minute run | 38% | 32% | ~54% |

The earlier idle hand on/off A/B measured ~17% of a core in `HaT-Context`, ~2 GPU points and 1-2 °C. Keeping hand tracking off is worthwhile, but it is a smaller win than the controller HAL.

### Samsung/Google packages are mostly not running

Across all process snapshots, the only Samsung/Google packages above 1% peak current CPU were:

| Package | Max CPU | Avg CPU | Note |
|---|---:|---:|---|
| `com.google.android.apps.youtube.xr` | 85.3% | 3.6% | only when YouTube is used |
| `com.samsung.android.app.xr.home` | 8.9% | 4.0% | XR home/launcher |
| `com.google.android.gms` | 3.2% | 0.1% | Play services |
| `com.sec.android.secxrcontrollerservice` | 3.0% | 1.1% | controller app service |

Bixby, Samsung account/cloud, Galaxy Store, browser, Notes, messaging, Samsung Pass, most Google apps and Samsung language packs did **not** appear as meaningful CPU consumers. Removing them saves storage/RAM and background wakeups, but will not materially improve Chronolink CPU or GPU by itself.

## Findings

| Area | Finding |
|---|---|
| Controller HAL | **The biggest reducible CPU item is the controller HAL**, not Samsung apps: ~35% of a core when active, dropping to 0 in observed controller-idle runs. |
| Hand tracking | **Costs more than the UI apps**, but less than controllers. Keep it off if you do not need it, especially on long Chronolink sessions. |
| Passthrough/camera | **Expensive**: camera provider ~32% and perceptionhost ~38% even with passthrough off; enabling passthrough adds substantially more. |
| XR baseline | **SystemUI + SurfaceFlinger**, roughly 10% + 23% CPU and large GPU memory. Not safe to disable and not "bloat". |
| Profiler | **Significant**: ~27% combined in adbd/logd/logcat/sh in the five-minute capture. Do not run the heavy profile while trying to play smoothly. |
| Consumer debloat | **Will not fix GPU load.** GPU is dominated by the compositor/XR pipeline and Chronolink; lower render resolution/refresh/bitrate has more effect than disabling Bixby. |

## What to try, in order

1. **Turn the headset controllers off physically** and repeat the five-minute run. If the vendor HAL falls to ~0, that is your biggest win. Keep your alternative PCVR controllers for input.
2. **Keep hand tracking and passthrough off** unless required. Confirm hand tracking stayed off after standby/reboot; the five-minute run had it back on.
3. **Use a lighter profiler profile for real play**: no logcat, no per-process capture, no sensors, no root extras. Record a short test run separately instead of profiling the whole session.
4. **Debloat unused consumer apps** for storage/RAM/background hygiene. Expect little CPU/GPU change.
5. **For GPU**, lower Chronolink/SteamVR render resolution or bitrate, and consider 60 Hz via Battery Saver only if you can tolerate the refresh/camera changes.

## Debloat commands

Prefer `disable-user` first; it is reversible and does not remove the system image:

```powershell
adb shell pm disable-user --user 0 <package>
adb shell pm enable <package>
```

Or remove for user 0 only:

```powershell
adb shell pm uninstall --user 0 <package>
adb shell cmd package install-existing <package>
```

Test one group at a time and restore anything that breaks pairing, sign-in, updates or XR features.

### Controller experiment

```powershell
# reversible: disable the controller app service
adb shell pm disable-user --user 0 com.sec.android.secxrcontrollerservice

# restore
adb shell pm enable com.sec.android.secxrcontrollerservice
```

The vendor HAL has no package name and is not covered by this command. If turning the controllers off physically already drops the HAL to 0, use that as the real test. Do not stop vendor HALs blindly; they are part of XR input.

## Measurement plan

1. Same spot, same battery/AC state, same Chronolink scene.
2. Record a 60 s baseline with hand off + controllers on, then 60 s with controllers physically off. Compare controller HAL, perceptionhost, camera, total CPU and GPU.
3. Record 60 s with hand on vs off at the same controller state.
4. Debloat groups one at a time; expect small CPU changes but watch for broken pairing or updates.
5. Keep the profiler profile light for actual play and use the full profile only for short comparison runs.

## Caveats

- Process CPU is per-process snapshots, not additive; GPU is device-wide busy percentage. Snapshot cadence is 10 s, so short spikes are missed.
- The controller HAL may be required for input even if the app service is disabled. `disable-user`/ `uninstall --user 0` changes user state and can be restored, but a bad vendor disable may require recovery mode/factory reset.
- Debloating removes features, updates and Samsung/Google account integration. Do it intentionally.

## Appendix: package lists

Reference lists for the commands above. Test one group at a time.

### Conservative first pass: unused consumer apps

```text
com.samsung.android.bixby.agent com.samsung.android.bixby.wakeup com.samsung.android.app.settings.bixby com.samsung.android.intellivoiceservice
com.samsung.android.app.contacts com.samsung.android.providers.contacts com.samsung.android.calendar com.samsung.android.app.notes
com.samsung.android.app.reminder com.samsung.android.messaging com.samsung.android.dialer com.samsung.android.incallui
com.samsung.android.app.telephonyui com.sec.android.app.clockpackage com.samsung.android.samsungpass com.samsung.android.samsungpassautofill
com.samsung.android.scloud com.samsung.android.fmm com.samsung.android.svcagent com.samsung.android.voc
com.samsung.android.app.sbrowser com.samsung.android.app.myfiles com.samsung.android.allshare.service.mediashare com.samsung.android.smartmirroring
com.samsung.android.mirroringplayer com.samsung.android.app.sharelive com.samsung.android.mdx.kit com.samsung.android.inputshare
com.sec.mhs.smarttethering com.samsung.android.aircommandmanager com.samsung.android.beaconmanager com.samsung.android.aware.service
com.samsung.android.cidmanager com.samsung.android.cmcconnection com.samsung.android.mcfds com.samsung.android.timezone.updater
com.samsung.SMT
```

Samsung TTS language packs (`com.samsung.SMT.lang_*`) can also be removed if you do not use Samsung TTS. Only remove languages you do not need.

### Optional/advanced Samsung cleanup

```text
com.samsung.android.dqagent com.sec.android.diagmonagent com.sec.android.sdhms
com.sec.android.soagent com.samsung.android.locproxy com.samsung.android.xr.aremojieditor
com.samsung.android.xr.aremojistudio com.samsung.android.xr.avatardatahub com.samsung.android.xr.immersive.avatareditor
com.samsung.xr.mtutorial com.samsung.androidvst.app.tips com.samsung.safetyinformation
com.samsung.android.timezone.data_V com.samsung.android.providers.trash com.samsung.android.mtp
```

`com.samsung.android.game.gos` is a special case: disabling Game Optimizing Service may change performance/thermal policy. Test it separately rather than grouping it with normal debloat.

### Google apps likely unused

```text
com.google.android.apps.bard com.google.android.apps.docs com.google.android.apps.maps
com.google.android.apps.messaging com.google.android.apps.photos com.google.android.apps.photosxr
com.google.android.apps.tachyon com.google.android.gm com.google.android.videos
com.google.android.googlequicksearchbox com.google.android.apps.immersiveviewxr com.google.vr.sceneviewerxr
```

Keep Play Store/GMS/WebView unless you intentionally want to lose app installs, updates and account-dependent features.

### Do not disable

```text
com.android.systemui
com.android.openxr.broker
com.android.xranchormanager
com.google.android.gms
com.google.android.gsf
com.android.webview
com.google.android.webview
com.google.xr.perception.inputserver
com.google.xr.facetracking.calibration
com.samsung.fitting.eyetracking.calibration
com.samsung.android.app.xr.home
com.samsung.android.app.xr.vstcontrollerui      # controller UI, unless you accept the risk
com.samsung.android.vst.batterysavingsettings
com.samsung.android.networkstack
com.samsung.android.wifi.*                       # WiFi overlays/resources
com.qualcomm.*                                   # XR/display/audio/input HALs
vendor.*                                         # hardware services
```

Disabling the wrong `vendor`/Qualcomm/XR component can break display, tracking, audio or input with no easy recovery short of a factory reset.
