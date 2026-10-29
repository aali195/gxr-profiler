from gxr_profiler.capture.logcat import LogcatStream
from gxr_profiler.capture.state import MetricState
from tests.fake_adb import FakeAdb


def test_logcat_dispatch_updates_state():
    st = MetricState()
    stream = LogcatStream(FakeAdb(), st)
    # Guard against regressing `process_line` back to `_handle` (which
    # threading.Thread.start() would clobber on Python 3.13).
    stream.process_line("10-19 07:00:00.000 I/SSRM:w  (11981): limitFanStrength:: setting step = 2")
    stream.process_line(
        '10-19 07:00:00.000 I/DynamicPolicyManager(1): {"Heartbeat":{"Spaceflinger":'
        '{"ExpectedFrameRate":72.0,"FrameRate":71.5}},"Thermal status":1}'
    )
    snap = st.snapshot()
    assert snap["fan_step"] == 2.0
    assert snap["xr_fps"] == 71.5
    assert snap["thermal_status"] == 1.0


def test_logcat_controller_updates_state():
    st = MetricState()
    stream = LogcatStream(FakeAdb(), st)
    stream.process_line(
        "10-21 22:40:56.873 I/SXRC_TSVC(12701): "
        "updateDeviceState hand_controller_right: state=connected, battery=64, hostFw=16.1"
    )
    stream.process_line(
        "10-21 22:40:56.641 I/CpmInput(11949): "
        "XRInputConnection: start tracking for hand_controller_right/pose_controller"
    )
    snap = st.snapshot()
    assert snap["ctrl_right_connected"] == 1.0
    assert snap["ctrl_right_battery"] == 64.0
    assert snap["ctrl_right_track"] == 1.0


def test_logcat_passthrough_updates_state():
    st = MetricState()
    stream = LogcatStream(FakeAdb(), st)
    stream.process_line(
        "10-21 22:53:15.440 I/PassthroughStateManager(12796): "
        "New requested state: Home(requestEnabled=true, alpha=null, overridden=false)"
    )
    snap = st.snapshot()
    assert snap["passthrough"] == 1.0
    assert snap["passthrough_mode"] == "Home"


def test_dev_seconds_month_boundary():
    from gxr_profiler.capture.logcat import dev_seconds

    october = dev_seconds("10-31 23:59:59.000")
    november = dev_seconds("11-01 00:00:00.000")
    assert october is not None and november is not None
    assert november > october
