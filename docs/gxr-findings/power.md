# Power rails & battery drain

[Findings index](../README.md) | [Commands](../COMMANDS.md) | [Thermal](thermal.md) | [Root](root.md)

> **Hardware state: MODDED.** These measurements are from the SoC thermal-modded headset (phase-change pads + copper shims), taken from 2026-11-01 onward. There is no stock baseline on this page.

The headset exposes a two-channel current/voltage/power monitor through Samsung sysfs (Maxim MAX34427 hardware). Only channel 1 produces meaningful measurements; the UI calls it **Power rail 1**. It is shell-readable and adds a real electrical measurement that the battery power-supply nodes do not provide. Channel 2 is effectively dead on this unit.

## In plain terms

- The headset can measure one internal 15 V power rail, not total battery or chip power.
- That rail drew about 0.6-1.0 W while idle and roughly 16-18 W during 8K HDR playback.
- Battery level, temperature and a rough battery-drain rate are also tracked.
- The second measurement channel reads zero on this unit.
- Battery voltage, current and power still show zero, so real battery draw is unknown.

## Tests & results

Probed 2026-11-01.

| Probe | Observed result |
|---|---|
| `/sys/class/sec/max34427/dev_id` | `72` |
| `all_ch1` | `0.037A, 0.560W, 15.142V` early in the session |
| `all_ch1` later | `0.068A, 1.028W, 15.125V` |
| `all_ch2` | `0.000A, 0.000W, 0.000V` |
| `pwr_ch1` / `vol_ch1` | `0.068` / `15.125` |
| `all_ch1` during 8K HDR playback | `1.20A, 17.710W, 14.759V`; other samples `1.07-1.19A, 15.8-17.7W` |
| `all_ch2` during 8K HDR playback | `0.000A, 0.000W, 0.002-0.013V` (noise) |
| `acc_ch1` / `acc_ch2` repeated | non-monotonic and reset/roll; not usable as cumulative energy |
| selected regulator rails | constant setpoints; e.g. `pmxr2230_s1` 1.816 V, `s2mpb02-l-bb` 3.0 V |
| `dumpsys battery` | AC/USB/wireless/dock powered false; voltage/current/power all `0` |

The values are readable without root. Channel 1 stayed around 15 V and roughly 0.6-1.0 W while idle and unplugged; channel 2 stayed at zero.

## Findings

- The power-rail monitor is a real, shell-readable voltage/current/power source.
- Rail 1 is a **15 V rail**, so it is not the main battery or SoC power measurement.
- Rail 1 tracks load: during 8K HDR playback it rose from roughly 11-16 W idle-ish levels to **~16-18 W**, with voltage staying near 14.8-14.9 V.
- Rail 2 always reads `0.000A` / `0.000W`; its voltage is only 0.002-0.013 V noise. It is not stored.
- The `acc_ch1` / `acc_ch2` registers are non-monotonic across reads; `acc_ch2` is non-zero even while channel 2 power is zero. They are not recorded as energy counters.
- The sysfs attributes do not identify the measured rail; the channel label is not exposed.
- Battery power-supply nodes still report voltage/current/power as `0`, so MAX34427 does not replace a real battery or SoC power measurement.
- gxr-profiler records the active channel as `max_ch1_voltage`, `max_ch1_current` and `max_ch1_power`.
- Rail power is integrated into `max_ch1_energy_wh` from those samples.
- Battery level, temperature, AC/USB state and a rolling `batt_drain_pct_h` rate are under the normal **Power & battery** section.
- The selected PMIC/sub-PMIC regulator rails were constant setpoints, so they are not recorded as time series.

## Details

- Base path: `/sys/class/sec/max34427`.
- `all_ch1` and `all_ch2` each contain three comma-separated values: `current A, power W, voltage V`; only `all_ch1` is read because channel 2 stayed at zero.
- The driver also exposes `pwr_chN`, `vol_chN`, raw `acc_chN` counters, `dev_id` and `control`/`update`.
- The device is attached at I2C address `0x36` (`i2c-22/22-0036`) with `dev_id=72`.
- The profiler reads `all_ch1` once per second and parses the three measurements.
- Energy is integrated from the previous sample's power over the elapsed time, then shown as cumulative Wh. It resets at recording start, after cooldown.
- The `acc_ch1` register is exposed as hex plus decimal, but repeated reads were non-monotonic (for example 78.2M -> 73.3M) even during steady playback. The physical semantics are undocumented, so it is not recorded.
- The regulator rails are readable only with root, but the selected rails are constant setpoints.

## Caveats

- The rail identity is unknown. Do not label channel 1 as display, charger, battery or SoC power without vendor documentation or a controlled correlation test.
- Channel 2 is not recorded because it has no meaningful current/power reading; a future firmware could make it useful. Its accumulator value is not evidence of channel-2 energy.
- The `acc` registers are not recorded because they reset/roll and do not behave like cumulative energy counters.
- `dumpsys battery` still reports AC/USB/dock offline during the 15 V reading, so the rail can be powered while the headset is discharging.
- MAX34427 measures one active rail, not total device power. It should not be summed with battery capacity or presented as SoC power.
- `batt_drain_pct_h` is coarse: battery level is integer percent and updates on the state cadence. Use longer runs for a meaningful rate.
