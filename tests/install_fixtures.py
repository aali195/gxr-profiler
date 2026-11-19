"""Synthetic APK/XAPK and fake ADB helpers for install tests."""

from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace


def _string_pool(strings: list[str]) -> bytes:
    entries = []
    for text in strings:
        raw = text.encode("utf-16-le")
        entries.append(struct.pack("<H", len(raw) // 2) + raw + b"\x00\x00")
    offsets: list[int] = []
    data = b""
    for entry in entries:
        offsets.append(len(data))
        data += entry
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    header_size = 28
    strings_start = header_size + 4 * len(strings)
    size = strings_start + len(data)
    header = struct.pack(
        "<HHIIIIII",
        1,
        header_size,
        size,
        len(strings),
        0,
        0,
        strings_start,
        0,
    )
    return header + b"".join(struct.pack("<I", offset) for offset in offsets) + data


def _start_element(strings: list[str], attrs: list[tuple[str, int | str, int]]) -> bytes:
    size = 16 + 20 + 20 * len(attrs)
    out = struct.pack("<HHI", 0x0102, 16, size)
    out += struct.pack("<II", 0, 0xFFFFFFFF)
    out += struct.pack(
        "<IIHHHHHH",
        0xFFFFFFFF,
        strings.index("manifest"),
        20,
        20,
        len(attrs),
        0,
        0,
        0,
    )
    for name, value, value_type in attrs:
        raw = value if value_type == 0x03 else 0xFFFFFFFF
        out += struct.pack("<III", 0xFFFFFFFF, strings.index(name), raw)
        out += struct.pack("<HBBI", 8, 0, value_type, int(value))
    return out


def build_manifest_axml(
    package: str,
    version_code: int = 1,
    version_name: str = "1.0",
    split: str = "",
) -> bytes:
    strings = ["package", "versionCode", "versionName", "split", "manifest", package, version_name, split]
    attrs: list[tuple[str, int | str, int]] = [
        ("package", strings.index(package), 0x03),
        ("versionCode", version_code, 0x10),
    ]
    if version_name:
        attrs.append(("versionName", strings.index(version_name), 0x03))
    if split:
        attrs.append(("split", strings.index(split), 0x03))
    pool = _string_pool(strings)
    element = _start_element(strings, attrs)
    size = 8 + len(pool) + len(element)
    return struct.pack("<HHI", 0x0003, 8, size) + pool + element


def build_apk_bytes(
    package: str,
    version_code: int = 1,
    version_name: str = "1.0",
    split: str = "",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "AndroidManifest.xml",
            build_manifest_axml(package, version_code, version_name, split),
        )
        archive.writestr("classes.dex", b"dex\n035\x00")
    return buffer.getvalue()


def build_apk(
    path: Path,
    package: str,
    version_code: int = 1,
    version_name: str = "1.0",
    split: str = "",
) -> Path:
    path.write_bytes(build_apk_bytes(package, version_code, version_name, split))
    return path


def build_xapk(
    path: Path,
    package: str,
    version_code: int = 1,
    obb_name: str = "",
    with_split: bool = True,
) -> Path:
    manifest = {
        "package_name": package,
        "version_code": version_code,
        "version_name": "1.0",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("base.apk", build_apk_bytes(package, version_code))
        if with_split:
            archive.writestr(
                "split_config.arm64_v8a.apk",
                build_apk_bytes(package, version_code, split="config.arm64_v8a"),
            )
        if obb_name:
            archive.writestr(f"Android/obb/{package}/{obb_name}", b"OBB!")
    return path


class FakeInstallAdb:
    def __init__(
        self,
        installed: bool = True,
        fail_install: bool = False,
        fail_push: bool = False,
        reported_version: int = 123,
        install_output: str = "Success\n",
        install_returncode: int = 0,
        stat_size: int | None = None,
        stat_output: str | None = None,
        dumpsys_output: str | None = None,
    ):
        self.installed = installed
        self.fail_install = fail_install
        self.fail_push = fail_push
        self.reported_version = reported_version
        self.install_output = install_output
        self.install_returncode = install_returncode
        self.stat_size = stat_size
        self.stat_output = stat_output
        self.dumpsys_output = dumpsys_output
        self.calls: list[list[str]] = []
        self.shell_calls: list[str] = []
        self.pushed: dict[str, int] = {}

    def run(self, args, timeout=25.0):
        self.calls.append(list(args))
        command = args[0]
        if command in {"install", "install-multiple"}:
            if self.fail_install:
                return SimpleNamespace(
                    stdout="Failure [INSTALL_FAILED_INVALID_APK]\n",
                    stderr="",
                    returncode=1,
                )
            return SimpleNamespace(
                stdout=self.install_output,
                stderr="",
                returncode=self.install_returncode,
            )
        if command == "push":
            if self.fail_push:
                return SimpleNamespace(stdout="", stderr="adb: error: failed to copy\n", returncode=1)
            local, remote = args[1], args[2]
            self.pushed[remote] = Path(local).stat().st_size
            return SimpleNamespace(stdout="1 file pushed\n", stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    def shell(self, script, timeout=25.0):
        self.shell_calls.append(script)
        if script.startswith("pm path "):
            return "package:/data/app/base.apk\n" if self.installed else ""
        if script.startswith("dumpsys package "):
            if self.dumpsys_output is not None:
                return self.dumpsys_output
            return f"versionCode={self.reported_version}\n" if self.installed else ""
        if script.startswith("df -k"):
            return "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/x 1000000 1 900000 1% /data\n"
        if script.startswith("stat -c %s "):
            if self.stat_output is not None:
                return self.stat_output
            remote = script.split(" ", 3)[-1].strip("'")
            return str(self.stat_size if self.stat_size is not None else self.pushed.get(remote, 0))
        return ""
