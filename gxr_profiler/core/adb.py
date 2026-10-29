"""adb access: an injectable client plus convenience helpers.

`AdbClient` is the seam used by the capture layer so tests can substitute a
fake. `RealAdb` wraps the local `adb` executable. All calls are read-only in
this project - nothing here writes to the device.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class AdbError(RuntimeError):
    pass


class RunNotFound(FileNotFoundError):
    pass


@runtime_checkable
class AdbClient(Protocol):
    """Minimal read-only adb surface."""

    def run(self, args: list[str], timeout: float = 25.0) -> subprocess.CompletedProcess: ...

    def shell(self, script: str, timeout: float = 25.0) -> str: ...

    def popen(self, args: list[str]): ...


@dataclass
class RealAdb:
    serial: str | None = None
    exe: str = field(default_factory=lambda: os.environ.get("ADB", "adb"))

    def run(self, args: list[str], timeout: float = 25.0) -> subprocess.CompletedProcess:
        cmd = [self.exe]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise AdbError("adb executable not found (set ADB env var)") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb timed out: {' '.join(cmd)}") from exc

    def shell(self, script: str, timeout: float = 25.0) -> str:
        proc = self.run(["shell", script], timeout=timeout)
        out = proc.stdout or ""
        if proc.stderr:
            out += ("\n" + proc.stderr) if out else proc.stderr
        return out

    def popen(self, args: list[str]) -> subprocess.Popen:
        cmd = [self.exe]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_NO_WINDOW,
        )


def _adhoc(serial: str | None) -> RealAdb:
    return RealAdb(serial=serial)


def run_adb(serial: str | None, args: list[str], timeout: float = 25.0) -> subprocess.CompletedProcess:
    return _adhoc(serial).run(args, timeout=timeout)


def devices_detailed() -> list[dict]:
    proc = run_adb(None, ["devices", "-l"])
    out: list[dict] = []
    for line in (proc.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        entry = {"serial": parts[0], "state": parts[1]}
        for tok in parts[2:]:
            if ":" in tok:
                key, val = tok.split(":", 1)
                entry[key] = val
        out.append(entry)
    return out


def list_devices() -> list[tuple[str, str]]:
    return [(d["serial"], d["state"]) for d in devices_detailed()]


def _physical_serial(serial: str) -> str:
    try:
        proc = run_adb(serial, ["shell", "getprop", "ro.serialno"], timeout=5.0)
        value = (proc.stdout or "").strip()
        if proc.returncode == 0 and value:
            return value
    except Exception:
        pass
    return ""


def resolve_serial(serial: str | None) -> str:
    """Return a usable serial; only collapse transports for the same physical device."""
    if serial:
        return serial
    env = os.environ.get("ANDROID_SERIAL")
    if env:
        return env
    all_devs = devices_detailed()
    ready = [d for d in all_devs if d["state"] == "device"]
    if not ready:
        found = ", ".join(f"{d['serial']}({d['state']})" for d in all_devs) or "none"
        raise AdbError(f"no adb device in 'device' state (found: {found})")
    if len(ready) == 1:
        return ready[0]["serial"]

    groups: dict[str, list[dict]] = {}
    for device in ready:
        physical = _physical_serial(device["serial"])
        # Never collapse unrelated transports just because the model matches.
        identity = f"serial:{physical}" if physical else f"transport:{device['serial']}"
        groups.setdefault(identity, []).append(device)
    if len(groups) != 1:
        raise AdbError("multiple adb devices connected; pass --serial. Found: " + ", ".join(d["serial"] for d in ready))

    transports = next(iter(groups.values()))

    def rank(device: dict) -> tuple[int, str]:
        name = device["serial"]
        if "._adb-tls-connect." in name:
            return (2, name)
        if ":" in name:
            return (1, name)
        return (0, name)

    return min(transports, key=rank)["serial"]
