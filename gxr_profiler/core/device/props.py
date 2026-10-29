"""Android property snapshot."""

from __future__ import annotations

import re

from ..adb import AdbClient

_PROP_RE = re.compile(r"^\[([^\]]+)\]: \[(.*)\]$")


def all_props(adb: AdbClient) -> dict[str, str]:
    txt = adb.run(["shell", "getprop"], timeout=15.0).stdout or ""
    props: dict[str, str] = {}
    for line in txt.splitlines():
        m = _PROP_RE.match(line.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return props
