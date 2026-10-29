"""Small filesystem helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: str | os.PathLike[str], text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.tmp-", dir=str(p.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(path: str | os.PathLike[str], data: dict, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent))
