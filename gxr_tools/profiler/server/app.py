"""App factory + launcher for the gxr_tools.profiler viewer/recorder."""

from __future__ import annotations

import os
import secrets
import threading
import webbrowser
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import gxr_tools.core
from gxr_tools.core.paths import default_runs_dir
from gxr_tools.core.server import asset_version, install_local_guard, resolve_port, start_uvicorn, wait_for_server

from ..runs.store import RunStore
from .export import ExportService, make_js_api
from .recording import RecordManager
from .routers import record, report, runs, spec
from .web_modules import PROFILER_JS_FILES

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
COMMON_DIR = os.path.join(os.path.dirname(gxr_tools.core.__file__), "web_common")


def create_app(runs_dir: str | None = None, serial: str | None = None) -> FastAPI:
    runs_dir = runs_dir or default_runs_dir()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        application.state.manager.shutdown()

    app = FastAPI(title="GXR Profiler", lifespan=lifespan)
    app.state.token = secrets.token_urlsafe(24)
    app.state.store = RunStore(runs_dir)
    app.state.manager = RecordManager(runs_dir, serial)

    app.include_router(spec.router)
    app.include_router(runs.router)
    app.include_router(record.router)
    app.include_router(report.router)
    app.mount("/common", StaticFiles(directory=COMMON_DIR), name="common")
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    install_local_guard(app)

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
            *(os.path.join(WEB_DIR, name) for name in PROFILER_JS_FILES),
        )
        html = html.replace("__GXR_ASSET_VERSION__", version)
        return HTMLResponse(html.replace("</head>", f"  {meta}\n</head>", 1))

    return app


def run_ui(port: int = 8765, browser: bool = False, runs_dir: str | None = None, serial: str | None = None) -> None:
    port = resolve_port(port)
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
        import uvicorn

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return

    thread = start_uvicorn(app, port)
    wait_for_server(url, thread)
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
    try:
        webview.start()
    finally:
        # pywebview ends the process without a graceful uvicorn shutdown, so stop
        # an active recorder here to finalize meta.json and clear the marker.
        app.state.manager.shutdown()
