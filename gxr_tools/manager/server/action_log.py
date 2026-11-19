"""Local JSONL audit log for explicit device-changing tool actions."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from gxr_tools.core.paths import ensure_writable_dir

log = logging.getLogger(__name__)


def append_action_log(log_dir: str, filename: str, entry: dict) -> bool:
    try:
        ensure_writable_dir(log_dir)
        record = {"at": datetime.now(UTC).isoformat(), **entry}
        with (Path(log_dir) / filename).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        log.warning("could not write action log %s", filename, exc_info=True)
        return False
