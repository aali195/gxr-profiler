"""Path validation and protected-root rules for the file explorer.

The headset is Linux, so all paths use POSIX semantics even though the manager
runs on Windows.  These helpers are pure and independent of ADB.
"""

from __future__ import annotations

import posixpath

from .file_errors import InvalidName, InvalidPath, PathDenied

MAX_NAME_BYTES = 255
MAX_PATH_CHARS = 4096

# Exact paths that may never be deleted or replaced, even with root.
PROTECTED_EXACT = frozenset(
    {
        "/",
        "/system",
        "/vendor",
        "/product",
        "/apex",
        "/metadata",
        "/persist",
        "/data",
        "/data/user",
        "/data/user_de",
        "/data/local",
        "/data/dalvik-cache",
        "/data/tombstones",
        "/data/media",
        "/storage",
        "/sdcard",
        "/mnt",
        "/proc",
        "/sys",
        "/dev",
    }
)

# Whole subtrees that are always protected.
PROTECTED_PREFIXES = (
    "/system",
    "/vendor",
    "/product",
    "/apex",
    "/metadata",
    "/persist",
    "/data/system",
    "/data/app",
    "/data/misc",
    "/data/vendor",
    "/data/adb",
    "/mnt",
    "/proc",
    "/sys",
    "/dev",
)

# Paths the normal shell user can write without root.
SHARED_WRITE_ROOTS = (
    "/sdcard",
    "/storage/emulated",
    "/data/local/tmp",
)


def normalize_path(value: str) -> str:
    """Return a normalised absolute POSIX path or raise ``InvalidPath``."""
    if not isinstance(value, str) or not value:
        raise InvalidPath("a path is required")
    if not value.startswith("/"):
        raise InvalidPath("paths must be absolute")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise InvalidPath("paths cannot contain control characters")
    if len(value) > MAX_PATH_CHARS:
        raise InvalidPath("path is too long")
    normalized = posixpath.normpath(value)
    if normalized.startswith("//"):
        normalized = "/" + normalized.lstrip("/")
    if not normalized.startswith("/"):
        raise InvalidPath("paths must be absolute")
    return normalized


def validate_name(value: str) -> str:
    """Validate a single file or folder name (no separators, no ``.``/``..``)."""
    if not isinstance(value, str) or not value:
        raise InvalidName("a name is required")
    if value in {".", ".."}:
        raise InvalidName("that name is reserved")
    if "/" in value or "\\" in value:
        raise InvalidName("names cannot contain path separators")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise InvalidName("names cannot contain control characters")
    if len(value.encode("utf-8")) > MAX_NAME_BYTES:
        raise InvalidName("name is too long")
    return value


def join_path(directory: str, name: str) -> str:
    return posixpath.join(normalize_path(directory), validate_name(name))


def parent_path(path: str) -> str | None:
    normalized = normalize_path(path)
    if normalized == "/":
        return None
    return posixpath.dirname(normalized) or "/"


def basename(path: str) -> str:
    return posixpath.basename(normalize_path(path))


def is_protected(path: str) -> bool:
    normalized = normalize_path(path)
    if normalized in PROTECTED_EXACT:
        return True
    return any(normalized == root or normalized.startswith(root + "/") for root in PROTECTED_PREFIXES)


def ensure_mutable(path: str) -> None:
    if is_protected(path):
        raise PathDenied(f"{path} is a protected system path")


def writable_without_root(path: str) -> bool:
    normalized = normalize_path(path)
    return any(normalized == root or normalized.startswith(root + "/") for root in SHARED_WRITE_ROOTS)


def ensure_writable(path: str, root: bool) -> None:
    if not root and not writable_without_root(path):
        raise PathDenied("enable root access to write outside shared storage")


def is_within(path: str, parent: str) -> bool:
    """True when ``path`` is ``parent`` or lives inside it."""
    child = normalize_path(path)
    root = normalize_path(parent)
    return child == root or child.startswith(root.rstrip("/") + "/")


def ensure_not_within(path: str, parent: str) -> None:
    if is_within(path, parent):
        raise InvalidPath("cannot move a folder into itself")
