"""adb access: an injectable client plus convenience helpers.

`AdbClient` is the seam used by the capture layer so tests can substitute a
fake. `RealAdb` wraps the local `adb` executable. Recording and diagnostics use
only reads here; the optional Tools > Apps workflow uses the same client for
explicit, confirmed package-manager actions.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .paths import runtime_dir

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

CONNECT_WAIT_S = 30.0
CONNECT_POLL_S = 5.0
DEVICE_LIST_TIMEOUT_S = 5.0


class AdbError(RuntimeError):
    pass


class RunNotFound(FileNotFoundError):
    pass


def resolve_adb_executable(base_dir: str | os.PathLike[str] | None = None) -> str:
    """Find adb from ADB, the runtime folder, platform-tools, or PATH."""
    env = os.environ.get("ADB")
    if env:
        return env
    name = "adb.exe" if os.name == "nt" else "adb"
    root = Path(base_dir) if base_dir is not None else runtime_dir()
    for candidate in (root / name, root / "platform-tools" / name):
        if candidate.is_file():
            return str(candidate)
    return "adb"


@runtime_checkable
class AdbClient(Protocol):
    """Minimal adb surface used by the profiler."""

    def run(self, args: list[str], timeout: float = 25.0) -> subprocess.CompletedProcess: ...

    def shell(self, script: str, timeout: float = 25.0) -> str: ...

    def popen(self, args: list[str]): ...


@dataclass
class RealAdb:
    serial: str | None = None
    exe: str = field(default_factory=resolve_adb_executable)

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
            raise AdbError("adb executable not found (set ADB or place adb.exe next to gxr-profiler.exe)") from exc
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


def devices_detailed(timeout: float = 25.0) -> list[dict]:
    proc = run_adb(None, ["devices", "-l"], timeout=timeout)
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


def list_devices(timeout: float = 25.0) -> list[tuple[str, str]]:
    return [(d["serial"], d["state"]) for d in devices_detailed(timeout=timeout)]


def _physical_serial(serial: str) -> str:
    try:
        proc = run_adb(serial, ["shell", "getprop", "ro.serialno"], timeout=5.0)
        value = (proc.stdout or "").strip()
        if proc.returncode == 0 and value:
            return value
    except Exception:
        pass
    return ""


def _select_ready_serial(ready: list[dict]) -> str:
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


def resolve_serial(
    serial: str | None,
    *,
    wait_seconds: float = 0.0,
    poll_seconds: float = CONNECT_POLL_S,
) -> str:
    """Return a usable serial; optionally wait for a wireless ADB reconnect."""
    if serial:
        return serial
    env = os.environ.get("ANDROID_SERIAL")
    if env:
        return env

    deadline = time.monotonic() + max(0.0, wait_seconds)
    interval = max(0.1, poll_seconds)
    last_error: AdbError | None = None
    while True:
        remaining = deadline - time.monotonic()
        timeout = min(DEVICE_LIST_TIMEOUT_S, max(0.5, remaining)) if wait_seconds > 0 else 25.0
        try:
            all_devs = devices_detailed(timeout=timeout)
        except AdbError as exc:
            if "adb executable not found" in str(exc):
                raise
            last_error = exc
            all_devs = []

        ready = [d for d in all_devs if d["state"] == "device"]
        if ready:
            return _select_ready_serial(ready)

        found = ", ".join(f"{d['serial']}({d['state']})" for d in all_devs) or "none"
        if wait_seconds > 0:
            last_error = AdbError(f"no adb device in 'device' state after {wait_seconds:.0f}s (last found: {found})")
        else:
            last_error = AdbError(f"no adb device in 'device' state (found: {found})")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise last_error
        time.sleep(min(interval, remaining))
