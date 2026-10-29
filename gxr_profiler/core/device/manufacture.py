"""Manufacture date, sales region, and approximate first-setup date."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from ..adb import AdbClient

log = logging.getLogger(__name__)

FIRST_SETUP_MARKERS = (
    "/data/system/users/0/settings_ssaid.xml",
    "/data/system/users/0/settings_secure.xml",
)


def parse_manufacture_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return text


def region_info(props: dict) -> dict:
    iso = (
        props.get("mdc.countryiso_code") or props.get("persist.sys.selected_country_iso") or ""
    ).strip().upper() or None
    name = (props.get("mdc.country_code") or "").strip() or None
    if name and name.isupper():
        name = name.title()
    sales = (props.get("ro.csc.sales_code") or props.get("ro.boot.sales_code") or "").strip() or None
    locale = (props.get("persist.sys.locale") or props.get("ro.product.locale") or "").strip() or None
    if not any((iso, name, sales, locale)):
        return {}
    return {
        "country": name,
        "country_iso": iso,
        "sales_code": sales,
        "locale": locale,
    }


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), UTC).isoformat(timespec="seconds")
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def first_setup_info(adb: AdbClient, check_root: bool) -> dict:
    if not check_root:
        return {}
    marks = " ".join(FIRST_SETUP_MARKERS)
    script = "su -c 'stat -c %Y " + marks + " 2>/dev/null'"
    try:
        text = adb.shell(script, timeout=8.0)
    except Exception:
        log.debug("could not read first-setup markers", exc_info=True)
        return {}
    epochs: list[float] = []
    for line in text.splitlines():
        try:
            epochs.append(float(line.strip()))
        except ValueError:
            continue
    if not epochs:
        return {}
    # The oldest user settings marker is the closest available signal for the
    # first user setup. It is not an authoritative reset timestamp.
    when = min(epochs)
    iso = _iso(when)
    if not iso:
        return {}
    days = max(0, int((datetime.now(UTC) - datetime.fromtimestamp(when, UTC)).total_seconds() // 86400))
    return {"first_setup_at": iso, "first_setup_days": days}
