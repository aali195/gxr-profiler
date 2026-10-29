from pathlib import Path


def test_recording_form_contains_max_wait_field():
    js = (Path(__file__).parents[1] / "gxr_profiler" / "server" / "web" / "app.js").read_text(encoding="utf-8")
    form_start = js.index("f.innerHTML = `")
    form_end = js.index("`;", form_start)
    form = js[form_start:form_end]
    assert 'id="r-cooldown-max-wait"' in form
    assert 'cooldownWaitInput = f.querySelector("#r-cooldown-max-wait")' in js
