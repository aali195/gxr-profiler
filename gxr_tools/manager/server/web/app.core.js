"use strict";

let activeTab = "tools";

let debugReport = null;
let debugStatus = null;
let debugPollTimer = null;
let debugStatusSeq = 0;
let debugRequestBusy = false;
let debugOptions = { root: false, include_tombstones: false, include_dmesg: false, log_lines: 1500 };
const appsState = {
  data: null, loaded: false, loading: false, error: "",
  query: "", filter: "all", sort: { key: "cpu_pct", dir: -1 },
  selected: null, detail: null, detailError: "", detailLoading: false, detailToken: 0,
  rootDetails: false, actionBusy: false,
  performanceDraft: null,
};
const appsInstallState = {
  view: "files", items: [], uploads: [], obbPackages: {},
  options: { replace: true, allow_downgrade: false, grant_permissions: false },
  busy: false, preview: null, job: null, jobId: "", pollTimer: null,
  notice: "", error: "", confirm: false, activeUploads: 0, seq: 0, pollSeq: 0, restored: false,
};
const settingsState = {
  data: null, loaded: false, loading: false, error: "", busy: {},
};
let activeToolTab = "diagnostics";
try {
  const savedToolTab = storedSetting("managerToolTab");
  if (savedToolTab) activeToolTab = savedToolTab;
} catch (e) {}

function closeModal(id) {
  const node = document.getElementById(id);
  if (!node) return;
  const previous = node._previousFocus;
  node.remove();
  if (previous && previous.isConnected) previous.focus();
}

function openModal(id, cardClass, onClose, label) {
  closeModal(id);
  const backdrop = el("div", "modal-backdrop");
  backdrop.id = id;
  backdrop._previousFocus = document.activeElement;
  const dialog = el("div", "modal-card" + (cardClass ? " " + cardClass : ""));
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  if (label) dialog.setAttribute("aria-label", label);
  dialog.tabIndex = -1;
  backdrop.appendChild(dialog);
  backdrop.onclick = (event) => { if (event.target === backdrop) onClose(); };
  document.body.appendChild(backdrop);
  dialog.focus();
  return dialog;
}

