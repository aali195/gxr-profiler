"""Shared parsing helpers."""

from __future__ import annotations


def split_sections(text: str) -> dict[str, list[str]]:
    """Split '###NAME' delimited output into {NAME: [lines]}."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("###"):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            stripped = line.strip()
            if stripped and not stripped.startswith("cat:") and "Permission denied" not in stripped:
                sections[current].append(stripped)
    return sections
