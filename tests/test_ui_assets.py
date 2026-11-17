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
    assert 'tab tab-utility' in html
    assert 'id="tools-separator"' in html
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
