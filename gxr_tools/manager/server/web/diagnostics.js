"use strict";

function stopDebugPolling() {
  debugStatusSeq += 1;
  if (debugPollTimer) {
    clearTimeout(debugPollTimer);
    debugPollTimer = null;
  }
}

function debugFrameText(frame) {
  if (!frame) return "";
  if (typeof frame === "string") return frame;
  return (frame.symbol || frame.path || "").trim();
}

function debugKvTable(rows) {
  const wrap = el("div", "table-scroll");
  const table = el("table", "diagkv");
  rows.forEach(([key, value]) => {
    const tr = el("tr");
    tr.appendChild(textEl("th", null, key));
    tr.appendChild(textEl("td", null, value == null || value === "" ? "--" : String(value)));
    table.appendChild(tr);
  });
  wrap.appendChild(table);
  return wrap;
}

function debugStatusBadge(status) {
  const label = (status && status.status) || "idle";
  const cls = label === "done" ? "badge good" : label === "error" ? "badge bad" : "badge";
  return textEl("span", cls, label);
}

function debugControlsCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Diagnostics snapshot"));
  card.appendChild(el("p", "muted cardnote", "Read-only snapshot of crash buffers, boot/rescue state, dropbox, exit-info and thermal context. Nothing is written to the headset."));
  const grid = el("div", "optgrid");
  grid.innerHTML = `
    <label class="optitem"><input class="optbox" id="d-root" type="checkbox" />
      <span class="optbody"><span class="opttitle">Root extras</span><span class="optdesc">Try tombstones, dropbox files, ANR traces and kernel log through read-only su.</span></span></label>
    <label class="optitem"><input class="optbox" id="d-tombstones" type="checkbox" />
      <span class="optbody"><span class="opttitle">Read tombstone / ANR files</span><span class="optdesc">Requires root. KernelSU may still be denied by SELinux.</span></span></label>
    <label class="optitem"><input class="optbox" id="d-dmesg" type="checkbox" />
      <span class="optbody"><span class="opttitle">Kernel log / pstore</span><span class="optdesc">Requires root. Adds dmesg, last_kmsg and pstore listing.</span></span></label>`;
  card.appendChild(grid);
  const field = el("div", "field");
  const label = el("label", null, "Log lines per buffer");
  const input = document.createElement("input");
  input.id = "d-log-lines";
  input.type = "number";
  input.min = "100";
  input.max = "5000";
  input.step = "100";
  input.value = String(debugOptions.log_lines || 1500);
  field.appendChild(label);
  field.appendChild(input);
  field.appendChild(el("span", "fieldhint", "Crash, events, system and main buffers are capped at this many lines."));
  card.appendChild(field);
  const actions = el("div", "recordactions");
  const collect = el("button", "primary", debugRequestBusy ? "Collecting..." : "Collect snapshot");
  collect.type = "button";
  collect.id = "debug-collect";
  collect.disabled = debugRequestBusy || !!(debugStatus && debugStatus.running);
  collect.onclick = () => startDebugCollection();
  const refresh = el("button", "toolbtn", "Refresh status");
  refresh.type = "button";
  refresh.onclick = () => refreshDebugStatus();
  const download = el("button", "toolbtn", "Download JSON");
  download.type = "button";
  download.disabled = !debugReport;
  download.onclick = () => downloadDebugReport();
  actions.appendChild(collect);
  actions.appendChild(refresh);
  actions.appendChild(download);
  actions.appendChild(debugStatusBadge(debugStatus));
  card.appendChild(actions);
  const status = textEl("span", "muted", "");
  if (debugStatus && debugStatus.error) status.textContent = debugStatus.error;
  else if (debugStatus && debugStatus.running) status.textContent = "Collecting...";
  else if (debugStatus && debugStatus.finished) status.textContent = "Last finished: " + debugStatus.finished;
  card.appendChild(status);

  const rootCb = card.querySelector("#d-root");
  const tombCb = card.querySelector("#d-tombstones");
  const dmesgCb = card.querySelector("#d-dmesg");
  const syncOptions = () => {
    debugOptions.root = rootCb.checked;
    debugOptions.include_tombstones = tombCb.checked;
    debugOptions.include_dmesg = dmesgCb.checked;
    debugOptions.log_lines = Math.max(100, Math.min(5000, parseInt(input.value, 10) || 1500));
    if (tombCb.checked || dmesgCb.checked) {
      rootCb.checked = true;
      debugOptions.root = true;
    }
  };
  [rootCb, tombCb, dmesgCb, input].forEach(node => node.addEventListener("change", syncOptions));
  rootCb.checked = !!debugOptions.root;
  tombCb.checked = !!debugOptions.include_tombstones;
  dmesgCb.checked = !!debugOptions.include_dmesg;
  syncOptions();
  grid.querySelectorAll("input[type=checkbox]").forEach(cb => {
    const item = cb.closest(".optitem");
    const sync = () => item.classList.toggle("selected", cb.checked);
    cb.addEventListener("change", sync);
    sync();
  });
  return card;
}

function debugSummaryCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Snapshot"));
  if (!debugReport) {
    card.appendChild(el("div", "muted", "No diagnostics snapshot loaded. Collect one to see findings."));
    return card;
  }
  const r = debugReport;
  const device = r.device || {};
  const boot = r.boot || {};
  const props = boot.props || {};
  const rows = [
    ["Collected", r.collected_at ? fmtStamp(Date.parse(r.collected_at), true) : "--"],
    ["Duration", r.duration_ms != null ? r.duration_ms + " ms" : "--"],
    ["Device", device.model || "--"],
    ["Build", device.build_display_id || device.build_fingerprint || "--"],
    ["Boot reason", props["sys.boot.reason"] || "--"],
    ["Rescue count", props["sys.rescue_boot_count"] || "--"],
    ["Crashes", String((r.crashes || []).length)],
    ["Native", String((r.crashes || []).filter(c => c.kind === "native").length)],
    ["Java", String((r.crashes || []).filter(c => c.kind === "java").length)],
    ["ANR", String((r.crashes || []).filter(c => c.kind === "anr").length)],
    ["Tombstones", String((r.tombstone_crashes || []).length)],
    ["Exit records", String((r.exit_info || []).length)],
    ["Findings", String((r.issues || []).length)],
  ];
  if (r.saved && r.saved.json) rows.push(["Saved JSON", r.saved.json]);
  if (r.saved && r.saved.markdown) rows.push(["Saved Markdown", r.saved.markdown]);
  card.appendChild(debugKvTable(rows));
  return card;
}

function debugIssuesCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Findings"));
  const issues = (debugReport && debugReport.issues) || [];
  if (!issues.length) {
    card.appendChild(el("div", "muted", "No findings in the latest snapshot."));
    return card;
  }
  issues.forEach(issue => {
    const box = el("div", "diag-issue sev-" + (issue.severity || "info"));
    const head = el("div", "diag-issue-head");
    head.appendChild(textEl("span", "badge sev-" + (issue.severity || "info"), (issue.severity || "info").toUpperCase()));
    head.appendChild(textEl("b", null, issue.title || "Finding"));
    box.appendChild(head);
    box.appendChild(textEl("p", "diag-summary", issue.summary || ""));
    const evidence = issue.evidence || [];
    if (evidence.length) {
      box.appendChild(copyablePre(evidence.join("\n")));
    }
    if (issue.recommendation) box.appendChild(textEl("p", "diag-reco", "Next: " + issue.recommendation));
    card.appendChild(box);
  });
  return card;
}

function debugCrashesCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Crashes"));
  const crashes = (debugReport && debugReport.crashes) || [];
  if (!crashes.length) {
    card.appendChild(el("div", "muted", "No recognized crash blocks in the collected buffers."));
    return card;
  }
  crashes.forEach((crash, index) => {
    const details = document.createElement("details");
    details.className = "diag-crash";
    if (index === 0) details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = [
      crash.timestamp || "unknown time",
      crash.process || "unknown process",
      "(" + (crash.kind || "native") + ")",
      crash.signal || crash.abort || "",
      crash.signature ? crash.signature.title : "",
    ].filter(Boolean).join(" | ");
    details.appendChild(summary);
    const meta = [
      ["Process", crash.process],
      ["PID/TID", [crash.pid, crash.tid].filter(Boolean).join(" / ")],
      ["Thread", crash.thread],
      ["Signal", crash.signal],
      ["Abort", crash.abort],
      ["Cause", crash.cause],
      ["Top frame", debugFrameText((crash.frames || [])[0]) || debugFrameText(crash.top_frame)],
    ].filter(row => row[1] != null && row[1] !== "");
    details.appendChild(debugKvTable(meta));
    if (crash.signature) {
      const box = el("div", "diag-signature");
      box.appendChild(textEl("b", null, crash.signature.title));
      box.appendChild(textEl("p", "diag-summary", crash.signature.summary || ""));
      if (crash.signature.recommendation) {
        box.appendChild(textEl("p", "diag-reco", "Next: " + crash.signature.recommendation));
      }
      details.appendChild(box);
    }
    const frames = (crash.frames || []).map(debugFrameText).filter(Boolean);
    if (frames.length) {
      details.appendChild(copyablePre(frames.join("\n")));
    }
    if (crash.raw && crash.raw.length) {
      details.appendChild(copyablePre(crash.raw.join("\n")));
    }
    card.appendChild(details);
  });
  return card;
}

function debugTombstonesCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Tombstones (history)"));
  if (!debugReport) return card;
  const entries = (debugReport.tombstone_crashes || []).slice().sort((a, b) =>
    String(b.timestamp || "").localeCompare(String(a.timestamp || ""))
  );
  if (!entries.length) {
    const raw = (debugReport.root && debugReport.root.tombstones) || [];
    if (!raw.length) {
      card.appendChild(el("div", "muted", "No tombstone files were read. Enable root extras and tombstone reading."));
      return card;
    }
    raw.forEach(tomb => {
      const details = document.createElement("details");
      details.className = "diag-crash";
      const summary = document.createElement("summary");
      summary.textContent = "Tombstone " + tomb.name;
      details.appendChild(summary);
      details.appendChild(copyablePre(tomb.content || ""));
      card.appendChild(details);
    });
    return card;
  }
  card.appendChild(el("p", "muted cardnote", "Older entries can predate the current issue. Check the timestamp and source file before acting."));
  entries.forEach((crash, index) => {
    const details = document.createElement("details");
    details.className = "diag-crash";
    if (index === 0) details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = [
      crash.tombstone || "tombstone",
      crash.timestamp || "unknown",
      crash.process || "unknown process",
      crash.signal || "",
      crash.abort || "",
      crash.signature ? crash.signature.title : "",
    ].filter(Boolean).join(" | ");
    details.appendChild(summary);
    const meta = [
      ["Tombstone", crash.tombstone],
      ["Timestamp", crash.timestamp],
      ["Process", crash.process],
      ["PID/TID", [crash.pid, crash.tid].filter(Boolean).join(" / ")],
      ["Signal", crash.signal],
      ["Abort", crash.abort],
      ["Cause", crash.cause],
      ["Top frame", debugFrameText((crash.frames || [])[0])],
    ].filter(row => row[1] != null && row[1] !== "");
    details.appendChild(debugKvTable(meta));
    if (crash.signature) {
      const box = el("div", "diag-signature");
      box.appendChild(textEl("b", null, crash.signature.title));
      box.appendChild(textEl("p", "diag-summary", crash.signature.summary || ""));
      if (crash.signature.recommendation) {
        box.appendChild(textEl("p", "diag-reco", "Next: " + crash.signature.recommendation));
      }
      details.appendChild(box);
    }
    const frames = (crash.frames || []).map(debugFrameText).filter(Boolean);
    if (frames.length) {
      details.appendChild(copyablePre(frames.join("\n")));
    }
    if (crash.raw && crash.raw.length) {
      details.appendChild(copyablePre(crash.raw.join("\n")));
    }
    card.appendChild(details);
  });
  return card;
}

function debugExitInfoCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Process exits (history)"));
  if (!debugReport) return card;
  const exits = (debugReport.exit_info || [])
    .filter(entry => entry.timestamp)
    .slice()
    .sort((a, b) => String(b.timestamp || "").localeCompare(String(a.timestamp || "")))
    .slice(0, 20);
  if (!exits.length) {
    card.appendChild(el("div", "muted", "No exit-info records were returned."));
    return card;
  }
  card.appendChild(el("p", "muted cardnote", "Latest 20 ActivityManager exit records; some may be historical. LOW_MEMORY can be a silent app kill."));
  const wrap = el("div", "table-scroll");
  const table = document.createElement("table");
  table.className = "diagkv";
  const head = document.createElement("tr");
  ["Time", "Process", "Reason", "Status"].forEach(label => head.appendChild(textEl("th", null, label)));
  table.appendChild(head);
  exits.forEach(entry => {
    const tr = document.createElement("tr");
    tr.appendChild(textEl("td", null, entry.timestamp || "--"));
    tr.appendChild(textEl("td", null, entry.process || entry.package || "--"));
    tr.appendChild(textEl("td", null, entry.reason_text || entry.reason || "--"));
    tr.appendChild(textEl("td", null, entry.status || "--"));
    table.appendChild(tr);
  });
  wrap.appendChild(table);
  card.appendChild(wrap);
  return card;
}

function debugBootCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Boot & rescue"));
  if (!debugReport) return card;
  const boot = debugReport.boot || {};
  const props = boot.props || {};
  const rows = [];
  ["sys.boot.reason", "sys.boot.reason.last", "ro.boot.bootreason", "sys.rescue_boot_count",
    "sys.boot_mitigation_count", "sys.max_rescue_level_attempted", "sys.attempting_reboot",
    "sys.attempting_factory_reset"].forEach(key => {
    if (props[key] != null && props[key] !== "") rows.push([key, props[key]]);
  });
  if (boot.uptime_s != null) rows.push(["Kernel uptime", Number(boot.uptime_s).toFixed(1) + " s"]);
  card.appendChild(debugKvTable(rows));
  const notes = boot.rescue_notes || [];
  if (notes.length) {
    card.appendChild(copyablePre(notes.slice(-8).map(n => `${n.timestamp} count=${n.count} window=${n.window_ms} ms`).join("\n")));
  }
  return card;
}

function debugThermalCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Thermal context"));
  if (!debugReport) return card;
  const t = debugReport.thermal || {};
  const rows = [
    ["Thermal status", t.thermal_status],
    ["AP", t.t_AP != null ? t.t_AP + " C" : null],
    ["WIFI", t.t_WIFI != null ? t.t_WIFI + " C" : null],
    ["LRP", t.t_LRP != null ? t.t_LRP + " C" : null],
    ["Fan step", t.fan_step],
    ["Battery", t.batt_temp != null ? t.batt_temp + " C" : null],
    ["DDR", t.ddr_temp != null ? t.ddr_temp + " C" : null],
    ["GPU clock", t.g_clock != null ? t.g_clock + " MHz" : null],
    ["GPU busy", t.g_busy != null ? t.g_busy + "%" : null],
  ].filter(row => row[1] != null && row[1] !== "");
  card.appendChild(rows.length ? debugKvTable(rows) : el("div", "muted", "Thermal preview unavailable."));
  card.appendChild(el("p", "muted cardnote", "Thermal values are context, not proof of causation."));
  return card;
}

function debugRootCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Root evidence"));
  if (!debugReport) return card;
  const r = debugReport.root || {};
  if (!r.requested) {
    card.appendChild(el("div", "muted", "Root extras were not requested."));
    return card;
  }
  if (!r.available) {
    card.appendChild(el("div", "muted", "Root was requested but is not available."));
    if ((r.errors || []).length) {
      card.appendChild(copyablePre(r.errors.join("\n")));
    }
    return card;
  }
  const rows = [
    ["Tombstone listing", r.tombstone_list ? "read" : "not readable"],
    ["Tombstones read", String((r.tombstones || []).length)],
    ["Dropbox files read", String((r.dropbox_files || []).length)],
    ["ANR files read", String((r.anr_files || []).length)],
    ["dmesg", r.dmesg ? "read" : "not collected"],
  ];
  card.appendChild(debugKvTable(rows));
  if ((r.errors || []).length) {
    card.appendChild(copyablePre(r.errors.join("\n")));
  }
  return card;
}

function debugRawCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Raw sections"));
  if (!debugReport) return card;
  const sections = { ...(debugReport.sections || {}) };
  const root = debugReport.root || {};
  const rootSections = {
    "root.dmesg": root.dmesg,
    "root.last_kmsg": root.last_kmsg,
    "root.pstore": root.pstore,
    "root.watchdog": root.watchdog,
    "root.package_watchdog": root.package_watchdog,
  };
  Object.entries(rootSections).forEach(([name, text]) => {
    if (text) sections[name] = text;
  });
  let any = false;
  Object.entries(sections).forEach(([name, text]) => {
    if (!text) return;
    any = true;
    const details = document.createElement("details");
    details.className = "diag-crash";
    const summary = document.createElement("summary");
    summary.textContent = name + " (" + text.length.toLocaleString() + " chars)";
    details.appendChild(summary);
    details.appendChild(copyablePre(text));
    card.appendChild(details);
  });
  if (!any) card.appendChild(el("div", "muted", "No raw sections."));
  return card;
}

function renderDiagnosticsTool(host) {
  host.innerHTML = "";
  const top = el("div", "twocol");
  top.appendChild(debugControlsCard());
  top.appendChild(debugSummaryCard());
  host.appendChild(top);
  if (debugReport) {
    host.appendChild(debugIssuesCard());
    host.appendChild(debugCrashesCard());
    host.appendChild(debugTombstonesCard());
    host.appendChild(debugExitInfoCard());
    const row = el("div", "twocol");
    row.appendChild(debugBootCard());
    row.appendChild(debugThermalCard());
    host.appendChild(row);
    host.appendChild(debugRootCard());
    host.appendChild(debugRawCard());
  }
}

async function startDebugCollection() {
  if (debugRequestBusy) return;
  const rootCb = document.getElementById("d-root");
  const tombCb = document.getElementById("d-tombstones");
  const dmesgCb = document.getElementById("d-dmesg");
  const linesInput = document.getElementById("d-log-lines");
  debugOptions = {
    root: !!(rootCb && rootCb.checked) || !!(tombCb && tombCb.checked) || !!(dmesgCb && dmesgCb.checked),
    include_tombstones: !!(tombCb && tombCb.checked),
    include_dmesg: !!(dmesgCb && dmesgCb.checked),
    log_lines: Math.max(100, Math.min(5000, parseInt((linesInput && linesInput.value) || "1500", 10) || 1500)),
  };
  debugRequestBusy = true;
  debugReport = null;
  debugStatus = { status: "running", running: true };
  renderActiveToolBody();
  try {
    await jpost("/api/debug/collect", debugOptions);
    refreshDebugStatus();
  } catch (e) {
    debugStatus = { status: "error", error: e.message || String(e) };
    debugRequestBusy = false;
    renderActiveToolBody();
  }
}

async function refreshDebugStatus() {
  stopDebugPolling();
  const seq = debugStatusSeq;
  try {
    const status = await jget("/api/debug/status");
    if (seq !== debugStatusSeq) return;
    debugStatus = status;
    if (status.status === "done") {
      debugReport = await jget("/api/debug/report");
      if (seq !== debugStatusSeq) return;
      debugRequestBusy = false;
    } else if (status.status === "error") {
      debugRequestBusy = false;
    }
    if (activeTab === "tools" && activeToolTab === "diagnostics") renderActiveToolBody();
    if ((status.running || status.status === "running") && activeTab === "tools" && activeToolTab === "diagnostics") {
      debugPollTimer = setTimeout(refreshDebugStatus, 1000);
    }
  } catch (e) {
    if (seq !== debugStatusSeq) return;
    debugStatus = { status: "error", error: e.message || String(e) };
    debugRequestBusy = false;
    if (activeTab === "tools" && activeToolTab === "diagnostics") renderActiveToolBody();
  }
}

function downloadDebugReport() {
  if (!debugReport) return;
  const stamp = String(debugReport.collected_at || new Date().toISOString()).replace(/[:.]/g, "-");
  const blob = new Blob([JSON.stringify(debugReport, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "gxr-diagnostics-" + stamp + ".json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

