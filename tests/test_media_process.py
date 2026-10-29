import csv
from pathlib import Path

from gxr_profiler.capture.media import MediaSampler
from gxr_profiler.capture.meta import build_meta
from gxr_profiler.capture.processes import ProcessSampler
from gxr_profiler.capture.writer import RunWriter
from gxr_profiler.core.models import RunConfig
from gxr_profiler.core.parsers.media import parse_media_resources, visible_sf_lines
from tests.fake_adb import FakeAdb

MEDIA_RESPONSE = """###MEDIA
{codec, (10-19 21:23:48.290), (com.google.android.apps.youtube.xr, 0, 12345), \
(android.media.mediacodec.codec=c2.qti.av1.decoder, \
android.media.mediacodec.mime=video/av01, android.media.mediacodec.mode=video, \
android.media.mediacodec.profile=1, android.media.mediacodec.hdr-format=0, \
android.media.mediacodec.width=1920, android.media.mediacodec.height=1080)}
###RESOURCES
ResourceManagerService: 0x0
  Processes:
    Pid: 12345
      Client:
        Id: -123456789
        Name: c2.qti.av1.decoder
        Resources:
          non-secure-codec/video-codec:[]:1
          battery/video-codec:[]:1
  Process Pid override:
  Events logs (most recent at top):
    10-24 21:23:48 addMediaInfo(pid 12345, clientId -123456789, resources 1920x1080 (fps:30) - sw codec : no, encoder : no componentName = c2.qti.av1.decoder bitrate = 17000000 ), allocated hw codec count 1
###DISPLAY
Display Brightness=0.75
Display SdrBrightness=0.9
###SFHDR
Current color mode: ColorMode::SRGB (7)
dataspace=V0_SRGB
format:         RGBA_8888_UBWC
###AUDIO
Audio Focus stack entries (last is top of stack):
  source:x -- pack: com.google.android.apps.youtube.xr -- client:y

players:
  AudioPlaybackConfiguration piid:815 state:started

ducked players piids:
mic mute FromSwitch=false FromRestrictions=false FromApi=false from system=false
- STREAM_MUSIC:
   Muted: false
   Max: 15
   streamVolume:9
- STREAM_ALARM:
###FLINGER
Output thread 0x1, name AudioOut_D, tid 1, type 9 (XR_SPATIALIZER):
  Standby: no
  Sample rate: 48000 Hz
  HAL format: 0x4 (AUDIO_FORMAT_PCM_8_24_BIT)
  Channel count: 2
  Output devices: 0x2 (AUDIO_DEVICE_OUT_SPEAKER)
  Master mute: off
  Threadloop write latency stats: ave=134.0 std=0.1
  Normal mixer raw underrun counters: partial=0 empty=0
  2 Tracks of which 1 are active
"""

PROCESS_RESPONSE = """###CPUINFO
  50.0% 1234/com.foo:
###PS
  1234 1000 2048 com.foo
###GPUMEM
  Proc 1234 total: 4096
###NET
uid rxBytes rxPackets txBytes txPackets
  1000 100 1 200 2
"""


def test_media_sampler():
    adb = FakeAdb(media_response=MEDIA_RESPONSE)
    sampler = MediaSampler(adb)
    out = sampler.poll(100.0, 0.0, 0.0)
    assert out["media_poll_ok"] == 1.0
    assert out["media_active"] == 1.0
    assert out["media_codec"] == "c2.qti.av1.decoder"
    assert out["media_mime"] == "video/av01"
    assert out["media_bit_depth"] == 8.0
    assert out["media_hw_dec"] == 1.0
    assert out["media_w"] == 1920.0
    assert out["media_h"] == 1080.0
    assert out["disp_brightness"] == 0.75
    assert out["disp_bit_depth"] == 8.0
    assert out["disp_color_mode"] == "SRGB"
    assert out["hdr_active"] == 0.0
    assert out["audio_out_active"] == 1.0
    assert out["audio_out_format"] == "PCM_8_24_BIT"
    assert out["audio_out_bits"] == 24.0
    assert out["audio_out_volume_pct"] == 60.0


def test_media_sampler_idle_does_not_report_previous_decoder():
    sampler = MediaSampler(FakeAdb(media_response="###MEDIA\n###DISPLAY\n"))
    out = sampler.poll(100.0, 0.0, 0.0)
    assert out["media_active"] == 0.0
    assert out["media_hw_dec"] == 0.0
    assert out["media_sw_dec"] == 0.0
    assert "media_codec" not in out


def test_process_sampler(tmp_path):
    writer = RunWriter(str(tmp_path), "procs")
    writer.open(with_procs=True)
    sampler = ProcessSampler(FakeAdb(process_response=PROCESS_RESPONSE), writer, top=5)
    sampler.poll(10.0, 0.0)
    writer.close()

    path = Path(writer.procs_path)
    assert path.exists()
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["pid"] == "1234"
    assert rows[0]["name"] == "com.foo"
    assert rows[0]["cpu_pct"] == "50.0"
    assert rows[0]["gpu_mem_kb"] == "4.0"


def test_build_meta_keys():
    meta = build_meta(
        RunConfig(name="meta", duration=1.0, interval=0.5),
        started="a",
        recording_started="r",
        ended="b",
        duration_actual_s=1.5,
        rows=2,
        device_info={"model": "SM-I610"},
        start_state={"low_power": 0},
        end_state={"low_power": 1},
    )
    assert meta["label"] == "meta"
    assert meta["rows"] == 2
    assert meta["duration_actual_s"] == 1.5
    assert meta["device_model"] == "SM-I610"
    assert meta["recording_started"] == "r"
    assert meta["cooldown_max_wait"] == 0
    assert {"schema_version", "features", "columns_meta", "start_state", "end_state"} <= set(meta)


PROCESS_IO_RESPONSE = """###IO
PID 1234
read_bytes: 1000
write_bytes: 2000
"""


def test_process_sampler_root_disk_io(tmp_path):
    adb = FakeAdb(process_response=PROCESS_RESPONSE, process_io_response=PROCESS_IO_RESPONSE)
    writer = RunWriter(str(tmp_path), "proc-io")
    writer.open(with_procs=True)
    sampler = ProcessSampler(adb, writer, top=5, root=True)
    sampler.poll(10.0, 0.0)
    adb.process_io_response = "###IO\nPID 1234\nread_bytes: 3000\nwrite_bytes: 4000\n"
    sampler.poll(15.0, 0.0)
    writer.close()

    with Path(writer.procs_path).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["io_read_bytes"] == "1000.0"
    assert rows[0]["io_read_bps"] == ""
    assert rows[1]["io_read_bytes"] == "3000.0"
    assert rows[1]["io_read_bps"] == "400.0"
    assert rows[1]["io_write_bps"] == "400.0"


def test_procs_for_includes_disk_rates(tmp_path):
    from gxr_profiler.report.data import procs_for
    from gxr_profiler.runs.store import RunStore

    runs = tmp_path / "runs"
    runs.mkdir()
    run = runs / "io"
    run.mkdir()
    (run / "procs.csv").write_text(
        "name,cpu_pct,rss_kb,gpu_mem_kb,io_read_bps,io_write_bps,net_rx_bytes,net_tx_bytes\n"
        "com.foo,50,2048,4096,1000,2000,100,200\n"
        "com.foo,30,2048,4096,3000,4000,100,200\n",
        encoding="utf-8",
    )
    rows = procs_for(RunStore(str(runs)), "io")
    assert rows[0]["io_r"] == 2000.0
    assert rows[0]["io_w"] == 3000.0


def test_hdr_active_resets_after_hdr_source_disappears():
    from gxr_profiler.capture.media import MediaSampler

    class SeqAdb:
        def __init__(self):
            self.responses = [
                "###SFHDR\ndataspace=BT2020_PQ\n###END\n",
                "###SFHDR\nformat: RGBA_8888\n###END\n",
            ]

        def shell(self, script, timeout=25.0):
            return self.responses.pop(0)

    sampler = MediaSampler(SeqAdb())
    first = sampler.poll(1.0, 0.0, 0.0)
    assert first["hdr_active"] == 1.0
    assert first["disp_bit_depth"] is None
    second = sampler.poll(2.0, 0.0, 0.0)
    assert second["hdr_active"] == 0.0
    assert second["disp_bit_depth"] == 8.0


def test_media_resources_filter_encoder_and_accept_multiple_instances():
    lines = [
        line.strip()
        for line in """ResourceManagerService: 0x0
  Processes:
    Pid: 100
      Client:
        Id: -1
        Name: c2.qti.av1.encoder
        Resources:
          non-secure-codec/video-codec:[]:1
    Pid: 200
      Client:
        Id: -2
        Name: c2.qti.hevc.decoder
        Resources:
          non-secure-codec/video-codec:[]:2
  Process Pid override:
  Events logs (most recent at top):
    10-24 21:23:48 addMediaInfo(pid 200, clientId -2, resources 3840x2160 (fps:30) - sw codec : no, encoder : no componentName = c2.qti.hevc.decoder bitrate = 17000000 )
    10-24 21:23:47 addMediaInfo(pid 100, clientId -1, resources 1920x1080 (fps:30) - sw codec : no, encoder : yes componentName = c2.qti.av1.encoder bitrate = 10000000 )
""".splitlines()
        if line.strip()
    ]
    out = parse_media_resources(lines)
    assert out["media_active"] == 1.0
    assert out["media_codec"] == "c2.qti.hevc.decoder"
    assert out["media_w"] == 3840.0 and out["media_h"] == 2160.0
    assert out["media_hw_dec"] == 1.0


def test_media_sampler_clears_last_session_fields_when_active_codec_changes():
    response = """###MEDIA
{codec, (10-19 21:23:48.290), (com.old.app, 0, 1), (android.media.mediacodec.codec=c2.qti.hevc.decoder, android.media.mediacodec.mime=video/hevc, android.media.mediacodec.mode=video, android.media.mediacodec.profile=2, android.media.mediacodec.hdr-format=1, android.media.mediacodec.width=1920, android.media.mediacodec.height=1080)}
###RESOURCES
ResourceManagerService: 0x0
  Processes:
    Pid: 2
      Client:
        Id: -2
        Name: c2.qti.av1.decoder
        Resources:
          non-secure-codec/video-codec:[]:1
  Process Pid override:
  Events logs (most recent at top):
    10-24 21:23:48 addMediaInfo(pid 2, clientId -2, resources 3840x2160 (fps:30) - sw codec : no, encoder : no componentName = c2.qti.av1.decoder bitrate = 17000000 )
###DISPLAY
###SFHDR
###AUDIO
###FLINGER
"""
    out = MediaSampler(FakeAdb(media_response=response)).poll(100.0, 0.0, 0.0)
    assert out["media_active"] == 1.0
    assert out["media_codec"] == "c2.qti.av1.decoder"
    assert out["media_w"] == 3840.0 and out["media_h"] == 2160.0
    assert out["media_app"] is None
    assert out["media_mime"] is None
    assert out["media_profile"] is None
    assert out["media_hdr_format"] is None


def test_visible_sf_lines_ignores_hidden_hdr_layer():
    lines = [
        "* Layer hidden",
        "composition type=INVALID (0)",
        "dataspace=BT2020_PQ",
        "* Layer visible",
        "composition type=DEVICE (2)",
        "dataspace=V0_SRGB",
        "format: RGBA_8888",
    ]
    visible = visible_sf_lines(lines)
    assert "dataspace=BT2020_PQ" not in visible
    assert "dataspace=V0_SRGB" in visible
    assert "format: RGBA_8888" in visible


def test_media_poll_failure_is_marked_not_ok():
    class FailAdb:
        def shell(self, script, timeout=25.0):
            raise RuntimeError("adb disconnected")

    out = MediaSampler(FailAdb()).poll(1.0, 0.0, 0.0)
    assert out == {"media_poll_ok": 0.0}
