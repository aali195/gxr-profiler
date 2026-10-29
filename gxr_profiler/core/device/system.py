"""Parsers for the one-time device info script sections."""

from __future__ import annotations

import re

WIFI_STANDARD = {
    1: "legacy",
    2: "11a",
    3: "11b",
    4: "11g",
    5: "11n",
    6: "11ac (Wi-Fi 5)",
    7: "11ad",
    8: "11be (Wi-Fi 7)",
}
WIFI_SECURITY = {
    0: "open",
    1: "WEP",
    2: "PSK (WPA2)",
    3: "EAP",
    4: "SAE (WPA3)",
    5: "OWE",
    6: "WAPI-PSK",
    7: "WAPI-CERT",
}
BATTERY_HEALTH = {
    1: "unknown",
    2: "good",
    3: "overheat",
    4: "dead",
    5: "over-voltage",
    6: "failure",
    7: "cold",
}
BATTERY_STATUS = {
    1: "unknown",
    2: "charging",
    3: "discharging",
    4: "not charging",
    5: "full",
}


def _band(freq_mhz: float | None) -> str | None:
    if not freq_mhz:
        return None
    if freq_mhz >= 5925:
        return "6 GHz"
    if freq_mhz >= 2400:
        return "5 GHz"
    return "2.4 GHz"


def parse_uname(lines: list[str]) -> str | None:
    return lines[0] if lines else None


def parse_mem(lines: list[str]) -> int | None:
    m = re.search(r"MemTotal:\s*(\d+)", lines[0]) if lines else None
    return int(m.group(1)) if m else None


def parse_df(lines: list[str]) -> dict | None:
    for line in lines:
        if line.startswith("/dev/"):
            parts = line.split()
            if len(parts) >= 5:
                return {"size": parts[1], "used": parts[2], "avail": parts[3], "use_pct": parts[4]}
    return None


def parse_gpu(lines: list[str]) -> dict:
    out: dict = {}
    if lines:
        out["gpu_model"] = lines[0]
    if len(lines) >= 2:
        try:
            out["gpu_max_mhz"] = round(int(lines[1]) / 1e6)
        except ValueError:
            pass
    if len(lines) >= 3:
        out["gpu_freqs_mhz"] = sorted({round(int(x) / 1e6) for x in lines[2].split()}, reverse=True)
    return out


def parse_battery(lines: list[str]) -> dict:
    b: dict = {}
    for line in lines:
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if k in ("level", "temperature", "health", "status", "AC powered"):
            b[k.lower().replace(" ", "_")] = v
    for key, table in (("health", BATTERY_HEALTH), ("status", BATTERY_STATUS)):
        if key in b:
            try:
                b[key + "_name"] = table.get(int(b[key]), b[key])
            except (TypeError, ValueError):
                pass
    return b


def parse_wifi(lines: list[str]) -> dict:
    text = "\n".join(lines)
    w: dict = {}
    for key, pat in (
        ("ssid", r'SSID:\s*"([^"]+)"'),
        ("bssid", r"BSSID:\s*([0-9a-f:]{17})"),
        ("ip", r"IP:\s*/([0-9.]+)"),
        ("security_type", r"Security type:\s*(\d+)"),
        ("standard", r"Wi-Fi standard:\s*(\d+)"),
        ("frequency_mhz", r"Frequency:\s*(\d+)"),
        ("tx_mbps", r"Tx Link speed:\s*(\d+)"),
        ("rx_mbps", r"Rx Link speed:\s*(\d+)"),
    ):
        m = re.search(pat, text)
        if m:
            v = m.group(1)
            w[key] = v if key in ("ssid", "bssid", "ip") else (int(v) if v.isdigit() else v)
    if "standard" in w:
        w["standard_name"] = WIFI_STANDARD.get(w["standard"], str(w["standard"]))
    if "security_type" in w:
        w["security_name"] = WIFI_SECURITY.get(w["security_type"], str(w["security_type"]))
    if "frequency_mhz" in w:
        w["band"] = _band(float(w["frequency_mhz"]))
    w["mlo"] = "MLO_LINK_STATE_ACTIVE" in text
    return w


def parse_ip(lines: list[str]) -> str | None:
    m = re.search(r"inet\s+([0-9.]+/\d+)", "\n".join(lines))
    return m.group(1).split("/")[0] if m else None
