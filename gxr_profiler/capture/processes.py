"""Per-process snapshot sampling."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..core import parsers as P
from ..core.adb import AdbClient
from .logcat import DEV_BASE
from .writer import RunWriter

log = logging.getLogger(__name__)

CPU_HZ = 100.0

PACKAGE_SCRIPT = "echo '###PKGS'; pm list packages -U; echo '###SYSPKGS'; pm list packages -s"

PROCESS_SCRIPT = (
    "echo '###CPUINFO'; dumpsys cpuinfo; "
    "echo '###PS'; ps -A -o PID,UID,RSS,NAME; "
    "echo '###STAT'; grep -H '' /proc/[0-9]*/stat 2>/dev/null; "
    "echo '###OOM'; grep -H '' /proc/[0-9]*/oom_score_adj 2>/dev/null; "
    "echo '###GPUMEM'; dumpsys gpu | sed -n '/Memory snapshot for GPU/,/driverPackageName/p'; "
    "echo '###NET'; dumpsys netstats"
)


class ProcessSampler:
    def __init__(
        self,
        adb: AdbClient,
        writer: RunWriter,
        top: int = 0,
        root: bool = False,
        include_kernel: bool = False,
        process_io: bool = True,
    ) -> None:
        self.adb = adb
        self.writer = writer
        self.top = max(0, int(top))
        self.root = root
        self.include_kernel = include_kernel
        self.process_io = process_io
        self._cpu_prev: dict[int, tuple[float, int, float]] = {}
        self._io_prev: dict[int, tuple[float, float, float, int | None]] = {}
        self._net_prev: dict[int, tuple[float, float, float]] = {}
        self._packages_loaded = False
        self._uid_packages: dict[int, list[str]] = {}
        self._system_packages: set[str] = set()
        self._packages: set[str] = set()

    def _load_packages(self) -> None:
        if self._packages_loaded:
            return
        try:
            text = self.adb.shell(PACKAGE_SCRIPT, timeout=10.0)
            sec = P.split_sections(text)
            self._uid_packages = P.parse_package_uids("\n".join(sec.get("PKGS", [])))
            self._system_packages = P.parse_system_packages("\n".join(sec.get("SYSPKGS", [])))
            self._packages = {pkg for names in self._uid_packages.values() for pkg in names}
            self._packages_loaded = True
        except Exception:
            log.debug("package map poll failed", exc_info=True)

    def _package_for(self, name: str, uid: int | None) -> str:
        base = name.split(":", 1)[0]
        if base in self._packages:
            return base
        if uid is None:
            return ""
        candidates = self._uid_packages.get(uid, [])
        if len(candidates) == 1:
            return candidates[0]
        return ""

    def _read_io(self, pids: set[int]) -> dict[int, dict[str, float]]:
        if not pids:
            return {}
        inner = 'echo "###IO"; grep -H -E "^(read_bytes|write_bytes):" /proc/[0-9]*/io 2>/dev/null'
        try:
            text = self.adb.shell(f"su -c '{inner}'", timeout=10.0)
        except Exception:
            log.debug("process I/O poll failed", exc_info=True)
            return {}
        parsed = P.parse_proc_io_paths(text)
        if not parsed:
            parsed = P.parse_proc_io(text)
        return {pid: rec for pid, rec in parsed.items() if pid in pids}

    def poll(self, now: float, t0: float | None, dev_baseline: float | None = None) -> None:
        if self.writer.procs_writer is None:
            return
        self._load_packages()
        try:
            text = self.adb.shell(PROCESS_SCRIPT, timeout=14.0)
        except Exception:
            log.debug("process poll failed", exc_info=True)
            return

        sec = P.split_sections(text)
        cpu = P.parse_cpuinfo("\n".join(sec.get("CPUINFO", [])))
        ps = P.parse_ps("\n".join(sec.get("PS", [])))
        stats = P.parse_proc_stats("\n".join(sec.get("STAT", [])))
        oom = P.parse_oom_scores("\n".join(sec.get("OOM", [])))
        gpu = P.parse_gpu_mem("\n".join(sec.get("GPUMEM", [])))
        net = P.parse_netstats_uid("\n".join(sec.get("NET", [])))
        pids = set(ps) | set(stats) | set(cpu) | set(gpu)
        if not pids:
            return

        cpu_now: dict[int, float] = {}
        for pid, st in stats.items():
            ticks = st["utime"] + st["stime"]
            prev = self._cpu_prev.get(pid)
            if prev is not None and prev[1] == st["starttime"]:
                dt = now - prev[2]
                delta = ticks - prev[0]
                if dt > 0 and delta >= 0:
                    cpu_now[pid] = 100.0 * delta / CPU_HZ / dt
            self._cpu_prev[pid] = (ticks, st["starttime"], now)

        net_bps: dict[int, dict[str, float]] = {}
        for uid, rec in net.items():
            prev = self._net_prev.get(uid)
            next_bps: dict[str, float] = {}
            if prev is not None:
                dt = now - prev[2]
                if dt > 0:
                    next_bps["net_rx_bps"] = max(0.0, (rec["net_rx_bytes"] - prev[0]) / dt)
                    next_bps["net_tx_bps"] = max(0.0, (rec["net_tx_bytes"] - prev[1]) / dt)
            net_bps[uid] = next_bps
            self._net_prev[uid] = (rec["net_rx_bytes"], rec["net_tx_bytes"], now)

        eligible = {
            pid
            for pid in pids
            if self.include_kernel or not P.is_kernel_process(pid, (ps.get(pid) or {}).get("name", ""))
        }
        if self.top:

            def sort_cpu(pid: int) -> float:
                return max(cpu_now.get(pid, 0.0), cpu.get(pid, {}).get("cpu_pct", 0.0))

            by_cpu = sorted(eligible, key=sort_cpu, reverse=True)
            by_rss = sorted(eligible, key=lambda p: (ps.get(p) or {}).get("rss_kb", 0.0), reverse=True)
            keep = set(by_cpu[: self.top]) | set(by_rss[: self.top]) | (set(gpu) & eligible)
        else:
            keep = eligible

        io = self._read_io(keep) if self.root and self.process_io else {}
        ts = f"{now:.3f}"
        if dev_baseline is not None and t0 is not None:
            dev_time = DEV_BASE + timedelta(seconds=dev_baseline + (now - t0))
            ts_dev = dev_time.strftime("%m-%d %H:%M:%S.%f")[:-3]
        else:
            ts_dev = datetime.fromtimestamp(now).strftime("%m-%d %H:%M:%S.%f")[:-3]
        elapsed = now - (t0 or now)
        for pid in sorted(keep):
            rec = ps.get(pid) or cpu.get(pid) or {}
            uid = rec.get("uid")
            name = rec.get("name", "") or stats.get(pid, {}).get("comm", "")
            package = self._package_for(name, uid)
            package_system = 1.0 if package and package in self._system_packages else 0.0
            kind = P.process_kind(pid, name, uid, package, self._system_packages)
            st = stats.get(pid, {})
            adj = oom.get(pid)
            irec = io.get(pid, {})
            read_bytes = irec.get("read_bytes")
            write_bytes = irec.get("write_bytes")
            read_bps: float | str = ""
            write_bps: float | str = ""
            if read_bytes is not None and write_bytes is not None:
                prev_io = self._io_prev.get(pid)
                if prev_io is not None and prev_io[3] == st.get("starttime"):
                    dt = now - prev_io[2]
                    if dt > 0:
                        read_bps = max(0.0, (read_bytes - prev_io[0]) / dt)
                        write_bps = max(0.0, (write_bytes - prev_io[1]) / dt)
                self._io_prev[pid] = (read_bytes, write_bytes, now, st.get("starttime"))
            nrec = net.get(uid, {}) if isinstance(uid, int) else {}
            nbps = net_bps.get(uid, {}) if isinstance(uid, int) else {}
            ticks = st.get("utime", 0.0) + st.get("stime", 0.0)
            self.writer.write_proc(
                {
                    "ts_host": ts,
                    "ts_dev": ts_dev,
                    "elapsed_s": f"{elapsed:.3f}",
                    "pid": pid,
                    "ppid": st.get("ppid", ""),
                    "uid": uid if uid is not None else "",
                    "name": name,
                    "kind": kind,
                    "package": package,
                    "pkg_system": package_system,
                    "cpu_pct": cpu.get(pid, {}).get("cpu_pct", ""),
                    "cpu_now_pct": cpu_now.get(pid, ""),
                    "cpu_time_s": ticks / CPU_HZ if pid in stats else "",
                    "rss_kb": ps.get(pid, {}).get("rss_kb", ""),
                    "gpu_mem_kb": gpu.get(pid, ""),
                    "io_read_bytes": read_bytes if read_bytes is not None else "",
                    "io_write_bytes": write_bytes if write_bytes is not None else "",
                    "io_read_bps": read_bps,
                    "io_write_bps": write_bps,
                    "net_rx_bytes": nrec.get("net_rx_bytes", ""),
                    "net_tx_bytes": nrec.get("net_tx_bytes", ""),
                    "net_rx_bps": nbps.get("net_rx_bps", ""),
                    "net_tx_bps": nbps.get("net_tx_bps", ""),
                    "state": st.get("state", ""),
                    "threads": st.get("threads", ""),
                    "oom_adj": adj if adj is not None else "",
                    "oom_class": P.oom_class(adj),
                }
            )
        for pid in list(self._cpu_prev):
            if pid not in keep:
                self._cpu_prev.pop(pid, None)
        for pid in list(self._io_prev):
            if pid not in keep:
                self._io_prev.pop(pid, None)
        for uid in list(self._net_prev):
            if uid not in net:
                self._net_prev.pop(uid, None)
        self.writer.flush_procs()
