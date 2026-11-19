"""App factory + launcher for the gxr_profiler viewer/recorder."""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import threading
import time
import urllib.request
import webbrowser
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.paths import default_reports_dir, default_runs_dir
from ..runs.store import RunStore
from .apps import AppsService
from .debug import DebugManager
from .export import ExportService, make_js_api
from .recording import RecordManager
from .routers import apps, debug, record, report, runs, settings, spec
from .settings import SettingsService

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


def _asset_version() -> str:
    digest = hashlib.sha256()
    for name in ("app.js", "styles.css"):
        with open(os.path.join(WEB_DIR, name), "rb") as fh:
            digest.update(fh.read())
    return digest.hexdigest()[:16]


def create_app(runs_dir: str | None = None, serial: str | None = None) -> FastAPI:
    runs_dir = runs_dir or default_runs_dir()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.apps.install.cleanup()
        yield
        application.state.manager.shutdown()
        application.state.debug.shutdown()

    app = FastAPI(title="GXR Profiler", default_response_class=ORJSONResponse, lifespan=lifespan)
    app.state.token = secrets.token_urlsafe(24)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.state.store = RunStore(runs_dir)
    app.state.manager = RecordManager(runs_dir, serial)
    app.state.debug = DebugManager(serial, os.path.join(default_reports_dir(), "debug"))
    app.state.apps = AppsService(
        serial,
        busy_check=lambda: app.state.manager.state().get("status") == "recording",
    )
    app.state.settings = SettingsService(serial)

    app.include_router(spec.router)
    app.include_router(runs.router)
    app.include_router(record.router)
    app.include_router(report.router)
    app.include_router(debug.router)
    app.include_router(apps.router)
    app.include_router(settings.router)
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
            origin = request.headers.get("origin")
            if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
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

    @app.get("/")
    def index():
        path = os.path.join(WEB_DIR, "index.html")
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        meta = f'<meta name="gxr-profiler-token" content="{app.state.token}" />'
        html = html.replace("__GXR_ASSET_VERSION__", _asset_version())
        return HTMLResponse(html.replace("</head>", f"  {meta}\n</head>", 1))

    return app


def _resolve_port(preferred: int) -> int:
    """Return a usable localhost port, moving forward if the requested one is taken."""
    if preferred == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    for candidate in range(preferred, min(preferred + 32, 65536)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", candidate))
            return candidate
        except OSError:
            continue
    raise OSError(f"no free localhost port at or after {preferred}")


def run_ui(port: int = 8765, browser: bool = False, runs_dir: str | None = None, serial: str | None = None) -> None:
    import uvicorn

    port = _resolve_port(port)
    runs_dir = runs_dir or default_runs_dir()
    app = create_app(runs_dir, serial)
    url = f"http://127.0.0.1:{port}"

    webview = None
    if not browser:
        try:
            import webview as _wv

            webview = _wv
        except Exception:
            webview = None

    if webview is None:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return

    thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning"),
        daemon=True,
    )
    thread.start()
    ready = False
    for _ in range(100):
        if not thread.is_alive():
            break
        try:
            with urllib.request.urlopen(url + "/api/spec", timeout=0.25):
                ready = True
                break
        except Exception:
            time.sleep(0.05)
    if not ready:
        raise RuntimeError(f"local UI server did not start on {url}")
    service = ExportService(runs_dir)
    window_ref: dict = {}
    api = make_js_api(service, lambda: window_ref.get("window"), webview)
    window = webview.create_window(
        "GXR Profiler",
        url,
        width=1280,
        height=900,
        min_size=(1000, 700),
        maximized=True,
        text_select=True,
        js_api=api,
    )
    window_ref["window"] = window
    webview.start()
