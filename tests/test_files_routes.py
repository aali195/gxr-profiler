import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gxr_tools.core.recording_state import clear_state, write_state
from gxr_tools.manager.core.file_errors import (
    ConfirmationRequired,
    FileConflict,
    FileMissing,
    FilesUnavailable,
    InvalidPath,
    PathDenied,
)
from gxr_tools.manager.server.app import create_manager_app
from gxr_tools.manager.server.deps import get_files_service


def _token(client):
    html = client.get("/").text
    return re.search(r'name="gxr-profiler-token" content="([^"]+)"', html).group(1)


class FakeFiles:
    def __init__(self, tmp_path):
        self.staging_dir = str(tmp_path / "staging")
        Path(self.staging_dir).mkdir(parents=True, exist_ok=True)
        self.max_upload_bytes = 1024
        self.root_enabled = False
        self.error = None
        self.uploaded = b""
        self.calls = []
        self.used_ticket = False

    def _check(self):
        if self.error is not None:
            raise self.error

    def list_dir(self, path):
        self._check()
        self.calls.append(("list", path))
        return {
            "path": path,
            "parent": "/",
            "entries": [],
            "root": self.root_enabled,
            "writable": True,
            "protected": False,
        }

    def download(self, path):
        self._check()
        self.calls.append(("download", path))
        return iter([b"abc"]), {"size": 3, "kind": "file"}, "a.txt"

    def create_download_ticket(self, path):
        self._check()
        return {"ticket": "t1", "url": "/api/files/download/t1", "name": "a.txt", "size": 3}

    def consume_download_ticket(self, token):
        self._check()
        if token == "t1" and not self.used_ticket:
            self.used_ticket = True
            return iter([b"abc"]), {"size": 3, "kind": "file"}, "a.txt"
        raise FileMissing("download link expired")

    def set_root(self, enabled):
        self._check()
        self.root_enabled = enabled
        return {"enabled": enabled}

    def mkdir(self, path, name):
        self._check()
        return {"path": path + "/" + name, "name": name}

    def rename(self, path, name):
        self._check()
        return {"from": path, "to": name}

    def move(self, paths, destination, overwrite=False):
        self._check()
        return [{"from": item, "to": destination, "ok": True, "error": ""} for item in paths]

    def delete(self, paths, recursive=False, confirm_text=""):
        self._check()
        return [{"path": item, "ok": True, "error": ""} for item in paths]

    def upload(self, local_path, path, name, overwrite=False):
        self.uploaded = Path(local_path).read_bytes()
        return {"path": path + "/" + name, "name": name, "size": len(self.uploaded)}


def _client(tmp_path, files=None):
    app = create_manager_app(serial="fake")
    fake = files or FakeFiles(tmp_path)
    app.dependency_overrides[get_files_service] = lambda: fake
    return TestClient(app), fake


def test_files_list_and_token_guard(tmp_path):
    client, fake = _client(tmp_path)
    assert client.get("/api/files?path=/sdcard").status_code == 200
    assert client.post("/api/files/mkdir", json={"path": "/sdcard", "name": "x"}).status_code == 403
    headers = {"X-GXR-Profiler-Token": _token(client)}
    assert client.post("/api/files/mkdir", json={"path": "/sdcard", "name": "x"}, headers=headers).status_code == 200
    assert client.post("/api/files/root", json={"enabled": True}, headers=headers).status_code == 200
    assert fake.root_enabled is True


def test_files_download_requires_token_and_streams(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/api/files/download?path=/sdcard/a.txt").status_code == 403
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.get("/api/files/download?path=/sdcard/a.txt", headers=headers)
    assert response.status_code == 200
    assert response.content == b"abc"
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (InvalidPath("bad path"), 400),
        (ConfirmationRequired("confirm"), 400),
        (PathDenied("denied"), 403),
        (FileMissing("missing"), 404),
        (FileConflict("conflict"), 409),
        (FilesUnavailable("offline"), 503),
    ],
)
def test_files_error_mapping(tmp_path, error, status):
    files = FakeFiles(tmp_path)
    files.error = error
    client, _ = _client(tmp_path, files)
    assert client.get("/api/files?path=/sdcard").status_code == status


def test_files_blocked_while_recording(tmp_path):
    client, _ = _client(tmp_path)
    write_state(True, label="files-test")
    try:
        assert client.get("/api/files?path=/sdcard").status_code == 409
        headers = {"X-GXR-Profiler-Token": _token(client)}
        response = client.post("/api/files/upload?path=/sdcard&name=a.txt", content=b"x", headers=headers)
        assert response.status_code == 409
    finally:
        clear_state()


def test_upload_streams_to_staging_and_cleans_up(tmp_path):
    client, files = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post(
        "/api/files/upload?path=/sdcard&name=a.txt",
        content=b"payload",
        headers=headers,
    )
    assert response.status_code == 200
    assert files.uploaded == b"payload"
    assert list(Path(files.staging_dir).glob("upload-*.part")) == []


def test_upload_limit(tmp_path):
    client, files = _client(tmp_path)
    files.max_upload_bytes = 3
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post(
        "/api/files/upload?path=/sdcard&name=a.txt",
        content=b"four",
        headers=headers,
    )
    assert response.status_code == 413


def test_files_download_ticket_is_one_use(tmp_path):
    client, _ = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post("/api/files/download-ticket", json={"path": "/sdcard/a.txt"}, headers=headers)
    assert response.status_code == 200
    url = response.json()["url"]
    first = client.get(url)
    assert first.status_code == 200
    assert first.content == b"abc"
    assert client.get(url).status_code == 404


def test_files_upload_rejects_bad_name_before_streaming(tmp_path):
    client, files = _client(tmp_path)
    headers = {"X-GXR-Profiler-Token": _token(client)}
    response = client.post(
        "/api/files/upload?path=/sdcard&name=..%2Fbad",
        content=b"payload",
        headers=headers,
    )
    assert response.status_code == 400
    assert files.uploaded == b""
