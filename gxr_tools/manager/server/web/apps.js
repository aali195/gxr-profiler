"use strict";


const APP_FILTERS = [
  { id: "all", label: "All" },
  { id: "system", label: "System" },
  { id: "user", label: "User" },
  { id: "disabled", label: "Disabled" },
  { id: "removed", label: "Removed" },
];
const GAME_FPS_OPTIONS = [
  ["disable", "Off"],
  ["30", "30 FPS"],
  ["45", "45 FPS"],
  ["60", "60 FPS"],
  ["90", "90 FPS"],
];
const GAME_SCALE_OPTIONS = [
  ["disable", "Off"],
  ["0.9", "90%"],
  ["0.8", "80%"],
  ["0.7", "70%"],
  ["0.6", "60%"],
  ["0.5", "50%"],
];
const APP_COLUMNS = [
  { key: "package", label: "Package" },
  { key: "kind", label: "Type", width: "110px" },
  { key: "state", label: "State", width: "120px" },
  { key: "running", label: "Running", width: "100px", dir: -1 },
  { key: "oom_class", label: "OOM", width: "110px" },
  { key: "size_kb", label: "Size", unit: "MB", scale: 1 / 1024, decimals: 0, dir: -1, width: "88px", numeric: true },
  { key: "cpu_pct", label: "CPU 5m", unit: "%", decimals: 1, dir: -1, width: "78px", numeric: true },
  { key: "rss_kb", label: "RSS", unit: "MB", scale: 1 / 1024, decimals: 0, dir: -1, width: "88px", numeric: true },
  { key: "gpu_mem_kb", label: "GPU mem", unit: "MB", scale: 1 / 1024, decimals: 0, dir: -1, width: "96px", numeric: true },
  { key: "threads", label: "Threads", decimals: 0, dir: -1, width: "78px", numeric: true },
  { key: "installer", label: "Installer", width: "190px" },
];

function appsRows() {
  return (appsState.data && appsState.data.packages) || [];
}

function appsKindLabel(row) {
  return ({ "system-updated": "System (updated)", system: "System", user: "User" })[row.kind] || "Unknown";
}

function appsStateLabel(row) {
  return ({ enabled: "Enabled", disabled: "Disabled", removed: "Removed for user 0" })[row.state] || row.state;
}

function appsStateClass(row) {
  return row.state === "enabled" ? "good" : row.state === "removed" ? "bad" : "sev-warning";
}

function appsProcCategory(row) {
  return row.kind === "user" ? "app" : "system-app";
}

function appsTypeClass(row) {
  return "kind-" + appsProcCategory(row);
}

function appsOomLabel(row) {
  const value = row.oom_class || "";
  return value ? value[0].toUpperCase() + value.slice(1) : "--";
}

function appsRunningLabel(row) {
  return row.running ? "Running" : "Not running";
}

function appsCellText(row, column) {
  const value = row[column.key];
  if (value == null || value === "") return "--";
  const scaled = Number(value) * (column.scale == null ? 1 : column.scale);
  if (!Number.isFinite(scaled)) return "--";
  return fmt(scaled, "", column.decimals) + (column.unit === "%" ? "%" : "");
}

function appsSortValue(row, key) {
  if (key === "kind") return appsKindLabel(row);
  if (key === "state") return appsStateLabel(row);
  if (key === "running") return row.running ? 1 : 0;
  if (key === "oom_class") return row.oom_adj;
  return row[key];
}

function appsFilteredRows() {
  let rows = appsRows().slice();
  if (appsState.filter === "system") rows = rows.filter(row => row.kind !== "user");
  else if (appsState.filter === "user") rows = rows.filter(row => row.kind === "user");
  else if (appsState.filter === "disabled") rows = rows.filter(row => row.state === "disabled");
  else if (appsState.filter === "removed") rows = rows.filter(row => row.state === "removed");
  const query = appsState.query.trim().toLowerCase();
  if (query) {
    rows = rows.filter(row => [row.package, row.installer, row.apk_path, row.kind, row.state, row.oom_class, ...(row.proc_names || [])]
      .filter(Boolean).join(" ").toLowerCase().includes(query));
  }
  const key = appsState.sort.key;
  const dir = appsState.sort.dir || 1;
  return rows.sort((a, b) => {
    const av = appsSortValue(a, key);
    const bv = appsSortValue(b, key);
    const an = av == null || av === "";
    const bn = bv == null || bv === "";
    if (an && bn) return String(a.package || "").localeCompare(String(b.package || ""));
    if (an) return 1;
    if (bn) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });
}

function appsFormatKb(value) {
  if (value == null || !Number.isFinite(Number(value))) return null;
  const kb = Number(value);
  if (kb >= 1048576) return (kb / 1048576).toFixed(1) + " GB";
  if (kb >= 1024) return (kb / 1024).toFixed(1) + " MB";
  return Math.round(kb).toLocaleString() + " KB";
}

async function appsFetch() {
  try {
    const data = await jget("/api/apps");
    appsState.data = data || {};
    appsState.loaded = true;
    appsState.error = "";
    const selected = appsState.selected;
    if (selected) {
      const next = appsRows().find(row => row.package === selected.package);
      if (next) appsState.selected = next;
      else {
        appsState.selected = null;
        appsState.detail = null;
        closeAppsDetailModal();
      }
    }
  } catch (e) {
    appsState.error = e.message || String(e);
  } finally {
    appsState.loading = false;
    if (activeTab === "tools" && activeToolTab === "apps") renderActiveToolBody();
    renderAppsDetailModal();
  }
}

function appsRefresh() {
  if (appsState.loading) return;
  appsState.loading = true;
  appsState.error = "";
  renderActiveToolBody();
  appsFetch();
}

async function appsFetchDetail(packageName, root) {
  const token = ++appsState.detailToken;
  appsState.detailLoading = true;
  appsState.detailError = "";
  renderAppsDetailModal();
  try {
    const data = await jget("/api/apps/" + encodeURIComponent(packageName) + "?root=" + (root ? "1" : "0"));
    if (token !== appsState.detailToken) return;
    appsState.detail = data;
  } catch (e) {
    if (token !== appsState.detailToken) return;
    appsState.detail = null;
    appsState.detailError = e.message || String(e);
  } finally {
    if (token === appsState.detailToken) {
      appsState.detailLoading = false;
      renderAppsDetailModal();
    }
  }
}

function selectApp(row) {
  appsState.selected = row;
  appsState.detail = null;
  appsState.detailError = "";
  appsState.performanceDraft = null;
  appsState.detailToken += 1;
  renderActiveToolBody();
  openAppsDetailModal();
  appsFetchDetail(row.package, appsState.rootDetails);
}

function closeAppsDetail() {
  appsState.detailToken += 1;
  appsState.selected = null;
  appsState.detail = null;
  appsState.detailError = "";
  appsState.detailLoading = false;
  appsState.performanceDraft = null;
  closeAppsDetailModal();
  renderActiveToolBody();
}

function appsDetailKeyHandler(event) {
  if (event.key !== "Escape" || document.getElementById("apps-modal")) return;
  closeAppsDetail();
}

function closeAppsDetailModal() {
  closeModal("apps-detail-modal");
  document.removeEventListener("keydown", appsDetailKeyHandler);
}

function renderAppsDetailModal() {
  const dialog = document.querySelector("#apps-detail-modal .modal-card");
  if (!dialog) return;
  if (!appsState.selected) {
    closeAppsDetailModal();
    return;
  }
  const scrollTop = dialog.scrollTop;
  const rootWasFocused = document.activeElement && document.activeElement.id === "apps-root-details";
  dialog.innerHTML = "";
  dialog.appendChild(appsDetailCard());
  dialog.scrollTop = scrollTop;
  if (rootWasFocused) {
    const rootBox = dialog.querySelector("#apps-root-details");
    if (rootBox) rootBox.focus();
  }
}

function openAppsDetailModal() {
  closeAppsDetailModal();
  openModal("apps-detail-modal", "apps-detail-card", closeAppsDetail, "Package details");
  document.addEventListener("keydown", appsDetailKeyHandler);
  renderAppsDetailModal();
}

function appsActionSpec(action) {
  const specs = (appsState.data && appsState.data.action_specs) || {};
  const spec = specs[action];
  if (!spec) return null;
  return {
    ...spec,
    button: spec.label,
    dataLoss: !!spec.data_loss,
    command: pkg => String(spec.command || "").replace("{package}", pkg),
  };
}

function appsModalKeyHandler(event) {
  if (event.key === "Escape") closeAppsModal();
}

function closeAppsModal() {
  closeModal("apps-modal");
  document.removeEventListener("keydown", appsModalKeyHandler);
}

function openAppsConfirm(row, action) {
  const spec = appsActionSpec(action);
  if (!spec) return;
  closeAppsModal();
  const dialog = openModal("apps-modal", "", closeAppsModal, spec.title);
  const head = el("div", "modal-head");
  head.appendChild(el("h3", null, spec.title));
  const close = el("button", "toolbtn", "✕");
  close.type = "button";
  close.title = "Cancel";
  close.onclick = closeAppsModal;
  head.appendChild(close);
  dialog.appendChild(head);
  const pkg = textEl("div", "modal-package", row.package);
  dialog.appendChild(pkg);
  dialog.appendChild(textEl("p", "modal-desc", spec.description));
  const command = spec.command(row.package);
  dialog.appendChild(copyablePre(command, "diag-evidence modal-command"));
  if (spec.dataLoss) {
    dialog.appendChild(textEl("p", "modal-warning", "This action may delete app data."));
  }
  const checks = [];
  const addCheck = (text) => {
    const label = el("label", "modal-check");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    label.appendChild(cb);
    label.appendChild(textEl("span", null, text));
    dialog.appendChild(label);
    checks.push(cb);
    cb.addEventListener("change", sync);
  };
  if (spec.dataLoss) addCheck("I understand app data may be deleted.");
  const actions = el("div", "modal-actions");
  const cancel = el("button", "toolbtn", "Cancel");
  cancel.type = "button";
  cancel.onclick = closeAppsModal;
  const confirm = el("button", "primary" + (spec.destructive ? " danger" : ""), spec.confirm);
  confirm.type = "button";
  function sync() {
    confirm.disabled = appsState.actionBusy || checks.some(cb => !cb.checked);
  }
  confirm.onclick = () => {
    if (confirm.disabled) return;
    confirm.disabled = true;
    runAppsAction(row, action);
  };
  actions.appendChild(cancel);
  actions.appendChild(confirm);
  dialog.appendChild(actions);
  document.addEventListener("keydown", appsModalKeyHandler);
  sync();
}

async function runAppsAction(row, action) {
  appsState.actionBusy = true;
  try {
    const result = await jpost("/api/apps/" + encodeURIComponent(row.package) + "/action", {
      action,
      confirm: true,
    });
    showToast({
      title: result.ok ? "Package action completed" : "Package action failed",
      message: result.output || (result.ok ? "The package action completed." : "The package action failed."),
      type: result.ok ? "success" : "error",
    });
    if (result.ok && action === "uninstall") {
      appsState.selected = null;
      appsState.detail = null;
    }
    await appsFetch();
    if (appsState.selected && appsState.selected.package === row.package) {
      appsFetchDetail(row.package, appsState.rootDetails);
    }
  } catch (e) {
    showToast({
      title: "Package action failed",
      message: e.message || String(e),
      type: "error",
    });
  } finally {
    appsState.actionBusy = false;
    closeAppsModal();
    if (activeTab === "tools" && activeToolTab === "apps") renderActiveToolBody();
  }
}

const INSTALL_ACCEPTED = new Set([".apk", ".obb", ".xapk"]);

function appsChip(label, value, className) {
  const chip = el("span", "appschip" + (className ? " " + className : ""));
  chip.appendChild(textEl("span", "appschipk", label));
  chip.appendChild(textEl("span", "appschipv", value == null ? "--" : String(value)));
  return chip;
}

function appsHeaderCard() {
  const card = el("section", "card");
  const head = el("div", "appstoolhead");
  const copy = el("div");
  copy.appendChild(el("h3", null, "Installed apps & services"));
  copy.appendChild(el("p", "muted cardnote", "Read installed packages, disable or remove them, and restore stock system packages. Every destructive action requires confirmation; critical system packages cannot be disabled or removed."));
  head.appendChild(copy);
  if (appsState.data) {
    const actions = el("div", "appstoolactions");
    const refresh = el("button", "toolbtn", appsState.loading ? "Loading..." : "Refresh");
    refresh.type = "button";
    refresh.disabled = appsState.loading;
    refresh.onclick = appsRefresh;
    actions.appendChild(refresh);
    head.appendChild(actions);
  }
  card.appendChild(head);
  if (appsState.data) {
    const summary = appsState.data.summary || {};
    const chips = el("div", "appschips");
    [
      ["Total", summary.total], ["System", summary.system], ["User", summary.user],
      ["Disabled", summary.disabled], ["Removed", summary.removed], ["Running", summary.running],
    ].forEach(([label, value]) => chips.appendChild(appsChip(label, value)));
    card.appendChild(chips);
    const totals = el("div", "appschips appstotals");
    [
      ["CPU 5m", summary.cpu_pct == null ? "--" : fmt(summary.cpu_pct, "%", 1)],
      ["RSS", appsFormatKb(summary.rss_kb) || "--"],
      ["GPU mem", appsFormatKb(summary.gpu_mem_kb) || "--"],
      ["Size", appsFormatKb(summary.size_kb) || "--"],
    ].forEach(([label, value]) => totals.appendChild(appsChip(label, value, "apptotal")));
    card.appendChild(totals);
  }
  if (appsState.loading && !appsState.data) card.appendChild(el("div", "muted", "Loading installed packages..."));
  card.appendChild(el("p", "muted cardnote", "Android does not expose reliable human-readable app labels over shell, so package IDs are shown. Stock/system packages are marked; per-user removal keeps the factory APK in the system image."));
  card.appendChild(el("p", "muted cardnote", "CPU, RSS, GPU memory, threads and OOM are a process snapshot taken when the list is fetched; Size is the install footprint. CPU is the ~5-minute dumpsys cpuinfo value. They are not live."));
  return card;
}

function appsErrorCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Package list unavailable"));
  card.appendChild(textEl("p", "muted", appsState.error));
  const retry = el("button", "toolbtn", "Retry");
  retry.type = "button";
  retry.onclick = appsRefresh;
  card.appendChild(retry);
  return card;
}

function appsLoadCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Load installed apps"));
  card.appendChild(el("p", "muted cardnote", "Connect the headset over ADB, then load the installed package list. This is a read-only snapshot."));
  const load = el("button", "primary", "Load apps");
  load.type = "button";
  load.onclick = appsRefresh;
  card.appendChild(load);
  return card;
}

function appsDetailCard() {
  const row = appsState.selected;
  const card = el("section", "card appsdetail");
  const head = el("div", "appstoolhead");
  const title = el("div", "appsdetail-title");
  title.appendChild(textEl("h3", null, row.package));
  const badges = el("div", "appbadges");
  badges.appendChild(textEl("span", "procbadge " + appsTypeClass(row), appsKindLabel(row)));
  badges.appendChild(textEl("span", "badge " + appsStateClass(row), appsStateLabel(row)));
  if (row.critical) badges.appendChild(textEl("span", "badge bad", "Critical"));
  if (row.running) badges.appendChild(textEl("span", "badge good", "Running"));
  title.appendChild(badges);
  head.appendChild(title);
  const close = el("button", "toolbtn", "Close");
  close.type = "button";
  close.onclick = closeAppsDetail;
  head.appendChild(close);
  card.appendChild(head);
  if (row.critical) {
    card.appendChild(textEl("p", "modal-warning", "This is a critical system component. Disable and remove actions are blocked for this package."));
  }
  const actions = el("div", "recordactions");
  (row.actions || []).forEach(action => {
    const spec = appsActionSpec(action);
    if (!spec) return;
    const button = el("button", "toolbtn" + (spec.destructive ? " danger" : ""), spec.button);
    button.type = "button";
    button.disabled = appsState.actionBusy;
    button.onclick = () => openAppsConfirm(row, action);
    actions.appendChild(button);
  });
  if (!actions.childElementCount) actions.appendChild(el("span", "muted", "No actions are available in this state."));
  const rootLabel = el("label", "modal-check approotcheck");
  const rootBox = document.createElement("input");
  rootBox.type = "checkbox";
  rootBox.id = "apps-root-details";
  rootBox.checked = !!appsState.rootDetails;
  rootBox.addEventListener("change", () => {
    appsState.rootDetails = rootBox.checked;
    appsFetchDetail(row.package, appsState.rootDetails);
  });
  rootLabel.appendChild(rootBox);
  rootLabel.appendChild(textEl("span", null, "Root details (data/cache size; may prompt)"));
  actions.appendChild(rootLabel);
  card.appendChild(actions);

  if (appsState.detailLoading) {
    card.appendChild(el("div", "muted", "Loading package details..."));
    return card;
  }
  if (appsState.detailError) {
    card.appendChild(textEl("p", "modal-warning", appsState.detailError));
  }
  const detail = appsState.detail && appsState.detail.detail ? appsState.detail.detail : {};
  const rows = [
    ["Type", appsKindLabel(row)],
    ["State", appsStateLabel(row)],
    ["Processes", row.proc_count ? row.proc_count + " running" : "not running"],
    ["OOM class", row.proc_count ? appsOomLabel(row) : null],
    ["CPU (5m)", row.proc_count ? fmt(row.cpu_pct, "%", 1) : null],
    ["RSS total", row.proc_count ? appsFormatKb(row.rss_kb) : null],
    ["GPU memory", row.proc_count ? appsFormatKb(row.gpu_mem_kb) : null],
    ["Install size", appsFormatKb(row.size_kb)],
    ["Threads", row.proc_count ? row.threads : null],
    ["Version", [detail.version_name, detail.version_code].filter(v => v != null && v !== "").join(" · ") || row.version_code],
    ["SDK", detail.min_sdk == null && detail.target_sdk == null ? null : "min " + (detail.min_sdk ?? "?") + " · target " + (detail.target_sdk ?? "?")],
    ["First installed", detail.first_install_time],
    ["Last updated", detail.last_update_time],
    ["Installer", detail.installer || row.installer],
    ["Code path", detail.code_path || row.apk_path],
    ["Data dir", detail.data_dir],
    ["ABI", detail.primary_cpu_abi],
    ["Flags", (detail.flags || []).join(" ")],
    ["Requested permissions", detail.requested_permissions_count],
    ["Users", (detail.user_states || []).map(state => "user " + state.user + (state.installed === false ? " (not installed)" : "")).join(", ")],
  ].filter(item => item[1] != null && item[1] !== "");
  if (rows.length) card.appendChild(debugKvTable(rows));
  if ((row.proc_names || []).length) {
    const procHead = el("div", "appsubhead", "Processes");
    card.appendChild(procHead);
    card.appendChild(copyablePre(row.proc_names.join("\n")));
  }
  if ((detail.apk_paths || []).length) {
    const apkHead = el("div", "appsubhead", "APK files");
    card.appendChild(apkHead);
    card.appendChild(copyablePre(detail.apk_paths.join("\n")));
  }
  const root = appsState.detail && appsState.detail.root;
  if (root && root.requested) {
    const rootRows = [
      ["Root available", root.available ? "yes" : "no"],
      ["App data", appsFormatKb(root.data_kb)],
      ["Cache", appsFormatKb(root.cache_kb)],
    ].filter(item => item[1] != null && item[1] !== "");
    if (rootRows.length) card.appendChild(debugKvTable(rootRows));
    if ((root.errors || []).length) {
      card.appendChild(copyablePre(root.errors.join("\n")));
    }
  }
  const game = appsState.detail && appsState.detail.game;
  if (game && game.supported && !row.critical) {
    card.appendChild(appsPerformanceCard(row, game));
  }
  return card;
}

function appsPerformanceCard(row, game) {
  const card = el("section", "appsperf");
  card.appendChild(el("div", "appsubhead", "Performance overrides"));
  card.appendChild(textEl(
    "p",
    "muted cardnote",
    "Android Game Mode custom interventions. Restart the app after applying; downscaling only takes effect on the next launch."
  ));
  const mode = game.current_mode || "unknown";
  const available = (game.available_modes || []).join(", ") || "none";
  card.appendChild(textEl(
    "p",
    "muted cardnote",
    "Current mode: " + mode + " · Available: " + available + " · " + (game.interventions || "No custom intervention")
  ));
  const draft = appsState.performanceDraft || {
    fps: game.fps || "disable",
    downscale: game.downscale || "disable",
  };
  const grid = el("div", "appsperf-grid");
  const fpsField = el("div", "field");
  fpsField.appendChild(el("label", null, "FPS cap"));
  const fps = document.createElement("select");
  GAME_FPS_OPTIONS.forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    fps.appendChild(option);
  });
  fps.value = draft.fps;
  fps.disabled = appsState.actionBusy;
  fps.onchange = () => {
    draft.fps = fps.value;
    appsState.performanceDraft = draft;
  };
  fpsField.appendChild(fps);
  grid.appendChild(fpsField);

  const scaleField = el("div", "field");
  scaleField.appendChild(el("label", null, "Render scale"));
  const scale = document.createElement("select");
  GAME_SCALE_OPTIONS.forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    scale.appendChild(option);
  });
  scale.value = draft.downscale;
  scale.disabled = appsState.actionBusy;
  scale.onchange = () => {
    draft.downscale = scale.value;
    appsState.performanceDraft = draft;
  };
  scaleField.appendChild(scale);
  grid.appendChild(scaleField);
  card.appendChild(grid);

  const actions = el("div", "recordactions");
  const apply = el("button", "primary", "Apply");
  apply.type = "button";
  apply.disabled = appsState.actionBusy;
  apply.onclick = () => openAppsPerformanceConfirm(row, "apply", draft);
  const reset = el("button", "toolbtn", "Reset");
  reset.type = "button";
  reset.disabled = appsState.actionBusy;
  reset.onclick = () => openAppsPerformanceConfirm(row, "reset", draft);
  actions.appendChild(apply);
  actions.appendChild(reset);
  card.appendChild(actions);
  return card;
}

function appsGameOverrideCommand(packageName, fps, downscale) {
  const args = [];
  if (fps !== "disable") args.push("--fps", fps);
  if (downscale !== "disable") args.push("--downscale", downscale);
  else if (fps !== "disable") args.push("--downscale", "disable");
  if (!args.length) return "cmd game reset " + packageName;
  return "cmd game set " + args.join(" ") + " " + packageName;
}

function openAppsPerformanceConfirm(row, mode, draft) {
  const reset = mode === "reset";
  const title = reset ? "Reset performance override" : "Apply performance override";
  closeAppsModal();
  const dialog = openModal("apps-modal", "", closeAppsModal, title);
  const head = el("div", "modal-head");
  head.appendChild(el("h3", null, title));
  const close = el("button", "toolbtn", "×");
  close.type = "button";
  close.title = "Cancel";
  close.onclick = closeAppsModal;
  head.appendChild(close);
  dialog.appendChild(head);
  dialog.appendChild(textEl("div", "modal-package", row.package));
  dialog.appendChild(textEl(
    "p",
    "modal-desc",
    reset
      ? "Remove the custom Game Mode intervention and restore the device configuration."
      : "Apply the selected FPS cap and render scale to this app's custom Game Mode."
  ));
  const command = reset
    ? "cmd game reset " + row.package
    : appsGameOverrideCommand(row.package, draft.fps, draft.downscale);
  dialog.appendChild(copyablePre(command, "diag-evidence modal-command"));
  dialog.appendChild(textEl(
    "p",
    "modal-warning",
    "The app must be restarted for the override to take effect. Higher FPS or a larger render scale may increase heat and power use."
  ));
  const actions = el("div", "modal-actions");
  const cancel = el("button", "toolbtn", "Cancel");
  cancel.type = "button";
  cancel.onclick = closeAppsModal;
  const confirm = el("button", "primary", reset ? "Reset override" : "Apply override");
  confirm.type = "button";
  confirm.disabled = appsState.actionBusy;
  confirm.onclick = () => {
    if (confirm.disabled) return;
    confirm.disabled = true;
    runAppsPerformance(
      row,
      reset ? "disable" : draft.fps,
      reset ? "disable" : draft.downscale
    );
  };
  actions.appendChild(cancel);
  actions.appendChild(confirm);
  dialog.appendChild(actions);
  document.addEventListener("keydown", appsModalKeyHandler);
}

async function runAppsPerformance(row, fps, downscale) {
  appsState.actionBusy = true;
  try {
    const result = await jpost(
      "/api/apps/" + encodeURIComponent(row.package) + "/performance",
      { fps, downscale, confirm: true }
    );
    showToast({
      title: result.ok ? "Performance override applied" : "Performance override failed",
      message: result.output || (result.ok ? "The override was applied." : "The override failed."),
      type: result.ok ? "success" : "error",
    });
    appsState.performanceDraft = null;
    await appsFetch();
    if (appsState.selected && appsState.selected.package === row.package) {
      await appsFetchDetail(row.package, appsState.rootDetails);
    }
  } catch (e) {
    showToast({
      title: "Performance override failed",
      message: e.message || String(e),
      type: "error",
    });
  } finally {
    appsState.actionBusy = false;
    closeAppsModal();
    if (appsState.selected && appsState.selected.package === row.package) {
      renderAppsDetailModal();
    } else {
      renderActiveToolBody();
    }
  }
}

function appsTableCard() {
  const card = el("section", "card");
  const head = el("div", "appstoolhead");
  const title = el("div");
  title.appendChild(el("h3", null, "Packages"));
  const count = el("span", "muted tablecount");
  title.appendChild(count);
  head.appendChild(title);
  const controls = el("div", "filterbar");
  APP_FILTERS.forEach(filter => {
    const button = el("button", "subtab" + (appsState.filter === filter.id ? " active" : ""), filter.label);
    button.type = "button";
    button.setAttribute("aria-pressed", String(appsState.filter === filter.id));
    button.onclick = () => {
      if (appsState.filter === filter.id) return;
      appsState.filter = filter.id;
      renderActiveToolBody();
    };
    controls.appendChild(button);
  });
  const search = document.createElement("input");
  search.type = "search";
  search.className = "filtersearch";
  search.setAttribute("aria-label", "Search installed packages");
  search.placeholder = "Search package, process, installer or path...";
  search.value = appsState.query;
  controls.appendChild(search);
  head.appendChild(controls);
  card.appendChild(head);

  const wrap = el("div", "table-scroll appstablewrap");
  const table = document.createElement("table");
  table.className = "appstable";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  APP_COLUMNS.forEach(column => {
    const th = document.createElement("th");
    th.scope = "col";
    th.tabIndex = 0;
    th.setAttribute("role", "button");
    if (column.numeric) th.className = "appnumhead";
    if (column.width) th.style.width = column.width;
    const label = el("span", "prochead-label");
    label.appendChild(document.createTextNode(column.label));
    if (appsState.sort.key === column.key) {
      label.appendChild(el("span", "sortarrow", appsState.sort.dir < 0 ? "▼" : "▲"));
      th.setAttribute("aria-sort", appsState.sort.dir < 0 ? "descending" : "ascending");
    } else {
      th.setAttribute("aria-sort", "none");
    }
    th.appendChild(label);
    th.appendChild(el("span", "procunit", column.unit || "\u00a0"));
    th.title = "Sort by " + column.label;
    th.onclick = () => {
      if (appsState.sort.key === column.key) appsState.sort.dir *= -1;
      else appsState.sort = { key: column.key, dir: column.dir || 1 };
      renderActiveToolBody();
    };
    th.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        th.click();
      }
    };
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  table.appendChild(tbody);
  wrap.appendChild(table);
  card.appendChild(wrap);

  function drawRows() {
    tbody.innerHTML = "";
    const rows = appsFilteredRows();
    count.textContent = rows.length + " of " + appsRows().length + " packages";
    if (appsState.loading && !appsRows().length) {
      const tr = document.createElement("tr");
      const td = textEl("td", "muted", "Loading installed packages...");
      td.colSpan = APP_COLUMNS.length;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    if (!appsState.loaded && !appsState.error) {
      const tr = document.createElement("tr");
      const td = textEl("td", "muted", "Click Load apps to fetch the installed package list.");
      td.colSpan = APP_COLUMNS.length;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = textEl("td", "muted", "No packages match this filter.");
      td.colSpan = APP_COLUMNS.length;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    rows.forEach(row => {
      const tr = el("tr", "approw proc-kind-" + appsProcCategory(row) + (appsState.selected && appsState.selected.package === row.package ? " selected" : ""));
      tr.tabIndex = 0;
      tr.onclick = () => selectApp(row);
      tr.onkeydown = (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectApp(row);
        }
      };
      const packageCell = el("td", "apppkgcell");
      const packageLine = el("div", "apppkgline");
      packageLine.appendChild(textEl("span", "apppkg", row.package));
      if (row.critical) packageLine.appendChild(textEl("span", "badge bad", "critical"));
      packageCell.appendChild(packageLine);
      const metaParts = [];
      if (row.version_code != null) metaParts.push("v" + row.version_code);
      if (row.uid != null) metaParts.push("UID " + row.uid);
      if (row.proc_count) metaParts.push(row.proc_count + (row.proc_count === 1 ? " proc" : " procs"));
      const meta = textEl("div", "apppkgmeta", metaParts.join(" · "));
      if ((row.proc_names || []).length) meta.title = "Processes: " + row.proc_names.join(", ");
      packageCell.appendChild(meta);
      tr.appendChild(packageCell);
      APP_COLUMNS.slice(1).forEach(column => {
        const td = el("td");
        if (column.key === "kind") {
          td.appendChild(textEl("span", "procbadge " + appsTypeClass(row), appsKindLabel(row)));
        } else if (column.key === "state") {
          td.appendChild(textEl("span", "badge " + appsStateClass(row), appsStateLabel(row)));
        } else if (column.key === "running") {
          td.appendChild(textEl("span", "badge " + (row.running ? "good" : "idle"), appsRunningLabel(row)));
        } else if (column.key === "oom_class") {
          if (row.oom_class) {
            td.appendChild(textEl("span", "procbadge oom-" + row.oom_class, appsOomLabel(row)));
          } else {
            td.textContent = "--";
          }
        } else if (column.key === "installer") {
          td.className = "appinstaller";
          td.textContent = row.installer || "--";
        } else {
          td.className = "appnum";
          td.textContent = appsCellText(row, column);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }
  search.oninput = () => { appsState.query = search.value; drawRows(); };
  drawRows();
  return card;
}

function renderAppsTool(host) {
  host.innerHTML = "";
  if (OFFLINE) {
    const card = el("section", "card");
    card.appendChild(el("h3", null, "Installed apps & services"));
    card.appendChild(el("div", "muted", "Apps management is not available in offline reports."));
    host.appendChild(card);
    return;
  }
  host.appendChild(appsHeaderCard());
  if (appsState.error) host.appendChild(appsErrorCard());
  if (appsState.data || appsState.loading) host.appendChild(appsTableCard());
  else if (!appsState.error) host.appendChild(appsLoadCard());
}

