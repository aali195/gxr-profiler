from gxr_core.parsers.crash import (
    parse_crashes,
    parse_dropbox,
    parse_events,
    parse_exit_info,
    parse_tombstone_text,
)
from gxr_manager.core.collector import DiagnosticsCollector
from gxr_manager.core.diagnostics import analyze_report, classify_crash, format_markdown, is_systemui_hwui_race
from tests.fake_adb import POLL_RESPONSE, FakeAdb


def _line(ts: str, tag: str, pid: int, msg: str, prio: str = "I") -> str:
    return f"11-17 {ts} {prio}/{tag}({pid}): {msg}"


SYSTEMUI_CRASH = "\n".join(
    [
        _line("00:41:48.881", "DEBUG", 31700, "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***", "F"),
        _line("00:41:48.881", "DEBUG", 31700, "Timestamp: 2026-11-17 00:41:47.751068593+0000", "F"),
        _line("00:41:48.881", "DEBUG", 31700, "Process uptime: 1860s", "F"),
        _line("00:41:48.881", "DEBUG", 31700, "Cmdline: com.android.systemui", "F"),
        _line(
            "00:41:48.881",
            "DEBUG",
            31700,
            "pid: 11754, tid: 11754, name: ndroid.systemui  >>> com.android.systemui <<<",
            "F",
        ),
        _line("00:41:48.881", "DEBUG", 31700, "signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------", "F"),
        _line("00:41:48.881", "DEBUG", 31700, "Abort message: 'sp<> assignment detected data race'", "F"),
        _line("00:41:48.882", "DEBUG", 31700, "backtrace:", "F"),
        _line(
            "00:41:48.882",
            "DEBUG",
            31700,
            "#05 pc 000000000025e484  /system/lib64/libhwui.so (android::uirenderer::PropertyValuesAnimatorSet::start(...)+160)",
            "F",
        ),
        _line(
            "00:41:48.882",
            "DEBUG",
            31700,
            "#10 pc 0000000002000688  /memfd:jit-cache (android.widget.ProgressBar$CircleAnimationCallback$1.run+280)",
            "F",
        ),
    ]
)

SYSTEMUI_RENDER_THREAD_CRASH = "\n".join(
    [
        _line("00:51:36.747", "DEBUG", 6866, "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***", "F"),
        _line("00:51:36.747", "DEBUG", 6866, "Timestamp: 2026-11-17 00:51:36.070078941+0000", "F"),
        _line("00:51:36.747", "DEBUG", 6866, "Cmdline: com.android.systemui", "F"),
        _line(
            "00:51:36.747",
            "DEBUG",
            6866,
            "pid: 611, tid: 980, name: RenderThread  >>> com.android.systemui <<<",
            "F",
        ),
        _line("00:51:36.747", "DEBUG", 6866, "signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x2", "F"),
        _line("00:51:36.747", "DEBUG", 6866, "Cause: null pointer dereference", "F"),
        _line("00:51:36.748", "DEBUG", 6866, "backtrace:", "F"),
        _line(
            "00:51:36.748",
            "DEBUG",
            6866,
            "#00 pc 000000000026aa5c  /system/lib64/libhwui.so (std::__1::set<android::sp<android::uirenderer::PropertyValuesAnimatorSet>>::insert(...)+344)",
            "F",
        ),
        _line(
            "00:51:36.748",
            "DEBUG",
            6866,
            "#01 pc 000000000026b4ec  /system/lib64/libhwui.so (android::uirenderer::AnimationContextBridge::startFrame(...)+196)",
            "F",
        ),
    ]
)

EVENTS = "\n".join(
    [
        _line("00:41:49.143", "rescue_note", 1963, "[0,2,79837]"),
        _line("00:41:49.143", "boot_progress_start", 1963, "78093"),
        _line("00:41:49.143", "am_proc_died", 1963, "[0,11754,com.android.systemui,-800,0,666,4040]"),
    ]
)

DROPBOX = """Drop box contents: 1 entry
========================================
2026-11-17 00:11:09 SYSTEM_RESTART (text, 578 bytes)
isPrevious: true
Build: samsung/xrvst2ue/xrvst2
========================================
"""

EXIT_INFO = """ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)
  package: com.foo
    Historical Process Exit for uid=10000
        ApplicationExitInfo #0:
          timestamp=2026-11-17 00:11:39.936 pid=123 realUid=10000 packageUid=10000 definingUid=10000 user=0
          process=com.foo reason=5 (APP CRASH(NATIVE)) subreason=0 (UNKNOWN) status=11
          importance=100 pss=456MB rss=602MB description=crash state=empty trace=null
"""


def test_parse_systemui_native_crash():
    crashes = parse_crashes(SYSTEMUI_CRASH)
    assert len(crashes) == 1
    crash = crashes[0]
    assert crash["kind"] == "native"
    assert crash["process"] == "com.android.systemui"
    assert crash["signal"] == "SIGABRT"
    assert crash["abort"] == "sp<> assignment detected data race"
    assert is_systemui_hwui_race(crash)
    assert "PropertyValuesAnimatorSet" in crash["frames"][0]["symbol"]


def test_systemui_render_thread_crash_is_same_class():
    crash = parse_crashes(SYSTEMUI_RENDER_THREAD_CRASH)[0]
    assert crash["signal"] == "SIGSEGV"
    assert crash["cause"] == "null pointer dereference"
    assert is_systemui_hwui_race(crash)


def test_parse_java_crash_and_anr():
    java = "\n".join(
        [
            _line("00:01:00.000", "AndroidRuntime", 123, "FATAL EXCEPTION: main", "E"),
            _line("00:01:00.000", "AndroidRuntime", 123, "Process: com.example.app, PID: 123", "E"),
            _line("00:01:00.000", "AndroidRuntime", 123, "java.lang.RuntimeException: boom", "E"),
            _line("00:01:00.000", "AndroidRuntime", 123, "\\tat com.example.app.Main.run(Main.java:1)", "E"),
        ]
    )
    crash = parse_crashes(java)[0]
    assert crash["kind"] == "java"
    assert crash["process"] == "com.example.app"
    assert "RuntimeException" in crash["cause"]

    anr = parse_crashes(_line("00:02:00.000", "ActivityManager", 1, "ANR in com.example.app (pid 123)"))
    assert anr[0]["kind"] == "anr"
    assert anr[0]["process"] == "com.example.app"


def test_parse_events_boot_and_rescue():
    events = parse_events(EVENTS)
    assert events["rescue_notes"][0]["count"] == 2
    assert events["rescue_notes"][0]["window_ms"] == 79837
    assert events["boot_progress"][0]["tag"] == "boot_progress_start"
    assert events["proc_died"][0]["process"] == "com.android.systemui"


def test_parse_dropbox_and_exit_info():
    entries = parse_dropbox(DROPBOX)
    assert len(entries) == 1
    assert entries[0]["tag"] == "SYSTEM_RESTART"
    assert "Build:" in entries[0]["body"]

    exits = parse_exit_info(EXIT_INFO)
    assert len(exits) == 1
    assert exits[0]["package"] == "com.foo"
    assert exits[0]["reason_text"] == "APP CRASH(NATIVE)"
    assert exits[0]["process"] == "com.foo"


def test_analysis_calls_systemui_race_software_not_thermal():
    crashes = parse_crashes(SYSTEMUI_CRASH)
    events = parse_events(EVENTS)
    report = {
        "crashes": crashes,
        "boot": {
            "props": {"sys.boot.reason": "reboot,rescueparty_warm_reboot", "sys.rescue_boot_count": "2"},
            "rescue_notes": events["rescue_notes"],
            "uptime_s": 1000.0,
        },
        "thermal": {"thermal_status": 3, "t_AP": 74.4, "t_WIFI": 78.2, "t_LRP": 62.4, "fan_step": 7},
        "dropbox": [{"tag": "SYSTEM_TOMBSTONE", "timestamp": "2026-11-17 00:41:49"}],
        "root": {"requested": False, "available": False},
    }
    issues = analyze_report(report)
    titles = {issue["title"]: issue for issue in issues}
    assert "SystemUI HWUI animation race" in titles
    assert titles["SystemUI HWUI animation race"]["severity"] == "critical"
    assert any("not a thermal" in issue["summary"] for issue in issues)
    assert "Framework soft-reboot / rescue state" in titles
    assert "High thermal state (context only)" in titles
    assert "Dropbox retained crash / tombstone entries" in titles
    md = format_markdown({**report, "issues": issues, "collected_at": "2026-11-17T00:00:00Z"})
    assert "SystemUI HWUI animation race" in md


def test_report_without_crash_is_ok():
    issues = analyze_report(
        {
            "crashes": [],
            "boot": {"props": {}, "rescue_notes": []},
            "thermal": {},
            "root": {"requested": False, "available": False},
        }
    )
    assert issues[0]["severity"] == "ok"


class DiagFakeAdb(FakeAdb):
    def shell(self, script: str, timeout: float = 25.0) -> str:
        self.shell_calls.append(script)
        if "logcat -d -b crash" in script:
            return SYSTEMUI_CRASH
        if "logcat -d -b events" in script:
            return EVENTS
        if "logcat -d -b " in script:
            return ""
        if "dumpsys dropbox" in script:
            return DROPBOX
        if "dumpsys activity exit-info" in script:
            return EXIT_INFO
        if "cat /proc/uptime" in script:
            return "1000.0 2000.0"
        if "###THERM" in script:
            return POLL_RESPONSE
        return ""


def test_collector_snapshot_shape():
    adb = DiagFakeAdb()
    report = DiagnosticsCollector(adb, log_lines=500).collect()
    assert report["device"]["model"] == "SM-I610"
    assert report["crashes"][0]["process"] == "com.android.systemui"
    assert report["boot"]["rescue_notes"][0]["count"] == 2
    assert report["dropbox"][0]["tag"] == "SYSTEM_RESTART"
    assert report["exit_info"][0]["process"] == "com.foo"
    assert "logcat -d -b crash" in "\n".join(adb.shell_calls)
    assert report["sections"]["crash"].startswith("11-17 00:41:48.881")


PLAIN_TOMBSTONE = """*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Timestamp: 2026-11-17 00:41:47.751068593+0000
Process uptime: 1860s
Cmdline: com.android.systemui
pid: 11754, tid: 11754, name: ndroid.systemui  >>> com.android.systemui <<<
signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------
Abort message: 'sp<> assignment detected data race'
backtrace:
      #05 pc 000000000025e484  /system/lib64/libhwui.so (android::uirenderer::PropertyValuesAnimatorSet::start(...)+160) (BuildId: abc)
"""


def test_parse_plain_tombstone_body():
    crash = parse_tombstone_text(PLAIN_TOMBSTONE)[0]
    assert crash["process"] == "com.android.systemui"
    assert crash["signal"] == "SIGABRT"
    assert crash["abort"] == "sp<> assignment detected data race"
    assert is_systemui_hwui_race(crash)


PERCEPTION_TOMBSTONE = """*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Timestamp: 2026-11-06 23:17:47.000000000+0000
Cmdline: /vendor/bin/hw/android.hardware.perceptionhost
signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------
Abort message: 'Head tracking failed to initialize the internal MotionTrackingAdapter component.'
backtrace:
      #00 pc 000000000005d110  /apex/com.android.runtime/lib64/bionic/libc.so (abort+168) (BuildId: abc)
"""


def test_historical_tombstone_and_silent_records_are_reported():
    tombstone_crashes = parse_tombstone_text(PERCEPTION_TOMBSTONE)
    tombstone_crashes[0]["tombstone"] = "tombstone_03"
    report = {
        "collected_at": "2026-11-17T19:00:00+00:00",
        "crashes": [],
        "tombstone_crashes": tombstone_crashes,
        "events": {
            "am_anrs": [
                {
                    "process": "com.example.app",
                    "timestamp": "11-17 18:00:00.000",
                    "message": "[0,123,com.example.app,0,input dispatching timed out]",
                }
            ]
        },
        "exit_info": [
            {
                "timestamp": "2026-11-17 18:01:02.000",
                "process": "com.example.app",
                "reason_text": "APP CRASH(NATIVE)",
                "status": "11",
            }
        ],
        "sections": {"system": "11-17 18:00:00.000 E Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS ***"},
        "boot": {"props": {}, "rescue_notes": []},
        "thermal": {},
        "root": {"requested": False, "available": False},
    }
    issues = analyze_report(report)
    titles = {issue["title"] for issue in issues}
    assert "Historical Perception head-tracking initialisation failure" in titles
    assert "ActivityManager ANR event: com.example.app" in titles
    assert "Recent abnormal app exits" in titles
    assert "System log fault indicators" in titles
    assert any(
        "WATCHDOG" in line
        for line in next(i for i in issues if i["title"] == "System log fault indicators")["evidence"]
    )


IMMERSIVE_TOMBSTONE = """*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
Timestamp: 2026-11-08 20:50:18.147410069+0000
Cmdline: com.google.android.apps.immersiveviewxr
pid: 27825, tid: 27950, name: Thread-24  >>> com.google.android.apps.immersiveviewxr <<<
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x00ffffffffffffff
backtrace:
      #00 pc 000000000020fd18  /vendor/lib64/hw/vulkan.adreno.so (vkCreateImage+328) (BuildId: abc)
      #01 pc 0000000000021fc0  /system/lib64/vulkan/libVkLayer_android_foveation.so (Initialize+612) (BuildId: def)
      #02 pc 0000000000ede808  /data/app/example/lib/arm64/libunity.so (BuildId: ghi)
"""


def test_known_perception_and_immersive_signatures():
    perception = parse_tombstone_text(PERCEPTION_TOMBSTONE)[0]
    sig = classify_crash(perception)
    assert sig is not None
    assert sig["id"] == "perception_head_tracking_init"

    immersive = parse_tombstone_text(IMMERSIVE_TOMBSTONE)[0]
    sig = classify_crash(immersive)
    assert sig is not None
    assert sig["id"] == "immersiveviewxr_foveation"
    report = {
        "collected_at": "2026-11-17T19:00:00+00:00",
        "crashes": [],
        "tombstone_crashes": [immersive],
        "events": {},
        "exit_info": [],
        "sections": {},
        "boot": {"props": {}, "rescue_notes": []},
        "thermal": {},
        "root": {"requested": False, "available": False},
    }
    titles = {issue["title"] for issue in analyze_report(report)}
    assert "Historical Immersive View XR Vulkan/foveation crash" in titles
    assert immersive.get("signature", {}).get("id") == "immersiveviewxr_foveation"
