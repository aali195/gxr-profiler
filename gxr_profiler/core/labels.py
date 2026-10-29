"""Human-friendly labels derived from the canonical column registry."""

from __future__ import annotations

from dataclasses import dataclass

from .columns import BANDS, COLUMN_BY_NAME

__all__ = ["BANDS", "Label", "friendly", "label"]


@dataclass(frozen=True)
class Label:
    name: str
    unit: str = ""
    group: str = "misc"
    tech: str = ""


def _pretty(col: str) -> str:
    return col.replace("_", " ").strip().capitalize()


def label(col: str) -> Label:
    c = COLUMN_BY_NAME.get(col)
    if c is None:
        return Label(_pretty(col), tech=col)
    return Label(c.label, c.unit, c.group, c.name)


def friendly(col: str) -> str:
    return label(col).name
