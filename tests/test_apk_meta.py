import json
import zipfile

from gxr_manager.core.apk import read_apk_metadata, read_xapk_manifest

from .install_fixtures import build_apk, build_xapk


def test_reads_package_and_version_from_apk(tmp_path):
    path = build_apk(tmp_path / "game.apk", "com.example.game", version_code=123, version_name="1.2.3")
    meta = read_apk_metadata(path)
    assert meta["error"] == ""
    assert meta["package"] == "com.example.game"
    assert meta["version_code"] == 123
    assert meta["version_name"] == "1.2.3"
    assert meta["split"] == ""


def test_reads_split_name(tmp_path):
    path = build_apk(
        tmp_path / "split.apk",
        "com.example.game",
        version_code=123,
        split="config.arm64_v8a",
    )
    meta = read_apk_metadata(path)
    assert meta["split"] == "config.arm64_v8a"


def test_malformed_apk_returns_error(tmp_path):
    path = tmp_path / "broken.apk"
    path.write_bytes(b"not a zip")
    meta = read_apk_metadata(path)
    assert meta["package"] == ""
    assert "could not read APK metadata" in meta["error"]


def test_reads_xapk_manifest(tmp_path):
    path = build_xapk(tmp_path / "game.xapk", "com.example.game", version_code=42)
    manifest = read_xapk_manifest(path)
    assert manifest["error"] == ""
    assert manifest["package"] == "com.example.game"
    assert manifest["version_code"] == 42


def test_xapk_without_manifest_returns_error(tmp_path):
    path = tmp_path / "plain.xapk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("base.apk", b"not really an apk")
    manifest = read_xapk_manifest(path)
    assert manifest["package"] == ""
    assert "manifest.json was not found" in manifest["error"]


def test_xapk_manifest_json_variants(tmp_path):
    path = tmp_path / "variant.xapk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"package": "com.example.variant", "versionCode": "7"}),
        )
    manifest = read_xapk_manifest(path)
    assert manifest["package"] == "com.example.variant"
    assert manifest["version_code"] == 7
