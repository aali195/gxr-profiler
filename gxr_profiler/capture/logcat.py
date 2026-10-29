"""Background logcat stream folded into MetricState.

Tags are filtered in Python: logcat's `-s` does exact tag matching (missing
colon tags like `SSRM:Temperature`) and `-e` matches only the message, so we
stream unfiltered with `-T 1` and match tags here.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from ..core import parsers as P
from ..core.adb import AdbClient
from .state import MetricState

TAG_PREFIXES = (
    "thermal_changed",
    "SSRM",
    "ThermalManagerService",
    "ThermalHalWrapper",
    "DynamicPolicyManager",
    "android.hardware.thermal",
    "SXRC_TSVC",
    "CpmInput",
    "PassthroughStateManager",
)

_DEV_TS_RE = re.compile(r"^(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})$")
DEV_BASE = datetime(2000, 1, 1, tzinfo=UTC)


def dev_seconds(ts_dev: str) -> float | None:
    m = _DEV_TS_RE.match(ts_dev.strip())
    if not m:
        return None
    month, day, hour, minute, second, millis = (int(x) for x in m.groups())
    try:
        stamp = datetime(2000, month, day, hour, minute, second, millis * 1000, tzinfo=UTC)
    except ValueError:
        return None
    return (stamp - DEV_BASE).total_seconds()


EventSink = Callable[[float, str, str, str, str, object], None]


class LogcatStream(threading.Thread):
    def __init__(
        self,
        adb: AdbClient,
        state: MetricState,
        dev_baseline: float | None = None,
        event_sink: EventSink | None = None,
        stop: threading.Event | None = None,
    ) -> None:
        super().__init__(name="logcat", daemon=True)
        self.adb = adb
        self.state = state
        self.dev_baseline = dev_baseline
        self.event_sink = event_sink
        self.stop = stop or threading.Event()
        self._proc = None

    def stop_stream(self) -> None:
        """Ask the reader loop to stop and unblock/kill its adb child."""
        self.stop.set()
        proc = self._proc
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                proc = self.adb.popen(["logcat", "-v", "time", "-T", "1"])
            except Exception:
                time.sleep(1.0)
                continue
            try:
                self._proc = proc
                assert proc.stdout is not None
                # readline (not `for line in`) - read-ahead buffering stalls on
                # low-volume streams.
                while not self.stop.is_set():
                    line = proc.stdout.readline()
                    if not line:
                        break
                    self.process_line(line.rstrip("\n"))
            except Exception:
                pass
            finally:
                if self._proc is proc:
                    self._proc = None
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
            if not self.stop.is_set():
                time.sleep(0.5)

    def process_line(self, line: str) -> None:
        # NB: do not name this `_handle` - Python 3.13's threading.Thread uses
        # `self._handle` internally and start() would overwrite the method.
        hdr = P.parse_header(line)
        if not hdr:
            return
        tag = hdr["tag"]
        msg = hdr["msg"]
        heartbeat = "XrHeartbeat" in msg
        irled = "IRLedController" in tag
        cib = "[CIB]" in msg
        controller = tag.startswith(("SXRC_TSVC", "SXRC_POSE", "CpmInput"))
        passthrough = tag.startswith("PassthroughStateManager")
        if (
            not heartbeat
            and not irled
            and not cib
            and not controller
            and not passthrough
            and not tag.startswith(TAG_PREFIXES)
        ):
            return
        ts_dev = f"{hdr['date']} {hdr['time']}"
        dev_s = dev_seconds(ts_dev)
        if self.dev_baseline is not None and dev_s is not None and dev_s < self.dev_baseline - 2.0:
            if self.dev_baseline - dev_s > 180 * 86400:
                dev_s += 366 * 86400
            else:
                return
        ts_host = time.time()

        if passthrough:
            self.state.update(P.parse_passthrough(msg))
        elif controller:
            self.state.update(P.parse_controller(msg))
        elif cib:
            self.state.update(P.parse_cib(msg))
        elif heartbeat:
            self.state.update(P.parse_xr_heartbeat(msg))
        elif irled:
            fps = P.parse_irled_fps(msg)
            if fps is not None:
                self.state.set("irled_fps", fps)
        elif tag.startswith("thermal_changed"):
            ev = P.parse_thermal_changed(msg)
            if ev:
                self.state.update({f"t_{ev['name']}": ev["value"], f"sev_{ev['name']}": ev["sev"]})
                self._event(ts_host, ts_dev, "thermal_changed", ev["name"], "temp", ev["value"])
        elif tag.startswith("SSRM"):
            if tag.endswith(":Temperature") or msg.startswith("SIOP"):
                for k, v in P.parse_kv_colon(msg).items():
                    if k in P.SSRM_SIOP_SENSORS:
                        self.state.set(f"t_{k}", v)
            elif tag.endswith(":S"):
                for k, v in P.parse_kv_eq(msg).items():
                    if k in P.SSRM_S_SENSORS:
                        self.state.set(f"t_{k}", v)
            elif tag.endswith(":w"):
                step = P.parse_fan_step(msg)
                if step is not None:
                    self.state.set("fan_step", float(step))
                    self._event(ts_host, ts_dev, "SSRM", "fan", "step", step)
        elif tag.startswith("ThermalManagerService"):
            d = P.parse_dcvsh(msg)
            if d:
                self.state.update(
                    {f"dcvsh_{d['cluster']}_limit": float(d["limit"]), f"dcvsh_{d['cluster']}_max": float(d["max"])}
                )
        elif tag.startswith("DynamicPolicyManager"):
            self.state.update(P.parse_dynpol(msg))

    def _event(self, ts_host: float, ts_dev: str, tag: str, name: str, key: str, value) -> None:
        if self.event_sink:
            self.event_sink(ts_host, ts_dev, tag, name, key, value)
