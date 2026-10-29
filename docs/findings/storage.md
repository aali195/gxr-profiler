# Storage I/O

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Disk capacity, whole-device counters, pressure and per-process I/O.

## Tests & results

Probed 2026-10-20.

| Probe | Observed result |
|---|---|
| `df -k /data` | 217.8 GB total, 211.6 GB free, 3% used |
| `/proc/diskstats` | readable; whole-device counters; rates derived from deltas |
| `/proc/pressure/io` | readable; avg10 recorded |
| root `/proc/<pid>/io` | counters returned; nonzero rates over 2 s samples |

## Findings

- Whole-device counters are aggregated; partitions/loop/zram are excluded to avoid double counting.
- The mount point string is unusual but maps to shared userdata.
- Per-process disk I/O requires root.
- `storaged`/per-UID I/O was not used.

## Details

- `/proc/diskstats` is readable by the shell and exposes whole-device counters: completed
  reads/writes, sectors read/written (512 B units), I/O time and weighted I/O time. gxr-profiler
  aggregates whole devices (`sd*`, `mmcblk*`, `nvme*n*`, `vd*`, `xvd*`) and excludes partitions,
  `dm-*`, `loop*` and `zram*` to avoid double counting.
- `/proc/pressure/io` (when present) reports PSI `some`/`full` averages; gxr-profiler records avg10.
- Per-process `/proc/<pid>/io` is root-only on this build. With `--root --processes`, gxr-profiler reads
  cumulative `read_bytes`/`write_bytes` for all captured non-kernel processes and derives `io_*_bps` from
  successive snapshots. `dumpsys diskstats`/`storaged` may expose per-UID or per-process I/O but
  was not used here. Live probe: `su -c` returned counters for shell-visible PIDs and rates were
  non-zero across 2 s process samples.
- `df -k /data` is captured once in `device_info.storage` and polled at 1 Hz for total, free and
  used percentage. On this build the mount point is reported as
  `/storage/emulated/0/Android/obb`, but it is the shared userdata filesystem.
- Live probe on 2026-10-20: 217.8 GB total, 211.6 GB free (3% used); diskstats/PSI parsed
  successfully.
