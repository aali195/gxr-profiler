from datetime import UTC, datetime

from gxr_profiler.capture.poller import POLL_SCRIPT, parse_poll
from gxr_profiler.core import parsers as P
from tests.fake_adb import POLL_RESPONSE


def test_parse_header_ssrm_colon_tag():
    line = "10-17 03:26:57.579 I/SSRM:Temperature(18731): SIOP::  CHG : 31.5  WIFI : 33.3  AP : 32.5"
    h = P.parse_header(line)
    assert h["tag"] == "SSRM:Temperature"
    kv = P.parse_kv_colon(h["msg"])
    assert kv["AP"] == 32.5 and kv["WIFI"] == 33.3


def test_parse_thermal_changed():
    ev = P.parse_thermal_changed("[AP,13,58.000000,1,0]")
    assert ev["name"] == "AP" and ev["value"] == 58.0 and ev["sev"] == 1


def test_parse_dynpol():
    msg = (
        '{"Heartbeat":{"Spaceflinger":{"ExpectedFrameRate":72.0,"FrameRate":72.07},'
        '"System utilization":{"CPU":0.11,"GPU":0.0,"RAM":0.57}},"Thermal status":0}'
    )
    d = P.parse_dynpol(msg)
    assert d["thermal_status"] == 0.0 and d["xr_fps"] == 72.07 and d["xr_cpu"] == 0.11


def test_parse_cib_and_netstats():
    assert P.parse_cib("[CIB] 'Hat': (180.0 FPS @ 180.0Hz)")["cib_hat_fps"] == 180.0
    net = "uid rxBytes rxPackets txBytes txPackets\n  1000 42562 193 15876 201\n  mStatsMapA:"
    parsed = P.parse_netstats_uid(net)
    assert parsed[1000]["net_rx_bytes"] == 42562.0


def test_parse_media_video_codec():
    line = (
        "{codec, (10-19 13:46:02.481), (com.android.providers.media.module, 0, 10236), "
        "(android.media.mediacodec.codec=c2.qti.hevc.decoder, "
        "android.media.mediacodec.hdr-format=0, android.media.mediacodec.height=1080, "
        "android.media.mediacodec.id=2140518426521632768, "
        "android.media.mediacodec.mime=video/hevc, android.media.mediacodec.mode=video, "
        "android.media.mediacodec.profile=1, android.media.mediacodec.width=1920)}"
    )
    d = P.parse_media_video([line])
    assert d["media_codec"] == "c2.qti.hevc.decoder"
    assert d["media_app"] == "com.android.providers.media.module"
    assert d["media_mime"] == "video/hevc"
    assert d["media_w"] == 1920.0 and d["media_h"] == 1080.0
    assert d["media_hdr_format"] == 0.0
    assert d["media_bit_depth"] == 8.0
    assert P.is_hw_codec(d["media_codec"]) and not P.is_sw_codec(d["media_codec"])
    assert P.parse_media_video([]) == {}


def test_bit_depth_helpers():
    assert P.media_bit_depth("video/hevc", 2) == 10.0
    assert P.media_bit_depth("video/av01", 1) == 8.0
    assert P.media_bit_depth("video/x-vnd.on2.vp9", 2) == 8.0
    assert P.bit_depth_from_formats(["format: RGBA_1010102"]) == 10.0
    assert P.bit_depth_from_formats(["format:         RGBA_8888_UBWC"]) == 8.0
    assert P.color_mode_from_lines(["Current color mode: ColorMode::SRGB (7)"]) == "SRGB"
    assert P.color_mode_from_lines(["dataspace=BT709"]) is None


def test_parse_display_props_and_hdr():
    d = P.parse_display_props("Display Brightness=0.75\nDisplay SdrBrightness=1.0")
    assert d["disp_brightness"] == 0.75 and d["disp_sdr_brightness"] == 1.0
    assert P.parse_display_props("mBrightnessState=0.5")["disp_brightness"] == 0.5
    assert P.hdr_from_dataspaces(["dataspace=V0_BT2020_PQ"])
    assert not P.hdr_from_dataspaces(["dataspace=V0_SRGB", "dataspace=UNKNOWN"])


def test_parse_audio_flinger():
    text = (
        "Output thread 0x1, name AudioOut_D, tid 10170, type 9 (XR_SPATIALIZER):\n"
        "  Standby: no\n"
        "  Sample rate: 48000 Hz\n"
        "  HAL format: 0x4 (AUDIO_FORMAT_PCM_8_24_BIT)\n"
        "  Channel count: 2\n"
        "  Output devices: 0x2 (AUDIO_DEVICE_OUT_SPEAKER)\n"
        "  Audio source: 0 (AUDIO_SOURCE_DEFAULT)\n"
        "  Master volume: 1.000000\n"
        "  Master mute: off\n"
        "  Threadloop write latency stats: ave=134.304 std=0.8 min=124 max=135\n"
        "  Normal mixer raw underrun counters: partial=0 empty=0\n"
        "  2 Tracks of which 1 are active\n"
        "Input thread 0x2, name AudioIn_1, tid 10200, type 0 ():\n"
        "  Standby: no\n"
        "  Sample rate: 48000 Hz\n"
        "  HAL format: 0x1 (AUDIO_FORMAT_PCM_16_BIT)\n"
        "  Channel count: 2\n"
        "  Input device: 0x80000004 (AUDIO_DEVICE_IN_BUILTIN_MIC)\n"
        "  Audio source: 1 (AUDIO_SOURCE_MIC)\n"
        "  1 Tracks of which 1 are active\n"
    )
    d = P.parse_audio_flinger(text)
    assert d["audio_out_active"] == 1.0
    assert d["audio_out_device"] == "SPEAKER"
    assert d["audio_out_format"] == "PCM_8_24_BIT"
    assert d["audio_out_bits"] == 24.0
    assert d["audio_out_rate"] == 48000.0
    assert d["audio_out_channels"] == 2.0
    assert d["audio_out_underruns"] == 0.0
    assert d["audio_out_write_ms"] == 134.304
    assert d["audio_out_mute"] == 0.0
    assert d["audio_in_active"] == 1.0
    assert d["audio_in_device"] == "BUILTIN_MIC"
    assert d["audio_in_bits"] == 16.0
    assert d["audio_in_source"] == "MIC"


def test_parse_audio_state_and_metrics():
    audio = (
        "Audio Focus stack entries (last is top of stack):\n"
        "  source:x -- pack: com.google.android.apps.youtube.xr -- client:y\n"
        "\nNo external focus policy\n"
        "  players:\n"
        "  AudioPlaybackConfiguration piid:799 state:idle\n"
        "  AudioPlaybackConfiguration piid:815 state:started\n"
        "\n  ducked players piids:\n"
        "mic mute FromSwitch=false FromRestrictions=false FromApi=false from system=false\n"
        "- STREAM_MUSIC:\n"
        "   Muted: false\n"
        "   Min: 0\n"
        "   Max: 15\n"
        "   streamVolume:7\n"
        "- STREAM_ALARM:\n"
    )
    d = P.parse_audio_state(audio)
    assert d["audio_app"] == "com.google.android.apps.youtube.xr"
    assert d["audio_players"] == 1.0
    assert d["audio_mic_mute"] == 0.0
    assert d["audio_out_mute"] == 0.0
    assert d["audio_out_volume_pct"] == 46.7

    stripped = "\n".join(line.strip() for line in audio.splitlines() if line.strip())
    d_stripped = P.parse_audio_state(stripped)
    assert d_stripped["audio_players"] == 1.0
    assert d_stripped["audio_out_volume_pct"] == 46.7

    line = (
        "{codec, (10-19 13:46:04.448), (android.uid.honeyboard, 0, 10111), "
        "(android.media.mediacodec.channelCount=2, "
        "android.media.mediacodec.codec=c2.android.vorbis.decoder, "
        "android.media.mediacodec.mime=audio/vorbis, android.media.mediacodec.mode=audio, "
        "android.media.mediacodec.sampleRate=48000)}"
    )
    m = P.parse_media_audio([line])
    assert m["audio_codec"] == "c2.android.vorbis.decoder"
    assert m["audio_codec_mime"] == "audio/vorbis"
    assert m["audio_codec_app"] == "android.uid.honeyboard"
    assert m["audio_codec_rate"] == 48000.0
    assert m["audio_codec_channels"] == 2.0
    expected = (
        datetime(2000, 10, 19, 13, 46, 4, 448000, tzinfo=UTC) - datetime(2000, 1, 1, tzinfo=UTC)
    ).total_seconds()
    assert m["audio_codec_ts"] == expected


def test_parse_radios():
    d = P.parse_radios(
        ["0", "enabled: false", "state: BLE_ON"],
        ["0", "null", "false"],
    )
    assert d["bt_on"] == 0.0 and d["bt_state"] == "BLE_ON"
    assert d["loc_enabled"] == 0.0
    assert d["loc_mode"] == 0.0 and d["loc_mode_name"] == "off"
    assert "loc_providers" not in d

    d = P.parse_radios(
        ["1", "enabled: true", "state: ON"],
        ["3", "gps,network", "true"],
    )
    assert d["bt_on"] == 1.0 and d["bt_state"] == "ON"
    assert d["loc_enabled"] == 1.0
    assert d["loc_mode"] == 3.0 and d["loc_mode_name"] == "high accuracy"
    assert d["loc_providers"] == "gps,network"


def test_parse_poll_sections():
    out = parse_poll(POLL_RESPONSE)
    assert out["f_cpu0"] == 1382400.0
    assert out["cpu_max2"] == 2361600.0
    assert out["g_clock"] == 421.0
    assert out["sec_ap"] == 30.0
    assert out["batt_level"] == 80.0
    assert out["t_CPU5"] == 37.8  # from thermalservice HAL block
    assert out["wifi_rssi"] == -44.0
    assert POLL_SCRIPT.count("###FREQ") == 1


MEMINFO = """MemTotal:       16066684 kB
MemFree:          699744 kB
MemAvailable:    7981612 kB
Buffers:            5084 kB
Cached:          7618440 kB
SwapTotal:       4194300 kB
SwapFree:        3443312 kB
Dirty:               112 kB
Writeback:             0 kB
"""


def test_parse_memory_and_tasks():
    d = P.parse_meminfo(MEMINFO)
    assert d["mem_total"] == 16066684.0
    assert d["mem_cached"] == 7618440.0
    assert d["mem_used"] == 8085072.0
    assert round(d["mem_used_pct"], 2) == 50.32
    assert d["swap_total"] == 4194300.0
    assert d["swap_used"] == 750988.0
    assert round(d["swap_used_pct"], 2) == 17.90
    load = P.parse_loadavg("0.50 0.40 0.30 2/1234 1/100")
    assert load["procs_running"] == 2.0 and load["procs_total"] == 1234.0


def test_parse_cpu_utilisation():
    lines = [
        "cpu  100 0 100 800 0 0 0 0 0 0",
        "cpu0 473416 5961 325337 1244274 786 37475 140083 0 0 0",
        "cpu1 502696 5898 313072 1241525 830 34909 123504 0 0 0",
        "procs_running 2",
    ]
    raw = P.parse_proc_stat(lines)
    assert raw["cpu_stat0_total"] == 473416 + 5961 + 325337 + 1244274 + 786 + 37475 + 140083
    assert raw["cpu_stat0_idle"] == 1244274 + 786
    assert raw["procs_running"] == 2.0
    prev = {"cpu_stat0_total": 1000.0, "cpu_stat0_idle": 600.0}
    cur = {"cpu_stat0_total": 1100.0, "cpu_stat0_idle": 650.0}
    assert P.cpu_rates(cur, prev)["cpu_util0"] == 50.0


def test_parse_memory_pressure_zram_and_df():
    assert P.parse_psi_memory(["some avg10=1.23 avg60=0.50", "full avg10=0.00"]) == {
        "mem_pressure_some": 1.23,
        "mem_pressure_full": 0.0,
    }
    z = P.parse_zram(["758415360 219236362 232644608 0 293482496"])
    assert z["zram_used_mb"] == 232.644608
    df = P.parse_df_usage(
        [
            "Filesystem 1K-blocks Used Available Use% Mounted on",
            "/dev/block/dm-47 228369372 6390748 221847552 3% /storage/emulated/0/Android/obb",
        ]
    )
    assert round(df["disk_total_gb"], 2) == 217.79
    assert round(df["disk_free_gb"], 2) == 211.57
    assert df["disk_used_pct"] == 3.0


CONTROLLER_LOG = """10-21 22:40:56.873 12701 13156 I SXRC_TSVC: updateDeviceState hand_controller_left: state=connected, battery=87, hostFw=16.1
10-21 22:40:58.507 12701 13146 I SXRC_TSVC: updateDeviceState hand_controller_right: state=connected, battery=64, hostFw=16.1
10-21 22:40:56.641 11949 12219 I CpmInput: XRInputConnection: start tracking for hand_controller_right/pose_controller
10-21 22:40:56.641 11949 12219 I CpmInput: XRInputConnection: start tracking for hand_controller_left/pose_controller
10-21 22:42:07.438 11949 12219 I CpmInput: XRControllerDevice: stop tracking for hand_controller_right, state=bound/connected
10-21 22:42:07.438 11949 12219 I CpmInput: XRControllerDevice: stop tracking for hand_controller_left, state=bound/connected
"""


def test_parse_controller_state_and_tracking():
    d = P.parse_controller_log(CONTROLLER_LOG)
    assert d["ctrl_left_connected"] == 1.0
    assert d["ctrl_right_connected"] == 1.0
    assert d["ctrl_left_battery"] == 87.0
    assert d["ctrl_right_battery"] == 64.0
    assert d["ctrl_left_track"] == 0.0
    assert d["ctrl_right_track"] == 0.0
    assert d["controllers_active"] == 0.0

    d = P.parse_controller_log(CONTROLLER_LOG.split("10-21 22:42")[0])
    assert d["ctrl_left_track"] == 1.0
    assert d["ctrl_right_track"] == 1.0
    assert d["controllers_active"] == 1.0


def test_parse_controller_pose_tracking():
    line = (
        "10-21 22:47:30.759 1257 1317 I SXRC_POSE: getPoseAtTimestamp() "
        "Contr[1] reqTs: 1, resTs: 2, id: 0, status:2, quality: 1 ret: 0(SUCCESS)"
    )
    d = P.parse_controller_log(line)
    assert d["ctrl_right_track"] == 1.0
    assert d["controllers_active"] == 1.0
    line = line.replace("status:2", "status:3")
    assert P.parse_controller(line)["ctrl_right_track"] == 0.0


PASSTHROUGH_HOME = (
    "10-21 22:53:15.440 12796 12936 D PassthroughStateManager: New requested state: "
    "Home(requestEnabled=true, alpha=null, overridden=false) computed from stack: PassthroughModeStateStack("
    "disabled=Disabled, spatialApi=SpatialApi(requestEnabled=false, alpha=0.0, overridden=true), "
    "home=Home(requestEnabled=true, alpha=null, overridden=false), window=Window(requestEnabled=false))"
)


def test_parse_passthrough_state():
    d = P.parse_passthrough(PASSTHROUGH_HOME)
    assert d["passthrough"] == 1.0
    assert d["passthrough_mode"] == "Home"
    d = P.parse_passthrough("New requested state: Disabled")
    assert d["passthrough"] == 0.0
    assert d["passthrough_mode"] == "Disabled"
    assert P.parse_passthrough("passthroughRunning: 0")["passthrough"] == 0.0


WIFI_STATUS = """WifiInfo: SSID: "Test", Rx Link speed: 3843Mbps, Tx Link speed: 3843Mbps, Link speed: 3843Mbps, RSSI: -40, Frequency: 6295MHz
successfulTxPackets: 931004
successfulTxPacketsPerSecond: 151.37436059346277
retriedTxPackets: 26163
retriedTxPacketsPerSecond: 6.868021751990613
lostTxPackets: 1
lostTxPacketsPerSecond: 0.0
successfulRxPackets: 13043907
successfulRxPacketsPerSecond: 149.7272023178446
"""

NETDEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  wlan0: 85364194777 59119387 0 0 0 0 0 0 2754088221 2625124 0 0 0 0 0 0
"""


def test_parse_wifi_rates_and_netdev():
    wifi = P.parse_wifi_status(WIFI_STATUS)
    assert wifi["wifi_tx_pps"] == 151.37436059346277
    assert wifi["wifi_rx_pps"] == 149.7272023178446
    assert wifi["wifi_retry_pps"] == 6.868021751990613
    assert wifi["wifi_retry_pct"] > 4.5
    net = P.parse_netdev(NETDEV.splitlines())
    assert net["netdev_rx_bytes"] == 85364194777
    assert net["netdev_tx_bytes"] == 2754088221
    assert net["netdev_rx_drops"] == 0
    previous = dict(net)
    current = dict(net)
    current["netdev_rx_bytes"] += 1_000_000
    current["netdev_tx_bytes"] += 2_000_000
    rates = P.netdev_rates(current, previous, 2.0)
    assert rates["wifi_rx_mbps"] == 4.0
    assert rates["wifi_tx_mbps"] == 8.0
