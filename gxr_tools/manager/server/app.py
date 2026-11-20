"""App factory + launcher for the GXR Manager device-tools app."""

from __future__ import annotations

import os
import secrets
import threading
import webbrowser
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import gxr_tools.core
from gxr_tools.core.paths import default_reports_dir
from gxr_tools.core.recording_state import is_recording
from gxr_tools.core.server import asset_version, install_local_guard, resolve_port, start_uvicorn, wait_for_server

from ..core.file_errors import FileOperationError
from .apps import AppsService
from .debug import DebugManager
from .files import FilesService
from .routers import apps, debug, files, recording, settings
from .settings import SettingsService
from .web_modules import MANAGER_JS_FILES

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
COMMON_DIR = os.path.join(os.path.dirname(gxr_tools.core.__file__), "web_common")


def create_manager_app(serial: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.apps.install.cleanup()
        application.state.files.cleanup()
        yield
        application.state.debug.shutdown()
        application.state.apps.install.cleanup()
        application.state.files.cleanup()

    app = FastAPI(title="GXR Manager", lifespan=lifespan)
    app.state.token = secrets.token_urlsafe(24)
    app.state.apps = AppsService(
        serial,
        busy_check=is_recording,
    )
    app.state.settings = SettingsService(serial, busy_check=is_recording)
    app.state.debug = DebugManager(serial, os.path.join(default_reports_dir(), "debug"))
    app.state.files = FilesService(serial, busy_check=is_recording)

    app.include_router(apps.router)
    app.include_router(settings.router)
    app.include_router(debug.router)
    app.include_router(files.router)
    app.include_router(recording.router)
    app.mount("/common", StaticFiles(directory=COMMON_DIR), name="common")
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    install_local_guard(app)

    @app.exception_handler(FileOperationError)
    async def file_error_handler(_request, exc: FileOperationError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.get("/")
    def index():
        path = os.path.join(WEB_DIR, "index.html")
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        meta = f'<meta name="gxr-profiler-token" content="{app.state.token}" />'
        version = asset_version(
            os.path.join(COMMON_DIR, "common.js"),
            os.path.join(COMMON_DIR, "common.css"),
            os.path.join(WEB_DIR, "styles.css"),
            *(os.path.join(WEB_DIR, name) for name in MANAGER_JS_FILES),
        )
        html = html.replace("__GXR_ASSET_VERSION__", version)
        return HTMLResponse(html.replace("</head>", f"  {meta}\n</head>", 1))

    return app


def run_ui(port: int = 8766, browser: bool = False, serial: str | None = None) -> None:
    port = resolve_port(port)
    app = create_manager_app(serial)
    url = f"http://127.0.0.1:{port}"

    webview = None
    if not browser:
        try:
            import webview as _wv

            _wv.settings["ALLOW_DOWNLOADS"] = True
            webview = _wv
        except Exception:
            webview = None

    if webview is None:
        import uvicorn

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return

    thread = start_uvicorn(app, port)
    wait_for_server(url, thread)
    webview.create_window(
        "GXR Manager",
        url,
        width=1280,
        height=900,
        min_size=(1000, 700),
        maximized=True,
        text_select=True,
    )
    try:
        webview.start()
    finally:
        # The pywebview path does not run the uvicorn shutdown handler.
        app.state.apps.install.cleanup()
        app.state.files.cleanup()
