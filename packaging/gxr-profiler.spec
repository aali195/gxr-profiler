# PyInstaller spec (onefile).
#   pip install pyinstaller
#   pyinstaller packaging/gxr-profiler.spec
#
# Produces dist/gxr-profiler.exe. On Windows the native window needs the WebView2
# runtime; otherwise pass `--browser`.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821

datas = [(str(ROOT / "gxr_profiler" / "server" / "web"), "gxr_profiler/server/web")]

hiddenimports = [
    "pandas",
    "numpy",
    "fastapi",
    "orjson",
    "rich",
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    *collect_submodules("uvicorn"),
    *collect_submodules("gxr_profiler"),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["plotly", "matplotlib", "scipy", "pytest", "coverage", "IPython", "jupyter"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821


def make_exe(name, console):  # noqa: F821
    return EXE(  # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )


# Double-clicking gxr-profiler.exe opens the UI without a console. gxr-profiler-cli.exe
# remains the terminal entry point for record/report/runs/devices.
exe = make_exe("gxr-profiler", console=False)
cli = make_exe("gxr-profiler-cli", console=True)

