"""Shared local-server plumbing for the profiler and manager apps."""

from __future__ import annotations

import hashlib
import socket
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
_LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost"})


def is_local_origin(origin: str) -> bool:
    """Accept only an http origin whose host is exactly localhost or 127.0.0.1."""
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in _LOCAL_HOSTNAMES
        and parsed.username is None
        and parsed.password is None
    )


def resolve_port(preferred: int) -> int:
    """Return a usable localhost port, moving forward if the requested one is taken."""
    if preferred == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    for candidate in range(preferred, min(preferred + 32, 65536)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", candidate))
            return candidate
        except OSError:
            continue
    raise OSError(f"no free localhost port at or after {preferred}")


def asset_version(*paths: str | Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:16]


def install_local_guard(app: FastAPI) -> None:
    """Install host/origin/token checks and the shared local response headers."""
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
            origin = request.headers.get("origin")
            if origin and not is_local_origin(origin):
                return JSONResponse({"detail": "unexpected origin"}, status_code=403)
            if request.headers.get("x-gxr-profiler-token") != app.state.token:
                return JSONResponse({"detail": "missing local API token"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' blob:; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def start_uvicorn(app: FastAPI, port: int) -> threading.Thread:
    import uvicorn

    thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning"),
        daemon=True,
    )
    thread.start()
    return thread


def wait_for_server(url: str, thread: threading.Thread | None = None, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if thread is not None and not thread.is_alive():
            break
        try:
            with urllib.request.urlopen(url + "/", timeout=0.25):
                return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"local UI server did not start on {url}")
