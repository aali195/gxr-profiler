"""One-off session state gathered around a recording."""

from __future__ import annotations

import logging

from ..core import parsers as P
from ..core.adb import AdbClient
from .logcat import dev_seconds
from .poller import Poller

log = logging.getLogger(__name__)


def read_dev_baseline(adb: AdbClient) -> float | None:
    try:
        return dev_seconds(adb.shell("date +'%m-%d %H:%M:%S'", timeout=8.0).strip() + ".000")
    except Exception:
        log.debug("could not read device clock", exc_info=True)
        return None


def _controller_state(adb: AdbClient) -> dict[str, float]:
    try:
        txt = adb.shell(
            "logcat -d -t 500 -s SXRC_TSVC CpmInput SXRC_POSE 2>/dev/null | "
            "grep -E 'updateDeviceState|tracking for hand_controller|Contr\\['",
            timeout=14.0,
        )
    except Exception:
        log.debug("could not read controller state", exc_info=True)
        return {}
    return P.parse_controller_log(txt)


def _passthrough_state(adb: AdbClient) -> dict[str, float | str]:
    try:
        txt = adb.shell(
            "logcat -d -t 50 -s PassthroughStateManager 2>/dev/null | tail -n 1",
            timeout=8.0,
        )
        out = P.parse_passthrough(txt)
    except Exception:
        log.debug("could not read passthrough state", exc_info=True)
        out = {}
    if "passthrough" in out:
        return out
    try:
        txt = adb.shell(
            "dumpsys cpm 2>/dev/null | grep -A6 'XrPassthroughController:'",
            timeout=10.0,
        )
    except Exception:
        log.debug("could not read passthrough controller", exc_info=True)
        return out
    return P.parse_passthrough(txt)


def capture_state(adb: AdbClient, poller: Poller) -> dict:
    st: dict = {}
    try:
        lp = adb.shell("settings get global low_power", timeout=5.0).strip()
        if lp in ("0", "1"):
            st["low_power"] = int(lp)
    except Exception:
        log.debug("could not read low_power", exc_info=True)
    try:
        txt = adb.shell(
            "dumpsys com.google.xr.frameworks.perception.IPerceptionLifecycleManager/default",
            timeout=14.0,
        )
        if "service_id=" in txt:
            st["hand_tracking_active"] = "HandJointTracking" in txt
    except Exception:
        log.debug("could not read perception lifecycle", exc_info=True)
    st.update(_controller_state(adb))
    st.update(_passthrough_state(adb))
    try:
        poll = poller.poll()
        for k in ("psm", "disp_hz", "batt_ac", "batt_level", "batt_temp", "thermal_status"):
            if k in poll:
                st[k] = poll[k]
    except Exception:
        log.debug("could not capture initial poll state", exc_info=True)
    return st
