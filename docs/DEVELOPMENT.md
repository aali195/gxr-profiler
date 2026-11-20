# Development, testing & packaging

[Documentation home](README.md) | [Profiler guide](PROFILER.md) | [Manager guide](MANAGER.md) | [CLI](CLI.md) | [Commands](COMMANDS.md)

Quick use of the packaged apps is covered in the root [README](../README.md). This page is for
running the **GXR Tools** suite from source, understanding the layout, testing changes and building
the four executables.

## Source setup

Requirements:

- Windows + Python 3.11+
- `adb` on PATH, set via `ADB`, or placed next to the executable (a `platform-tools` subfolder also works)
- Headset paired over wireless ADB

```powershell
pip install -e ".[dev]"
gxr-profiler ui
gxr-manager ui
```

Without installing, run `python -m gxr_tools.profiler ...` or
`python -m gxr_tools.manager.cli.app ...`.

## Architecture

```text
gxr_tools/
  __init__.py    suite version and identity
  core/          shared ADB, device/parsers, paths/fs/schema, recording state, server/web primitives
  profiler/
    cli/         Typer commands (record, runs, report, ui, devices)
    __main__.py  python -m gxr_tools.profiler
    core/        run models
    capture/     Recorder lifecycle, logcat stream, media/process samplers, meta/writer
    runs/        RunStore: list/load/rename/delete runs
    report/      chart spec, series shaping, self-contained offline app export
    server/      profiler app factory, recording manager, export service, routers/, ECharts SPA modules
  manager/
    cli/         manager UI/status commands
    core/        package/APK/settings/diagnostics helpers, file path/entry/stream rules
    server/      manager app factory, apps/installer/settings/diagnostics/files services, routers, SPA modules
packaging/       PyInstaller specs + entry points for both apps
tests/           pytest suite with FakeAdb
```

## Tests and linting

```powershell
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
```

The tests use a fake ADB device and do not require a connected headset. `pytest` covers parsers,
recording/storage, both web route surfaces, export behaviour, package parsing/actions and UI asset
checks. The Apps/Installer/Settings tests use fake `pm`/`dumpsys`/`device_config` output and never
touch a real device.

## Building the executables

```powershell
pip install -e ".[packaging]"
pyinstaller packaging/gxr-profiler.spec --noconfirm
pyinstaller packaging/gxr-manager.spec --noconfirm
```

This produces:

```text
dist/gxr-profiler.exe       profiler windowed UI
dist/gxr-profiler-cli.exe   profiler terminal/CLI
dist/gxr-manager.exe        manager windowed UI
dist/gxr-manager-cli.exe    manager terminal/CLI
```

The onefile builds bundle Python, FastAPI, pywebview and their web assets. The profiler also bundles
pandas/ECharts. Both need `adb` on PATH and the WebView2 runtime for the native window (`--browser`
is a fallback). Keep both apps in the same folder so they share `recording.json` and the manager can
block device changes while the profiler records. The profiler also marks CLI recordings, so
`gxr-profiler-cli.exe record` blocks manager actions the same way.

When invoked from a terminal with arguments, the windowed exes attach to the parent console.
`runs/` and `reports/` are created next to the profiler exe; manager staging/logs are next to the
manager exe. The exe folder must be writable, or pass `--runs-dir` / `--out`.

## CI and releases

`.github/workflows/build.yml` runs on:

- pushes to `main`
- pull requests targeting `main`
- manual dispatch
- `v*` tag pushes

The `build-test` job runs Ruff formatting/linting, JavaScript syntax checks and pytest on Python 3.11 and 3.13.

The `release` job runs only for `v*` tags after tests pass. It:

1. Builds both profiler executables and both manager executables.
2. Verifies all four files and runs both CLI help commands as a smoke test.
3. Writes `dist/SHA256SUMS.txt`.
4. Uploads a `gxr-tools-windows` workflow artifact.
5. Creates or updates the **GXR Tools** GitHub release using the tag name.

Create a release by pushing a tag such as `v2.1.0`.
