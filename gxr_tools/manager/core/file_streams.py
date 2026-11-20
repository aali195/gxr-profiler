"""Binary download streams for the file explorer.

``adb pull`` and text-mode shell calls cannot read root-only paths without
leaving a copy on the local disk.  ``adb exec-out`` gives us a binary pipe that
works for both root and non-root reads.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterator

from gxr_tools.core.adb import AdbClient, AdbError

CHUNK_BYTES = 64 * 1024


class DownloadStream:
    """Iterate a remote file and always clean up the adb process."""

    def __init__(self, proc) -> None:
        self._proc = proc
        self._first = b""
        self._closed = False

    def prime(self) -> bytes:
        """Read the first chunk so failures surface before headers are sent."""
        if self._proc.stdout is None:
            self._first = b""
        else:
            self._first = self._proc.stdout.read(CHUNK_BYTES) or b""
        return self._first

    def __iter__(self) -> Iterator[bytes]:
        try:
            if self._first:
                yield self._first
            if self._proc.stdout is not None:
                while True:
                    chunk = self._proc.stdout.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._proc.stdout is not None:
            try:
                self._proc.stdout.close()
            except Exception:
                pass
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
        else:
            try:
                self._proc.wait()
            except Exception:
                pass


def open_download(adb: AdbClient, path: str, root: bool) -> DownloadStream:
    """Start a binary cat of ``path`` and validate the first chunk."""
    if root:
        args = ["exec-out", "su", "-c", f"cat -- {shlex.quote(path)}"]
    else:
        args = ["exec-out", "sh", "-c", f"cat -- {shlex.quote(path)}"]
    try:
        proc = adb.exec_out(args)
    except OSError as exc:
        raise AdbError(f"could not start adb: {exc}") from exc
    stream = DownloadStream(proc)
    first = stream.prime()
    if not first:
        code = proc.poll()
        if code not in (None, 0):
            stream.close()
            raise AdbError(f"could not read {path}")
    return stream
