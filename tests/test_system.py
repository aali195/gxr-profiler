import pytest

from gxr_profiler.capture import poller


class _SequencedAdb:
    def __init__(self, responses):
        self.responses = list(responses)

    def shell(self, script, timeout=25.0):
        return self.responses.pop(0)

    def run(self, args, timeout=25.0):
        raise AssertionError("unexpected run")

    def popen(self, args):
        raise AssertionError("unexpected popen")


def test_poller_derives_cpu_utilisation():
    first = "###STAT\ncpu0 100 0 100 800 0 0 0 0 0 0\n"
    second = "###STAT\ncpu0 150 0 150 900 0 0 0 0 0 0\n"
    p = poller.Poller(_SequencedAdb([first, second]))
    assert "cpu_util0" not in p.poll()
    out = p.poll()
    assert out["cpu_util0"] == 50.0


def test_poller_reads_thermal_sensor():
    text = "Temperature{mValue=41.5, mType=0, mName=CPU5, mStatus=0}"
    p = poller.Poller(_SequencedAdb([text]))
    assert p.poll_thermal()["t_CPU5"] == 41.5


def test_preview_fan_step_does_not_use_broken_logcat_tag_filter():
    assert "-s SSRM:w" not in poller.PREVIEW_SCRIPT
    assert "grep -F 'limitFanStrength'" in poller.PREVIEW_SCRIPT


def test_poller_preview_computes_wifi_rate():
    text = (
        "###NETDEV1\n  wlan0: 1000 0 0 0 0 0 0 0 2000 0 0 0 0 0 0 0\n"
        "###T1\n100.0 1.0\n"
        "###NETDEV2\n  wlan0: 1001000 0 0 0 0 0 0 0 2000 0 0 0 0 0 0 0\n"
        "###T2\n100.5 1.0\n"
    )
    out = poller.Poller(_SequencedAdb([text])).poll_preview()
    assert out["wifi_rx_mbps"] == pytest.approx(16.0)


def test_poller_accumulates_max_energy(monkeypatch):
    times = iter([1000.0, 1010.0])
    monkeypatch.setattr(poller.time, "monotonic", lambda: next(times))
    first = "###MAX\nch1 0.0A, 1.0W, 1.0V\n"
    second = "###MAX\nch1 0.0A, 2.0W, 1.0V\n"
    p = poller.Poller(_SequencedAdb([first, second]))
    assert p.poll()["max_ch1_energy_wh"] == 0.0
    assert p.poll()["max_ch1_energy_wh"] == pytest.approx(10.0 / 3600.0)


def test_capture_profiles():
    from gxr_profiler.core.models import RunConfig, apply_profile

    cfg = RunConfig(name="profile")
    apply_profile(cfg, "standard")
    assert cfg.processes is True
    assert cfg.processes_interval == 10
    assert cfg.media_interval == 30
    assert cfg.root is False
    apply_profile(cfg, "everything")
    assert cfg.processes_kernel is True
    assert cfg.process_io is True
    assert cfg.root is True
    assert cfg.state_interval == 1
    assert cfg.features()["profile"] == "everything"


def test_record_request_resolves_profiles_and_overrides(tmp_path):
    import pytest

    from gxr_profiler.server.models import RecordRequest

    cfg = RecordRequest(profile="everything").to_config(str(tmp_path))
    assert cfg.processes is True
    assert cfg.processes_kernel is True
    assert cfg.process_io is True
    assert cfg.root is True
    assert cfg.state_interval == 1
    assert cfg.features()["profile"] == "everything"

    cfg = RecordRequest(
        profile="standard",
        sensor="CPU5",
        cooldown=36,
        cooldown_max_wait=120,
        processes=False,
    ).to_config(str(tmp_path))
    assert cfg.processes is False
    assert cfg.root is False
    assert cfg.media_interval == 30
    assert cfg.cooldown_sensor == "CPU5"
    assert cfg.cooldown_below == 36
    assert cfg.cooldown_max_wait == 120

    with pytest.raises(ValueError, match="unknown cooldown sensor"):
        RecordRequest(sensor="BOGUS").to_config(str(tmp_path))

    with pytest.raises(ValueError, match="process-io"):
        RecordRequest(profile="standard", process_io=True).to_config(str(tmp_path))


def test_process_io_requires_process_sampling(tmp_path):
    from gxr_profiler.core.models import RunConfig
    from gxr_profiler.server.models import RecordRequest

    with pytest.raises(ValueError, match="process sampling"):
        RunConfig(name="io", out_dir=str(tmp_path), root=True, processes=False, process_io=True)
    with pytest.raises(ValueError, match="process sampling"):
        RecordRequest(profile="standard", root=True, processes=False, process_io=True).to_config(str(tmp_path))


def test_record_manager_sequences_events(tmp_path):
    from types import SimpleNamespace

    from gxr_profiler.server.recording import RecordManager

    manager = RecordManager(str(tmp_path))
    manager._on_sample(SimpleNamespace(elapsed_s=0.0, row={"x": 1}))
    manager._on_sample(SimpleNamespace(elapsed_s=1.0, row={"x": 2}))
    assert [event["seq"] for event in manager.events] == [1, 2]
    assert manager.state()["rows"] == 2
