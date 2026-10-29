"""PyInstaller entry point (absolute import; works as __main__).

The packaged GUI exe opens the viewer when double-clicked; the console exe
(`gxr-profiler-cli.exe`) keeps the normal Typer command line.
"""

from __future__ import annotations

import sys
from pathlib import Path

from gxr_profiler.cli.app import main


def _is_ui_launch(argv: list[str], executable: str) -> bool:
    return len(argv) == 1 and "cli" not in Path(executable).stem.lower()


def _attach_parent_console() -> None:
    """Let the windowed exe behave like a console tool when invoked with args."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        if not ctypes.windll.kernel32.AttachConsole(-1):
            return
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
    except Exception:
        pass


def _show_error(exc: BaseException) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"GXR Profiler could not start the app:\n\n{exc}\n\n"
            "Install the Microsoft Edge WebView2 runtime or run gxr-profiler-cli.exe ui --browser.",
            "GXR Profiler",
            0x10,
        )
    except Exception:
        pass


if __name__ == "__main__":
    if _is_ui_launch(sys.argv, sys.argv[0]):
        try:
            main(["ui"])
        except Exception as exc:
            _show_error(exc)
            raise
    else:
        _attach_parent_console()
        main()
