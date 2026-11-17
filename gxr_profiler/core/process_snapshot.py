"""Shared per-process snapshot shell sections.

The recorder and the Apps tool both need the same CPU/RSS/thread/OOM/GPU
snapshot. Keeping the command text in one place prevents the two paths from
drift apart.
"""

from __future__ import annotations

PROCESS_SNAPSHOT_SCRIPT = """echo '###CPUINFO'; dumpsys cpuinfo
echo '###PS'; ps -A -o PID,UID,RSS,NAME
echo '###STAT'; grep -H '' /proc/[0-9]*/stat 2>/dev/null
echo '###OOM'; grep -H '' /proc/[0-9]*/oom_score_adj 2>/dev/null
echo '###GPUMEM'; dumpsys gpu | sed -n '/Memory snapshot for GPU/,/driverPackageName/p'
"""

PROCESS_SNAPSHOT_WITH_NET_SCRIPT = PROCESS_SNAPSHOT_SCRIPT + "echo '###NET'; dumpsys netstats\n"
