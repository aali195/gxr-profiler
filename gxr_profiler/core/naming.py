"""Run label and output-filename validation."""

from __future__ import annotations

import re
import unicodedata

MAX_NAME_LENGTH = 100
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ALLOWED_PUNCT = frozenset(" ._-")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value or "")


def validate_run_name(name: str) -> str:
    """Return a safe, portable run name or raise ValueError.

    Unicode letters/digits are allowed; separators, control characters and
    Windows-invalid characters are not.
    """
    raw = name or ""
    if raw != raw.strip():
        raise ValueError("invalid run name: leading/trailing whitespace is not allowed")
    name = _nfc(raw)
    if not name:
        raise ValueError("invalid run name: name cannot be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"invalid run name: maximum {MAX_NAME_LENGTH} characters")
    if not name[0].isalnum():
        raise ValueError("invalid run name: must start with a letter or digit")
    if any(not (ch.isalnum() or ch in _ALLOWED_PUNCT) for ch in name):
        raise ValueError("invalid run name: use letters, digits, spaces, '.', '_' or '-'")
    if name.endswith((".", " ")):
        raise ValueError("invalid run name: cannot end with a dot or space")
    if name.split(".", 1)[0].strip().upper() in _RESERVED:
        raise ValueError("invalid run name: reserved Windows device name")
    if name.casefold().endswith((".csv", ".json")):
        raise ValueError("invalid run name: file suffixes are reserved")
    return name


def base_label(label: str) -> str:
    """Strip an optional .csv suffix and validate the label."""
    return validate_run_name((label or "").removesuffix(".csv"))


def safe_filename(value: str, fallback: str = "run") -> str:
    """Turn a label/expression into a cross-platform filename stem."""
    value = _INVALID.sub("_", _nfc(value)).rstrip(" .")
    value = value[:MAX_NAME_LENGTH]
    if not value or value.split(".", 1)[0].strip().upper() in _RESERVED:
        return fallback
    return value
