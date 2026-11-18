from pathlib import Path


def test_recording_form_contains_max_wait_field():
    js = (Path(__file__).parents[1] / "gxr_profiler" / "server" / "web" / "app.js").read_text(encoding="utf-8")
    form_start = js.index("f.innerHTML = `")
    form_end = js.index("`;", form_start)
    form = js[form_start:form_end]
    assert 'id="r-cooldown-max-wait"' in form
    assert 'cooldownWaitInput = f.querySelector("#r-cooldown-max-wait")' in js


def test_tools_hub_contains_diagnostics():
    web = Path(__file__).parents[1] / "gxr_profiler" / "server" / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    js = (web / "app.js").read_text(encoding="utf-8")
    assert 'data-tab="tools"' in html
    assert "tab tab-utility" in html
    assert 'id="tools-separator"' in html
    assert html.index('data-tab="compare"') < html.index('id="tools-separator"')
    assert html.index('id="tools-separator"') < html.index('id="tools-tab"')
    assert 'class="sidebar-edge"' in html
    assert "sidebartoggle" not in html
    assert html.index("</aside>") < html.index('id="btn-sidebar"')
    assert 'data-tab="debug"' not in html
    assert 'id="viewtools"' in html
    assert html.count('class="toolbtn view-only"') == 3
    assert "renderToolsView" in js
    assert "renderDiagnosticsTool" in js
    assert "debugTombstonesCard" in js
    assert "debugExitInfoCard" in js
    assert "diag-signature" in js
    assert "setToolTab" in js
    assert "/api/debug/collect" in js
    assert "renderAppsTool" in js
    assert "/api/apps" in js
    assert "apps-modal" in js
    assert "apps-detail-modal" in js
    assert "Disable and remove actions are blocked" in js
    assert "appsCellText" in js
    assert "appsRunningLabel" in js
    assert "appsPerformanceCard" in js
    assert "Performance overrides" in js
    assert "/performance" in js
    assert "Render scale" in js
    assert "FPS cap" in js
    assert "toast-region" in js
    assert "showToast" in js
    assert "TOAST_DEFAULT_MS = 7000" in js
    assert "TOAST_WARNING_MS = 10000" in js
    assert "TOAST_LONG_MS = 15000" in js
    assert "mouseenter" in js
    assert "mouseleave" in js
    assert "aria-atomic" in js
    assert "tabIndex" in js
    assert "toast-open" in js
    assert "appsFlashCard" not in js
    assert "settingsFlashCard" not in js

    css = (web / "styles.css").read_text(encoding="utf-8")
    assert ".toast-region" in css
    assert ".toast-error" in css
    assert ".toast-body" in css
    assert ".toast-body:focus-visible" in css
    assert "body.toast-open .floatnav" in css
    assert "processFilterBar" in js
    assert "PROC_FILTERS" in js
    assert 'sort: { key: "cpu_pct", dir: -1 }' in js
    assert 'col.unit || "\\u00a0"' in js
    assert "CPU 5m" in js
    assert "GPU mem" in js
    assert "gpu_mem_kb" in js
    assert "size_kb" in js
    assert "Install size" in js
    assert "settings-confirm-modal" in js
    assert "Disable boundary" in js
    assert "settingselect" in js
    assert "OLED burn-in" in js
    assert "Test only" in js
    assert "Recommended: hide the recording indicator" in js
    assert 'textEl("span", "badge good", "Recommended")' in js
    assert "settings-header-sep" in js

    start = js.index("const APP_COLUMNS = [")
    columns = js[start : js.index("];", start)]
    assert columns.index('key: "size_kb"') < columns.index('key: "cpu_pct"')
    assert columns.index('key: "installer"') > columns.index('key: "threads"')
