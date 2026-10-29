"""Schema metadata for run files, derived from the column registry."""

from __future__ import annotations

from .columns import COLUMN_BY_NAME

SCHEMA_VERSION = 6


def describe(col: str) -> dict:
    """Return {group, unit, kind, source} for a column name."""
    c = COLUMN_BY_NAME.get(col)
    if c is None:
        return {"group": "misc", "unit": "", "kind": "poll", "source": ""}
    return {"group": c.group, "unit": c.unit, "kind": c.kind, "source": c.source}


def columns_meta(columns: list[str]) -> dict[str, dict]:
    return {c: describe(c) for c in columns}
