"""Orchestrates a recording: logcat stream + 1 Hz poll -> run files.

Emits a `SampleEvent` to listeners (TUI / SSE) each tick. Read-only to the
device: only `cat`/`dumpsys`/`cmd wifi`/`getprop`/`logcat` (and read-only
`su -c` when `--root` is requested).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ..core import parsers as P
from ..core.adb import AdbClient
from ..core.device import collect_device_info
from ..core.models import RunConfig, SampleEvent
from .logcat import DEV_BASE, LogcatStream
from .media import MediaSampler
from .meta import build_meta
from .poller import Poller
from .processes import ProcessSampler
from .session import capture_state, read_dev_baseline
from .state import MetricState
from .writer import RunWriter

log = logging.getLogger(__name__)

SampleListener = Callable[[SampleEvent], None]
StatusListener = Callable[[str], None]


class Recorder:
    def __init__(
        self,
        adb: AdbClient,
        config: RunConfig,
        on_sample: SampleListener | None = None,
        on_status: StatusListener | None = None,
    ) -> None:
        self.adb = adb
        self.cfg = config
        self.state = MetricState()
        self.poller = Poller(adb, use_root=config.root)
        self.writer = RunWriter(config.out_dir, config.name)
        self.media = MediaSampler(adb)
        self.processes = ProcessSampler(
            adb,
            self.writer,
            config.processes_top,
            root=config.root,
            include_kernel=config.processes_kernel,
            process_io=config.process_io,
        )
        self.on_sample = on_sample
        self.on_status = on_status or (lambda _m: None)

        self.row_count = 0
        self._stop = threading.Event()
        self._t0: float | None = None
        self._dev_baseline: float | None = None
        self._logcat: LogcatStream | None = None
        self._aux_thread: threading.Thread | None = None
        self._aux_stop = threading.Event()
        self._started_iso: str | None = None
        self._recording_started_iso: str | None = None
        self._ended_iso: str | None = None
        self._duration_actual_s: float | None = None
        self._dev_info: dict = {}
        self._start_state: dict = {}
        self._end_state: dict = {}

    # -- lifecycle -------------------------------------------------------
    def stop(self) -> None:
        self._stop.set()
        self._aux_stop.set()

    def run(self) -> str:
        self._started_iso = datetime.now(UTC).isoformat()
        try:
            self._device_info()

            if self.cfg.cooldown_below is not None:
                self._cooldown()
            if self._stop.is_set():
                raise RuntimeError("recording cancelled")

            self._start_state = capture_state(self.adb, self.poller)
            self.state.update(self._start_state)
            self._dev_baseline = read_dev_baseline(self.adb)
            self.writer.open(with_procs=self.cfg.processes)

            if self.cfg.logcat:
                self._logcat = LogcatStream(
                    self.adb,
                    self.state,
                    dev_baseline=self._dev_baseline,
                    event_sink=self.writer.write_event,
                    stop=self._stop,
                )
                self._logcat.start()

            self._t0 = time.time()
            self._recording_started_iso = datetime.fromtimestamp(self._t0, UTC).isoformat()
            self._aux_thread = threading.Thread(target=self._aux_loop, name="aux-sampler", daemon=True)
            self._aux_thread.start()
            next_tick = self._t0
            self.on_status("Recording... press Ctrl-C to stop.")

            while not self._stop.is_set():
                now = time.time()
                if self.cfg.duration and (now - self._t0) >= self.cfg.duration:
                    break
                poll = self._safe_poll()
                row = self._build_row(now, poll)
                self.writer.write_row(row)
                self.row_count += 1
                if self.on_sample:
                    try:
                        self.on_sample(SampleEvent(elapsed_s=now - self._t0, row=row))
                    except Exception:
                        log.debug("sample listener failed", exc_info=True)
                next_tick += self.cfg.interval
                delay = next_tick - time.time()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.time()
        finally:
            self._stop.set()
            self._aux_stop.set()
            if self._logcat is not None:
                self._logcat.stop_stream()
                self._logcat.join(timeout=3.0)
            if self._aux_thread is not None:
                self._aux_thread.join(timeout=5.0)
            self._ended_iso = datetime.now(UTC).isoformat()
            if self._t0 is not None:
                self._duration_actual_s = time.time() - self._t0
            if self.writer.opened:
                self._end_state = self._capture_end_state()
                try:
                    self.writer.close()
                finally:
                    self._write_meta()
        return self.writer.csv_path

    def _capture_end_state(self) -> dict:
        try:
            return capture_state(self.adb, self.poller)
        except Exception:
            log.debug("could not capture end state", exc_info=True)
            return self.state.snapshot()

    # -- device ----------------------------------------------------------
    def _device_info(self) -> None:
        try:
            self._dev_info = collect_device_info(self.adb, check_root=self.cfg.root)
        except Exception:
            log.warning("device info collection failed", exc_info=True)
            self._dev_info = {}

    # -- cooldown --------------------------------------------------------
    def _cooldown(self) -> None:
        sensor = self.cfg.cooldown_sensor
        col = f"t_{sensor}"
        self.on_status(f"Cooling down: waiting for {sensor} <= {self.cfg.cooldown_below} C...")
        start = time.time()
        last_val = None
        last_print = 0.0
        fallback_col = {"AP": "sec_ap", "WIFI": "sec_wf"}.get(sensor)
        while not self._stop.is_set():
            if self.cfg.cooldown_max_wait and (time.time() - start) >= self.cfg.cooldown_max_wait:
                self.on_status("Cooldown time limit reached; starting anyway.")
                return
            thermal = {}
            try:
                thermal = self.poller.poll_thermal()
                self.state.update(thermal)
            except Exception:
                log.debug("thermal poll failed during cooldown", exc_info=True)
            val = thermal.get(col)
            if val is None and fallback_col:
                val = self._safe_poll().get(fallback_col)
            now = time.time()
            if isinstance(val, (int, float)):
                if val <= self.cfg.cooldown_below:
                    self.on_status(f"Baseline reached ({val:.1f} C).")
                    return
                if last_val is None or abs(val - last_val) >= 0.5 or (now - last_print) >= 5.0:
                    self.on_status(f"  {sensor}: {val:.1f} C")
                    last_val, last_print = val, now
            elif now - last_print >= 5.0:
                self.on_status(f"  {sensor}: waiting for sensor value...")
                last_print = now
            time.sleep(1.0)

    # -- sampling --------------------------------------------------------
    def _safe_poll(self) -> dict:
        for attempt in range(2):
            try:
                return self.poller.poll_fast()
            except Exception:
                if attempt == 0:
                    time.sleep(0.2)
                else:
                    log.debug("device poll failed twice", exc_info=True)
        return {}

    def _build_row(self, now: float, poll: dict) -> dict:
        row = self.state.snapshot()
        sev = [v for k, v in row.items() if k.startswith("sev_") and isinstance(v, (int, float))]
        row["thermal_max_sev"] = max(sev) if sev else 0.0
        ctrl_keys = (
            "ctrl_left_track",
            "ctrl_right_track",
            "ctrl_left_connected",
            "ctrl_right_connected",
        )
        if any(k in row for k in ctrl_keys):
            active = P.controller_active({k: float(row[k]) for k in ctrl_keys if k in row})
            if active is not None:
                row["ctrl_active"] = active
        row.update(poll)
        row["ts_host"] = f"{now:.3f}"
        if self._dev_baseline is not None and self._t0 is not None:
            dev_time = DEV_BASE + timedelta(seconds=self._dev_baseline + (now - self._t0))
            row["ts_dev"] = dev_time.strftime("%m-%d %H:%M:%S.%f")[:-3]
        else:
            row["ts_dev"] = datetime.fromtimestamp(now).strftime("%m-%d %H:%M:%S.%f")[:-3]
        row["elapsed_s"] = f"{now - self._t0:.3f}"
        row["poll_ok"] = 1.0 if poll else 0.0
        return row

    def _aux_loop(self) -> None:
        """Slow samplers run off the 1 Hz writer path."""
        t0 = self._t0 or time.time()
        next_state = next_radio = next_sensors = next_procs = next_media = 0.0
        while not self._aux_stop.is_set():
            now = time.time()
            if now >= next_state:
                try:
                    self.state.update(self.poller.poll_state())
                except Exception:
                    log.debug("state poll failed", exc_info=True)
                next_state = time.time() + max(0.5, self.cfg.state_interval)
            if now >= next_radio:
                try:
                    self.state.update(self.poller.poll_radio())
                except Exception:
                    log.debug("radio poll failed", exc_info=True)
                next_radio = time.time() + max(1.0, self.cfg.radio_interval)
            if self.cfg.sensors and now >= next_sensors:
                try:
                    self.state.update(P.parse_sensors(self.adb.shell("dumpsys sensorservice", timeout=10.0)))
                except Exception:
                    log.debug("sensor poll failed", exc_info=True)
                next_sensors = time.time() + max(1.0, self.cfg.sensors_interval)
            if self.cfg.processes and now >= next_procs:
                try:
                    self.processes.poll(now, t0, self._dev_baseline)
                except Exception:
                    log.debug("process poll failed", exc_info=True)
                next_procs = time.time() + max(1.0, self.cfg.processes_interval)
            if now >= next_media:
                try:
                    self.state.update(self.media.poll(now, t0, self._dev_baseline))
                except Exception:
                    log.debug("media poll failed", exc_info=True)
                next_media = time.time() + max(1.0, self.cfg.media_interval)
            due = min(
                next_state,
                next_radio,
                next_media,
                next_procs if self.cfg.processes else next_media,
                next_sensors if self.cfg.sensors else next_media,
            )
            self._aux_stop.wait(min(0.2, max(0.02, due - time.time())))

    # -- finalize --------------------------------------------------------
    def _write_meta(self) -> None:
        meta = build_meta(
            self.cfg,
            started=self._started_iso,
            recording_started=self._recording_started_iso,
            ended=self._ended_iso,
            duration_actual_s=self._duration_actual_s,
            rows=self.row_count,
            device_info=self._dev_info,
            start_state=self._start_state,
            end_state=self._end_state,
        )
        self.writer.write_meta(meta)
