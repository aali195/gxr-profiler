from gxr_profiler.core.device import parse_display_info
from gxr_profiler.core.parsers import parse_audio_policy

TEXT = (
    'DisplayDeviceInfo{"Built-in Screen": uniqueId="local:1", 7104 x 3840, modeId 2, '
    "renderFrameRate 72.00001, colorMode 0, supportedColorModes [0, 7, 9], "
    "hdrCapabilities HdrCapabilities{mSupportedHdrTypes=[2, 3], mMaxLuminance=500.0, "
    "mMaxAverageLuminance=500.0, mMinLuminance=0.0}, allmSupported false, "
    "gameContentTypeSupported false, density 240, brightnessMinimum 0.0, "
    "brightnessMaximum 1.0, brightnessDefault 0.425197, hdrSdrRatio NaN}\n"
    "mActiveSfDisplayMode=DisplayMode{id=1, width=7104, height=3840, xDpi=3922.643, "
    "yDpi=3901.44, refreshRate=72.00001, appVsyncOffsetNanos=2000000, "
    "presentationDeadlineNanos=13888888, supportedHdrTypes=[2, 3], group=0}"
)


def test_parse_display_info():
    d = parse_display_info(TEXT)
    assert d["width"] == 7104 and d["height"] == 3840
    assert d["refresh_hz"] == 72.0
    assert d["hdr_types"] == ["HDR10", "HLG"]
    assert d["max_luminance_nits"] == 500.0
    assert d["brightness"] == {"min": 0.0, "max": 1.0, "default": 0.425197}
    assert d["color_modes"] == ["NATIVE", "SRGB", "DISPLAY_P3"]
    assert d["bit_depth"] == 10
    assert d["allm"] is False and d["game_mode"] is False


def test_parse_audio_policy():
    text = (
        "Available output devices (1):\n"
        '  1. Port ID: 2; "Speaker"; {AUDIO_DEVICE_OUT_SPEAKER, @:}\n'
        "   - Profiles (2):\n"
        '      1. ""; AUDIO_FORMAT_PCM_16_BIT (0x1)\n'
        "         sampling rates: 48000\n"
        "         channel masks: 0x0003\n"
        '      2. ""; AUDIO_FORMAT_PCM_8_24_BIT (0x4)\n'
        "         sampling rates: 48000\n"
        "         channel masks: 0x0003\n"
        "Available input devices (1):\n"
        '  1. Port ID: 12; "Built-In Mic"; {AUDIO_DEVICE_IN_BUILTIN_MIC, @:bottom}\n'
        "   - Profiles (1):\n"
        '      1. ""; AUDIO_FORMAT_PCM_16_BIT (0x1)\n'
        "         sampling rates: 8000, 16000, 48000\n"
        "         channel masks: 0x000c\n"
        "Hardware modules (1):\n"
    )
    d = parse_audio_policy(text)
    assert d["outputs"][0]["name"] == "Speaker"
    assert d["outputs"][0]["formats"] == ["PCM_16_BIT", "PCM_8_24_BIT"]
    assert d["outputs"][0]["rates_hz"] == [48000]
    assert d["inputs"][0]["name"] == "Built-In Mic"
    assert d["inputs"][0]["rates_hz"] == [8000, 16000, 48000]


def test_resolve_serial_collapses_only_same_physical(monkeypatch):
    from gxr_profiler.core import adb

    devices = [
        {"serial": "usb1", "state": "device", "device": "xrvst2", "model": "SM-I610"},
        {"serial": "192.168.0.2:5555", "state": "device", "device": "xrvst2", "model": "SM-I610"},
    ]
    monkeypatch.setattr(adb, "devices_detailed", lambda: devices)
    monkeypatch.setattr(adb, "_physical_serial", lambda serial: "R3GYC02MM2P")
    assert adb.resolve_serial(None) == "usb1"

    monkeypatch.setattr(adb, "_physical_serial", lambda serial: serial)
    with __import__("pytest").raises(adb.AdbError):
        adb.resolve_serial(None)


def test_calibration_parsers():
    from gxr_profiler.core.device.calibration import parse_cpm_ipd, parse_ipd_textproto

    ipd = parse_ipd_textproto(
        "created_at {\n  seconds: 1791938387\n}\n"
        "ipd_adjustment {\n ipd_mm: 71.85291\n encoder_left_mm: 35.926456\n"
        " encoder_right_mm: 35.926456\n}\n"
    )
    assert ipd["ipd_mm"] == 71.85291
    assert ipd["ipd_left_mm"] == 35.926456
    assert ipd["ipd_calibrated_at"] == "2026-10-14T00:39:47+00:00"
    cpm = parse_cpm_ipd("IPD Used For Rendering - Left Eye: 34.151501 Right Eye: 34.151501")
    assert cpm["ipd_in_use_mm"] == 68.303


def test_boundary_settings_parser():
    from gxr_profiler.core.device.boundary import parse_boundary_settings

    out = parse_boundary_settings(
        [
            "guardian_radius=1",
            "toggle_guardian=0",
            "guardian_boundary_placement_mode=0",
            "guardian_consent_granted=1",
            "guardian_floor_height_setup_mode=2",
            "guardian_floor_y_offset_from_head=-1.0361316",
            "guardian_position_setup_available=0",
            "guardian_toggle_radius_available=1",
        ]
    )
    assert out["consent_granted"] is True
    assert out["toggle_guardian"] is False
    assert out["radius_m"] == 1.0
    assert out["position_setup_available"] is False
    assert out["floor_offset_m"] == -1.0361316


def test_manufacture_date_parser():
    from gxr_profiler.core.device.manufacture import parse_manufacture_date

    assert parse_manufacture_date("20251201") == "2025-12-01"
    assert parse_manufacture_date("2025-12-01") == "2025-12-01"
    assert parse_manufacture_date(None) is None


def test_region_info():
    from gxr_profiler.core.device.manufacture import region_info

    assert region_info(
        {
            "mdc.country_code": "UNITED KINGDOM",
            "mdc.countryiso_code": "GB",
            "ro.csc.sales_code": "TXV",
            "persist.sys.locale": "en-GB",
        }
    ) == {
        "country": "United Kingdom",
        "country_iso": "GB",
        "sales_code": "TXV",
        "locale": "en-GB",
    }
    assert region_info({}) == {}
