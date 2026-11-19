"use strict";

async function settingsFetch() {
  try {
    const data = await jget("/api/settings");
    settingsState.data = data || {};
    settingsState.loaded = true;
    settingsState.error = "";
  } catch (e) {
    settingsState.error = e.message || String(e);
  } finally {
    settingsState.loading = false;
    if (activeTab === "tools" && activeToolTab === "settings") renderActiveToolBody();
  }
}

function settingsRefresh() {
  if (settingsState.loading) return;
  settingsState.loading = true;
  settingsState.error = "";
  if (activeTab === "tools" && activeToolTab === "settings") renderActiveToolBody();
  settingsFetch();
}

async function settingsToggle(item, enabled) {
  if (settingsState.busy[item.id]) return;
  settingsState.busy[item.id] = true;
  if (activeTab === "tools" && activeToolTab === "settings") renderActiveToolBody();
  try {
    const result = await jpost("/api/settings/" + encodeURIComponent(item.id), { enabled });
    let text = result.output
      || (result.ok ? "The setting was updated." : "The setting was applied, but verification failed.");
    if (result.ok && item.id === "xr_perf_metrics" && enabled) {
      text += "\nReminder: turn the performance overlay off when finished to avoid OLED burn-in.";
    }
    showToast({
      title: result.ok ? "Setting updated" : "Setting verification failed",
      message: text,
      type: result.ok ? "success" : "error",
    });
  } catch (e) {
    showToast({
      title: "Setting update failed",
      message: e.message || String(e),
      type: "error",
    });
  } finally {
    delete settingsState.busy[item.id];
    await settingsFetch();
  }
}

async function settingsSetValue(item, value) {
  if (settingsState.busy[item.id] || value === (item.value || "")) return;
  settingsState.busy[item.id] = true;
  if (activeTab === "tools" && activeToolTab === "settings") renderActiveToolBody();
  try {
    const result = await jpost("/api/settings/" + encodeURIComponent(item.id), { value });
    const label = result.label || value;
    showToast({
      title: result.ok ? "Setting updated" : "Setting verification failed",
      message: result.output
        || (result.ok ? "Updated to " + label + "." : "The setting was applied, but verification failed."),
      type: result.ok ? "success" : "error",
    });
  } catch (e) {
    showToast({
      title: "Setting update failed",
      message: e.message || String(e),
      type: "error",
    });
  } finally {
    delete settingsState.busy[item.id];
    await settingsFetch();
  }
}

function settingsRequestToggle(item, enabled) {
  if (item.confirm_on_disable && !enabled) {
    settingsConfirmDisable(item);
    return;
  }
  settingsToggle(item, enabled);
}

function settingsModalKeyHandler(event) {
  if (event.key === "Escape") closeSettingsConfirm();
}

function closeSettingsConfirm() {
  closeModal("settings-confirm-modal");
  document.removeEventListener("keydown", settingsModalKeyHandler);
}

function settingsConfirmDisable(item) {
  closeSettingsConfirm();
  const dialog = openModal("settings-confirm-modal", "", closeSettingsConfirm, "Disable " + item.label);
  const head = el("div", "modal-head");
  head.appendChild(el("h3", null, "Disable " + item.label + "?"));
  const close = el("button", "toolbtn", "✕");
  close.type = "button";
  close.title = "Cancel";
  close.onclick = closeSettingsConfirm;
  head.appendChild(close);
  dialog.appendChild(head);
  dialog.appendChild(textEl("p", "modal-desc", item.warning || "This is a safety-related change."));
  const command = (item.commands && item.commands.revert && item.commands.revert[0]) || "";
  dialog.appendChild(copyablePre(command, "diag-evidence modal-command"));
  const actions = el("div", "modal-actions");
  const cancel = el("button", "toolbtn", "Cancel");
  cancel.type = "button";
  cancel.onclick = closeSettingsConfirm;
  const confirm = el("button", "primary danger", "Disable setting");
  confirm.type = "button";
  confirm.onclick = () => {
    closeSettingsConfirm();
    settingsToggle(item, false);
  };
  actions.appendChild(cancel);
  actions.appendChild(confirm);
  dialog.appendChild(actions);
  document.addEventListener("keydown", settingsModalKeyHandler);
}

function settingsChoiceLabel(item) {
  const option = (item.options || []).find(entry => entry.value === item.value);
  return option ? option.label : "Unknown";
}

function settingsDefaultLabel(item) {
  if (item.default_label) return item.default_label;
  return item.default_enabled ? "On" : "Off";
}

function settingsStatusLabel(item) {
  if (item.kind === "choice") return settingsChoiceLabel(item);
  return ({
    active: "On",
    inactive: "Off",
    partial: "Needs reapply",
    unavailable: "Not installed",
    unknown: "Unknown",
  })[item.state] || "Unknown";
}

function settingsStatusClass(item) {
  if (item.kind === "choice") return item.state === "active" ? "good" : "bad";
  return item.state === "active" ? "good" : item.state === "inactive" ? "idle" : item.state === "partial" ? "sev-warning" : "bad";
}

function settingsPersistenceLabel(item) {
  return ({
    persistent: "Survives reboots",
    until_reboot: "Until reboot",
    module: "Requires module/service",
  })[item.persistence] || "Persistence unknown";
}

function settingsPersistenceClass(item) {
  return item.persistence === "persistent" ? "good" : item.persistence === "until_reboot" ? "sev-warning" : "bad";
}

function settingsHeaderCard() {
  const card = el("section", "card");
  const head = el("div", "appstoolhead");
  const copy = el("div");
  copy.appendChild(el("h3", null, "Settings"));
  copy.appendChild(el("p", "muted cardnote", "Device settings here are not tied to a run; changes are applied immediately and can be reverted."));
  copy.appendChild(el("p", "muted cardnote", "Recommended: hide the recording indicator (green dot) under Privacy indicators."));
  const checked = settingsState.data && settingsState.data.checked_at;
  copy.appendChild(el("p", "muted cardnote", checked
    ? "Status checked " + fmtStamp(Date.parse(checked), true) + "."
    : (settingsState.loading ? "Checking current setting values..." : "No status snapshot loaded.")));
  head.appendChild(copy);
  if (settingsState.data) {
    const refresh = el("button", "toolbtn", settingsState.loading ? "Checking..." : "Refresh");
    refresh.type = "button";
    refresh.disabled = settingsState.loading;
    refresh.onclick = settingsRefresh;
    head.appendChild(refresh);
  }
  card.appendChild(head);
  card.appendChild(el("div", "settings-header-sep"));
  return card;
}

function settingsLoadCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Load device settings"));
  card.appendChild(el("p", "muted cardnote", "Connect the headset over ADB, then load the current setting values. This is a read-only snapshot."));
  const load = el("button", "primary", "Load settings");
  load.type = "button";
  load.onclick = settingsRefresh;
  card.appendChild(load);
  return card;
}

function settingsErrorCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Settings unavailable"));
  card.appendChild(textEl("p", "muted", settingsState.error));
  const retry = el("button", "toolbtn", "Retry");
  retry.type = "button";
  retry.onclick = settingsRefresh;
  card.appendChild(retry);
  return card;
}

function settingsRow(item) {
  const row = el("div", "settingrow" + (item.state === "partial" ? " partial" : ""));
  const main = el("div", "settingmain");
  const title = el("div", "settingtitle");
  title.appendChild(textEl("h4", null, item.label));
  if (item.recommended) title.appendChild(textEl("span", "badge good", "Recommended"));
  title.appendChild(textEl("span", "badge " + settingsStatusClass(item), settingsStatusLabel(item)));
  const persistence = textEl("span", "badge " + settingsPersistenceClass(item), settingsPersistenceLabel(item));
  if (item.persistence_note) persistence.title = item.persistence_note;
  title.appendChild(persistence);
  if (item.root_required) title.appendChild(textEl("span", "badge sev-warning", "Root required"));
  main.appendChild(title);
  main.appendChild(textEl("p", "settingdesc", item.description));
  if (item.warning) main.appendChild(textEl("p", "settingwarning", item.warning));
  if (item.error) main.appendChild(textEl("p", "settingerror", item.error));
  const details = item.details || [];
  const meta = el("div", "settingmeta");
  meta.appendChild(textEl("span", "settingmetaitem", "Default: " + settingsDefaultLabel(item)));
  details.forEach(detail => {
    meta.appendChild(textEl("span", "settingmetaitem", detail.label + ": " + detail.value));
  });
  main.appendChild(meta);
  if (item.commands) {
    const commandBox = document.createElement("details");
    commandBox.className = "settingcommands";
    const summary = document.createElement("summary");
    summary.textContent = "Commands";
    commandBox.appendChild(summary);
    const lines = [
      "Read:", ...(item.commands.read || []).map(line => "  " + line),
    ];
    if (item.kind === "choice") {
      (item.options || []).forEach(option => {
        lines.push(option.label + ":", ...(option.commands || []).map(line => "  " + line));
      });
    } else {
      lines.push(
        "Apply:", ...(item.commands.apply || []).map(line => "  " + line),
        "Revert:", ...(item.commands.revert || []).map(line => "  " + line),
      );
    }
    commandBox.appendChild(copyablePre(lines.join("\n"), ""));
    main.appendChild(commandBox);
  }
  row.appendChild(main);

  const controls = el("div", "settingcontrols");
  if (item.kind === "choice") {
    const select = document.createElement("select");
    select.className = "settingselect";
    select.disabled = !!settingsState.busy[item.id] || item.state === "unavailable";
    select.setAttribute("aria-label", item.label);
    const current = item.value || "";
    const hasCurrent = (item.options || []).some(option => option.value === current);
    if (!hasCurrent) {
      const unknown = document.createElement("option");
      unknown.value = current;
      unknown.textContent = current ? "Unknown (" + current + ")" : "Unknown";
      select.appendChild(unknown);
    }
    (item.options || []).forEach(option => {
      const node = document.createElement("option");
      node.value = option.value;
      node.textContent = option.label;
      select.appendChild(node);
    });
    select.value = current;
    select.onchange = () => settingsSetValue(item, select.value);
    controls.appendChild(select);
  } else {
    const checked = !!item.enabled;
    const toggle = el("button", "settingswitch" + (checked ? " on" : ""));
    toggle.type = "button";
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-checked", String(checked));
    toggle.setAttribute("aria-label", (checked ? "Disable " : "Enable ") + item.label);
    toggle.title = checked ? "Turn off" : "Turn on";
    toggle.disabled = !!settingsState.busy[item.id] || item.state === "unavailable";
    toggle.onclick = () => settingsRequestToggle(item, !checked);
    controls.appendChild(toggle);
    if (item.state === "partial") {
      const reapply = el("button", "toolbtn", "Reapply");
      reapply.type = "button";
      reapply.disabled = !!settingsState.busy[item.id];
      reapply.title = "Reapply this setting";
      reapply.onclick = () => settingsToggle(item, true);
      controls.appendChild(reapply);
    }
  }
  row.appendChild(controls);
  return row;
}

function settingsSectionCard(section) {
  const card = el("section", "card settings-section");
  const title = el("div", "settings-summarytitle");
  title.appendChild(el("h3", null, section.title));
  if (section.test_only) title.appendChild(textEl("span", "badge sev-warning", "Test only"));
  card.appendChild(title);
  if (section.description) card.appendChild(el("p", "muted cardnote", section.description));
  const list = el("div", "settings-list");
  (section.settings || []).forEach(item => list.appendChild(settingsRow(item)));
  card.appendChild(list);
  return card;
}

function renderSettingsTool(host) {
  host.innerHTML = "";
  if (OFFLINE) {
    const card = el("section", "card");
    card.appendChild(el("h3", null, "Settings"));
    card.appendChild(el("div", "muted", "Settings are not available in offline reports."));
    host.appendChild(card);
    return;
  }
  host.appendChild(settingsHeaderCard());
  if (settingsState.error) host.appendChild(settingsErrorCard());
  const sections = (settingsState.data && settingsState.data.sections) || [];
  sections.forEach(section => host.appendChild(settingsSectionCard(section)));
  if (!settingsState.data && !settingsState.loading && !settingsState.error) host.appendChild(settingsLoadCard());
}
