# Development, testing & packaging

Quick use of the packaged UI is covered in the root [README](../README.md). This page is for
running from source, understanding the layout, testing changes and building executables.

## Source setup

Requirements:

- Windows + Python 3.11+
- `adb` on PATH (or set `ADB`)
- Headset paired over wireless ADB

```powershell
pip install -e ".[dev]"
gxr-profiler ui
```

Without installing, run `python -m gxr_profiler ...`.

## Architecture

```text
gxr_profiler/
  cli/       Typer commands (record, runs, report, ui, devices)
  core/      column registry, schema/labels derived from it, adb client, models, fs/paths
    parsers/ logcat, thermal, media, audio, radios, cameras, sensors, process, system, display
    device/  props, system, display/panel, audio, root snapshot
  capture/   Recorder lifecycle, logcat stream, pollers, media/process samplers, meta/writer
  runs/      RunStore: list/load/rename/delete runs
  report/    chart spec, series shaping, self-contained offline app export
  server/    app factory, deps, recording manager, export service, routers/, ECharts SPA
packaging/   PyInstaller onefile spec + entry point
tests/       pytest suite with a FakeAdb
```

## Tests and linting

```powershell
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
```

The tests use a fake ADB device and do not require a connected headset. `pytest` covers parsers,
recording/storage, the web routes, export behaviour and UI asset checks.

## Building the executables

```powershell
pip install -e ".[packaging]"
pyinstaller packaging/gxr-profiler.spec --noconfirm
```

This produces:

```text
dist/gxr-profiler.exe       windowed UI build
dist/gxr-profiler-cli.exe   terminal/CLI build
```

The onefile build bundles Python, pandas, FastAPI, pywebview, the web app and ECharts. It still
needs `adb` on PATH and the WebView2 runtime for the native window (`--browser` is a fallback).

When invoked from a terminal with arguments, `gxr-profiler.exe` attaches to the parent console, so
`--help`, `record`, `report`, `runs` and `devices` work like the console build. `runs/` and
`reports/` are created next to the exe; when running from source they stay relative to the current
working directory. The exe folder must be writable, or pass `--runs-dir` / `--out`.

## CI and releases

`.github/workflows/build.yml` runs on:

- pushes to `main`
- pull requests targeting `main`
- manual dispatch
- `v*` tag pushes

The `build-test` job runs Ruff formatting/linting and pytest on Python 3.11, 3.12 and 3.13.

The `release` job runs only for `v*` tags after tests pass. It:

1. Builds both `gxr-profiler.exe` and `gxr-profiler-cli.exe`.
2. Verifies both files and runs the CLI help as a smoke test.
3. Writes `dist/SHA256SUMS.txt`.
4. Uploads a workflow artifact.
5. Creates or updates the GitHub release using the tag name.

Create a release by pushing a tag such as `v0.3.0`.
