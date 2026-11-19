"""One-time device/build/connection snapshot."""

from __future__ import annotations

import logging

from ..adb import AdbClient
from .audio import audio_info
from .boundary import boundary_info
from .calibration import calibration_info
from .display import display_info, panel_info
from .manufacture import first_setup_info, parse_manufacture_date, region_info
from .props import all_props
from .root import root_info
from .system import parse_battery, parse_df, parse_gpu, parse_ip, parse_mem, parse_uname, parse_wifi

log = logging.getLogger(__name__)


def collect_device_info(adb: AdbClient, check_root: bool = False) -> dict:
    p = all_props(adb)
    info: dict = {
        "model": p.get("ro.product.model"),
        "device": p.get("ro.product.device"),
        "product": p.get("ro.product.name"),
        "manufacturer": p.get("ro.product.manufacturer"),
        "brand": p.get("ro.product.brand"),
        "board": p.get("ro.board.platform"),
        "soc": p.get("ro.soc.model"),
        "soc_manufacturer": p.get("ro.soc.manufacturer"),
        "cpu_abi": p.get("ro.product.cpu.abi"),
        "kernel": p.get("ro.kernel.version"),
        "android": p.get("ro.build.version.release"),
        "sdk": p.get("ro.build.version.sdk"),
        "build_id": p.get("ro.build.id"),
        "build_display_id": p.get("ro.build.display.id"),
        "build_incremental": p.get("ro.build.version.incremental"),
        "build_pda": p.get("ro.build.PDA"),
        "bootloader": p.get("ro.bootloader"),
        "build_fingerprint": p.get("ro.build.fingerprint"),
        "build_type": p.get("ro.build.type"),
        "build_tags": p.get("ro.build.tags"),
        "build_date": p.get("ro.build.date"),
        "security_patch": p.get("ro.build.version.security_patch"),
        "oneui": p.get("ro.build.version.oneui"),
        "verified_boot": p.get("ro.boot.verifiedbootstate"),
        "bootloader_locked": p.get("ro.boot.flash.locked"),
        "debuggable": p.get("ro.debuggable"),
        "secure": p.get("ro.secure"),
        "manufacture_date": parse_manufacture_date(p.get("ril.manufacturedate")),
        "region": region_info(p),
    }
    if info.get("oneui"):
        try:
            info["oneui_name"] = f"{int(info['oneui']) / 10000:.1f}"
        except (TypeError, ValueError):
            pass

    script = (
        "echo '###UNAME'; uname -a; "
        "echo '###MEM'; grep MemTotal /proc/meminfo; "
        "echo '###DF'; df -h /data; "
        "echo '###GPU'; cat /sys/class/kgsl/kgsl-3d0/gpu_model; echo; "
        "cat /sys/class/kgsl/kgsl-3d0/max_gpuclk; echo; "
        "cat /sys/class/kgsl/kgsl-3d0/gpu_available_frequencies; echo; "
        "echo '###DISPLAY'; dumpsys display 2>/dev/null "
        "| grep -m2 -E 'DisplayDeviceInfo|mActiveSfDisplayMode'; "
        "echo '###BATTERY'; dumpsys battery; "
        "echo '###WIFI'; cmd wifi status 2>/dev/null | head -6; "
        "echo '###IP'; ip -4 addr show wlan0 2>/dev/null; "
        "echo '###SELINUX'; getenforce; "
        "echo '###THERMAL'; dumpsys thermalservice 2>/dev/null | grep -m1 -iE 'ThermalHAL'"
    )
    try:
        txt = adb.shell(script, timeout=20.0)
    except Exception:
        log.debug("device info script failed", exc_info=True)
        txt = ""

    def section(name: str) -> list[str]:
        out: list[str] = []
        cur = None
        for line in txt.splitlines():
            if line.startswith("###"):
                cur = line[3:].strip()
            elif cur == name and line.strip():
                out.append(line.strip())
        return out

    uname = parse_uname(section("UNAME"))
    if uname:
        info["kernel_full"] = uname
    ram = parse_mem(section("MEM"))
    if ram:
        info["ram_kb"] = ram
    storage = parse_df(section("DF"))
    if storage:
        info["storage"] = storage
    gpu = parse_gpu(section("GPU"))
    if gpu:
        info.update(gpu)
    disp = section("DISPLAY")
    if disp:
        display = display_info("\n".join(disp), p)
        if display:
            info["display"] = display
    bat = parse_battery(section("BATTERY"))
    if bat:
        info["battery"] = bat
    wifi = parse_wifi(section("WIFI"))
    if wifi:
        info["wifi"] = wifi
    ip = parse_ip(section("IP"))
    if ip:
        info.setdefault("wifi", {})["ip"] = ip
    sel = section("SELINUX")
    if sel:
        info["selinux"] = sel[0]
    therm = section("THERMAL")
    if therm:
        info["thermal_hal"] = therm[0]

    try:
        info["root"] = root_info(adb, check_root)
    except Exception:
        log.debug("root info failed", exc_info=True)
    try:
        info["panel"] = panel_info(adb, check_root)
    except Exception:
        log.debug("panel info failed", exc_info=True)
    try:
        audio = audio_info(adb)
        if audio:
            info["audio"] = audio
    except Exception:
        log.debug("audio info failed", exc_info=True)
    try:
        calibration = calibration_info(adb, check_root)
        if calibration:
            info["calibration"] = calibration
    except Exception:
        log.debug("calibration info failed", exc_info=True)
    try:
        boundary = boundary_info(adb)
        if boundary:
            info["boundary"] = boundary
    except Exception:
        log.debug("boundary info failed", exc_info=True)
    try:
        setup = first_setup_info(adb, check_root)
        if setup:
            info["first_setup"] = setup
    except Exception:
        log.debug("first setup date failed", exc_info=True)

    return {k: v for k, v in info.items() if v not in (None, "", [])}
