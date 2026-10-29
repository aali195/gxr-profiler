"""Live terminal panel (rich) driven by SampleEvent from the Recorder."""

from __future__ import annotations

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    _RICH = True
except Exception:  # pragma: no cover
    _RICH = False

NOMINAL_CPU_MAX = 2361600


def _rollup(row: dict) -> str:
    def g(col: str) -> str:
        v = row.get(col)
        return f"{v:.1f}" if isinstance(v, (int, float)) else "--"

    cpus = [row.get(f"t_CPU{i}") for i in range(6)]
    gpus = [row.get(f"t_GPU{i}") for i in range(8)]
    cpus = [v for v in cpus if isinstance(v, (int, float))]
    gpus = [v for v in gpus if isinstance(v, (int, float))]
    cpu = f"{max(cpus):.1f}" if cpus else "--"
    gpu = f"{max(gpus):.1f}" if gpus else "--"
    status = row.get("thermal_status")
    status = f"{status:.0f}" if isinstance(status, (int, float)) else "?"
    return (
        f"status {status} | AP {g('t_AP')} | CPUmax {cpu} | GPUmax {gpu} | "
        f"LRP {g('t_LRP')} | WIFI {g('t_WIFI')} | NPU {g('t_nsp0')} | skin {g('t_skin')}"
    )


class Tui:
    def __init__(self, label: str) -> None:
        self.label = label
        self.console = Console() if _RICH else None
        self.live = None
        self.rows = 0

    def say(self, msg: str) -> None:
        if self.console:
            self.console.print(msg)
        else:
            print(msg)

    def on_sample(self, event) -> None:
        self.rows += 1
        if not (self.console and _RICH):
            return
        if self.live is None:
            self.live = Live(self._render(event.row, event.elapsed_s), console=self.console, refresh_per_second=4)
            self.live.start()
            return
        self.live.update(self._render(event.row, event.elapsed_s))

    def start(self) -> None:  # retained for API symmetry; Live starts lazily
        pass

    def stop(self) -> None:
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass

    def _render(self, row: dict, elapsed: float):
        def val(key, fmt="{:.1f}"):
            v = row.get(key)
            if isinstance(v, (int, float)):
                try:
                    return fmt.format(v)
                except Exception:
                    return str(v)
            return "--"

        def mhz(key):
            v = row.get(key)
            return f"{v / 1000:.0f}" if isinstance(v, (int, float)) else "--"

        def gb(key):
            v = row.get(key)
            return f"{v / 1048576:.1f}" if isinstance(v, (int, float)) else "--"

        cap0, cap2 = row.get("cpu_max0"), row.get("cpu_max2")
        capped = (isinstance(cap0, (int, float)) and cap0 < NOMINAL_CPU_MAX) or (
            isinstance(cap2, (int, float)) and cap2 < NOMINAL_CPU_MAX
        )
        cap_txt = Text(
            f"{mhz('cpu_max0')} / {mhz('cpu_max2')} MHz" + ("  CAPPED" if capped else ""),
            style="bold red" if capped else "bold cyan",
        )

        grid = Table(box=None, show_header=False, expand=True, pad_edge=False)
        grid.add_column(style="dim", no_wrap=True)
        grid.add_column(style="bold cyan", no_wrap=True, justify="right")
        grid.add_column(style="dim", no_wrap=True, min_width=12)
        grid.add_column(style="bold cyan", no_wrap=True, justify="right")
        grid.add_row("elapsed", f"{elapsed:.0f}s", "fan step", val("fan_step", "{:.0f}"))
        grid.add_row("thermal", val("thermal_status", "{:.0f}"), "max sev", val("thermal_max_sev", "{:.0f}"))
        grid.add_row("CPU freq", f"{mhz('f_cpu0')} / {mhz('f_cpu2')} MHz", "cap", cap_txt)
        grid.add_row("GPU clock", f"{val('g_clock', '{:.0f}')} MHz", "GPU busy", f"{val('g_busy', '{:.0f}')}%")
        grid.add_row(
            "XR fps", f"{val('xr_fps', '{:.1f}')} / {val('xr_target', '{:.0f}')}", "fan RPM", val("fan_rpm", "{:.0f}")
        )
        grid.add_row(
            "Wi-Fi tx/rx",
            f"{val('wifi_tx', '{:.0f}')}/{val('wifi_rx', '{:.0f}')} Mbps",
            "signal",
            val("wifi_rssi", "{:.0f}"),
        )
        grid.add_row(
            "battery",
            f"{val('batt_temp', '{:.1f}')}°C {val('batt_level', '{:.0f}')}%",
            "free mem",
            f"{gb('mem_available')} GB",
        )

        title = Text(_rollup(row), style="bold cyan")
        return Panel(
            Group(title, grid, Text(f"rows: {self.rows}", style="dim")),
            title=f"GXR Profiler :: {self.label}",
            border_style="cyan",
        )
