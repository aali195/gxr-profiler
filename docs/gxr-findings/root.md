# Root

[Findings index](../README.md) | [Commands](../COMMANDS.md)

> **Hardware state: MIXED - STOCK BEFORE 2026-11-01, MODDED AFTER.** Runs before 2026-11-01 are from the unmodified headset. Runs from 2026-11-01 onward, including the in-between and after runs, are from the SoC thermal-modded headset (phase-change pads + copper shims). Thermal status 4 was only observed on the stock unit.

What read-only KernelSU access unlocks, and what it still cannot see.

## In plain terms

- Optional root access adds fan speed, per-app disk activity, calibration dates and an estimated first-setup date.
- Root does not unlock real battery/chip power use, AI/DSP load or per-camera rates.
- All root reads are read-only and do not change the headset.
- Using root may show a permission prompt.

## Tests & results

Probed 2026-10-20 to 2026-11-01.

| Probe | Observed result |
|---|---|
| `su -c id` | `uid=0`, KernelSU context |
| fan sysfs | `curr_rpm=4137`, `curr_rpm2=4037`, PWM 95 |
| `/proc/<pid>/io` | counters readable per PID |
| regulator class | ~129 rails enumerated; selected setpoints were constant and are not recorded |
| process mappings | hand plugin + `libcdsprpc.so`; no `libQnn*`/`libSnpe*` in process |
| OpenPX calibration / user-settings mtimes | readable, used for calibration and first setup |
| debugfs / tracefs / NPU | debugfs absent; tracefs needs writes; NPU sysfs `0x0` |

## Findings

- Root adds fan RPM/PWM, per-process I/O, active panel, calibration metadata and first-setup mtime.
- It does not expose real SoC/battery power, NPU/DSP utilisation, or sensor-level camera rates.
- All privileged operations are read-only; no writes, pushes or sysfs changes.
- Hand tracking has no user-facing setting; use the perception lifecycle dump, not the service prop.

## Details

Root works via **KernelSU** (`su -c id` -> `uid=0`, `context=u:r.ksu:s0`). Probes were read-only (`cat`/`ls`/`grep`/`dumpsys`).

**Confirmed with root:**
- **Mappings** (`/proc/12004/maps`, denied to shell): `libperception_hand_joint_tracking_host_plugin.so` and `libcdsprpc.so` are mapped. No `libQnn*`/`libSnpe*` in-process - QNN runs remotely on the CDSP.
- **Real GPU clock** (`kgsl-3d0`): `gpuclk = 421000000`, `devfreq/cur_freq = 421000000`, `devfreq/max_freq = 788000000` - matches the shell-visible `clock_mhz`.
- **Real fan speed** (`/sys/class/sec_fan/fan/`, root-only - SELinux denies shell): `curr_rpm = 4137`, `curr_rpm2 = 4037`, `get_status = rpm1=4137, rpm2=4037, pwm=95`.
- **Battery pack** (`power_supply/pogo`): `temp = 280` (28.0 C), `capacity = 51`, status Discharging, health Good. `battery/current_now` and `voltage_now` read **0**; `pogo/power/*` is runtime-PM, not electrical - **actual battery/SoC power draw is still unavailable**. Separately, `/sys/class/sec/max34427` exposes an unlabeled 15 V rail monitor (shell-readable); see [power rail](power.md).
- **Regulator rails** (`/sys/class/regulator/*/microvolts`): the class exposes ~129 rails, but the selected rails were constant setpoints with no current data, so they are not recorded.
- **OpenPX calibration metadata**: measured IPD textproto plus eye/face calibration file mtimes.
- **User-settings mtimes**: used only for the approximate first-setup date.

**Still not available even with root:**
- `/sys/kernel/debug` is **not mounted** (empty); no `msm_npu`/CDSP/kgsl debug counters.
- Tracefs **is** mounted (`/sys/kernel/tracing`) with `kgsl`, `fastrpc`, `clk_qcom`, `rproc_qcom` events - but `tracing_on=0` and only the `nop` tracer; enabling events requires **writes** (not done).
- NPU sysfs (`/sys/devices/soc0/npu`) is `0x0`; no utilisation counter.
- `/sys/kernel/boot_cdsp/boot` is permission-denied even as root.

The tool records **fan RPM/PWM** and **per-process disk I/O** (`/proc/<pid>/io`, with `--processes`) using read-only `su -c`. Enabling `kgsl`/`fastrpc` tracepoints for GPU/DSP timelines would require writes and is not done.

Caveat: `su -c` is an escalation and may trigger a root prompt; used only for reads it does not change the device. `IPerceptionControlPlane` still refuses `dumpsys` (`FAILED_TRANSACTION`).

Caveat on hand tracking: there is no user-facing setting - it is driven by `IPerceptionCheckboxManager` + `IPerceptionLifecycleManager`. The prop `init.svc.com.google.xr.hardware.perception.handtracking-service` reads `stopped` in **both** states, so it is **not** a reliable indicator; use the lifecycle dump.
