"""IPD and eye/face calibration metadata (best effort, read-only)."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from ..adb import AdbClient

log = logging.getLogger(__name__)

IPD_FILE = "/data/vendor/openpx/calibration/records/ipd.textproto"
EYE_CAL_FILE = "/data/vendor/openpx/eye_tracking/eye_tracking_calibration.bin"
FACE_CAL_FILE = "/data/vendor/openpx/face_tracking/face_tracking_calibration.pb"


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), UTC).isoformat(timespec="seconds")
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def parse_ipd_textproto(text: str) -> dict:
    out: dict = {}
    m = re.search(r"ipd_mm:\s*([\d.]+)", text)
    if m:
        out["ipd_mm"] = float(m.group(1))
    m = re.search(r"encoder_left_mm:\s*([\d.]+)", text)
    if m:
        out["ipd_left_mm"] = float(m.group(1))
    m = re.search(r"encoder_right_mm:\s*([\d.]+)", text)
    if m:
        out["ipd_right_mm"] = float(m.group(1))
    m = re.search(r"created_at\s*\{\s*seconds:\s*(\d+)", text)
    if m:
        out["ipd_calibrated_at"] = _iso(int(m.group(1)))
    return out


def parse_cpm_ipd(text: str) -> dict:
    m = re.search(r"Left Eye:\s*([\d.]+)\s+Right Eye:\s*([\d.]+)", text)
    if not m:
        return {}
    left, right = float(m.group(1)), float(m.group(2))
    return {
        "ipd_in_use_left_mm": left,
        "ipd_in_use_right_mm": right,
        "ipd_in_use_mm": round(left + right, 3),
    }


def _read_root_files(adb: AdbClient) -> tuple[str, str, str, dict[str, int]]:
    script = (
        "su -c 'echo @@IPD; cat " + IPD_FILE + " 2>/dev/null; "
        "echo @@EYE_MTIME; stat -c %Y " + EYE_CAL_FILE + " 2>/dev/null; "
        "echo @@FACE_MTIME; stat -c %Y " + FACE_CAL_FILE + " 2>/dev/null; "
        "echo @@IPD_MTIME; stat -c %Y " + IPD_FILE + " 2>/dev/null'"
    )
    text = adb.shell(script, timeout=10.0)
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("@@"):
            current = line[2:].strip()
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.strip())
    mtimes: dict[str, int] = {}
    for key, name in (("EYE_MTIME", "eye"), ("FACE_MTIME", "face"), ("IPD_MTIME", "ipd")):
        if sections.get(key):
            try:
                mtimes[name] = int(sections[key][0])
            except ValueError:
                pass
    return "\n".join(sections.get("IPD", [])), "", "", mtimes


def calibration_info(adb: AdbClient, check_root: bool) -> dict:
    out: dict = {}
    try:
        cpm = adb.shell("dumpsys cpm 2>/dev/null | grep -A1 'IPD Data'", timeout=10.0)
        out.update(parse_cpm_ipd(cpm))
    except Exception:
        log.debug("could not read CPM IPD", exc_info=True)

    try:
        values = adb.shell(
            "settings get system eye_tracking_calibration_needed; "
            "settings get system user_eye_calibration_status; "
            "settings get system user_face_calibration_in_progress",
            timeout=8.0,
        ).splitlines()
        values = [v.strip() for v in values]
        if values and values[0] in ("0", "1"):
            out["eye_calibration_needed"] = values[0] == "1"
        if len(values) > 1 and values[1].lstrip("-").isdigit():
            out["eye_calibration_status"] = int(values[1])
        if len(values) > 2 and values[2] in ("0", "1"):
            out["face_calibration_in_progress"] = values[2] == "1"
    except Exception:
        log.debug("could not read calibration settings", exc_info=True)

    if not check_root:
        return out
    try:
        ipd_text, _, _, mtimes = _read_root_files(adb)
        out.update(parse_ipd_textproto(ipd_text))
        if "ipd_calibrated_at" not in out and "ipd" in mtimes:
            out["ipd_calibrated_at"] = _iso(mtimes["ipd"])
        if "eye" in mtimes:
            out["eye_calibrated_at"] = _iso(mtimes["eye"])
        if "face" in mtimes:
            out["face_calibrated_at"] = _iso(mtimes["face"])
    except Exception:
        log.debug("could not read openpx calibration files", exc_info=True)
    return out
