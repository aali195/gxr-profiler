"""GXR Manager command-line interface."""

from __future__ import annotations

import typer

from gxr_core.adb import AdbError, list_devices
from gxr_core.recording_state import read_state

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Device management tools for Galaxy XR.",
)


@app.command()
def ui(
    port: int = typer.Option(8766, "--port"),
    browser: bool = typer.Option(False, "--browser", help="open in the default browser"),
    serial: str | None = typer.Option(None, "--serial", help="adb device serial (auto-detected)"),
) -> None:
    """Launch the manager UI."""
    from ..server.app import run_ui

    run_ui(port=port, browser=browser, serial=serial)


@app.command()
def status() -> None:
    """Show connected devices and whether the profiler is recording."""
    try:
        devices = list_devices()
    except AdbError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for serial, state in devices:
        typer.echo(f"{serial}\t{state}")
    recording = read_state()
    if recording.get("active"):
        typer.echo(f"profiler recording: {recording.get('label') or 'yes'}")
    elif recording.get("stale"):
        typer.echo("profiler recording state is stale")
    else:
        typer.echo("profiler recording: no")


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        app()
    else:
        app(args=argv)


if __name__ == "__main__":
    main()
