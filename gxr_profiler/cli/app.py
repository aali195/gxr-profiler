"""GXR Profiler command-line interface (Typer)."""

from __future__ import annotations

import typer

from ..core.adb import AdbError, RealAdb, RunNotFound, list_devices, resolve_serial
from ..core.columns import TEMP_SENSORS
from ..core.models import RunConfig
from ..core.paths import default_runs_dir

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Read-only thermal/performance profiler for Galaxy XR (SM-I610).",
)


def _fail(msg: str, code: int = 1):
    typer.secho(f"error: {msg}", fg="red", err=True)
    raise typer.Exit(code)


@app.command()
def record(
    name: str = typer.Option(..., "--name", "-n", help="run name, e.g. before / after"),
    duration: float = typer.Option(0.0, "--duration", "-d", help="seconds (0 = until Ctrl-C)"),
    interval: float = typer.Option(1.0, "--interval", help="poll interval seconds"),
    out: str | None = typer.Option(None, "--out", help="output directory (default: next to the exe)"),
    cooldown: float | None = typer.Option(None, "--cooldown", help="wait until the sensor is below this temperature"),
    sensor: str = typer.Option("AP", "--sensor", help="sensor for --cooldown"),
    cooldown_max_wait: float = typer.Option(
        0.0, "--cooldown-max-wait", help="max seconds to wait before starting anyway"
    ),
    notes: str = typer.Option("", "--notes", help="free-form note stored in meta.json"),
    root: bool = typer.Option(
        False,
        "--root",
        help="also read fan RPM/PWM + active panel (read-only su)",
    ),
    sensors: bool = typer.Option(False, "--sensors", help="also sample dumpsys sensorservice summary"),
    processes: bool = typer.Option(
        True, "--processes/--no-processes", help="snapshot processes (all non-kernel by default)"
    ),
    processes_interval: float = typer.Option(10.0, "--processes-interval"),
    processes_top: int = typer.Option(0, "--processes-top", help="max processes; 0 = all non-kernel"),
    processes_kernel: bool = typer.Option(False, "--processes-kernel", help="include kernel threads"),
    process_io: bool = typer.Option(False, "--process-io", help="read per-process disk I/O (requires --root)"),
    sensors_interval: float = typer.Option(10.0, "--sensors-interval"),
    media_interval: float = typer.Option(30.0, "--media-interval"),
    state_interval: float = typer.Option(5.0, "--state-interval"),
    radio_interval: float = typer.Option(30.0, "--radio-interval"),
    logcat: bool = typer.Option(True, "--logcat/--no-logcat", help="stream logcat for temps/throttle/fan"),
    serial: str | None = typer.Option(None, "--serial", help="adb device serial (auto-detected)"),
) -> None:
    """Record a run (logcat stream + 1 Hz poll)."""
    from ..capture.recorder import Recorder
    from ..tui import Tui

    try:
        serial = resolve_serial(serial)
    except AdbError as exc:
        _fail(str(exc))

    if sensor not in TEMP_SENSORS:
        _fail(f"unknown cooldown sensor '{sensor}'; choose {', '.join(TEMP_SENSORS)}")
    if cooldown_max_wait < 0:
        _fail("--cooldown-max-wait cannot be negative")
    if interval <= 0:
        _fail("--interval must be greater than zero")
    if duration < 0:
        _fail("--duration cannot be negative")
    if cooldown is not None and cooldown < 0:
        _fail("--cooldown cannot be negative")
    if process_io and not root:
        _fail("--process-io requires --root")
    if processes_top < 0:
        _fail("--processes-top cannot be negative")

    cfg = RunConfig(
        name=name,
        out_dir=out or default_runs_dir(),
        duration=duration,
        interval=interval,
        cooldown_below=cooldown,
        cooldown_sensor=sensor,
        cooldown_max_wait=cooldown_max_wait,
        notes=notes,
        logcat=logcat,
        root=root,
        sensors=sensors,
        sensors_interval=sensors_interval,
        processes=processes,
        processes_interval=processes_interval,
        processes_top=processes_top,
        processes_kernel=processes_kernel,
        process_io=process_io,
        media_interval=media_interval,
        state_interval=state_interval,
        radio_interval=radio_interval,
    )
    adb = RealAdb(serial=serial)
    tui = Tui(name)
    try:
        rec = Recorder(adb, cfg, on_sample=tui.on_sample, on_status=tui.say)
    except (ValueError, OSError) as exc:
        _fail(str(exc))
    tui.say(f"GXR Profiler recording '{name}' on {serial}")
    try:
        rec.run()
    except KeyboardInterrupt:
        tui.say("Stopping...")
    except AdbError as exc:
        _fail(str(exc))
    finally:
        tui.stop()
    typer.secho(f"Saved {rec.row_count} rows -> {rec.writer.csv_path}", fg="green")


@app.command()
def runs(runs_dir: str | None = typer.Option(None, "--runs-dir")) -> None:
    """List recorded runs."""
    from ..runs.store import RunStore

    runs_dir = runs_dir or default_runs_dir()
    store = RunStore(runs_dir)
    items = store.list()
    if not items:
        typer.echo(f"no runs in {runs_dir}")
        return
    for r in items:
        flags = []
        if r.power_saving is not None:
            flags.append("power-save" if r.power_saving else "no-power-save")
        if r.hand_tracking is not None:
            flags.append("hand" if r.hand_tracking else "no-hand")
        if r.panel:
            flags.append(r.panel)
        typer.echo(f"{r.label:<20} {r.rows:>6} rows  {r.started[:19]:<19}  {' '.join(flags)}")


@app.command()
def report(
    labels: list[str] = typer.Argument(..., help="one or more run labels"),
    out: str | None = typer.Option(None, "--out", help="output html path"),
    runs_dir: str | None = typer.Option(None, "--runs-dir"),
) -> None:
    """Build a static HTML report (compare 2+ runs, or view one)."""
    from ..report.static import generate

    try:
        path = generate(labels, runs_dir=runs_dir or default_runs_dir(), out=out)
    except (RunNotFound, OSError, ValueError) as exc:
        _fail(str(exc))
    typer.secho(f"report written: {path}", fg="green")


@app.command()
def devices() -> None:
    """List adb devices."""
    try:
        devices = list_devices()
    except AdbError as exc:
        _fail(str(exc))
    for serial, state in devices:
        typer.echo(f"{serial}\t{state}")


@app.command()
def ui(
    port: int = typer.Option(8765, "--port"),
    browser: bool = typer.Option(False, "--browser", help="open in the default browser instead of a native window"),
    runs_dir: str | None = typer.Option(None, "--runs-dir"),
    serial: str | None = typer.Option(None, "--serial"),
) -> None:
    """Launch the viewer/recorder app."""
    from ..server.app import run_ui

    run_ui(port=port, browser=browser, runs_dir=runs_dir or default_runs_dir(), serial=serial)


# aliases
app.command("compare", hidden=True)(report)
app.command("list", hidden=True)(runs)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        app()
    else:
        app(args=argv)


if __name__ == "__main__":
    main()
