"use strict";

function toolDefinitions() {
  return [
    { id: "diagnostics", label: "Diagnostics", render: renderDiagnosticsTool },
    { id: "apps", label: "Apps", render: renderAppsTool },
    { id: "installer", label: "Installer", render: renderInstallerTool },
    { id: "settings", label: "Settings", render: renderSettingsTool },
  ];
}

function renderActiveToolBody() {
  const host = document.getElementById("tools-body");
  if (!host) return;
  const tools = toolDefinitions();
  const tool = tools.find(item => item.id === activeToolTab) || tools[0];
  if (!tool) return;
  if (activeToolTab !== tool.id) {
    activeToolTab = tool.id;
    try { localStorage.setItem("gxr-profiler.managerToolTab", tool.id); } catch (e) {}
  }
  host.innerHTML = "";
  tool.render(host);
}

function setToolTab(id) {
  if (id === activeToolTab) return;
  const tools = toolDefinitions();
  if (!tools.some(tool => tool.id === id)) return;
  activeToolTab = id;
  try { localStorage.setItem("gxr-profiler.managerToolTab", id); } catch (e) {}
  if (id !== "apps") {
    closeAppsDetailModal();
    appsState.selected = null;
    appsState.detail = null;
  }
  if (id !== "diagnostics") stopDebugPolling();
  const bar = document.getElementById("tools-inner-tabs");
  if (bar) {
    bar.querySelectorAll(".innertab").forEach(btn => {
      const on = btn.dataset.tool === id;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", String(on));
    });
  }
  renderActiveToolBody();
  if (id === "diagnostics") refreshDebugStatus();
}

function renderToolsView() {
  if (OFFLINE) return;
  const v = document.getElementById("view");
  v.innerHTML = "";
  const card = el("section", "card results tools-hub");
  const header = el("div", "results-header");
  header.appendChild(el("h3", "results-title", "GXR Manager"));
  header.appendChild(el("div", "results-note muted", "Device tools for the connected headset."));
  card.appendChild(header);
  const bar = el("div", "inner-tabs");
  bar.id = "tools-inner-tabs";
  bar.setAttribute("role", "tablist");
  const tools = toolDefinitions();
  if (!tools.some(tool => tool.id === activeToolTab)) activeToolTab = tools[0].id;
  tools.forEach(tool => {
    const button = el("button", "innertab" + (tool.id === activeToolTab ? " active" : ""), tool.label);
    button.type = "button";
    button.dataset.tool = tool.id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", String(tool.id === activeToolTab));
    button.onclick = () => setToolTab(tool.id);
    bar.appendChild(button);
  });
  card.appendChild(bar);
  const body = el("div", "tools-body");
  body.id = "tools-body";
  card.appendChild(body);
  v.appendChild(card);
  renderActiveToolBody();
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

async function refreshRecordingStatus() {
  const banner = document.getElementById("recording-banner");
  if (!banner) return;
  try {
    const state = await jget("/api/recording");
    if (state && state.active) {
      banner.hidden = false;
      banner.textContent = "Profiler is recording" + (state.label ? ": " + state.label : "") + " - device changes are blocked.";
    } else {
      banner.hidden = true;
      banner.textContent = "";
    }
  } catch (e) {
    banner.hidden = true;
  }
}

renderToolsView();
refreshDebugStatus();
refreshRecordingStatus();
setInterval(refreshRecordingStatus, 2000);
