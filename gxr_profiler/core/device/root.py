"""Root/su detection."""

from __future__ import annotations

from ..adb import AdbClient


def root_info(adb: AdbClient, active: bool) -> dict:
    """Passive indicators always; active `su -c id` only when requested."""
    out: dict = {}
    try:
        txt = adb.shell("command -v su; command -v ksud; command -v magisk", timeout=6.0)
    except Exception:
        txt = ""
    paths = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    out["su_present"] = any(ln.endswith("/su") for ln in paths)
    out["ksud_present"] = any(ln.endswith("/ksud") for ln in paths)
    out["magisk_present"] = any(ln.endswith("/magisk") for ln in paths)
    if not active:
        return out
    try:
        proc = adb.run(["shell", "su", "-c", "id"], timeout=8.0)
        ident = (proc.stdout or "").strip()
    except Exception:
        ident = ""
    if ident:
        out["id"] = ident
        out["active"] = "uid=0" in ident
        if "ksu" in ident:
            out["manager"] = "KernelSU"
        elif "magisk" in ident:
            out["manager"] = "Magisk"
        else:
            out["manager"] = "su"
    else:
        out["active"] = False
    if "manager" not in out:
        if out.get("ksud_present"):
            out["manager"] = "KernelSU"
        elif out.get("magisk_present"):
            out["manager"] = "Magisk"
    return out
