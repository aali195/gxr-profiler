"""Install staging, preview and job execution for explicit APK/OBB installs."""

from __future__ import annotations

import copy
import hashlib
import logging
import os
import shutil
import threading
import time
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from gxr_tools.core.adb import AdbClient, RealAdb, resolve_serial
from gxr_tools.core.paths import default_reports_dir, ensure_writable_dir, runtime_dir

from ..core.apk import read_apk_metadata, read_xapk_manifest
from ..core.apps import parse_obb_name, validate_obb_filename
from ..core.install_files import (
    MAX_STAGED_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_XAPK_ENTRIES,
    MAX_XAPK_UNCOMPRESSED,
    MIN_FREE_BYTES,
    STAGING_RETENTION_S,
    StagedInstallFile,
    normalize_relative_path,
    package_from_obb_path,
    package_or_empty,
    safe_basename,
    validate_upload_name,
)
from ..core.install_job import InstallJobMixin
from ..core.install_plan import InstallPlanMixin

log = logging.getLogger(__name__)


class InstallManager(InstallPlanMixin, InstallJobMixin):
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
        self._default_staging = staging_dir is None
        if staging_dir:
            self.staging_root = Path(staging_dir)
        else:
            # Keep each running manager in its own staging folder so a second
            # window cannot clear files that belong to an active install.
            self.staging_root = runtime_dir() / "apps-staging" / str(os.getpid())
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
            if self._default_staging:
                self._prune_old_staging()
        except OSError:
            log.warning("could not clear install staging", exc_info=True)

    def _prune_old_staging(self) -> None:
        """Remove abandoned per-process staging folders from crashed managers."""
        parent = self.staging_root.parent
        if not parent.is_dir():
            return
        now = time.time()
        for entry in parent.iterdir():
            if entry == self.staging_root or not entry.is_dir():
                continue
            try:
                if now - entry.stat().st_mtime > STAGING_RETENTION_S:
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                log.debug("could not prune staging folder %s", entry, exc_info=True)

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
            relative = normalize_relative_path(relative_path, base)
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
                package = package_or_empty(meta.get("package") or "")
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
                path_package = package_from_obb_path(relative)
                package = package_or_empty(parsed.get("package") or "") or path_package
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
            manifest_package = package_or_empty(manifest.get("package") or "")
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
                    base = safe_basename(pure.name)
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
                        package = package_or_empty(meta.get("package") or "")
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
                        path_package = package_from_obb_path(raw_name)
                        package = package_or_empty(parsed.get("package") or "") or path_package or manifest_package
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
                # The UI removes a whole XAPK by its bundle id.
                item = next((entry for entry in self._staged.values() if entry.bundle_id == stage_id), None)
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
