# PyInstaller spec for GXR Manager (onefile).
#   pyinstaller packaging/gxr-manager.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821

datas = [
    (str(ROOT / "gxr_manager" / "server" / "web"), "gxr_manager/server/web"),
    (str(ROOT / "gxr_core" / "web_common"), "gxr_core/web_common"),
]

hiddenimports = [
    "fastapi",
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    *collect_submodules("uvicorn"),
    *collect_submodules("gxr_core"),
    *collect_submodules("gxr_manager"),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry_manager.py")],
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


exe = make_exe("gxr-manager", console=False)
cli = make_exe("gxr-manager-cli", console=True)
