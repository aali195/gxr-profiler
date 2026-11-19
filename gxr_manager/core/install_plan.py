"""Planning helpers for staged APK/OBB installs."""

from __future__ import annotations

import logging
import re
import shlex

from gxr_core.adb import AdbClient

from .apps import build_install_args, format_adb_command, is_critical_package, obb_remote_path
from .install_files import MAX_INSTALL_FILES, StagedInstallFile, device_free_bytes, package_or_empty

log = logging.getLogger(__name__)


class InstallPlanMixin:
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
            package = package_or_empty((obb_packages or {}).get(item.id, "") or item.package)
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
                free = device_free_bytes(adb.shell("df -k /data", timeout=10.0))
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
