"""File-explorer service: listing, transfers and confirmed file operations."""

from __future__ import annotations

import logging
import os
import posixpath
import shlex
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from gxr_tools.core.adb import AdbClient, AdbError, RealAdb, resolve_serial
from gxr_tools.core.paths import default_reports_dir, runtime_dir

from ..core.file_entries import entry_to_dict, parse_ls_listing
from ..core.file_errors import (
    ConfirmationRequired,
    DeviceBusy,
    FileConflict,
    FileMissing,
    FileOperationError,
    FilesUnavailable,
    InvalidPath,
    PathDenied,
    RecursiveDeleteRequired,
    RootDenied,
)
from ..core.file_paths import (
    basename,
    ensure_mutable,
    ensure_not_within,
    ensure_writable,
    is_protected,
    join_path,
    normalize_path,
    parent_path,
    writable_without_root,
)
from ..core.file_streams import DownloadStream, open_download
from ..core.install_files import push_timeout
from .action_log import append_action_log

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 8 * 1024**3
DOWNLOAD_TICKET_TTL_S = 120
_ERROR_MARKERS = (
    "permission denied",
    "operation not permitted",
    "read-only file system",
    "no such file",
    "not found",
    "file exists",
    "cross-device link",
)


class FilesService:
    """Read and mutate device files, optionally through a root session."""

    def __init__(
        self,
        serial: str | None = None,
        reports_dir: str | None = None,
        adb_factory: Callable[..., AdbClient] = RealAdb,
        busy_check: Callable[[], bool] | None = None,
        staging_dir: str | None = None,
    ) -> None:
        self.serial = serial
        self.reports_dir = reports_dir or str(Path(default_reports_dir()) / "files")
        self.adb_factory = adb_factory
        self.busy_check = busy_check
        self.root_enabled = False
        self.max_upload_bytes = MAX_UPLOAD_BYTES
        self.staging_dir = staging_dir or str(Path(runtime_dir()) / "files-staging" / str(os.getpid()))
        self._mutation_lock = threading.Lock()
        self._ticket_lock = threading.Lock()
        self._download_tickets: dict[str, dict] = {}
        self._ensure_staging()

    # ------------------------------------------------------------------ setup

    def _ensure_staging(self) -> None:
        Path(self.staging_dir).mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        for path in Path(self.staging_dir).glob("upload-*.part"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.debug("could not remove file staging temp", exc_info=True)
        with self._ticket_lock:
            self._download_tickets.clear()

    def _adb(self) -> AdbClient:
        return self.adb_factory(serial=resolve_serial(self.serial))

    def _ensure_idle(self) -> None:
        if self.busy_check and self.busy_check():
            raise DeviceBusy("file operations are blocked while GXR Profiler is recording")

    # ------------------------------------------------------------------- shell

    def _shell(self, script: str, timeout: float = 20.0, root: bool | None = None) -> str:
        use_root = self.root_enabled if root is None else root
        adb = self._adb()
        try:
            if use_root:
                return adb.shell(f"su -c {shlex.quote(script)}", timeout=timeout)
            return adb.shell(script, timeout=timeout)
        except AdbError as exc:
            raise FilesUnavailable(str(exc)) from exc

    def _run(self, args: list[str], timeout: float = 60.0):
        try:
            return self._adb().run(args, timeout=timeout)
        except AdbError as exc:
            raise FilesUnavailable(str(exc)) from exc

    @staticmethod
    def _output(proc) -> str:
        parts = [(proc.stdout or "").strip(), (proc.stderr or "").strip()]
        return "\n".join(part for part in parts if part)

    def _raise_for_output(self, output: str, path: str) -> None:
        text = (output or "").strip()
        low = text.lower()
        if not text or not any(marker in low for marker in _ERROR_MARKERS):
            return
        if "permission denied" in low or "operation not permitted" in low or "read-only" in low:
            raise PathDenied(f"permission denied: {path}")
        if "no such file" in low or "not found" in low:
            raise FileMissing(f"{path} was not found")
        if "file exists" in low:
            raise FileConflict(f"{path} already exists")
        raise FilesUnavailable(text)

    @staticmethod
    def _ls_error(output: str) -> str:
        for line in (output or "").splitlines():
            text = line.strip()
            if not text.lower().startswith("ls:"):
                continue
            low = text.lower()
            if "permission denied" in low:
                return "permission"
            if "not a directory" in low:
                return "notdir"
            if "no such file" in low or "not found" in low:
                return "missing"
        return ""

    # -------------------------------------------------------------------- read

    def _stat(self, path: str, root: bool | None = None, follow: bool = False) -> dict:
        flag = "stat -Lc" if follow else "stat -c"
        script = f"{flag} '%F|%s|%Y' -- {shlex.quote(path)}"
        output = self._shell(script, timeout=15, root=root)
        text = (output or "").strip()
        if not text:
            raise FileMissing(f"{path} was not found")
        if "permission denied" in text.lower():
            raise PathDenied(f"permission denied: {path}")
        if "no such file" in text.lower() or "not found" in text.lower():
            raise FileMissing(f"{path} was not found")
        first = text.splitlines()[0]
        parts = first.split("|", 2)
        if len(parts) < 3:
            raise FileMissing(f"{path} was not found")
        kind_text, size_text, modified_text = parts
        low = kind_text.lower()
        if "directory" in low:
            kind = "dir"
        elif "link" in low:
            kind = "link"
        elif "file" in low:
            kind = "file"
        else:
            kind = "other"
        try:
            size = int(size_text)
        except ValueError:
            size = None
        try:
            modified = int(modified_text)
        except ValueError:
            modified = None
        return {"kind": kind, "size": size, "modified": modified}

    def list_dir(self, path: str) -> dict:
        self._ensure_idle()
        root = self.root_enabled
        normalized = normalize_path(path)
        display = normalized if normalized.endswith("/") else normalized + "/"
        output = self._shell(f"ls -lAN -- {shlex.quote(display)}", timeout=20, root=root)
        error = self._ls_error(output)
        if error == "permission":
            raise PathDenied(f"permission denied: {normalized}")
        if error == "notdir":
            raise InvalidPath(f"{normalized} is not a folder")
        if error == "missing":
            raise FileMissing(f"{normalized} was not found")
        entries = parse_ls_listing(output, normalized)
        return {
            "path": normalized,
            "parent": parent_path(normalized),
            "entries": [entry_to_dict(entry) for entry in entries],
            "root": root,
            "writable": root or writable_without_root(normalized),
            "protected": is_protected(normalized),
        }

    def download(self, path: str) -> tuple[DownloadStream, dict, str]:
        self._ensure_idle()
        root = self.root_enabled
        normalized = normalize_path(path)
        info = self._stat(normalized, root=root, follow=True)
        if info["kind"] != "file":
            raise InvalidPath("only regular files can be downloaded")
        try:
            stream = open_download(self._adb(), normalized, root)
        except AdbError as exc:
            raise FilesUnavailable(str(exc)) from exc
        return stream, info, basename(normalized)

    def create_download_ticket(self, path: str) -> dict:
        """Create a short-lived, one-use URL for a native browser download."""
        self._ensure_idle()
        root = self.root_enabled
        normalized = normalize_path(path)
        info = self._stat(normalized, root=root, follow=True)
        if info["kind"] != "file":
            raise InvalidPath("only regular files can be downloaded")
        token = uuid.uuid4().hex
        now = time.time()
        with self._ticket_lock:
            self._purge_tickets_locked(now)
            self._download_tickets[token] = {
                "path": normalized,
                "root": root,
                "expires": now + DOWNLOAD_TICKET_TTL_S,
                "size": info["size"],
                "name": basename(normalized),
            }
        return {
            "ticket": token,
            "url": f"/api/files/download/{token}",
            "name": basename(normalized),
            "size": info["size"],
        }

    def consume_download_ticket(self, token: str) -> tuple[DownloadStream, dict, str]:
        now = time.time()
        with self._ticket_lock:
            self._purge_tickets_locked(now)
            ticket = self._download_tickets.pop(token, None)
        if ticket is None:
            raise FileMissing("download link expired")
        try:
            stream = open_download(self._adb(), ticket["path"], ticket["root"])
        except AdbError as exc:
            raise FilesUnavailable(str(exc)) from exc
        return stream, {"size": ticket["size"], "kind": "file"}, ticket["name"]

    def _purge_tickets_locked(self, now: float) -> None:
        for token in [key for key, value in self._download_tickets.items() if value["expires"] <= now]:
            self._download_tickets.pop(token, None)

    # ------------------------------------------------------------------- write

    def set_root(self, enabled: bool) -> dict:
        self._ensure_idle()
        if enabled:
            try:
                output = self._adb().shell("su -c id", timeout=10)
            except AdbError as exc:
                raise RootDenied(f"root is not available: {exc}") from exc
            if "uid=0" not in (output or ""):
                raise RootDenied("root access was denied")
        with self._mutation_lock:
            self.root_enabled = bool(enabled)
        self._audit("root", extra={"enabled": self.root_enabled})
        return {"enabled": self.root_enabled}

    def upload(self, local_path: str, remote_dir: str, name: str, overwrite: bool = False) -> dict:
        self._ensure_idle()
        root = self.root_enabled
        directory = normalize_path(remote_dir)
        target = join_path(directory, name)
        ensure_mutable(target)
        ensure_writable(target, root)
        if self._stat(directory, root=root)["kind"] != "dir":
            raise InvalidPath("destination is not a folder")
        existing_kind = None
        try:
            existing_kind = self._stat(target, root=root, follow=True)["kind"]
        except FileMissing:
            pass
        if existing_kind == "dir":
            raise FileConflict(f"a folder already uses the name {target}")
        if existing_kind is not None and not overwrite:
            raise FileConflict(f"{target} already exists")
        size = os.path.getsize(local_path)
        token = uuid.uuid4().hex
        temp = f"/data/local/tmp/gxr-upload-{token}" if root else posixpath.join(directory, f".gxr-upload-{token}")
        with self._mutation_lock:
            proc = self._run(["push", str(local_path), temp], timeout=push_timeout(size))
            if proc.returncode != 0:
                self._remove_quietly(temp, root=root)
                raise FilesUnavailable(self._output(proc) or "adb push failed")
            try:
                temp_info = self._stat(temp, root=root)
                if temp_info["size"] != size:
                    raise FilesUnavailable("uploaded file size does not match")
                output = self._shell(
                    f"mv -f -- {shlex.quote(temp)} {shlex.quote(target)}",
                    timeout=60,
                    root=root,
                )
                self._raise_for_output(output, target)
                result = self._stat(target, root=root)
                if result["size"] != size:
                    raise FilesUnavailable("uploaded file size does not match")
            except FileOperationError:
                self._remove_quietly(temp, root=root)
                raise
        self._audit("upload", paths=[target], extra={"size": size, "overwrite": overwrite}, root=root)
        return {"path": target, "name": name, "size": size}

    def mkdir(self, parent: str, name: str) -> dict:
        self._ensure_idle()
        root = self.root_enabled
        target = join_path(parent, name)
        ensure_mutable(target)
        ensure_writable(target, root)
        try:
            self._stat(target, root=root)
        except FileMissing:
            pass
        else:
            raise FileConflict(f"{target} already exists")
        with self._mutation_lock:
            output = self._shell(f"mkdir -- {shlex.quote(target)}", timeout=20, root=root)
            self._raise_for_output(output, target)
            if self._stat(target, root=root)["kind"] != "dir":
                raise FilesUnavailable(f"could not create {target}")
        self._audit("mkdir", paths=[target], root=root)
        return {"path": target, "name": name}

    def rename(self, path: str, name: str) -> dict:
        self._ensure_idle()
        root = self.root_enabled
        source = normalize_path(path)
        ensure_mutable(source)
        target = join_path(parent_path(source) or "/", name)
        ensure_mutable(target)
        ensure_writable(target, root)
        if source == target:
            return {"from": source, "to": target}
        try:
            self._stat(target, root=root)
        except FileMissing:
            pass
        else:
            raise FileConflict(f"{target} already exists")
        with self._mutation_lock:
            output = self._shell(
                f"mv -- {shlex.quote(source)} {shlex.quote(target)}",
                timeout=30,
                root=root,
            )
            self._raise_for_output(output, target)
        self._audit("rename", paths=[source, target], root=root)
        return {"from": source, "to": target}

    def move(self, paths: list[str], destination: str, overwrite: bool = False) -> list[dict]:
        self._ensure_idle()
        root = self.root_enabled
        dest = normalize_path(destination)
        ensure_mutable(dest)
        ensure_writable(dest, root)
        if self._stat(dest, root=root)["kind"] != "dir":
            raise InvalidPath("destination is not a folder")
        prepared: list[tuple[str, str]] = []
        for raw in paths:
            source = normalize_path(raw)
            ensure_mutable(source)
            ensure_not_within(dest, source)
            target = join_path(dest, basename(source))
            if source == target:
                continue
            target_kind = None
            try:
                target_kind = self._stat(target, root=root, follow=True)["kind"]
            except FileMissing:
                pass
            if target_kind == "dir":
                raise FileConflict(f"a folder already uses the name {target}")
            if target_kind is not None and not overwrite:
                raise FileConflict(f"{target} already exists")
            prepared.append((source, target))
        results = []
        with self._mutation_lock:
            for source, target in prepared:
                output = self._shell(
                    f"mv -f -- {shlex.quote(source)} {shlex.quote(target)}",
                    timeout=30,
                    root=root,
                )
                try:
                    self._raise_for_output(output, target)
                except FileOperationError as exc:
                    results.append({"from": source, "to": target, "ok": False, "error": str(exc)})
                else:
                    results.append({"from": source, "to": target, "ok": True, "error": ""})
        self._audit(
            "move",
            paths=[item[0] for item in prepared],
            extra={"destination": dest, "overwrite": overwrite},
            root=root,
        )
        return results

    def delete(self, paths: list[str], recursive: bool = False, confirm_text: str = "") -> list[dict]:
        self._ensure_idle()
        root = self.root_enabled
        if root and (confirm_text or "").strip().upper() != "DELETE":
            raise ConfirmationRequired("type DELETE to remove files with root access")
        prepared: list[tuple[str, str]] = []
        for raw in paths:
            source = normalize_path(raw)
            ensure_mutable(source)
            info = self._stat(source, root=root)
            if info["kind"] == "dir" and not recursive:
                raise RecursiveDeleteRequired(f"{source} is a folder; confirm recursive delete")
            prepared.append((source, "dir" if info["kind"] == "dir" else "file"))
        results = []
        with self._mutation_lock:
            for source, kind in prepared:
                command = "rm -rf --" if kind == "dir" else "rm -f --"
                output = self._shell(f"{command} {shlex.quote(source)}", timeout=60, root=root)
                try:
                    self._raise_for_output(output, source)
                except FileOperationError as exc:
                    results.append({"path": source, "ok": False, "error": str(exc)})
                else:
                    results.append({"path": source, "ok": True, "error": ""})
        self._audit(
            "delete",
            paths=[item[0] for item in prepared],
            extra={"recursive": recursive},
            root=root,
        )
        return results

    # ------------------------------------------------------------------ helpers

    def _remove_quietly(self, path: str, root: bool | None = None) -> None:
        try:
            self._shell(f"rm -f -- {shlex.quote(path)}", timeout=15, root=root)
        except Exception:
            log.debug("could not remove temporary upload %s", path, exc_info=True)

    def _audit(
        self,
        action: str,
        paths: list[str] | None = None,
        extra: dict | None = None,
        root: bool | None = None,
    ) -> None:
        entry = {"action": action, "root": self.root_enabled if root is None else root, "ok": True}
        if paths:
            entry["paths"] = paths
        if extra:
            entry.update(extra)
        append_action_log(self.reports_dir, "file-actions.jsonl", entry)
