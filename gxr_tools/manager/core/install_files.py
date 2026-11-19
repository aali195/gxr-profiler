"""Shared install-file validation, staging models and timeout/output helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from ..core.apps import (
    validate_package_name,
)

MAX_INSTALL_FILES = 64
MAX_UPLOAD_BYTES = 32 * 1024**3
MAX_STAGED_BYTES = 64 * 1024**3
MAX_XAPK_ENTRIES = 2000
MAX_XAPK_UNCOMPRESSED = 64 * 1024**3
MIN_FREE_BYTES = 512 * 1024**2
STAGING_RETENTION_S = 7 * 24 * 3600
INSTALL_TIMEOUT_S = 900.0
MAX_PUSH_TIMEOUT_S = 3600.0
OUTPUT_LIMIT = 8000

_ALLOWED_SUFFIXES = {".apk", ".obb", ".xapk"}
_BAD_NAME_CHARS = set('<>:"|?*')


def install_failed(output: str, returncode: int) -> bool:
    if returncode != 0:
        return True
    for raw in (output or "").splitlines():
        line = raw.strip().lower()
        if line.startswith(("failure", "error", "exception")):
            return True
        if "install_failed" in line or "failed to install" in line:
            return True
    return False


class InstallStepError(RuntimeError):
    pass


class StagedFileDict(TypedDict):
    id: str
    name: str
    kind: str
    size: int
    sha256: str
    relative_path: str
    package: str
    version_code: int | None
    version_name: str
    split: str
    bundle_id: str
    bundle_name: str
    readable: bool
    warnings: list[str]


@dataclass
class StagedInstallFile:
    id: str
    name: str
    path: Path
    kind: str
    size: int
    sha256: str
    relative_path: str = ""
    package: str = ""
    version_code: int | None = None
    version_name: str = ""
    split: str = ""
    bundle_id: str = ""
    bundle_name: str = ""
    readable: bool = True
    warnings: list[str] = field(default_factory=list)

    def public(self) -> StagedFileDict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "relative_path": self.relative_path,
            "package": self.package,
            "version_code": self.version_code,
            "version_name": self.version_name,
            "split": self.split,
            "bundle_id": self.bundle_id,
            "bundle_name": self.bundle_name,
            "readable": self.readable,
            "warnings": list(self.warnings),
        }


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def clean_output(text: str) -> str:
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.rstrip() for line in value.splitlines()]
    value = "\n".join(line for line in lines if line)
    if len(value) > OUTPUT_LIMIT:
        return value[:OUTPUT_LIMIT] + "\n... (truncated)"
    return value


def safe_basename(name: str) -> str:
    base = (name or "").strip()
    if not base or len(base) > 255 or base in {".", ".."}:
        raise ValueError("invalid file name")
    if base != base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]:
        raise ValueError("file name must not contain a path")
    if any(ch in _BAD_NAME_CHARS or ord(ch) < 32 for ch in base):
        raise ValueError("file name contains unsupported characters")
    return base


def validate_upload_name(name: str) -> str:
    base = safe_basename(name)
    if Path(base).suffix.lower() not in _ALLOWED_SUFFIXES:
        raise ValueError("unsupported file type; choose an APK, OBB or XAPK file")
    return base


def normalize_relative_path(value: str, fallback: str) -> str:
    text = (value or "").replace("\\", "/").strip()
    text = "".join(ch for ch in text if ord(ch) >= 32)
    parts = [part for part in text.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("relative path must not contain '..'")
    return ("/".join(parts) or fallback)[:512]


def package_from_obb_path(path: str) -> str:
    parts = (path or "").replace("\\", "/").split("/")
    for index in range(len(parts) - 2):
        if parts[index].lower() == "android" and parts[index + 1].lower() == "obb":
            try:
                return validate_package_name(parts[index + 2])
            except ValueError:
                return ""
    return ""


def package_or_empty(package: str) -> str:
    try:
        return validate_package_name(package)
    except ValueError:
        return ""


def push_timeout(size: int) -> float:
    # Wireless ADB can be slow; allow roughly 0.5 MB/s plus a minute of setup.
    return min(MAX_PUSH_TIMEOUT_S, max(120.0, 60.0 + size / (512 * 1024)))


def device_free_bytes(text: str) -> int | None:
    for raw in reversed((text or "").splitlines()):
        parts = raw.split()
        if len(parts) >= 4 and parts[3].isdigit():
            return int(parts[3]) * 1024
    return None
