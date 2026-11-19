"""Read package metadata from APK and XAPK files without Android SDK tools.

The GXR Manager > Installer workflow needs the Android package name before it
can group split APKs, match OBB files and apply the critical-package guard.
Android binary XML is small and well documented, so a minimal reader is
enough; no third-party APK library is required.
"""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

_RES_XML_TYPE = 0x0003
_RES_STRING_POOL_TYPE = 0x0001
_RES_XML_START_ELEMENT_TYPE = 0x0102
_NO_ENTRY = 0xFFFFFFFF
_TYPE_STRING = 0x03
_TYPE_INT_DEC = 0x10
_TYPE_INT_HEX = 0x11

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_XAPK_MANIFEST_BYTES = 4 * 1024 * 1024


class ApkError(ValueError):
    """An APK or its manifest could not be read."""


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ApkError("truncated binary XML")
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ApkError("truncated binary XML")
    return struct.unpack_from("<I", data, offset)[0]


def _length8(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first & 0x80:
        if offset >= len(data):
            raise ApkError("truncated binary XML string")
        return ((first & 0x7F) << 8) | data[offset], offset + 1
    return first, offset


def _string_pool(data: bytes, start: int, header_size: int, size: int) -> list[str]:
    if size < 28:
        return []
    count = _u32(data, start + 8)
    flags = _u32(data, start + 16)
    strings_start = _u32(data, start + 20)
    if count > 200_000 or strings_start >= size:
        raise ApkError("invalid binary XML string pool")
    offsets_at = start + max(header_size, 28)
    strings_at = start + strings_start
    utf8 = bool(flags & 0x100)
    out: list[str] = []
    for index in range(count):
        offset = _u32(data, offsets_at + index * 4)
        pos = strings_at + offset
        if pos >= start + size:
            out.append("")
            continue
        try:
            if utf8:
                _, pos = _length8(data, pos)
                byte_len, pos = _length8(data, pos)
                end = min(pos + byte_len, start + size)
                out.append(data[pos:end].decode("utf-8", errors="replace"))
            else:
                length = _u16(data, pos)
                pos += 2
                if length & 0x8000:
                    length = ((length & 0x7FFF) << 16) | _u16(data, pos)
                    pos += 2
                end = min(pos + length * 2, start + size)
                out.append(data[pos:end].decode("utf-16-le", errors="replace"))
        except (ApkError, IndexError, UnicodeDecodeError):
            out.append("")
    return out


def _attr_value(
    data: bytes,
    raw_value: int,
    value_type: int,
    value_data: int,
    strings: list[str],
) -> object:
    if raw_value != _NO_ENTRY and raw_value < len(strings):
        return strings[raw_value]
    if value_type == _TYPE_STRING and value_data < len(strings):
        return strings[value_data]
    if value_type in (_TYPE_INT_DEC, _TYPE_INT_HEX):
        return int(value_data)
    return None


def _manifest_attributes(data: bytes, start: int, header_size: int, strings: list[str]) -> dict:
    base = start + header_size
    name_index = _u32(data, base + 4)
    name = strings[name_index] if name_index < len(strings) else ""
    if name != "manifest":
        return {}
    attr_start = _u16(data, base + 8)
    attr_size = _u16(data, base + 10)
    attr_count = _u16(data, base + 12)
    if attr_size < 20 or attr_count > 10_000:
        raise ApkError("invalid binary XML attributes")
    attrs: dict[str, object] = {}
    attr_at = base + attr_start
    for index in range(attr_count):
        offset = attr_at + index * attr_size
        name_idx = _u32(data, offset + 4)
        raw_value = _u32(data, offset + 8)
        value_type = data[offset + 15]
        value_data = _u32(data, offset + 16)
        key = strings[name_idx] if name_idx < len(strings) else ""
        if key in {"package", "versionCode", "versionName", "split"}:
            attrs[key] = _attr_value(data, raw_value, value_type, value_data, strings)
    return attrs


def parse_axml_manifest(data: bytes) -> dict:
    """Return the attributes of the root ``manifest`` element in binary XML."""
    if len(data) < 8 or _u16(data, 0) != _RES_XML_TYPE:
        raise ApkError("AndroidManifest.xml is not binary XML")
    total = min(_u32(data, 4) or len(data), len(data))
    strings: list[str] = []
    pos = 8
    while pos + 8 <= total:
        chunk_type = _u16(data, pos)
        header_size = _u16(data, pos + 2)
        chunk_size = _u32(data, pos + 4)
        if chunk_size < 8 or pos + chunk_size > total:
            break
        if chunk_type == _RES_STRING_POOL_TYPE:
            strings = _string_pool(data, pos, header_size, chunk_size)
        elif chunk_type == _RES_XML_START_ELEMENT_TYPE and strings:
            attrs = _manifest_attributes(data, pos, header_size, strings)
            if attrs:
                return attrs
        pos += chunk_size
    raise ApkError("manifest element was not found")


def read_apk_metadata(path: str | Path) -> dict:
    """Read package/version/split from an APK, returning an error instead of raising."""
    result = {
        "package": "",
        "version_code": None,
        "version_name": "",
        "split": "",
        "error": "",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("AndroidManifest.xml")
            if info.file_size > MAX_MANIFEST_BYTES:
                raise ApkError("AndroidManifest.xml is too large")
            data = archive.read(info)
        attrs = parse_axml_manifest(data)
        package = str(attrs.get("package") or "").strip()
        version_code = attrs.get("versionCode")
        result["package"] = package
        result["version_code"] = int(version_code) if isinstance(version_code, int) else None
        result["version_name"] = str(attrs.get("versionName") or "")
        result["split"] = str(attrs.get("split") or "")
    except Exception as exc:
        result["error"] = f"could not read APK metadata: {exc}"
    return result


def read_xapk_manifest(path: str | Path) -> dict:
    """Read the optional ``manifest.json`` from an XAPK archive."""
    result = {
        "package": "",
        "version_code": None,
        "version_name": "",
        "error": "",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > MAX_XAPK_MANIFEST_BYTES:
                raise ApkError("manifest.json is too large")
            data = json.loads(archive.read(info).decode("utf-8-sig"))
    except KeyError:
        result["error"] = "XAPK manifest.json was not found"
        return result
    except Exception as exc:
        result["error"] = f"could not read XAPK manifest: {exc}"
        return result
    if not isinstance(data, dict):
        result["error"] = "XAPK manifest.json is not an object"
        return result
    package = data.get("package_name") or data.get("package") or ""
    result["package"] = str(package).strip() if isinstance(package, str) else ""
    version_code = data.get("version_code") or data.get("versionCode")
    if isinstance(version_code, int):
        result["version_code"] = version_code
    elif isinstance(version_code, str) and version_code.isdigit():
        result["version_code"] = int(version_code)
    version_name = data.get("version_name") or data.get("versionName") or ""
    result["version_name"] = str(version_name) if isinstance(version_name, str) else ""
    return result
