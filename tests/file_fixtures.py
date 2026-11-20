"""Fake ADB helpers for file-explorer tests."""

from __future__ import annotations

import io
import shlex
from types import SimpleNamespace

LS_SAMPLE = """total 12
drwxrws--- 2 u0_a236 media_rw 3452 2026-11-16 22:16 Alarms
-rwxrwx--- 1 u0_a236 media_rw 241898 2026-10-19 20:52 Galaxy XR Haptics.zip
lrwxrwxrwx 1 root root 21 2008-12-31 15:00 shortcut -> /sdcard/Download
"""


class FakeProc:
    def __init__(self, data: bytes = b"", returncode: int = 0):
        self.stdout = io.BytesIO(data)
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


class FakeFileAdb:
    def __init__(
        self,
        listing: str = LS_SAMPLE,
        data: bytes = b"file-bytes",
        root_ok: bool = True,
        permission_denied: bool = False,
    ):
        self.listing = listing
        self.data = data
        self.root_ok = root_ok
        self.permission_denied = permission_denied
        self.shell_calls: list[str] = []
        self.run_calls: list[list[str]] = []
        self.exec_calls: list[list[str]] = []
        self.dirs = {"/sdcard", "/storage/emulated/0", "/data/local/tmp"}
        self.files: dict[str, int] = {}
        self.links: dict[str, str] = {}
        self.fail_mv = False
        self.fail_push = False
        self.push_size_override: int | None = None

    @staticmethod
    def _command(script: str) -> str:
        if script.startswith("su -c "):
            return shlex.split(script)[-1]
        return script

    @classmethod
    def _path(cls, script: str) -> str:
        return shlex.split(cls._command(script))[-1]

    def shell(self, script: str, timeout: float = 25.0) -> str:
        self.shell_calls.append(script)
        script = script.replace("'\"'\"'", "'")
        if "su -c id" in script:
            return "uid=0(root) gid=0(root)\n" if self.root_ok else "uid=2000(shell)\n"
        if "ls -lAN" in script:
            if self.permission_denied:
                return "ls: /private: Permission denied\n"
            return self.listing
        if "stat -Lc" in script or "stat -c" in script:
            path = self._path(script)
            follow = "stat -Lc" in script
            if path in self.links:
                if not follow:
                    return f"symbolic link|{len(self.links[path])}|1760000000\n"
                path = self.links[path]
            if path in self.dirs:
                return "directory|4096|1760000000\n"
            if path in self.files:
                return f"regular file|{self.files[path]}|1760000000\n"
            return "stat: 'x': No such file or directory\n"
        if "mv " in script:
            if self.fail_mv:
                return "mv: Permission denied\n"
            source, target = shlex.split(self._command(script))[-2:]
            if source in self.dirs:
                self.dirs.discard(source)
                self.dirs.add(target)
            elif source in self.files:
                self.files[target] = self.files.pop(source)
            elif source in self.links:
                self.links[target] = self.links.pop(source)
            return ""
        if "rm -rf" in script or "rm -f" in script:
            path = self._path(script)
            self.files.pop(path, None)
            self.links.pop(path, None)
            self.dirs.discard(path)
            return ""
        if "mkdir " in script:
            path = self._path(script)
            if path in self.dirs:
                return "mkdir: 'x': File exists\n"
            self.dirs.add(path)
            return ""
        return ""

    def run(self, args, timeout: float = 25.0):
        self.run_calls.append(list(args))
        if args[0] == "push":
            if self.fail_push:
                return SimpleNamespace(stdout="", stderr="adb: error: failed to copy\n", returncode=1)
            local, remote = args[1], args[2]
            size = len(open(local, "rb").read())
            self.files[remote] = self.push_size_override if self.push_size_override is not None else size
            return SimpleNamespace(stdout="1 file pushed\n", stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    def exec_out(self, args):
        self.exec_calls.append(list(args))
        return FakeProc(self.data, 0)


def quote_path(path: str) -> str:
    return shlex.quote(path)
