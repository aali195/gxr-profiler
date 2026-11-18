"""Device settings snapshot, toggle verification and local audit log."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..core.adb import CONNECT_POLL_S, CONNECT_WAIT_S, AdbClient, RealAdb, resolve_serial
from ..core.paths import default_reports_dir
from ..core.settings import (
    SETTING_KIND_CHOICE,
    SETTING_SECTIONS,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    SettingDefinition,
    get_setting_definition,
    public_setting,
)
from .action_log import append_action_log

log = logging.getLogger(__name__)

_FAILURE_MARKERS = (
    "error",
    "exception",
    "permission denied",
    "bad arguments",
    "invalid",
    "unknown",
    "must be root",
)


class SettingsService:
    def __init__(
        self,
        serial: str | None = None,
        reports_dir: str | None = None,
        adb_factory: Callable[..., AdbClient] = RealAdb,
    ) -> None:
        self.serial = serial
        self.reports_dir = reports_dir or str(Path(default_reports_dir()) / "settings")
        self.adb_factory = adb_factory
        self.lock = threading.Lock()

    def _adb(self) -> AdbClient:
        return self.adb_factory(
            serial=resolve_serial(self.serial, wait_seconds=CONNECT_WAIT_S, poll_seconds=CONNECT_POLL_S)
        )

    @staticmethod
    def _output(proc) -> str:
        return ((proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")).strip()

    @staticmethod
    def _failed(text: str, returncode: int = 0) -> bool:
        low = (text or "").lower()
        return returncode != 0 or any(marker in low for marker in _FAILURE_MARKERS)

    def _read_setting(self, adb: AdbClient, definition: SettingDefinition) -> dict:
        values: dict[str, str] = {}
        errors: list[str] = []
        for key, command in definition.read_commands:
            try:
                proc = adb.run(["shell", command], timeout=10.0)
                text = self._output(proc)
                if self._failed(text, proc.returncode):
                    errors.append(f"{command}: {text or 'failed'}")
                values[key] = text
            except Exception as exc:
                errors.append(f"{command}: {exc}")
                values[key] = ""
        if errors:
            values["_error"] = "; ".join(errors)
        status = definition.reader(values)
        status["checked"] = not errors
        return status

    def snapshot(self) -> dict:
        with self.lock:
            adb = self._adb()
            sections = []
            for section in SETTING_SECTIONS:
                items = []
                for setting_id in section["settings"]:
                    definition = get_setting_definition(setting_id)
                    status = self._read_setting(adb, definition)
                    public = public_setting(definition)
                    if not status.get("warning"):
                        status["warning"] = public.get("warning", "")
                    items.append({**public, **status})
                sections.append({**section, "settings": items})
            return {"sections": sections, "checked_at": datetime.now(UTC).isoformat()}

    def _run_commands(self, adb: AdbClient, commands: tuple[str, ...]) -> tuple[bool, list[str]]:
        output = []
        ok = True
        for command in commands:
            try:
                proc = adb.run(["shell", command], timeout=15.0)
                text = self._output(proc)
                output.append(f"$ {command}" + (f"\n{text}" if text else ""))
                if self._failed(text, proc.returncode):
                    ok = False
                    break
            except Exception as exc:
                output.append(f"$ {command}\n{exc}")
                ok = False
                break
        return ok, output

    def set_enabled(self, setting_id: str, enabled: bool) -> dict:
        definition = get_setting_definition(setting_id)
        if definition.kind == SETTING_KIND_CHOICE:
            raise ValueError(f"setting requires a value: {setting_id}")
        commands = definition.apply_commands if enabled else definition.revert_commands
        with self.lock:
            adb = self._adb()
            command_ok, output = self._run_commands(adb, commands)
            status = self._read_setting(adb, definition)
            expected = STATUS_ACTIVE if enabled else STATUS_INACTIVE
            ok = command_ok and status["state"] == expected
            result = {
                "ok": ok,
                "setting_id": definition.id,
                "enabled": enabled,
                "commands": list(commands),
                "output": "\n".join(output),
                "state": status,
            }
            append_action_log(
                self.reports_dir,
                "setting-actions.jsonl",
                {
                    "ok": ok,
                    "setting_id": definition.id,
                    "enabled": enabled,
                    "commands": list(commands),
                    "output": result["output"],
                    "state": status.get("state"),
                },
            )
            return result

    def set_value(self, setting_id: str, value: str) -> dict:
        definition = get_setting_definition(setting_id)
        if definition.kind != SETTING_KIND_CHOICE:
            raise ValueError(f"setting does not accept a value: {setting_id}")
        option = next((item for item in definition.options if item.value == value), None)
        if option is None:
            raise ValueError(f"invalid value for {setting_id}: {value}")
        with self.lock:
            adb = self._adb()
            command_ok, output = self._run_commands(adb, option.commands)
            status = self._read_setting(adb, definition)
            ok = command_ok and status.get("value") == option.value and status.get("state") == STATUS_ACTIVE
            result = {
                "ok": ok,
                "setting_id": definition.id,
                "value": option.value,
                "label": option.label,
                "commands": list(option.commands),
                "output": "\n".join(output),
                "state": status,
            }
            append_action_log(
                self.reports_dir,
                "setting-actions.jsonl",
                {
                    "ok": ok,
                    "setting_id": definition.id,
                    "value": option.value,
                    "label": option.label,
                    "commands": list(option.commands),
                    "output": result["output"],
                    "state": status.get("state"),
                },
            )
            return result
