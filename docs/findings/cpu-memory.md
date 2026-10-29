# CPU & memory

[Findings index](../README.md) | [Commands](../COMMANDS.md)

Memory, swap/zram pressure and per-core CPU utilisation.

## Tests & results

Probed 2026-10-21.

| Probe | Observed result |
|---|---|
| `/proc/meminfo` | 16,066,684 kB total; 4,194,300 kB swap |
| live memory | ~50.7% used, 7.9 GB available, 7.6 GB cached |
| zram | ~698 MB swap used, ~223 MB resident |
| memory PSI | 0.00 |
| `/proc/stat` | cumulative per-core ticks; utilisation from idle/total deltas |

## Findings

- `MemAvailable` is the best available estimate; used is derived.
- Swap is zram-backed.
- CPU utilisation is delta-based, not a direct counter.
- Per-process RSS/GPU memory lives in `procs.csv`; total GPU memory is not summed.

## Details

- `/proc/meminfo` exposes 16,066,684 kB total (16 GB class), with MemAvailable as the best
  "available" estimate; used is derived as `MemTotal - MemAvailable`. Swap is 4,194,300 kB
  (~4 GB) backed by zram.
- `/proc/pressure/memory` reports PSI `some`/`full` avg10; `/sys/block/zram0/mm_stat` gives the
  original, compressed and resident zram sizes.
- `/proc/stat` provides cumulative per-core user/nice/system/idle/iowait/irq/softirq/steal ticks;
  gxr-profiler records per-core utilisation from idle/total deltas and the live `procs_running` count.
- Live probe: ~50.7% RAM used, 7.9 GB available, 7.6 GB cached, ~698 MB swap used, ~223 MB zram
  resident, memory PSI 0.00.
- Per-process RSS and GPU memory are in `.procs.csv`; GPU memory total is not currently summed.
