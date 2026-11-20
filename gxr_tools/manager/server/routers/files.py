"""File-explorer HTTP routes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from ...core.file_paths import validate_name
from ..deps import FilesDep, IdleDep, TokenDep
from ..files import FilesService
from ..models import (
    FileDeleteRequest,
    FileDownloadTicketRequest,
    FileMkdirRequest,
    FileMoveRequest,
    FileRenameRequest,
    FileRootRequest,
)

router = APIRouter()


def _stream_response(stream, info: dict, name: str) -> StreamingResponse:
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
        "X-Content-Type-Options": "nosniff",
    }
    if isinstance(info.get("size"), int):
        headers["Content-Length"] = str(info["size"])
    return StreamingResponse(stream, media_type="application/octet-stream", headers=headers)


def _upload_limit(files: FilesService) -> str:
    gigabytes = files.max_upload_bytes / (1024**3)
    return f"file is larger than the {gigabytes:g} GB upload limit"


@router.get("/api/files")
def list_files(files: FilesDep, _idle: IdleDep, path: str = Query("/sdcard", max_length=4096)):
    return files.list_dir(path)


@router.get("/api/files/download")
def download_file(
    files: FilesDep,
    _token: TokenDep,
    _idle: IdleDep,
    path: str = Query(..., min_length=1, max_length=4096),
):
    stream, info, name = files.download(path)
    return _stream_response(stream, info, name)


@router.post("/api/files/download-ticket")
def create_download_ticket(body: FileDownloadTicketRequest, files: FilesDep, _idle: IdleDep):
    return files.create_download_ticket(body.path)


@router.get("/api/files/download/{ticket}")
def download_ticket(ticket: str, files: FilesDep, _idle: IdleDep):
    stream, info, name = files.consume_download_ticket(ticket)
    return _stream_response(stream, info, name)


@router.post("/api/files/root")
def set_root(body: FileRootRequest, files: FilesDep, _idle: IdleDep):
    return files.set_root(body.enabled)


@router.post("/api/files/mkdir")
def make_folder(body: FileMkdirRequest, files: FilesDep, _idle: IdleDep):
    return files.mkdir(body.path, body.name)


@router.post("/api/files/rename")
def rename_file(body: FileRenameRequest, files: FilesDep, _idle: IdleDep):
    return files.rename(body.path, body.name)


@router.post("/api/files/move")
def move_files(body: FileMoveRequest, files: FilesDep, _idle: IdleDep):
    return files.move(body.paths, body.destination, body.overwrite)


@router.post("/api/files/delete")
def delete_files(body: FileDeleteRequest, files: FilesDep, _idle: IdleDep):
    return files.delete(body.paths, body.recursive, body.confirm)


@router.post("/api/files/upload")
async def upload_file(
    request: Request,
    files: FilesDep,
    _idle: IdleDep,
    path: str = Query("/sdcard", max_length=4096),
    name: str = Query(..., min_length=1, max_length=255),
    overwrite: bool = Query(False),
):
    validate_name(name)
    limit = _upload_limit(files)
    try:
        size_hint = int(request.headers.get("content-length") or 0)
    except ValueError:
        size_hint = 0
    if size_hint > files.max_upload_bytes:
        raise HTTPException(status_code=413, detail=limit)

    fd, raw_path = tempfile.mkstemp(dir=files.staging_dir, prefix="upload-", suffix=".part")
    temp_path = Path(raw_path)
    size = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > files.max_upload_bytes:
                    raise HTTPException(status_code=413, detail=limit)
                handle.write(chunk)
        return await run_in_threadpool(files.upload, str(temp_path), path, name, overwrite)
    finally:
        temp_path.unlink(missing_ok=True)
