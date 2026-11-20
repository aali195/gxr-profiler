"use strict";

const filesState = {
  path: "/sdcard",
  data: null,
  loading: false,
  error: "",
  seq: 0,
  selected: new Set(),
  uploads: [],
  downloads: [],
  transferSeq: 0,
  busy: false,
  root: false,
  rootBusy: false,
  historyStarted: false,
  pendingHistoryPath: null,
};

function filesFormatSize(bytes) {
  if (bytes == null || isNaN(bytes)) return "--";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

function filesKindLabel(kind) {
  if (kind === "dir") return "Folder";
  if (kind === "file") return "File";
  if (kind === "link") return "Link";
  return "Other";
}

function filesRenderIfActive() {
  if (activeTab === "tools" && activeToolTab === "files") renderActiveToolBody();
}

function filesCrumbs(path) {
  const parts = (path || "/").split("/").filter(Boolean);
  const crumbs = [{ label: "/", path: "/" }];
  let current = "";
  parts.forEach(part => {
    current += "/" + part;
    crumbs.push({ label: part, path: current });
  });
  return crumbs;
}

function filesSelectedEntries() {
  const entries = (filesState.data && filesState.data.entries) || [];
  return entries.filter(entry => filesState.selected.has(entry.path));
}

function filesEnsureLoaded() {
  if (filesState.pendingHistoryPath) {
    const pending = filesState.pendingHistoryPath;
    filesState.pendingHistoryPath = null;
    filesLoad(pending, { fromHistory: true });
    return;
  }
  if (filesState.loading || filesState.error) return;
  if (filesState.data && filesState.data.path === filesState.path) return;
  filesLoad(filesState.path);
}

async function filesLoad(path, options) {
  const opts = options || {};
  const seq = ++filesState.seq;
  filesState.path = path;
  filesState.loading = true;
  filesState.error = "";
  filesRenderIfActive();
  try {
    const data = await jget("/api/files?path=" + encodeURIComponent(path));
    if (seq !== filesState.seq) return;
    filesState.data = data || null;
    filesState.root = !!(data && data.root);
    if (!opts.fromHistory) {
      if (!filesState.historyStarted) {
        history.pushState({ gxrFilesBase: true }, "");
        filesState.historyStarted = true;
      }
      history.pushState({ gxrFilesPath: path }, "");
    }
  } catch (e) {
    if (seq !== filesState.seq) return;
    filesState.data = null;
    filesState.error = e.message || String(e);
  } finally {
    if (seq === filesState.seq) {
      filesState.loading = false;
      filesRenderIfActive();
    }
  }
}

function filesReload() {
  return filesLoad(filesState.path, { fromHistory: true });
}

function filesRefresh() {
  if (filesState.loading) return;
  filesReload();
}

function filesNavigate(path) {
  if (filesState.loading) return;
  if (path === filesState.path && filesState.data) return;
  filesState.selected.clear();
  filesLoad(path);
}

async function filesMutate(url, body) {
  if (filesState.busy) return null;
  filesState.busy = true;
  filesRenderIfActive();
  try {
    return await jpost(url, body);
  } finally {
    filesState.busy = false;
    filesRenderIfActive();
  }
}

function filesToolButton(label, onClick, options) {
  const opts = options || {};
  const button = el("button", "toolbtn" + (opts.danger ? " danger" : ""), label);
  button.type = "button";
  button.disabled = !!opts.disabled;
  if (opts.title) button.title = opts.title;
  button.onclick = onClick;
  return button;
}

function filesHeaderCard() {
  const card = el("section", "card");
  const head = el("div", "appstoolhead");
  const copy = el("div");
  copy.appendChild(el("h3", null, "Files"));
  copy.appendChild(el("p", "muted cardnote", "Browse, download and manage files on the headset. Writes outside shared storage require root access."));
  head.appendChild(copy);
  card.appendChild(head);
  return card;
}

function filesToolbar() {
  const data = filesState.data;
  const writable = !!(data && data.writable);
  const selected = filesSelectedEntries();
  const disabled = filesState.busy || filesState.loading;
  const toolbar = el("div", "files-toolbar");

  toolbar.appendChild(filesToolButton("Refresh", filesRefresh, { disabled: disabled }));
  toolbar.appendChild(filesToolButton("New folder", filesMkdir, {
    disabled: disabled || !writable,
    title: writable ? "Create a folder here" : "Enable root access to write here",
  }));
  toolbar.appendChild(filesToolButton("Upload", () => {
    const input = document.getElementById("files-upload-input");
    if (input) input.click();
  }, {
    disabled: disabled || !writable,
    title: writable ? "Upload files into this folder" : "Enable root access to write here",
  }));
  toolbar.appendChild(filesToolButton("Rename", filesRename, {
    disabled: disabled || selected.length !== 1 || !writable,
  }));
  toolbar.appendChild(filesToolButton("Move", filesMove, {
    disabled: disabled || !selected.length || !writable,
  }));
  toolbar.appendChild(filesToolButton("Delete", filesDelete, {
    disabled: disabled || !selected.length,
    danger: true,
  }));

  const root = filesToolButton(
    filesState.root ? "Root: on" : "Root: off",
    filesToggleRoot,
    { disabled: disabled || filesState.rootBusy, danger: filesState.root }
  );
  root.setAttribute("aria-pressed", String(filesState.root));
  toolbar.appendChild(root);

  const uploadInput = document.createElement("input");
  uploadInput.type = "file";
  uploadInput.multiple = true;
  uploadInput.id = "files-upload-input";
  uploadInput.hidden = true;
  uploadInput.onchange = () => {
    const files = Array.from(uploadInput.files || []);
    uploadInput.value = "";
    if (files.length) filesUpload(files);
  };
  toolbar.appendChild(uploadInput);
  return toolbar;
}

function filesRootBanner() {
  const card = el("section", "card files-root-banner");
  card.appendChild(el("strong", null, "Root access is enabled."));
  card.appendChild(el("p", "muted cardnote", "File operations can now change system paths. The toggle resets when the manager restarts."));
  return card;
}

function filesPathCard() {
  const card = el("section", "card");
  const data = filesState.data;
  const parent = data && data.parent;
  const row = el("div", "files-pathrow");
  const home = filesToolButton("Home", () => filesNavigate("/sdcard"), {
    disabled: filesState.loading || filesState.path === "/sdcard",
    title: "Go to /sdcard",
  });
  row.appendChild(home);
  const up = filesToolButton("Up", () => { if (parent) filesNavigate(parent); }, {
    disabled: filesState.loading || !parent,
  });
  up.classList.add("files-up");
  row.appendChild(up);

  const crumbs = el("nav", "files-crumbs");
  crumbs.setAttribute("aria-label", "Current folder");
  filesCrumbs(filesState.path).forEach(crumb => {
    const button = el("button", "files-crumb", crumb.label);
    button.type = "button";
    button.disabled = filesState.loading;
    button.onclick = () => filesNavigate(crumb.path);
    crumbs.appendChild(button);
  });
  row.appendChild(crumbs);
  card.appendChild(row);

  const form = el("form", "files-pathform");
  const input = document.createElement("input");
  input.type = "text";
  input.className = "files-pathinput";
  input.value = filesState.path;
  input.setAttribute("aria-label", "Folder path");
  input.spellcheck = false;
  const go = el("button", "toolbtn", "Go");
  go.type = "submit";
  go.disabled = filesState.loading;
  form.onsubmit = event => {
    event.preventDefault();
    const value = input.value.trim();
    if (value) filesNavigate(value);
  };
  form.appendChild(input);
  form.appendChild(go);
  card.appendChild(form);
  card.appendChild(filesToolbar());
  return card;
}

function filesErrorCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Files unavailable"));
  card.appendChild(textEl("p", "muted", filesState.error));
  const retry = filesToolButton("Retry", filesReload);
  card.appendChild(retry);
  return card;
}

function filesUploadsCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Uploads"));
  filesState.uploads.forEach(upload => {
    const row = el("div", "files-uploadrow");
    row.dataset.transferId = "upload:" + upload.id;
    const name = textEl("div", "files-uploadname", upload.name);
    row.appendChild(name);
    const track = el("div", "files-progress");
    const fill = el("i", "");
    fill.style.width = Math.round((upload.progress || 0) * 100) + "%";
    track.appendChild(fill);
    row.appendChild(track);
    const status = textEl("div", "muted files-uploadstatus", upload.status || "");
    row.appendChild(status);
    card.appendChild(row);
  });
  return card;
}

function filesDownloadsCard() {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Downloads"));
  filesState.downloads.forEach(download => {
    const row = el("div", "files-downloadrow");
    row.dataset.transferId = "download:" + download.id;
    row.appendChild(textEl("div", "files-downloadname", download.name));
    const track = el("div", "files-progress" + (download.indeterminate ? " indeterminate" : ""));
    const fill = el("i", "");
    if (!download.indeterminate) fill.style.width = Math.round((download.progress || 0) * 100) + "%";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(textEl("div", "muted files-downloadstatus", download.status || ""));
    card.appendChild(row);
  });
  return card;
}

function filesProgressRowUpdate(kind, item) {
  const now = Date.now();
  if (item._lastRowAt && now - item._lastRowAt < 100) return;
  item._lastRowAt = now;
  filesUpdateTransferRow(kind, item);
}

function filesUpdateTransferRow(kind, item) {
  const row = document.querySelector('[data-transfer-id="' + kind + ":" + item.id + '"]');
  if (!row) return;
  const track = row.querySelector(".files-progress");
  const fill = row.querySelector(".files-progress i");
  const status = row.querySelector(".files-uploadstatus, .files-downloadstatus");
  if (!track || !fill) return;
  if (item.indeterminate) {
    track.classList.add("indeterminate");
    fill.style.width = "";
  } else {
    track.classList.remove("indeterminate");
    fill.style.width = Math.round((item.progress || 0) * 100) + "%";
  }
  if (status) status.textContent = item.status || "";
}

function filesTableCard() {
  const card = el("section", "card");
  if (filesState.loading && !filesState.data) {
    card.appendChild(el("div", "muted", "Loading folder..."));
    return card;
  }
  if (!filesState.data) {
    card.appendChild(el("div", "muted", "No folder is loaded."));
    return card;
  }
  const entries = filesState.data.entries || [];
  if (!entries.length) {
    card.appendChild(el("div", "muted", "This folder is empty."));
    return card;
  }
  const table = el("table", "filestable");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["", "Name", "Type", "Size", "Modified", ""].forEach(label => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  entries.forEach(entry => {
    const tr = document.createElement("tr");
    if (filesState.selected.has(entry.path)) tr.classList.add("selected");

    const checkCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = filesState.selected.has(entry.path);
    checkbox.setAttribute("aria-label", "Select " + entry.name);
    checkbox.onchange = () => {
      if (checkbox.checked) filesState.selected.add(entry.path);
      else filesState.selected.delete(entry.path);
      filesRenderIfActive();
    };
    checkCell.appendChild(checkbox);
    tr.appendChild(checkCell);

    const nameCell = document.createElement("td");
    const nameButton = el("button", "files-namebtn" + (entry.kind === "dir" ? " is-dir" : ""));
    nameButton.type = "button";
    nameButton.appendChild(el("span", "files-kindtag", entry.kind === "dir" ? "DIR" : entry.kind === "link" ? "LINK" : "FILE"));
    nameButton.appendChild(textEl("span", "files-entryname", entry.name));
    nameButton.title = entry.kind === "link" && entry.target ? entry.name + " -> " + entry.target : entry.path;
    nameButton.onclick = () => {
      if (entry.kind === "dir") filesNavigate(entry.path);
      else filesDownload(entry);
    };
    nameCell.appendChild(nameButton);
    tr.appendChild(nameCell);

    const typeCell = document.createElement("td");
    typeCell.textContent = filesKindLabel(entry.kind);
    tr.appendChild(typeCell);

    const sizeCell = document.createElement("td");
    sizeCell.className = "files-size";
    sizeCell.textContent = entry.kind === "dir" ? "--" : filesFormatSize(entry.size);
    tr.appendChild(sizeCell);

    const modifiedCell = document.createElement("td");
    modifiedCell.className = "files-modified";
    modifiedCell.textContent = entry.modified || "--";
    tr.appendChild(modifiedCell);

    const actionCell = document.createElement("td");
    if (entry.kind !== "dir") {
      const download = el("button", "toolbtn small", "Download");
      download.type = "button";
      download.onclick = () => filesDownload(entry);
      actionCell.appendChild(download);
    }
    tr.appendChild(actionCell);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  card.appendChild(table);
  return card;
}

function renderFilesTool(host) {
  host.innerHTML = "";
  if (OFFLINE) {
    const card = el("section", "card");
    card.appendChild(el("h3", null, "Files"));
    card.appendChild(el("div", "muted", "File management is not available in offline reports."));
    host.appendChild(card);
    return;
  }
  host.appendChild(filesHeaderCard());
  if (filesState.root) host.appendChild(filesRootBanner());
  if (filesState.error) host.appendChild(filesErrorCard());
  host.appendChild(filesPathCard());
  if (filesState.uploads.length) host.appendChild(filesUploadsCard());
  if (filesState.downloads.length) host.appendChild(filesDownloadsCard());
  host.appendChild(filesTableCard());
  filesEnsureLoaded();
}

function filesModal(title, message) {
  const dialog = openModal("files-modal", "files-modal-card", () => {}, title);
  dialog.appendChild(el("h3", null, title));
  if (message) dialog.appendChild(textEl("p", "muted", message));
  return dialog;
}

function filesActionRow(dialog, confirm, onCancel) {
  const row = el("div", "files-modalactions");
  const cancel = el("button", "toolbtn", "Cancel");
  cancel.type = "button";
  cancel.onclick = onCancel;
  row.appendChild(cancel);
  row.appendChild(confirm);
  dialog.appendChild(row);
}

function filesConfirm(options) {
  return new Promise(resolve => {
    let settled = false;
    const done = value => {
      if (settled) return;
      settled = true;
      closeModal("files-modal");
      resolve(value);
    };
    const dialog = filesModal(options.title, options.message);
    dialog.parentElement.onclick = event => { if (event.target === dialog.parentElement) done(false); };
    dialog.onkeydown = event => { if (event.key === "Escape") done(false); };
    let input = null;
    if (options.requireText) {
      input = document.createElement("input");
      input.type = "text";
      input.className = "files-pathinput";
      input.placeholder = options.requireText;
      input.setAttribute("aria-label", options.requireText);
      dialog.appendChild(input);
    }
    const confirm = el("button", "primary" + (options.danger ? " danger" : ""), options.confirmLabel || "Confirm");
    confirm.type = "button";
    confirm.disabled = !!options.requireText;
    if (input) {
      input.oninput = () => {
        confirm.disabled = input.value.trim().toUpperCase() !== String(options.requireText).toUpperCase();
      };
      input.onkeydown = event => {
        if (event.key === "Enter" && !confirm.disabled) done(true);
        if (event.key === "Escape") done(false);
      };
    }
    confirm.onclick = () => { if (!confirm.disabled) done(true); };
    filesActionRow(dialog, confirm, () => done(false));
    dialog.focus();
    if (input) input.focus();
  });
}

function filesPrompt(title, label, value) {
  return new Promise(resolve => {
    let settled = false;
    const done = result => {
      if (settled) return;
      settled = true;
      closeModal("files-modal");
      resolve(result);
    };
    const dialog = filesModal(title);
    dialog.parentElement.onclick = event => { if (event.target === dialog.parentElement) done(null); };
    dialog.onkeydown = event => { if (event.key === "Escape") done(null); };
    const field = document.createElement("label");
    field.className = "files-field";
    field.appendChild(textEl("span", null, label));
    const input = document.createElement("input");
    input.type = "text";
    input.className = "files-pathinput";
    input.value = value || "";
    input.spellcheck = false;
    input.onkeydown = event => {
      if (event.key === "Enter") done(input.value.trim() || null);
      if (event.key === "Escape") done(null);
    };
    field.appendChild(input);
    dialog.appendChild(field);
    const confirm = el("button", "primary", "OK");
    confirm.type = "button";
    confirm.disabled = !input.value.trim();
    input.oninput = () => { confirm.disabled = !input.value.trim(); };
    confirm.onclick = () => { if (!confirm.disabled) done(input.value.trim()); };
    filesActionRow(dialog, confirm, () => done(null));
    setTimeout(() => { input.focus(); input.select(); }, 0);
  });
}

async function filesNativeDownload(entry) {
  const response = await fetch("/api/files/download-ticket", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-GXR-Profiler-Token": API_TOKEN },
    body: JSON.stringify({ path: entry.path }),
  });
  if (!response.ok) {
    let detail = "download failed";
    try { detail = (await response.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  const ticket = await response.json();
  const link = document.createElement("a");
  link.href = ticket.url;
  link.download = ticket.name || entry.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  showToast({ title: "Download started", message: "Choose a location in the save dialog if prompted.", type: "success" });
}

async function filesStreamDownload(entry, onChunk) {
  const response = await fetch("/api/files/download?path=" + encodeURIComponent(entry.path), {
    headers: { "X-GXR-Profiler-Token": API_TOKEN },
  });
  if (!response.ok) {
    let detail = "download failed";
    try { detail = (await response.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (!response.body) throw new Error("download stream is unavailable");
  const total = Number(response.headers.get("Content-Length")) || 0;
  const reader = response.body.getReader();
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.length;
    await onChunk(value, total ? received / total : null);
  }
  return received;
}

async function filesDownload(entry) {
  const download = { id: ++filesState.transferSeq, name: entry.name, progress: 0, indeterminate: false, status: "Starting..." };
  filesState.downloads.push(download);
  filesRenderIfActive();
  let removeDelay = 900;
  try {
    if (!window.showSaveFilePicker) {
      download.indeterminate = true;
      download.status = "Choose a save location...";
      filesUpdateTransferRow("download", download);
      await filesNativeDownload(entry);
      download.status = "In progress";
      filesUpdateTransferRow("download", download);
      removeDelay = 12000;
      return;
    }
    let handle;
    try {
      handle = await window.showSaveFilePicker({ suggestedName: entry.name });
    } catch (e) {
      if (e && e.name === "AbortError") {
        download.status = "Cancelled";
        filesUpdateTransferRow("download", download);
        return;
      }
      throw e;
    }
    const writable = await handle.createWritable();
    await filesStreamDownload(entry, async (chunk, progress) => {
      await writable.write(chunk);
      if (progress == null) {
        download.indeterminate = true;
        download.status = "In progress";
      } else {
        download.progress = progress;
        download.status = Math.round(progress * 100) + "%";
      }
      filesProgressRowUpdate("download", download);
    });
    await writable.close();
    download.progress = 1;
    download.status = "Done";
    filesUpdateTransferRow("download", download);
    showToast({ title: "Downloaded", message: entry.name, type: "success" });
  } catch (e) {
    if (e && e.name === "AbortError") {
      download.status = "Cancelled";
    } else {
      download.status = "Failed";
      showToast({ title: "Download failed", message: e.message || String(e), type: "error" });
    }
    filesUpdateTransferRow("download", download);
  } finally {
    setTimeout(() => {
      filesState.downloads = filesState.downloads.filter(item => item !== download);
      filesRenderIfActive();
    }, removeDelay);
  }
}

function filesUploadRequest(file, destination, overwrite, onProgress, onSent) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const url = "/api/files/upload?path=" + encodeURIComponent(destination) +
      "&name=" + encodeURIComponent(file.name) + (overwrite ? "&overwrite=true" : "");
    let sent = false;
    const markSent = () => {
      if (sent) return;
      sent = true;
      onSent();
    };
    xhr.open("POST", url);
    xhr.setRequestHeader("X-GXR-Profiler-Token", API_TOKEN);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      onProgress(event.loaded / event.total);
      if (event.loaded >= event.total) markSent();
    };
    xhr.upload.onload = markSent;
    xhr.onerror = () => reject(new Error("upload failed"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        let data = {};
        try { data = JSON.parse(xhr.responseText || "{}"); } catch (e) {}
        resolve(data);
        return;
      }
      let detail = "upload failed";
      try { detail = JSON.parse(xhr.responseText).detail || detail; } catch (e) {}
      const error = new Error(detail);
      error.status = xhr.status;
      reject(error);
    };
    xhr.send(file);
  });
}

async function filesUploadOne(file, destination) {
  const upload = { id: ++filesState.transferSeq, name: file.name, progress: 0, status: "Uploading..." };
  filesState.uploads.push(upload);
  filesRenderIfActive();
  const reportProgress = progress => {
    upload.progress = Math.min(0.85, progress * 0.85);
    upload.status = "Uploading...";
    filesProgressRowUpdate("upload", upload);
  };
  const reportSent = () => {
    upload.progress = 0.9;
    upload.status = "Writing to headset...";
    filesUpdateTransferRow("upload", upload);
  };
  try {
    try {
      await filesUploadRequest(file, destination, false, reportProgress, reportSent);
    } catch (error) {
      if (error.status === 409 && !/recording/i.test(error.message)) {
        const replace = await filesConfirm({
          title: "Replace existing file?",
          message: file.name + " already exists in this folder.",
          confirmLabel: "Replace",
          danger: true,
        });
        if (!replace) {
          upload.status = "Cancelled";
          filesUpdateTransferRow("upload", upload);
          return;
        }
        await filesUploadRequest(file, destination, true, reportProgress, reportSent);
      } else {
        throw error;
      }
    }
    upload.status = "Done";
    upload.progress = 1;
    filesUpdateTransferRow("upload", upload);
    showToast({ title: "Uploaded", message: file.name, type: "success" });
  } catch (error) {
    upload.status = "Failed";
    filesUpdateTransferRow("upload", upload);
    showToast({ title: "Upload failed", message: error.message || String(error), type: "error" });
  } finally {
    setTimeout(() => {
      filesState.uploads = filesState.uploads.filter(item => item !== upload);
      filesRenderIfActive();
    }, 700);
  }
}

async function filesUpload(files) {
  const destination = filesState.path;
  for (const file of files) {
    await filesUploadOne(file, destination);
  }
  filesState.selected.clear();
  filesReload();
}

async function filesToggleRoot() {
  if (filesState.rootBusy) return;
  const enable = !filesState.root;
  const confirmed = await filesConfirm({
    title: enable ? "Enable root access?" : "Disable root access?",
    message: enable
      ? "Root access lets the file explorer read and write system paths. It is reset when the manager restarts."
      : "Root access will be disabled. Writes are limited to shared storage again.",
    confirmLabel: enable ? "Enable root" : "Disable root",
    danger: enable,
  });
  if (!confirmed) return;
  filesState.rootBusy = true;
  filesRenderIfActive();
  try {
    const result = await jpost("/api/files/root", { enabled: enable });
    filesState.root = !!(result && result.enabled);
    showToast({ title: filesState.root ? "Root enabled" : "Root disabled", type: "info" });
    filesReload();
  } catch (error) {
    showToast({ title: "Could not change root access", message: error.message || String(error), type: "error" });
  } finally {
    filesState.rootBusy = false;
    filesRenderIfActive();
  }
}

async function filesMkdir() {
  const name = await filesPrompt("New folder", "Folder name", "");
  if (!name) return;
  try {
    const result = await filesMutate("/api/files/mkdir", { path: filesState.path, name });
    if (result === null) return;
    showToast({ title: "Folder created", message: name, type: "success" });
    filesState.selected.clear();
    filesReload();
  } catch (error) {
    showToast({ title: "Could not create folder", message: error.message || String(error), type: "error" });
  }
}

async function filesRename() {
  const selected = filesSelectedEntries();
  if (selected.length !== 1) return;
  const entry = selected[0];
  const name = await filesPrompt("Rename", "New name", entry.name);
  if (!name || name === entry.name) return;
  try {
    const result = await filesMutate("/api/files/rename", { path: entry.path, name });
    if (result === null) return;
    showToast({ title: "Renamed", message: name, type: "success" });
    filesState.selected.clear();
    filesReload();
  } catch (error) {
    showToast({ title: "Could not rename", message: error.message || String(error), type: "error" });
  }
}

async function filesMove() {
  const selected = filesSelectedEntries();
  if (!selected.length) return;
  const destination = await filesPrompt("Move", "Destination folder", filesState.path);
  if (!destination) return;
  try {
    const results = await filesMutate("/api/files/move", {
      paths: selected.map(entry => entry.path),
      destination,
      overwrite: false,
    });
    if (results === null) return;
    const failed = (results || []).filter(item => !item.ok);
    if (failed.length) showToast({ title: "Some items were not moved", message: failed.map(item => item.error).join("\n"), type: "error" });
    else showToast({ title: "Moved", message: selected.length + " item(s)", type: "success" });
    filesState.selected.clear();
    filesReload();
  } catch (error) {
    if (/already exists/i.test(error.message || "")) {
      const replace = await filesConfirm({
        title: "Replace existing items?",
        message: "One or more items already exist in the destination folder.",
        confirmLabel: "Replace",
        danger: true,
      });
      if (replace) {
        try {
          await filesMutate("/api/files/move", {
            paths: selected.map(entry => entry.path),
            destination,
            overwrite: true,
          });
          filesState.selected.clear();
          filesReload();
          return;
        } catch (retryError) {
          showToast({ title: "Could not move", message: retryError.message || String(retryError), type: "error" });
          return;
        }
      }
    } else {
      showToast({ title: "Could not move", message: error.message || String(error), type: "error" });
    }
  }
}

async function filesDelete() {
  const selected = filesSelectedEntries();
  if (!selected.length) return;
  const hasFolder = selected.some(entry => entry.kind === "dir");
  const message = "Delete " + selected.length + " item(s)?" +
    (hasFolder ? "\n\nFolders and everything inside them will be removed." : "");
  const confirmed = await filesConfirm({
    title: "Delete files?",
    message,
    confirmLabel: "Delete",
    danger: true,
    requireText: filesState.root ? "DELETE" : "",
  });
  if (!confirmed) return;
  try {
    const results = await filesMutate("/api/files/delete", {
      paths: selected.map(entry => entry.path),
      recursive: hasFolder,
      confirm: filesState.root ? "DELETE" : "",
    });
    if (results === null) return;
    const failed = (results || []).filter(item => !item.ok);
    if (failed.length) showToast({ title: "Some items were not deleted", message: failed.map(item => item.error).join("\n"), type: "error" });
    else showToast({ title: "Deleted", message: selected.length + " item(s)", type: "success" });
    filesState.selected.clear();
    filesReload();
  } catch (error) {
    showToast({ title: "Could not delete", message: error.message || String(error), type: "error" });
  }
}

window.addEventListener("popstate", event => {
  const state = event.state || {};
  if (!state.gxrFilesPath) return;
  if (activeToolTab !== "files") {
    filesState.pendingHistoryPath = state.gxrFilesPath;
    if (typeof setToolTab === "function") setToolTab("files");
    return;
  }
  filesLoad(state.gxrFilesPath, { fromHistory: true });
});
