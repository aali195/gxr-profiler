"""Parsed directory entries for the file explorer."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass

from .file_paths import normalize_path

KIND_BY_PERMISSION = {
    "d": "dir",
    "-": "file",
    "l": "link",
}


@dataclass(frozen=True, slots=True)
class FileEntry:
    name: str
    path: str
    kind: str
    size: int | None
    modified: str
    target: str | None = None


def entry_to_dict(entry: FileEntry) -> dict:
    return {
        "name": entry.name,
        "path": entry.path,
        "kind": entry.kind,
        "size": entry.size,
        "modified": entry.modified,
        "target": entry.target,
    }


def parse_ls_line(line: str, directory: str) -> FileEntry | None:
    """Parse one ``ls -lAN`` row.

    Toybox emits ``perms links owner group size YYYY-MM-DD HH:MM name``.  The
    name is the remainder, so spaces are preserved.
    """
    stripped = line.rstrip("\r\n")
    if not stripped or stripped.startswith("total ") or stripped.startswith("ls:"):
        return None
    parts = stripped.split(None, 7)
    if len(parts) < 8:
        return None
    perms, _links, _owner, _group, size_text, date, time, raw_name = parts
    if not date[:4].isdigit():
        return None
    name = raw_name
    target = None
    kind = KIND_BY_PERMISSION.get(perms[:1], "other")
    if kind == "link" and " -> " in name:
        name, target = name.split(" -> ", 1)
    if name in {"", ".", ".."} or name.startswith(".gxr-upload-"):
        return None
    try:
        size = int(size_text)
    except ValueError:
        size = None
    return FileEntry(
        name=name,
        path=posixpath.join(normalize_path(directory), name),
        kind=kind,
        size=size,
        modified=f"{date} {time}",
        target=target,
    )


def parse_ls_listing(text: str, directory: str) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for line in (text or "").splitlines():
        entry = parse_ls_line(line, directory)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda item: (item.kind != "dir", item.name.casefold()))
    return entries
