"""Staging, preview and execution for explicit APK/OBB installs."""

from __future__ import annotations

import copy
import hashlib
import logging
import os
import re
import shlex
import shutil
import threading
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from ..core.adb import AdbClient, RealAdb, resolve_serial
from ..core.apk import read_apk_metadata, read_xapk_manifest
from ..core.apps import (
    build_install_args,
    format_adb_command,
    is_critical_package,
    obb_remote_path,
    parse_obb_name,
    validate_obb_filename,
    validate_package_name,
)
from ..core.paths import default_reports_dir, ensure_writable_dir, runtime_dir
from .action_log import append_action_log

log = logging.getLogger(__name__)

MAX_INSTALL_FILES = 64
MAX_UPLOAD_BYTES = 32 * 1024**3
MAX_STAGED_BYTES = 64 * 1024**3
MAX_XAPK_ENTRIES = 2000
MAX_XAPK_UNCOMPRESSED = 64 * 1024**3
MIN_FREE_BYTES = 512 * 1024**2
INSTALL_TIMEOUT_S = 900.0
MAX_PUSH_TIMEOUT_S = 3600.0
OUTPUT_LIMIT = 8000

_ALLOWED_SUFFIXES = {".apk", ".obb", ".xapk"}
_BAD_NAME_CHARS = set('<>:"|?*')


def _install_failed(output: str, returncode: int) -> bool:
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

    def public(self) -> dict:
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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_output(text: str) -> str:
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.rstrip() for line in value.splitlines()]
    value = "\n".join(line for line in lines if line)
    if len(value) > OUTPUT_LIMIT:
        return value[:OUTPUT_LIMIT] + "\n... (truncated)"
    return value


def _safe_basename(name: str) -> str:
    base = (name or "").strip()
    if not base or len(base) > 255 or base in {".", ".."}:
        raise ValueError("invalid file name")
    if base != base.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]:
        raise ValueError("file name must not contain a path")
    if any(ch in _BAD_NAME_CHARS or ord(ch) < 32 for ch in base):
        raise ValueError("file name contains unsupported characters")
    return base


def validate_upload_name(name: str) -> str:
    base = _safe_basename(name)
    if Path(base).suffix.lower() not in _ALLOWED_SUFFIXES:
        raise ValueError("unsupported file type; choose an APK, OBB or XAPK file")
    return base


def _normalize_relative_path(value: str, fallback: str) -> str:
    text = (value or "").replace("\\", "/").strip()
    text = "".join(ch for ch in text if ord(ch) >= 32)
    parts = [part for part in text.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("relative path must not contain '..'")
    return ("/".join(parts) or fallback)[:512]


def _package_from_obb_path(path: str) -> str:
    parts = (path or "").replace("\\", "/").split("/")
    for index in range(len(parts) - 2):
        if parts[index].lower() == "android" and parts[index + 1].lower() == "obb":
            try:
                return validate_package_name(parts[index + 2])
            except ValueError:
                return ""
    return ""


def _package_or_empty(package: str) -> str:
    try:
        return validate_package_name(package)
    except ValueError:
        return ""


def _push_timeout(size: int) -> float:
    # Wireless ADB can be slow; allow roughly 0.5 MB/s plus a minute of setup.
    return min(MAX_PUSH_TIMEOUT_S, max(120.0, 60.0 + size / (512 * 1024)))


def _device_free_bytes(text: str) -> int | None:
    for raw in reversed((text or "").splitlines()):
        parts = raw.split()
        if len(parts) >= 4 and parts[3].isdigit():
            return int(parts[3]) * 1024
    return None


class InstallManager:
    """Owns install staging and at most one install job at a time."""

    def __init__(
        self,
        serial: str | None = None,
        reports_dir: str | None = None,
        user: int = 0,
        staging_dir: str | None = None,
        busy_check: Callable[[], bool] | None = None,
        adb_factory: Callable[..., AdbClient] = RealAdb,
        device_lock: threading.Lock | None = None,
    ) -> None:
        self.serial = serial
        self.user = user
        self.reports_dir = reports_dir or str(Path(default_reports_dir()) / "apps")
        self.staging_root = Path(staging_dir) if staging_dir else runtime_dir() / "apps-staging"
        self.busy_check = busy_check
        self.adb_factory = adb_factory
        self.device_lock = device_lock or threading.Lock()
        self._lock = threading.Lock()
        self._job_lock = threading.Lock()
        self._staged: dict[str, StagedInstallFile] = {}
        self._job: dict | None = None

    def _adb(self) -> AdbClient:
        return self.adb_factory(serial=resolve_serial(self.serial))

    @property
    def upload_dir(self) -> Path:
        path = self.staging_root / ".uploads"
        ensure_writable_dir(path)
        return path

    @property
    def max_upload_bytes(self) -> int:
        return MAX_UPLOAD_BYTES

    def validate_upload(self, name: str, size_hint: int | None = None) -> str:
        base = validate_upload_name(name)
        if size_hint is not None and size_hint > MAX_UPLOAD_BYTES:
            raise ValueError("file is larger than the 32 GB upload limit")
        with self._lock:
            staged = sum(item.size for item in self._staged.values())
        if staged + (size_hint or 0) > MAX_STAGED_BYTES:
            raise ValueError("staged files exceed the 64 GB session limit")
        free = shutil.disk_usage(self.upload_dir).free
        if size_hint and free < size_hint + MIN_FREE_BYTES:
            raise OSError("not enough free disk space to stage this file")
        return base

    def cleanup(self) -> None:
        if self.active():
            return
        with self._lock:
            self._staged.clear()
        try:
            if self.staging_root.exists():
                shutil.rmtree(self.staging_root, ignore_errors=True)
        except OSError:
            log.warning("could not clear install staging", exc_info=True)

    def list_staged(self) -> list[dict]:
        with self._lock:
            return [item.public() for item in self._staged.values()]

    def state(self) -> dict:
        with self._lock:
            files = [item.public() for item in self._staged.values()]
        with self._job_lock:
            job = copy.deepcopy(self._job) if self._job else None
        return {"files": files, "job": job}

    def accept_upload(
        self,
        temp_path: str | Path,
        name: str,
        relative_path: str,
        sha256: str,
        size: int,
    ) -> dict:
        source = Path(temp_path)
        try:
            base = validate_upload_name(name)
            relative = _normalize_relative_path(relative_path, base)
            if size <= 0 or size > MAX_UPLOAD_BYTES or not source.is_file():
                raise ValueError("uploaded file is empty, missing or too large")
            if source.stat().st_size != size:
                raise ValueError("uploaded file size did not match the request")
            ensure_writable_dir(self.staging_root)
            suffix = Path(base).suffix.lower()
            if suffix == ".xapk":
                files, warnings = self._stage_xapk(source, base, relative)
            else:
                files = [self._stage_plain(source, base, relative, sha256, size)]
                warnings = []
            return {"ok": True, "files": [item.public() for item in files], "warnings": warnings}
        finally:
            if source.exists():
                try:
                    source.unlink()
                except OSError:
                    log.debug("could not remove upload temp file", exc_info=True)

    def _stage_plain(self, source: Path, name: str, relative: str, sha256: str, size: int) -> StagedInstallFile:
        stage_id = uuid.uuid4().hex
        stage_dir = self.staging_root / stage_id
        ensure_writable_dir(stage_dir)
        suffix = Path(name).suffix.lower()
        dest = stage_dir / ("file" + suffix)
        try:
            os.replace(source, dest)
        except OSError:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise
        warnings: list[str] = []
        package = ""
        version_code = None
        version_name = ""
        split = ""
        readable = True
        kind = suffix.lstrip(".")
        try:
            if kind == "apk":
                meta = read_apk_metadata(dest)
                package = _package_or_empty(meta.get("package") or "")
                version_code = meta.get("version_code")
                version_name = meta.get("version_name") or ""
                split = meta.get("split") or ""
                readable = not bool(meta.get("error"))
                if meta.get("error"):
                    warnings.append(meta["error"])
                elif not package:
                    warnings.append("the APK package name could not be read")
            else:
                validate_obb_filename(name)
                parsed = parse_obb_name(name)
                path_package = _package_from_obb_path(relative)
                package = _package_or_empty(parsed.get("package") or "") or path_package
                version_code = parsed.get("version_code")
                if parsed.get("package") and path_package and parsed["package"] != path_package:
                    warnings.append(f"OBB file name says {parsed['package']} but its folder says {path_package}")
                if not package:
                    warnings.append("OBB target package could not be inferred from the file name")
        except Exception:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise
        item = StagedInstallFile(
            id=stage_id,
            name=name,
            path=dest,
            kind=kind,
            size=size,
            sha256=sha256,
            relative_path=relative,
            package=package,
            version_code=version_code,
            version_name=version_name,
            split=split,
            warnings=warnings,
            readable=readable,
        )
        with self._lock:
            self._staged[item.id] = item
        return item

    def _stage_xapk(self, source: Path, name: str, relative: str) -> tuple[list[StagedInstallFile], list[str]]:
        bundle_id = uuid.uuid4().hex
        bundle_dir = self.staging_root / bundle_id
        ensure_writable_dir(bundle_dir)
        archive_path = bundle_dir / "bundle.xapk"
        try:
            os.replace(source, archive_path)
            manifest = read_xapk_manifest(archive_path)
            manifest_package = _package_or_empty(manifest.get("package") or "")
            warnings: list[str] = []
            if manifest.get("error"):
                warnings.append(manifest["error"])
            files: list[StagedInstallFile] = []
            with zipfile.ZipFile(archive_path) as archive:
                infos = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir()
                    and PurePosixPath(info.filename.replace("\\", "/")).suffix.lower() in {".apk", ".obb"}
                ]
                if len(infos) > MAX_XAPK_ENTRIES:
                    raise ValueError("XAPK contains too many files")
                total = sum(info.file_size for info in infos)
                if total > MAX_XAPK_UNCOMPRESSED:
                    raise ValueError("XAPK contents are larger than the 64 GB extraction limit")
                free = shutil.disk_usage(bundle_dir).free
                if total > free - MIN_FREE_BYTES:
                    raise ValueError("not enough free disk space to extract the XAPK")
                for index, info in enumerate(infos):
                    raw_name = info.filename.replace("\\", "/")
                    pure = PurePosixPath(raw_name)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise ValueError("XAPK contains an unsafe path")
                    if info.flag_bits & 0x1:
                        raise ValueError("encrypted XAPK entries are not supported")
                    suffix = pure.suffix.lower()
                    base = _safe_basename(pure.name)
                    if suffix == ".obb":
                        validate_obb_filename(base)
                    kind = suffix.lstrip(".")
                    dest = bundle_dir / f"{index:03d}{suffix}"
                    digest = hashlib.sha256()
                    written = 0
                    with archive.open(info) as src, dest.open("wb") as dst:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > info.file_size + 1024 * 1024:
                                raise ValueError("XAPK entry is larger than declared")
                            digest.update(chunk)
                            dst.write(chunk)
                    item_warnings: list[str] = []
                    package = ""
                    version_code = manifest.get("version_code")
                    version_name = manifest.get("version_name") or ""
                    split = ""
                    readable = True
                    if kind == "apk":
                        meta = read_apk_metadata(dest)
                        package = _package_or_empty(meta.get("package") or "")
                        version_code = (
                            meta.get("version_code") if meta.get("version_code") is not None else version_code
                        )
                        version_name = meta.get("version_name") or version_name
                        split = meta.get("split") or ""
                        readable = not bool(meta.get("error"))
                        if meta.get("error"):
                            item_warnings.append(meta["error"])
                        if not package and manifest_package:
                            package = manifest_package
                            item_warnings.append("used the XAPK manifest package name")
                        if manifest_package and package and package != manifest_package:
                            item_warnings.append(
                                f"APK package {package} differs from the XAPK manifest {manifest_package}"
                            )
                    else:
                        parsed = parse_obb_name(base)
                        path_package = _package_from_obb_path(raw_name)
                        package = _package_or_empty(parsed.get("package") or "") or path_package or manifest_package
                        version_code = parsed.get("version_code") or version_code
                        if parsed.get("package") and manifest_package and parsed["package"] != manifest_package:
                            item_warnings.append(
                                f"OBB package {parsed['package']} differs from the XAPK manifest {manifest_package}"
                            )
                        if not package:
                            item_warnings.append("OBB target package could not be inferred")
                    item = StagedInstallFile(
                        id=uuid.uuid4().hex,
                        name=base,
                        path=dest,
                        kind=kind,
                        size=written,
                        sha256=digest.hexdigest(),
                        relative_path=raw_name[:512],
                        package=package,
                        version_code=version_code,
                        version_name=version_name,
                        split=split,
                        bundle_id=bundle_id,
                        bundle_name=name,
                        readable=readable,
                        warnings=item_warnings,
                    )
                    files.append(item)
            if not any(item.kind == "apk" for item in files):
                raise ValueError("XAPK does not contain any APKs")
            with self._lock:
                for item in files:
                    self._staged[item.id] = item
            try:
                archive_path.unlink()
            except OSError:
                pass
            return files, warnings
        except Exception:
            shutil.rmtree(bundle_dir, ignore_errors=True)
            raise

    def discard(self, stage_id: str) -> dict:
        if self.active():
            raise RuntimeError("cannot remove staged files while an install is running")
        return self._discard_unchecked(stage_id)

    def _discard_unchecked(self, stage_id: str) -> dict:
        with self._lock:
            item = self._staged.get(stage_id)
            if item is None:
                raise LookupError("staged file not found or already removed")
            if item.bundle_id:
                removed = [entry for entry in self._staged.values() if entry.bundle_id == item.bundle_id]
                for entry in removed:
                    self._staged.pop(entry.id, None)
            else:
                removed = [item]
                self._staged.pop(item.id, None)
        for entry in removed:
            self._remove_dir(entry.path.parent)
        return {"ok": True, "removed": len(removed)}

    def clear(self) -> dict:
        if self.active():
            raise RuntimeError("cannot clear staged files while an install is running")
        with self._lock:
            removed = len(self._staged)
            self._staged.clear()
        try:
            if self.staging_root.exists():
                shutil.rmtree(self.staging_root, ignore_errors=True)
        except OSError:
            log.warning("could not clear install staging", exc_info=True)
        return {"ok": True, "removed": removed}

    def _remove_dir(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            root = self.staging_root.resolve()
            if resolved == root or root not in resolved.parents:
                return
            shutil.rmtree(resolved, ignore_errors=True)
        except OSError:
            log.debug("could not remove staging directory", exc_info=True)

    def _remove_items(self, items: list[StagedInstallFile]) -> None:
        seen: set[str] = set()
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            try:
                self._discard_unchecked(item.id)
            except LookupError:
                pass

    def _installed_version(self, adb: AdbClient | None, cache: dict, package: str) -> tuple[bool, int | None]:
        if package in cache:
            return cache[package]
        installed = False
        version = None
        if adb is not None:
            try:
                output = adb.shell("pm path " + shlex.quote(package), timeout=10.0)
                installed = "package:" in output
                if installed:
                    detail = adb.shell("dumpsys package " + shlex.quote(package), timeout=20.0)
                    match = re.search(r"\bversionCode=(\d+)", detail)
                    if match:
                        version = int(match.group(1))
            except Exception:
                log.debug("installed package check failed for %s", package, exc_info=True)
        cache[package] = (installed, version)
        return cache[package]

    def preview(
        self, items: list[str], obb_packages: dict[str, str] | None = None, options: dict | None = None
    ) -> dict:
        options = options or {}
        obb_packages = obb_packages or {}
        ids = list(dict.fromkeys(items or []))
        if not ids:
            raise ValueError("select at least one staged file")
        if len(ids) > MAX_INSTALL_FILES:
            raise ValueError(f"too many staged files; the limit is {MAX_INSTALL_FILES}")
        with self._lock:
            records = [self._staged[item_id] for item_id in ids if item_id in self._staged]
        if len(records) != len(ids):
            raise ValueError("one or more staged files have expired; add them again")
        errors: list[str] = []
        warnings: list[str] = []
        apks = [item for item in records if item.kind == "apk"]
        obbs = [item for item in records if item.kind == "obb"]
        adb: AdbClient | None = None
        adb_error = ""
        if apks or obbs:
            try:
                adb = self._adb()
            except Exception as exc:
                adb_error = str(exc)
                errors.append(f"could not reach the headset: {adb_error}")
        if not apks and not obbs:
            errors.append("select at least one APK or OBB file")
        version_cache: dict[str, tuple[bool, int | None]] = {}
        groups: list[dict] = []
        grouped: dict[str, list[StagedInstallFile]] = {}
        for item in apks:
            if not item.readable:
                errors.append(f"{item.name}: not a readable APK")
            grouped.setdefault(item.package or "__unknown__", []).append(item)
        for package, files in grouped.items():
            for item in files:
                warnings.extend(f"{item.name}: {warning}" for warning in item.warnings)
            known = package != "__unknown__"
            if known and is_critical_package(package):
                errors.append(f"{package} is a critical system package; installs are blocked")
                continue
            if not known and len(files) > 1:
                warnings.append("Several APKs have unreadable package names; they will be installed as one split set.")
            if not known:
                if any(item.readable for item in files):
                    warnings.append(
                        "The APK package name could not be read; Android still verifies signatures, "
                        "but the critical-package guard cannot inspect it."
                    )
                package = ""
            files = sorted(
                files,
                key=lambda item: (
                    1 if item.split or "split" in item.name.lower() else 0,
                    item.name.casefold(),
                ),
            )
            split = len(files) > 1 or any(item.split for item in files)
            if len(files) == 1 and files[0].split:
                errors.append(f"{files[0].name} is a split APK; add its base APK")
            versions = {item.version_code for item in files if item.version_code is not None}
            if len(versions) > 1:
                warnings.append(f"{package or 'selected APKs'}: APK version codes differ")
            args = build_install_args(
                [str(item.path) for item in files],
                replace=bool(options.get("replace", True)),
                allow_downgrade=bool(options.get("allow_downgrade", False)),
                grant_permissions=bool(options.get("grant_permissions", False)),
                user=self.user,
                split=split,
            )
            groups.append(
                {
                    "package": package,
                    "label": ("Install " + package) if package else "Install selected APKs",
                    "critical": bool(package and is_critical_package(package)),
                    "split": split,
                    "apk_count": len(files),
                    "version_code": next(
                        (item.version_code for item in files if item.version_code is not None),
                        None,
                    ),
                    "files": [item.public() for item in files],
                    "args": args,
                    "command": format_adb_command(args),
                }
            )
        planned_packages = {group["package"] for group in groups if group["package"]}
        obb_plan: list[dict] = []
        seen_remote: set[str] = set()
        for item in obbs:
            warnings.extend(f"{item.name}: {warning}" for warning in item.warnings)
            package = _package_or_empty((obb_packages or {}).get(item.id, "") or item.package)
            if not package:
                errors.append(f"{item.name}: choose the target package")
                continue
            if is_critical_package(package):
                errors.append(f"{item.name}: {package} is a critical system package")
                continue
            try:
                remote = obb_remote_path(package, item.name)
            except ValueError as exc:
                errors.append(f"{item.name}: {exc}")
                continue
            if remote in seen_remote:
                errors.append(f"{item.name}: another OBB already targets {remote}")
                continue
            seen_remote.add(remote)
            if package not in planned_packages:
                if adb is None:
                    warnings.append(f"could not confirm {package} is installed: {adb_error or 'adb unavailable'}")
                else:
                    installed, installed_version = self._installed_version(adb, version_cache, package)
                    if not installed:
                        errors.append(f"{item.name}: {package} is not installed; include its APK in this batch")
                    elif (
                        item.version_code is not None
                        and installed_version is not None
                        and item.version_code != installed_version
                    ):
                        warnings.append(
                            f"{item.name}: OBB version {item.version_code} differs from installed version {installed_version}"
                        )
            group_version = next(
                (
                    group["version_code"]
                    for group in groups
                    if group["package"] == package and group["version_code"] is not None
                ),
                None,
            )
            if item.version_code is not None and group_version is not None and item.version_code != group_version:
                warnings.append(
                    f"{item.name}: OBB version {item.version_code} differs from APK version {group_version}"
                )
            remote_dir = remote.rsplit("/", 1)[0]
            obb_plan.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "package": package,
                    "version_code": item.version_code,
                    "size": item.size,
                    "sha256": item.sha256,
                    "remote_path": remote,
                    "remote_dir": remote_dir,
                    "local_path": str(item.path),
                    "command": format_adb_command(["push", str(item.path), remote]),
                    "mkdir_command": "adb shell mkdir -p " + shlex.quote(remote_dir),
                }
            )
        if adb is not None:
            try:
                free = _device_free_bytes(adb.shell("df -k /data", timeout=10.0))
                total = sum(item.size for item in records)
                if free is not None and total > free:
                    errors.append(
                        f"the headset has {free // (1024 * 1024)} MB free but this batch needs "
                        f"{total // (1024 * 1024)} MB"
                    )
                elif free is not None and total > free * 0.9:
                    warnings.append("the headset is close to full; the install may fail")
            except Exception:
                log.debug("device free-space check failed", exc_info=True)
        total_size = sum(item.size for item in records)
        warnings = list(dict.fromkeys(warnings))
        errors = list(dict.fromkeys(errors))
        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "groups": groups,
            "obb": obb_plan,
            "total_size": total_size,
            "options": {
                "replace": bool(options.get("replace", True)),
                "allow_downgrade": bool(options.get("allow_downgrade", False)),
                "grant_permissions": bool(options.get("grant_permissions", False)),
                "user": self.user,
            },
        }

    def active(self) -> bool:
        with self._job_lock:
            return bool(self._job and self._job.get("status") == "running")

    def start(
        self,
        items: list[str],
        obb_packages: dict[str, str] | None = None,
        options: dict | None = None,
        confirm: bool = False,
    ) -> dict:
        if not confirm:
            raise ValueError("confirmation is required")
        if self.busy_check and self.busy_check():
            raise PermissionError("cannot install packages while a recording is in progress")
        with self._job_lock:
            if self._job and self._job.get("status") == "running":
                raise RuntimeError("an install is already running")
        plan = self.preview(items, obb_packages, options)
        if plan["errors"]:
            raise ValueError("; ".join(plan["errors"]))
        steps: list[dict] = []
        actions: list[tuple[str, str, dict]] = []
        for index, group in enumerate(plan["groups"]):
            step_id = f"install-{index}"
            steps.append(
                {
                    "id": step_id,
                    "label": group["label"] + (f" ({group['apk_count']} APKs)" if group["apk_count"] > 1 else ""),
                    "status": "pending",
                    "output": "",
                }
            )
            actions.append((step_id, "install", group))
            if group["package"]:
                verify_id = f"verify-{index}"
                steps.append(
                    {
                        "id": verify_id,
                        "label": "Verify " + group["package"],
                        "status": "pending",
                        "output": "",
                    }
                )
                actions.append((verify_id, "verify_package", group))
        for index, obb in enumerate(plan["obb"]):
            step_id = f"push-{index}"
            steps.append(
                {
                    "id": step_id,
                    "label": "Push " + obb["name"],
                    "status": "pending",
                    "output": "",
                }
            )
            actions.append((step_id, "push_obb", obb))
            verify_id = f"verify-obb-{index}"
            steps.append(
                {
                    "id": verify_id,
                    "label": "Verify " + obb["name"],
                    "status": "pending",
                    "output": "",
                }
            )
            actions.append((verify_id, "verify_obb", obb))
        job = {
            "id": uuid.uuid4().hex,
            "status": "running",
            "step": "Preparing",
            "steps": steps,
            "output": "",
            "error": "",
            "started_at": _now(),
            "finished_at": "",
            "result": {},
        }
        records = self._records_for(plan)
        with self._job_lock:
            if self._job and self._job.get("status") == "running":
                raise RuntimeError("an install is already running")
            self._job = job
        thread = threading.Thread(
            target=self._run_job,
            args=(job["id"], plan, actions, records),
            name="gxr-install",
            daemon=True,
        )
        thread.start()
        return self.status(job["id"])

    def _records_for(self, plan: dict) -> list[StagedInstallFile]:
        ids: list[str] = []
        for group in plan["groups"]:
            ids.extend(item["id"] for item in group["files"])
        ids.extend(item["id"] for item in plan["obb"])
        with self._lock:
            records = [self._staged[item_id] for item_id in dict.fromkeys(ids) if item_id in self._staged]
        if len(records) != len(dict.fromkeys(ids)):
            raise ValueError("one or more staged files have expired; add them again")
        return records

    def _set_step(self, job_id: str, step_id: str, status: str, output: str | None = None) -> None:
        with self._job_lock:
            if not self._job or self._job["id"] != job_id:
                return
            for step in self._job["steps"]:
                if step["id"] == step_id:
                    step["status"] = status
                    if output is not None:
                        step["output"] = _clean_output(output)
                    if status == "running":
                        self._job["step"] = step["label"]
                    break

    def _finish(self, job_id: str, status: str, error: str = "", result: dict | None = None) -> None:
        with self._job_lock:
            if not self._job or self._job["id"] != job_id:
                return
            self._job["status"] = status
            self._job["error"] = _clean_output(error)
            self._job["finished_at"] = _now()
            if result is not None:
                self._job["result"] = result
            if status == "done":
                self._job["step"] = "Finished"
            elif status == "error":
                self._job["step"] = "Failed"

    def _require_not_recording(self) -> None:
        if self.busy_check and self.busy_check():
            raise InstallStepError("a recording started; the install was stopped")

    def _run_job(
        self,
        job_id: str,
        plan: dict,
        actions: list[tuple[str, str, dict]],
        records: list[StagedInstallFile],
    ) -> None:
        output_parts: list[str] = []
        current_step = ""
        try:
            adb = self._adb()
            with self.device_lock:
                for step_id, kind, payload in actions:
                    self._require_not_recording()
                    current_step = step_id
                    self._set_step(job_id, step_id, "running")
                    if kind == "install":
                        proc = adb.run(payload["args"], timeout=INSTALL_TIMEOUT_S)
                        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                        if _install_failed(output, proc.returncode):
                            raise InstallStepError(
                                _clean_output(output) or f"adb install exited with code {proc.returncode}"
                            )
                        output_parts.append(f"{payload['label']}:\n{_clean_output(output)}")
                        self._set_step(job_id, step_id, "done", output)
                    elif kind == "verify_package":
                        package = payload["package"]
                        check = adb.shell("pm path " + shlex.quote(package), timeout=15.0)
                        if "package:" not in check:
                            raise InstallStepError(f"{package} was not found after install")
                        notes = [check.strip()]
                        expected_version = payload.get("version_code")
                        if expected_version is not None:
                            detail = adb.shell("dumpsys package " + shlex.quote(package), timeout=20.0)
                            match = re.search(r"\bversionCode=(\d+)", detail)
                            if not match:
                                raise InstallStepError(f"{package}: could not verify versionCode {expected_version}")
                            found_version = int(match.group(1))
                            if found_version != int(expected_version):
                                raise InstallStepError(
                                    f"{package} reports versionCode {found_version}, expected {expected_version}"
                                )
                            notes.append(f"versionCode={found_version}")
                        self._set_step(job_id, step_id, "done", "\n".join(notes))
                    elif kind == "push_obb":
                        adb.shell("mkdir -p " + shlex.quote(payload["remote_dir"]), timeout=15.0)
                        proc = adb.run(
                            ["push", payload["local_path"], payload["remote_path"]],
                            timeout=_push_timeout(int(payload.get("size") or 0)),
                        )
                        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                        if proc.returncode != 0:
                            raise InstallStepError(
                                _clean_output(output) or f"adb push exited with code {proc.returncode}"
                            )
                        output_parts.append(f"{payload['name']}:\n{_clean_output(output)}")
                        self._set_step(job_id, step_id, "done", output)
                    elif kind == "verify_obb":
                        check = adb.shell(
                            "stat -c %s " + shlex.quote(payload["remote_path"]),
                            timeout=15.0,
                        )
                        try:
                            remote_size = int(check.strip().splitlines()[-1])
                        except (ValueError, IndexError):
                            raise InstallStepError(f"{payload['name']}: could not verify the remote file") from None
                        if remote_size != int(payload.get("size") or 0):
                            raise InstallStepError(
                                f"{payload['name']}: device has {remote_size} bytes, expected {payload['size']}"
                            )
                        self._set_step(job_id, step_id, "done", f"{remote_size} bytes")
            packages = [group["package"] for group in plan["groups"] if group["package"]]
            packages.extend(item["package"] for item in plan["obb"] if item["package"])
            packages = list(dict.fromkeys(packages))
            self._remove_items(records)
            self._log_job(job_id, plan, True, "", "\n\n".join(output_parts))
            self._finish(
                job_id,
                "done",
                result={
                    "packages": packages,
                    "apk_count": sum(group["apk_count"] for group in plan["groups"]),
                    "obb_count": len(plan["obb"]),
                },
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            if current_step:
                self._set_step(job_id, current_step, "error", message)
            self._log_job(job_id, plan, False, message, "\n\n".join(output_parts))
            self._finish(job_id, "error", message)

    def _log_job(self, job_id: str, plan: dict, ok: bool, error: str, output: str) -> None:
        files = []
        for group in plan["groups"]:
            for item in group["files"]:
                files.append(
                    {
                        "name": item["name"],
                        "size": item["size"],
                        "sha256": item["sha256"],
                        "package": item["package"],
                        "kind": "apk",
                    }
                )
        for item in plan["obb"]:
            files.append(
                {
                    "name": item["name"],
                    "size": item["size"],
                    "sha256": item["sha256"],
                    "package": item["package"],
                    "kind": "obb",
                }
            )
        packages = [group["package"] for group in plan["groups"] if group["package"]]
        packages.extend(item["package"] for item in plan["obb"] if item["package"])
        append_action_log(
            self.reports_dir,
            "app-actions.jsonl",
            {
                "ok": ok,
                "package": ", ".join(dict.fromkeys(packages)),
                "action": "install",
                "command": "\n".join(
                    [group["command"] for group in plan["groups"]]
                    + [item["mkdir_command"] + "\n" + item["command"] for item in plan["obb"]]
                ),
                "output": _clean_output(output)[-OUTPUT_LIMIT:],
                "error": error,
                "job_id": job_id,
                "files": files,
                "obb_count": len(plan["obb"]),
                "options": plan["options"],
            },
        )

    def status(self, job_id: str) -> dict:
        with self._job_lock:
            if not self._job or self._job["id"] != job_id:
                raise LookupError("install job not found")
            return copy.deepcopy(self._job)
