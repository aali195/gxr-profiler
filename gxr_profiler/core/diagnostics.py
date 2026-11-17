"""Turn a diagnostics snapshot into human-readable findings.

This is intentionally conservative: logs can show a crash without proving a
cause, and a hot headset can be a symptom rather than a trigger.  Issues keep
the raw evidence and describe what the evidence does and does not mean.
"""

from __future__ import annotations

import re

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}


def analyze_report(report: dict) -> list[dict]:
    annotate_crashes(report)
    issues: list[dict] = []
    crashes = report.get("crashes") or []
    systemui_hwui = [c for c in crashes if is_systemui_hwui_race(c)]
    other_crashes = [c for c in crashes if c not in systemui_hwui]

    if systemui_hwui:
        evidence = []
        for crash in systemui_hwui:
            evidence.append(_crash_summary(crash))
            for frame in (crash.get("frames") or [])[:6]:
                evidence.append(_frame_summary(frame))
        issues.append(
            _issue(
                "critical",
                "SystemUI HWUI animation race",
                (
                    "SystemUI crashed in Android's HWUI animation code. The crash signature "
                    "matches a strong-pointer/data-race abort or a null animator in "
                    "PropertyValuesAnimatorSet, not a thermal, power or kernel fault by itself."
                ),
                evidence,
                (
                    "Check for a SystemUI/system update and capture a tombstone/bugreport. "
                    "Avoid repeatedly triggering the overlay or animation; bright, even "
                    "lighting may reduce tracking/poor-condition overlays. A factory reset "
                    "may clear a corrupt system state, but treat that as a test, not a fix."
                ),
            )
        )

    for crash in other_crashes:
        kind = crash.get("kind") or "native"
        process = crash.get("process") or "unknown process"
        signature = crash.get("signature") or classify_crash(crash)
        if signature and signature["id"] == "perception_head_tracking_init":
            issues.append(
                _issue(
                    "warning",
                    signature["title"],
                    signature["summary"],
                    [_crash_summary(crash), _top_frame(crash)],
                    signature["recommendation"],
                )
            )
            continue
        if signature and signature["id"] == "immersiveviewxr_foveation":
            issues.append(
                _issue(
                    "warning",
                    signature["title"],
                    signature["summary"],
                    [_crash_summary(crash), _top_frame(crash)],
                    signature["recommendation"],
                )
            )
            continue
        if kind == "native":
            issues.append(
                _issue(
                    "warning",
                    f"Native crash in {process}",
                    _crash_summary(crash),
                    [_frame_summary(f) for f in (crash.get("frames") or [])[:8]],
                    "Record the tombstone with `adb bugreport` or a root context, then check the "
                    "top frame against the process role. Do not assume thermal causation from "
                    "temperature alone.",
                )
            )
        elif kind == "java":
            issues.append(
                _issue(
                    "warning",
                    f"Java crash in {process}",
                    crash.get("error") or "FATAL EXCEPTION",
                    (crash.get("raw") or [])[:8],
                    "Read the Java stack and the app version/build. This is an app/runtime failure, "
                    "not a native HWUI or kernel fault.",
                )
            )
        elif kind == "anr":
            issues.append(
                _issue(
                    "warning",
                    f"ANR in {process}",
                    "The app main thread did not respond in time.",
                    (crash.get("raw") or [])[:8],
                    "Collect the ANR trace and look for a blocked binder call, disk wait or lock. "
                    "ANR is not the same as a native crash or a reboot.",
                )
            )

    events = report.get("events") or {}
    for record in events.get("am_crashes") or []:
        process = record.get("process") or "unknown process"
        if any(crash.get("process") == process and crash.get("kind") == "java" for crash in crashes):
            continue
        issues.append(
            _issue(
                "warning",
                f"ActivityManager crash event: {process}",
                "The events buffer recorded an `am_crash` entry that was not parsed into a Java stack.",
                [record.get("message") or "", f"timestamp={record.get('timestamp')}"],
                "Open the raw events section and match the timestamp with the app/system logs. "
                "This can catch a crash after the main log has rotated.",
            )
        )
    for record in events.get("am_anrs") or []:
        process = record.get("process") or "unknown process"
        if any(crash.get("process") == process and crash.get("kind") == "anr" for crash in crashes):
            continue
        issues.append(
            _issue(
                "warning",
                f"ActivityManager ANR event: {process}",
                "The events buffer recorded an `am_anr` entry.",
                [record.get("message") or "", f"timestamp={record.get('timestamp')}"],
                "Open the raw events section and the ANR trace. This can catch a silent ANR that "
                "never produced a crash block.",
            )
        )

    abnormal_exits = _abnormal_exits(report.get("exit_info") or [])
    if abnormal_exits:
        current_day = (report.get("collected_at") or "")[:10]
        recent = [
            entry
            for entry in abnormal_exits
            if not current_day or str(entry.get("timestamp") or "").startswith(current_day)
        ]
        if recent:
            recent.sort(key=lambda entry: str(entry.get("timestamp") or ""), reverse=True)
            issues.append(
                _issue(
                    "warning" if any("CRASH" in (entry.get("reason_text") or "") for entry in recent) else "info",
                    "Recent abnormal app exits",
                    (
                        "ActivityManager recorded app exits with a crash, ANR or low-memory reason. "
                        "These can be silent because they do not always produce a logcat crash block."
                    ),
                    [
                        f"{entry.get('timestamp')} {entry.get('process')} {entry.get('reason_text')}"
                        for entry in recent[:8]
                    ],
                    "Check the app/package and timestamp. If this is a repeated low-memory kill, "
                    "look at memory pressure and background processes; if it is a crash/ANR, "
                    "collect the tombstone/ANR trace.",
                )
            )

    tombstone_crashes = report.get("tombstone_crashes") or []
    if tombstone_crashes:
        for group in _group_crashes(tombstone_crashes):
            first = group[0]
            if is_systemui_hwui_race(first) and systemui_hwui:
                continue
            if any(_same_crash_signature(first, crash) for crash in crashes):
                continue
            process = first.get("process") or "unknown process"
            signature = first.get("signature") or classify_crash(first)
            title = (
                f"Historical {signature['title']}"
                if signature
                else f"Historical tombstone crash: {process}"
            )
            files = ", ".join(str(item.get("tombstone")) for item in group[:5] if item.get("tombstone"))
            evidence = [
                f"{item.get('tombstone')} {item.get('timestamp')} {item.get('signal')} "
                f"{item.get('abort') or item.get('cause') or ''}".strip()
                for item in group[:6]
            ]
            top = _top_frame(first)
            if top:
                evidence.append(top)
            issues.append(
                _issue(
                    "info",
                    title,
                    (
                        f"{len(group)} tombstone(s) share this signature. This is separate from "
                        "the current crash buffer and may predate the current issue."
                    ),
                    evidence,
                    f"Check the timestamps and tombstone files ({files or 'names unavailable'}). "
                    "If this is new or repeats near the current time, capture a full `adb bugreport`.",
                )
            )

    boot = report.get("boot") or {}
    props = boot.get("props") or {}
    rescue_count = _as_int(props.get("sys.rescue_boot_count"))
    mitigation_count = _as_int(props.get("sys.boot_mitigation_count"))
    max_level = _as_int(props.get("sys.max_rescue_level_attempted"))
    reason = (props.get("sys.boot.reason") or "").strip()
    attempting_reset = _truthy(props.get("sys.attempting_factory_reset"))
    attempting_reboot = _truthy(props.get("sys.attempting_reboot"))
    rescue_notes = boot.get("rescue_notes") or []
    if (
        "rescueparty" in reason.lower()
        or rescue_count
        or mitigation_count
        or max_level
        or attempting_reboot
        or attempting_reset
        or rescue_notes
    ):
        evidence = []
        if reason:
            evidence.append(f"sys.boot.reason={reason}")
        for key in (
            "sys.boot.reason.last",
            "ro.boot.bootreason",
            "sys.rescue_boot_count",
            "sys.boot_mitigation_count",
            "sys.max_rescue_level_attempted",
            "sys.attempting_reboot",
            "sys.attempting_factory_reset",
        ):
            value = props.get(key)
            if value not in (None, ""):
                evidence.append(f"{key}={value}")
        for note in rescue_notes[-4:]:
            evidence.append(
                f"rescue_note {note.get('timestamp')}: count={note.get('count')} "
                f"window={note.get('window_ms')} ms"
            )
        severity = "info"
        if attempting_reset or (max_level or 0) >= 4:
            severity = "critical"
        elif crashes:
            severity = "warning"
        summary = (
            "The framework reports a rescue/warm-boot state. This can be triggered by "
            "system-server/persistent-app crashes, but a DFroot/KernelSU soft reboot can "
            "also look similar. Use the timestamps and crash entries to separate them."
        )
        if not crashes:
            summary += " No crash block was found in this snapshot; if this was the DFroot routine, it may be expected."
        issues.append(
            _issue(
                severity,
                "Framework soft-reboot / rescue state",
                summary,
                evidence,
                (
                    "If this was not the deliberate root-initialisation reboot, avoid repeated "
                    "reproduction: the rescue counter can escalate to settings resets and a "
                    "factory-reset prompt. Capture crash logs and tombstones before rebooting again."
                ),
            )
        )

    dropbox = report.get("dropbox") or []
    tombstone_tags = {
        "SYSTEM_TOMBSTONE",
        "SYSTEM_TOMBSTONE_PROTO_WITH_HEADERS",
        "system_server_crash",
        "system_server_watchdog",
        "data_app_crash",
        "data_app_anr",
    }
    dropbox_hits = [entry for entry in dropbox if entry.get("tag") in tombstone_tags]
    if dropbox_hits:
        issues.append(
            _issue(
                "info",
                "Dropbox retained crash / tombstone entries",
                (
                    "Dropbox can survive logcat rotation and may hold the native tombstone after "
                    "the crash buffer has moved on. Treat it as evidence to compare with the "
                    "parsed crash blocks."
                ),
                [f"{entry.get('timestamp')} {entry.get('tag')}" for entry in dropbox_hits[:8]],
                "Open the raw Dropbox section or run `adb bugreport` for the full tombstone. "
                "A Dropbox entry alone does not prove the cause; match the process and signal.",
            )
        )

    kernel_hits = _kernel_hits(report)
    if kernel_hits:
        issues.append(
            _issue(
                "warning",
                "Kernel / GPU fault indicators",
                "The root-only kernel log contains fault-like lines.",
                kernel_hits,
                "A kernel panic, GPU fault, OOM kill or watchdog reset is a different class from "
                "a framework soft reboot. Preserve `dmesg`/pstore and the reboot reason.",
            )
        )

    system_hits = _system_signals(report)
    if system_hits:
        issues.append(
            _issue(
                "warning",
                "System log fault indicators",
                "The system/main buffers contain watchdog, low-memory or system_server fault-like lines.",
                system_hits,
                "Open the raw system/main sections and match the timestamp. This is a heuristic "
                "net for issues that do not produce a normal crash block.",
            )
        )

    thermal = report.get("thermal") or {}
    status = _as_float(thermal.get("thermal_status"))
    ap = _as_float(thermal.get("t_AP") if thermal.get("t_AP") is not None else thermal.get("sec_ap"))
    wifi = _as_float(thermal.get("t_WIFI") if thermal.get("t_WIFI") is not None else thermal.get("sec_wf"))
    fan = _as_float(thermal.get("fan_step"))
    if (status is not None and status >= 3) or (ap is not None and ap >= 70) or (wifi is not None and wifi >= 75):
        evidence = []
        for key, value in (
            ("thermal_status", status),
            ("AP", ap),
            ("WIFI", wifi),
            ("LRP", _as_float(thermal.get("t_LRP"))),
            ("fan_step", fan),
            ("battery", thermal.get("batt_temp")),
        ):
            if value is not None:
                evidence.append(f"{key}={value}")
        issues.append(
            _issue(
                "info",
                "High thermal state (context only)",
                (
                    "The snapshot was taken while the headset was hot. This is useful context, "
                    "but it is not evidence that heat caused the crash. The system UI/GPU/kernel "
                    "stack and boot reason should decide the classification."
                ),
                evidence,
                "Keep the workload and cooling conditions in the report; use the profiler run data "
                "to check whether this was a sustained thermal limit or just a warm snapshot.",
            )
        )

    root = report.get("root") or {}
    if root.get("requested") and not root.get("available"):
        issues.append(
            _issue(
                "info",
                "Root-only evidence unavailable",
                "Root extras were requested, but `su` did not return uid=0.",
                (root.get("errors") or [])[:8],
                "Tombstones, dropbox files, ANR traces and dmesg need root. Use a root context "
                "that can read them, or collect `adb bugreport`.",
            )
        )
    elif root.get("errors"):
        issues.append(
            _issue(
                "info",
                "Some root-only paths were blocked",
                "Root is available, but one or more evidence paths were denied.",
                (root.get("errors") or [])[:10],
                "KernelSU's `u:r:ksu:s0` context may not read `/data/tombstones` or "
                "`/data/system/dropbox`. Try `adb bugreport` or a root file manager.",
            )
        )

    if not issues:
        issues.append(
            _issue(
                "ok",
                "No crash signature found",
                "The collected crash/events/system buffers did not contain a recognized crash.",
                [f"crashes={len(crashes)}"],
                "If the problem is intermittent, collect again immediately after the event. "
                "Logcat buffers are rings and can rotate quickly.",
            )
        )

    issues.sort(key=lambda item: (SEVERITY_ORDER.get(item.get("severity"), 9), item.get("title", "")))
    return issues


_SYSTEMUI_HWUI_SIGNATURE = {
    "id": "systemui_hwui_race",
    "title": "SystemUI HWUI animation race",
    "summary": (
        "SystemUI crashed in Android's HWUI animation code. The crash signature matches a "
        "strong-pointer/data-race abort or a null animator in PropertyValuesAnimatorSet, not a "
        "thermal, power or kernel fault by itself."
    ),
    "recommendation": (
        "Check for a SystemUI/system update and capture a tombstone/bugreport. Avoid repeatedly "
        "triggering the overlay or animation; bright, even lighting may reduce poor-condition "
        "overlays. A factory reset may clear a corrupt system state, but treat that as a test."
    ),
}

_PERCEPTION_HEAD_TRACKING_SIGNATURE = {
    "id": "perception_head_tracking_init",
    "title": "Perception head-tracking initialisation failure",
    "summary": (
        "The perception host aborted because its internal MotionTrackingAdapter could not "
        "initialise. This is a native tracking/camera service failure, separate from SystemUI "
        "and ordinary app crashes."
    ),
    "recommendation": (
        "Check whether it follows standby/wake, camera use or a specific app. Reboot and see if "
        "it returns; if it repeats, collect a bugreport and check for a system update or a "
        "camera/perception service fault."
    ),
}

_IMMERSIVE_VIEW_FOVEATION_SIGNATURE = {
    "id": "immersiveviewxr_foveation",
    "title": "Immersive View XR Vulkan/foveation crash",
    "summary": (
        "The Immersive View XR Unity app crashed while creating a Vulkan framebuffer/image "
        "through Android's foveation layer and the Adreno driver. This points to app/content or "
        "foveation/driver handling, not the SystemUI HWUI animation race."
    ),
    "recommendation": (
        "Update the app and system, try different content or disable foveation if the app "
        "exposes it, and record the app version. It is not thermal by itself."
    ),
}


def _crash_text(crash: dict) -> str:
    return " ".join(
        [
            crash.get("abort") or "",
            crash.get("cause") or "",
            crash.get("error") or "",
            " ".join(crash.get("raw") or []),
            " ".join(
                f"{frame.get('path', '')} {frame.get('symbol', '')}"
                for frame in (crash.get("frames") or [])
            ),
        ]
    )


def is_systemui_hwui_race(crash: dict) -> bool:
    process = (crash.get("process") or "").strip().lower()
    if process != "com.android.systemui":
        return False
    text = _crash_text(crash)
    return any(
        marker in text
        for marker in (
            "PropertyValuesAnimatorSet",
            "AnimationContextBridge",
            "sp<> assignment detected data race",
            "ProgressBar$CircleAnimationCallback",
        )
    ) or ("AnimatedVectorDrawable" in text and "libhwui" in text)


def is_perception_head_tracking_init(crash: dict) -> bool:
    process = (crash.get("process") or "").strip().lower()
    return "android.hardware.perceptionhost" in process and (
        "MotionTrackingAdapter" in _crash_text(crash)
        or "libperception_head_tracking_host_plugin" in _crash_text(crash)
    )


def is_immersiveviewxr_foveation_crash(crash: dict) -> bool:
    if (crash.get("process") or "").strip().lower() != "com.google.android.apps.immersiveviewxr":
        return False
    text = _crash_text(crash)
    return "libVkLayer_android_foveation" in text or (
        "vulkan.adreno" in text and "libunity" in text
    )


def classify_crash(crash: dict) -> dict | None:
    if is_systemui_hwui_race(crash):
        return _SYSTEMUI_HWUI_SIGNATURE
    if is_perception_head_tracking_init(crash):
        return _PERCEPTION_HEAD_TRACKING_SIGNATURE
    if is_immersiveviewxr_foveation_crash(crash):
        return _IMMERSIVE_VIEW_FOVEATION_SIGNATURE
    return None


def annotate_crashes(report: dict) -> None:
    for key in ("crashes", "tombstone_crashes"):
        for crash in report.get(key) or []:
            signature = classify_crash(crash)
            if signature:
                crash["signature"] = signature


def format_markdown(report: dict) -> str:
    """Render a compact, saved Markdown report next to the JSON snapshot."""
    collected = report.get("collected_at") or ""
    device = report.get("device") or {}
    boot = report.get("boot") or {}
    props = boot.get("props") or {}
    thermal = report.get("thermal") or {}
    lines = [
        "# GXR diagnostic snapshot",
        "",
        f"- Collected: {collected}",
        f"- Device: {device.get('model') or 'unknown'}",
        f"- Build: {device.get('build_display_id') or device.get('fingerprint') or 'unknown'}",
        f"- Android: {device.get('android') or 'unknown'}",
        "",
        "## Summary",
        "",
    ]
    for issue in report.get("issues") or []:
        lines.append(f"- **{issue.get('severity', '').upper()} - {issue.get('title')}**: {issue.get('summary')}")
    lines += ["", "## Boot", ""]
    for key in (
        "sys.boot.reason",
        "sys.boot.reason.last",
        "ro.boot.bootreason",
        "sys.rescue_boot_count",
        "sys.boot_mitigation_count",
        "sys.max_rescue_level_attempted",
    ):
        if props.get(key) not in (None, ""):
            lines.append(f"- `{key}`: `{props[key]}`")
    if boot.get("uptime_s") is not None:
        lines.append(f"- Kernel uptime: {boot['uptime_s']:.1f} s")
    for note in boot.get("rescue_notes") or []:
        lines.append(
            f"- `rescue_note` {note.get('timestamp')}: count={note.get('count')} "
            f"window={note.get('window_ms')} ms"
        )

    lines += ["", "## Crashes", ""]
    crashes = report.get("crashes") or []
    if not crashes:
        lines.append("_No recognized crash blocks._")
    for crash in crashes:
        lines.append(f"### {crash.get('timestamp')} - {crash.get('process') or 'unknown'} ({crash.get('kind')})")
        lines.append("")
        lines.append(f"- Signal: {crash.get('signal') or crash.get('cause') or 'n/a'}")
        if crash.get("signature"):
            lines.append(f"- Signature: {crash['signature']['title']}")
            lines.append(f"- Meaning: {crash['signature']['summary']}")
        if crash.get("abort"):
            lines.append(f"- Abort: {crash['abort']}")
        for frame in (crash.get("frames") or [])[:8]:
            lines.append(f"  - {_frame_summary(frame)}")
        lines.append("")

    tombstones = report.get("tombstone_crashes") or []
    if tombstones:
        lines += ["## Tombstones (history)", ""]
        for crash in tombstones[:20]:
            signature = crash.get("signature", {}).get("title")
            lines.append(
                f"- {crash.get('tombstone') or 'tombstone'}: {crash.get('timestamp') or 'unknown'} "
                f"{crash.get('process') or 'unknown'} {crash.get('signal') or ''}"
                + (f" - {signature}" if signature else "")
            )
        lines.append("")

    exits = _abnormal_exits(report.get("exit_info") or [])
    if exits:
        exits = sorted(exits, key=lambda entry: str(entry.get("timestamp") or ""), reverse=True)
        lines += ["## Recent abnormal app exits", ""]
        for entry in exits[:12]:
            lines.append(
                f"- {entry.get('timestamp')} {entry.get('process') or 'unknown'} "
                f"{entry.get('reason_text') or ''}"
            )
        lines.append("")

    lines += ["## Thermal context", ""]
    for key, label in (
        ("thermal_status", "Thermal status"),
        ("t_AP", "AP"),
        ("t_WIFI", "WIFI"),
        ("t_LRP", "LRP"),
        ("fan_step", "Fan step"),
    ):
        if thermal.get(key) is not None:
            lines.append(f"- {label}: {thermal[key]}")
    lines += ["", "> Thermal values are context, not a crash-cause proof.", ""]

    saved = report.get("saved") or {}
    if saved:
        lines += ["## Saved files", ""]
        for kind, path in saved.items():
            lines.append(f"- {kind}: `{path}`")
        lines.append("")
    return "\n".join(lines)


def _abnormal_exits(records: list[dict]) -> list[dict]:
    abnormal = {"APP CRASH(NATIVE)", "APP CRASH(JAVA)", "ANR", "LOW_MEMORY"}
    return [
        entry
        for entry in records
        if entry.get("reason_text") in abnormal and entry.get("timestamp")
    ]


def _group_crashes(crashes: list[dict]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for crash in crashes:
        groups.setdefault(_crash_signature(crash), []).append(crash)
    return list(groups.values())


def _crash_signature(crash: dict) -> tuple:
    signature = classify_crash(crash)
    if signature:
        return (signature["id"],)
    return (crash.get("process"), crash.get("signal"), _top_frame(crash))


def _same_crash_signature(left: dict, right: dict) -> bool:
    return _crash_signature(left) == _crash_signature(right)


def _top_frame(crash: dict) -> str:
    frames = crash.get("frames") or []
    if not frames:
        return ""
    first = frames[0]
    if isinstance(first, dict):
        return (first.get("symbol") or first.get("path") or "").strip()
    return str(first).strip()


def _system_signals(report: dict) -> list[str]:
    sections = report.get("sections") or {}
    patterns = (
        r"watchdog.*killing system process",
        r"watchdog.*blocked",
        r"lowmemorykiller",
        r"lmkd.*kill",
        r"out of memory",
        r"system_server.*(fatal|crash|died)",
    )
    hits: list[str] = []
    for name in ("system", "main"):
        text = sections.get(name) or ""
        for line in text.splitlines():
            low = line.lower()
            if any(re.search(pattern, low) for pattern in patterns):
                clean = line.strip()
                if clean:
                    hits.append(f"{name}: {clean[:300]}")
                if len(hits) >= 8:
                    return hits
    return hits


def _kernel_hits(report: dict) -> list[str]:
    root = report.get("root") or {}
    sections = {
        "dmesg": root.get("dmesg") or "",
        "last_kmsg": root.get("last_kmsg") or "",
        "pstore": root.get("pstore") or "",
    }
    patterns = (
        "kernel panic",
        r"panic\(",
        "bug: unable",
        "internal error:",
        "watchdog: bug",
        "hard lockup",
        "soft lockup",
        "oom-kill",
        "out of memory: killed process",
        "gpu fault",
        "kgsl.*fault",
        "gpu hang",
        "thermal.*shutdown",
        "thermal.*critical",
    )

    hits: list[str] = []
    for name, text in sections.items():
        for line in text.splitlines():
            low = line.lower()
            if any(re.search(pattern, low) for pattern in patterns):
                clean = line.strip()
                if clean:
                    hits.append(f"{name}: {clean[:300]}")
                if len(hits) >= 12:
                    return hits
    return hits


def _crash_summary(crash: dict) -> str:
    bits = [str(crash.get("timestamp") or "")]
    parts = [
        crash.get("process") or "unknown",
        crash.get("signal") or "",
        crash.get("abort") or "",
        crash.get("cause") or "",
    ]
    bits.extend(part for part in parts if part)
    return " | ".join(bits)


def _frame_summary(frame: dict) -> str:
    if not isinstance(frame, dict):
        return str(frame)
    path = frame.get("path") or ""
    symbol = frame.get("symbol") or ""
    num = frame.get("num")
    prefix = f"#{num} " if num is not None else ""
    return (prefix + (symbol or path)).strip()


def _issue(
    severity: str,
    title: str,
    summary: str,
    evidence: list[str],
    recommendation: str,
) -> dict:
    return {
        "severity": severity,
        "title": title,
        "summary": summary,
        "evidence": [str(item) for item in evidence if item],
        "recommendation": recommendation,
    }


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
