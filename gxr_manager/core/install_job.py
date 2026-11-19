"""Background execution helpers for staged APK/OBB installs."""

from __future__ import annotations

import copy
import re
import shlex
import threading
import uuid

from ..server.action_log import append_action_log
from .install_files import (
    INSTALL_TIMEOUT_S,
    OUTPUT_LIMIT,
    InstallStepError,
    StagedInstallFile,
    clean_output,
    install_failed,
    now_iso,
    push_timeout,
)


class InstallJobMixin:
    def active(self) -> bool:
        with self._job_lock:
            return bool(self._job and self._job.get("status") == "running")

    def start(
        self,
        items: list[str],
        obb_packages: dict[str, str] | None = None,
        options: dict | None = None,
        confirm: bool = False,
    ) -> dict:
        if not confirm:
            raise ValueError("confirmation is required")
        if self.busy_check and self.busy_check():
            raise PermissionError("cannot install packages while a recording is in progress")
        with self._job_lock:
            if self._job and self._job.get("status") == "running":
                raise RuntimeError("an install is already running")
        plan = self.preview(items, obb_packages, options)
        if plan["errors"]:
            raise ValueError("; ".join(plan["errors"]))
        steps: list[dict] = []
        actions: list[tuple[str, str, dict]] = []
        for index, group in enumerate(plan["groups"]):
            step_id = f"install-{index}"
            steps.append(
                {
                    "id": step_id,
                    "label": group["label"] + (f" ({group['apk_count']} APKs)" if group["apk_count"] > 1 else ""),
                    "status": "pending",
                    "output": "",
                }
            )
            actions.append((step_id, "install", group))
            if group["package"]:
                verify_id = f"verify-{index}"
                steps.append(
                    {
                        "id": verify_id,
                        "label": "Verify " + group["package"],
                        "status": "pending",
                        "output": "",
                    }
                )
                actions.append((verify_id, "verify_package", group))
        for index, obb in enumerate(plan["obb"]):
            step_id = f"push-{index}"
            steps.append(
                {
                    "id": step_id,
                    "label": "Push " + obb["name"],
                    "status": "pending",
                    "output": "",
                }
            )
            actions.append((step_id, "push_obb", obb))
            verify_id = f"verify-obb-{index}"
            steps.append(
                {
                    "id": verify_id,
                    "label": "Verify " + obb["name"],
                    "status": "pending",
                    "output": "",
                }
            )
            actions.append((verify_id, "verify_obb", obb))
        job = {
            "id": uuid.uuid4().hex,
            "status": "running",
            "step": "Preparing",
            "steps": steps,
            "output": "",
            "error": "",
            "started_at": now_iso(),
            "finished_at": "",
            "result": {},
        }
        records = self._records_for(plan)
        with self._job_lock:
            if self._job and self._job.get("status") == "running":
                raise RuntimeError("an install is already running")
            self._job = job
        thread = threading.Thread(
            target=self._run_job,
            args=(job["id"], plan, actions, records),
            name="gxr-install",
            daemon=True,
        )
        thread.start()
        return self.status(job["id"])

    def _records_for(self, plan: dict) -> list[StagedInstallFile]:
        ids: list[str] = []
        for group in plan["groups"]:
            ids.extend(item["id"] for item in group["files"])
        ids.extend(item["id"] for item in plan["obb"])
        with self._lock:
            records = [self._staged[item_id] for item_id in dict.fromkeys(ids) if item_id in self._staged]
        if len(records) != len(dict.fromkeys(ids)):
            raise ValueError("one or more staged files have expired; add them again")
        return records

    def _set_step(self, job_id: str, step_id: str, status: str, output: str | None = None) -> None:
        with self._job_lock:
            if not self._job or self._job["id"] != job_id:
                return
            for step in self._job["steps"]:
                if step["id"] == step_id:
                    step["status"] = status
                    if output is not None:
                        step["output"] = clean_output(output)
                    if status == "running":
                        self._job["step"] = step["label"]
                    break

    def _finish(self, job_id: str, status: str, error: str = "", result: dict | None = None) -> None:
        with self._job_lock:
            if not self._job or self._job["id"] != job_id:
                return
            self._job["status"] = status
            self._job["error"] = clean_output(error)
            self._job["finished_at"] = now_iso()
            if result is not None:
                self._job["result"] = result
            if status == "done":
                self._job["step"] = "Finished"
            elif status == "error":
                self._job["step"] = "Failed"

    def _require_not_recording(self) -> None:
        if self.busy_check and self.busy_check():
            raise InstallStepError("a recording started; the install was stopped")

    def _run_job(
        self,
        job_id: str,
        plan: dict,
        actions: list[tuple[str, str, dict]],
        records: list[StagedInstallFile],
    ) -> None:
        output_parts: list[str] = []
        current_step = ""
        try:
            adb = self._adb()
            with self.device_lock:
                for step_id, kind, payload in actions:
                    self._require_not_recording()
                    current_step = step_id
                    self._set_step(job_id, step_id, "running")
                    if kind == "install":
                        proc = adb.run(payload["args"], timeout=INSTALL_TIMEOUT_S)
                        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                        if install_failed(output, proc.returncode):
                            raise InstallStepError(
                                clean_output(output) or f"adb install exited with code {proc.returncode}"
                            )
                        output_parts.append(f"{payload['label']}:\n{clean_output(output)}")
                        self._set_step(job_id, step_id, "done", output)
                    elif kind == "verify_package":
                        package = payload["package"]
                        check = adb.shell("pm path " + shlex.quote(package), timeout=15.0)
                        if "package:" not in check:
                            raise InstallStepError(f"{package} was not found after install")
                        notes = [check.strip()]
                        expected_version = payload.get("version_code")
                        if expected_version is not None:
                            detail = adb.shell("dumpsys package " + shlex.quote(package), timeout=20.0)
                            match = re.search(r"\bversionCode=(\d+)", detail)
                            if not match:
                                raise InstallStepError(f"{package}: could not verify versionCode {expected_version}")
                            found_version = int(match.group(1))
                            if found_version != int(expected_version):
                                raise InstallStepError(
                                    f"{package} reports versionCode {found_version}, expected {expected_version}"
                                )
                            notes.append(f"versionCode={found_version}")
                        self._set_step(job_id, step_id, "done", "\n".join(notes))
                    elif kind == "push_obb":
                        adb.shell("mkdir -p " + shlex.quote(payload["remote_dir"]), timeout=15.0)
                        proc = adb.run(
                            ["push", payload["local_path"], payload["remote_path"]],
                            timeout=push_timeout(int(payload.get("size") or 0)),
                        )
                        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
                        if proc.returncode != 0:
                            raise InstallStepError(
                                clean_output(output) or f"adb push exited with code {proc.returncode}"
                            )
                        output_parts.append(f"{payload['name']}:\n{clean_output(output)}")
                        self._set_step(job_id, step_id, "done", output)
                    elif kind == "verify_obb":
                        check = adb.shell(
                            "stat -c %s " + shlex.quote(payload["remote_path"]),
                            timeout=15.0,
                        )
                        try:
                            remote_size = int(check.strip().splitlines()[-1])
                        except (ValueError, IndexError):
                            raise InstallStepError(f"{payload['name']}: could not verify the remote file") from None
                        if remote_size != int(payload.get("size") or 0):
                            raise InstallStepError(
                                f"{payload['name']}: device has {remote_size} bytes, expected {payload['size']}"
                            )
                        self._set_step(job_id, step_id, "done", f"{remote_size} bytes")
            packages = [group["package"] for group in plan["groups"] if group["package"]]
            packages.extend(item["package"] for item in plan["obb"] if item["package"])
            packages = list(dict.fromkeys(packages))
            self._remove_items(records)
            self._log_job(job_id, plan, True, "", "\n\n".join(output_parts))
            self._finish(
                job_id,
                "done",
                result={
                    "packages": packages,
                    "apk_count": sum(group["apk_count"] for group in plan["groups"]),
                    "obb_count": len(plan["obb"]),
                },
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            if current_step:
                self._set_step(job_id, current_step, "error", message)
            self._log_job(job_id, plan, False, message, "\n\n".join(output_parts))
            self._finish(job_id, "error", message)

    def _log_job(self, job_id: str, plan: dict, ok: bool, error: str, output: str) -> None:
        files = []
        for group in plan["groups"]:
            for item in group["files"]:
                files.append(
                    {
                        "name": item["name"],
                        "size": item["size"],
                        "sha256": item["sha256"],
                        "package": item["package"],
                        "kind": "apk",
                    }
                )
        for item in plan["obb"]:
            files.append(
                {
                    "name": item["name"],
                    "size": item["size"],
                    "sha256": item["sha256"],
                    "package": item["package"],
                    "kind": "obb",
                }
            )
        packages = [group["package"] for group in plan["groups"] if group["package"]]
        packages.extend(item["package"] for item in plan["obb"] if item["package"])
        append_action_log(
            self.reports_dir,
            "app-actions.jsonl",
            {
                "ok": ok,
                "package": ", ".join(dict.fromkeys(packages)),
                "action": "install",
                "command": "\n".join(
                    [group["command"] for group in plan["groups"]]
                    + [item["mkdir_command"] + "\n" + item["command"] for item in plan["obb"]]
                ),
                "output": clean_output(output)[-OUTPUT_LIMIT:],
                "error": error,
                "job_id": job_id,
                "files": files,
                "obb_count": len(plan["obb"]),
                "options": plan["options"],
            },
        )

    def status(self, job_id: str) -> dict:
        with self._job_lock:
            if not self._job or self._job["id"] != job_id:
                raise LookupError("install job not found")
            return copy.deepcopy(self._job)
