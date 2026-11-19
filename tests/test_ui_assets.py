import inspect
from pathlib import Path

from gxr_manager.server.app import run_ui as run_manager_ui
from gxr_manager.server.web_modules import MANAGER_JS_FILES
from gxr_profiler.server.app import run_ui as run_profiler_ui
from gxr_profiler.server.web_modules import PROFILER_JS_FILES

ROOT = Path(__file__).parents[1]
PROFILER_WEB = ROOT / "gxr_profiler" / "server" / "web"
MANAGER_WEB = ROOT / "gxr_manager" / "server" / "web"
COMMON_WEB = ROOT / "gxr_core" / "web_common"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _profiler_js() -> str:
    return "\n".join(_read(PROFILER_WEB / name) for name in PROFILER_JS_FILES)


def test_profiler_recording_form_contains_max_wait_field():
    js = _profiler_js()
    form_start = js.index("f.innerHTML = `")
    form_end = js.index("`;", form_start)
    form = js[form_start:form_end]
    assert 'id="r-cooldown-max-wait"' in form
    assert 'cooldownWaitInput = f.querySelector("#r-cooldown-max-wait")' in js


def test_profiler_keeps_only_run_tabs():
    html = _read(PROFILER_WEB / "index.html")
    js = _profiler_js()
    assert 'data-tab="live"' in html
    assert 'data-tab="run"' in html
    assert 'data-tab="compare"' in html
    assert 'data-tab="tools"' not in html
    assert 'id="tools-separator"' not in html
    assert 'id="viewtools"' in html
    assert html.count('class="toolbtn view-only"') == 3
    assert "/common/common.css" in html
    assert "/common/common.js" in html
    for name in PROFILER_JS_FILES:
        assert f"/static/{name}" in html
    assert "renderToolsView" not in js
    assert "renderInstallerTool" not in js
    assert "appsState" not in js
    assert "settingsState" not in js
    assert "renderLiveView" in js
    assert "renderCompareView" in js
    assert "processFilterBar" in js
    assert "PROC_FILTERS" in js
    assert 'col.unit || "\\u00a0"' in js


def test_compare_process_card_uses_the_shared_filter_bar():
    js = _profiler_js()
    start = js.index("async function compareProcessesCard")
    end = js.index("function renderCompareView", start)
    card = js[start:end]
    assert "processFilterBar" in card
    assert "search.oninput" not in card


def test_manager_ui_contains_device_tools():
    html = _read(MANAGER_WEB / "index.html")
    js = "\n".join(_read(MANAGER_WEB / name) for name in MANAGER_JS_FILES)
    assert "GXR Manager" in html
    assert 'id="recording-banner"' in html
    assert "/common/common.css" in html
    assert "/common/common.js" in html
    for name in MANAGER_JS_FILES:
        assert f"/static/{name}" in html
    assert "toolDefinitions" in js
    assert 'id: "diagnostics"' in js
    assert 'id: "apps"' in js
    assert 'id: "installer"' in js
    assert 'id: "settings"' in js
    assert "renderDiagnosticsTool" in js
    assert "debugTombstonesCard" in js
    assert "diag-signature" in js
    assert "/api/debug/collect" in js
    assert "renderAppsTool" in js
    assert "/api/apps" in js
    assert 'sort: { key: "cpu_pct", dir: -1 }' in js
    assert "CPU 5m" in js
    assert "GPU mem" in js
    assert "apps-detail-modal" in js
    assert "appsPerformanceCard" in js
    assert "Performance overrides" in js
    assert "Render scale" in js
    assert "FPS cap" in js
    assert "Load apps" in js
    assert "Load settings" in js
    assert "renderInstallerTool" in js
    assert "installerHeaderCard" in js
    assert "appsInstallFilesView" in js
    assert "appsInstallStartPolling" in js
    assert "appsInstallRestore" in js
    assert "/api/apps/install/state" in js
    assert "webkitGetAsEntry" in js
    assert "Review install" in js
    assert "Install completed" in js
    assert "Install APK / OBB" not in js
    assert "renderSettingsTool" in js
    assert "settings-confirm-modal" in js
    assert "Disable setting" in js
    assert "OLED burn-in" in js
    assert "Test only" in js
    assert "refreshRecordingStatus" in js
    assert "/api/recording" in js
    assert "renderLiveView" not in js
    assert "renderCompareView" not in js


def test_shared_assets_contain_toast_and_copy_styles():
    js = _read(COMMON_WEB / "common.js")
    css = _read(COMMON_WEB / "common.css")
    assert "toast-region" in js
    assert "showToast" in js
    assert "TOAST_DEFAULT_MS = 7000" in js
    assert "TOAST_WARNING_MS = 10000" in js
    assert "TOAST_LONG_MS = 15000" in js
    assert "mouseenter" in js
    assert "mouseleave" in js
    assert "aria-atomic" in js
    assert "toast-open" in js
    assert "copyText" in js
    assert "copyButton" in js
    assert "copyablePre" in js
    assert "function fmtStamp" in js
    assert "toast-copy" in js
    assert "Copy failed" in js
    assert ".toast-region" in css
    assert ".toast-error" in css
    assert ".toast-body" in css
    assert ".toast-body:focus-visible" in css
    assert ".copyblock" in css
    assert ".copybtn" in css


def test_manager_installer_done_clears_in_place():
    js = "\n".join(_read(MANAGER_WEB / name) for name in MANAGER_JS_FILES)
    assert "Install another" not in js
    installer = _read(MANAGER_WEB / "installer.js")
    start = installer.index("async function appsInstallViewPackage")
    body = installer[start:]
    assert body.index("await appsFetch()") < body.index('setToolTab("apps")')


def test_manager_styles_contain_installer_styles():
    css = _read(MANAGER_WEB / "styles.css")
    assert ".install-drop" in css
    assert ".install-body" in css
    assert ".install-step" in css
    assert ".install-progress-fill" in css


def test_styles_are_split_between_shared_and_app_sheets():
    common = _read(COMMON_WEB / "common.css")
    profiler = _read(PROFILER_WEB / "styles.css")
    manager = _read(MANAGER_WEB / "styles.css")
    for selector in (".sidebar", "#runlist", ".runitem", ".chart", ".floatnav", ".pickitem"):
        assert selector not in common
        assert selector in profiler
    for selector in (".appstable", ".install-drop", ".diag-issue", ".settingrow", ".appschip"):
        assert selector not in common
        assert selector in manager
    assert "/static/styles.css" in _read(PROFILER_WEB / "index.html")
    assert "/static/styles.css" in _read(MANAGER_WEB / "index.html")


def test_native_windows_allow_text_selection():
    assert "text_select=True" in inspect.getsource(run_profiler_ui)
    assert "text_select=True" in inspect.getsource(run_manager_ui)
