from gxr_tools.profiler.report.charts import GROUPS


def test_thermal_charts_mirror_into_cpu_gpu_tabs():
    by_id = {group.id: group for group in GROUPS}
    assert "CPU" in by_id["thermal_cpu"].extra_sections
    assert "GPU" in by_id["thermal_gpu"].extra_sections


def test_raw_cameras_share_camera_section():
    by_id = {group.id: group for group in GROUPS}
    assert by_id["camera_raw"].section == "Cameras"
