"use strict";

function appsInstallSize(bytes) {
  const value = Number(bytes) || 0;
  if (value >= 1024 ** 3) return (value / 1024 ** 3).toFixed(2) + " GB";
  if (value >= 1024 ** 2) return (value / 1024 ** 2).toFixed(1) + " MB";
  if (value >= 1024) return (value / 1024).toFixed(0) + " KB";
  return value.toLocaleString() + " B";
}

function appsInstallReset(keepJob = false) {
  appsInstallState.view = "files";
  appsInstallState.items = [];
  appsInstallState.uploads = [];
  appsInstallState.obbPackages = {};
  appsInstallState.options = { replace: true, allow_downgrade: false, grant_permissions: false };
  appsInstallState.busy = false;
  appsInstallState.preview = null;
  appsInstallState.notice = "";
  appsInstallState.error = "";
  appsInstallState.confirm = false;
  appsInstallState.activeUploads = 0;
  if (!keepJob) {
    appsInstallState.job = null;
    appsInstallState.jobId = "";
    appsInstallStopPolling();
  }
}

function appsInstallAbortUploads() {
  appsInstallState.uploads.forEach(upload => {
    upload.cancelled = true;
    if (upload.xhr) {
      try { upload.xhr.abort(); } catch (e) {}
    }
  });
}

async function appsInstallDiscardAll() {
  if (appsInstallState.job && appsInstallState.job.status === "running") return;
  if (!window.confirm("Discard all staged install files?")) return;
  appsInstallAbortUploads();
  try {
    await jdel("/api/apps/install/stage");
  } catch (e) {
    showToast({
      title: "Could not discard staged files",
      message: e.message || String(e),
      type: "error",
    });
    return;
  }
  appsInstallReset();
  renderInstaller();
}

function renderInstaller() {
  if (activeTab === "tools" && activeToolTab === "installer") renderActiveToolBody();
}

async function appsInstallRestore() {
  if (appsInstallState.restored) return;
  appsInstallState.restored = true;
  try {
    const state = await jget("/api/apps/install/state");
    if (!appsInstallState.items.length && !appsInstallState.uploads.length) {
      appsInstallState.items = state.files || [];
    }
    const job = state.job || null;
    if (job) {
      appsInstallState.job = job;
      appsInstallState.jobId = job.id;
      if (job.status === "running") {
        appsInstallState.view = "progress";
        appsInstallStartPolling();
      } else {
        appsInstallState.view = "result";
      }
    } else if (appsInstallState.items.length) {
      appsInstallState.view = "files";
    }
    renderInstaller();
  } catch (e) {
    appsInstallState.restored = false;
    showToast({
      title: "Could not restore installer state",
      message: e.message || String(e),
      type: "warning",
    });
  }
}

function installerHeaderCard() {
  const card = el("section", "card");
  const head = el("div", "appstoolhead");
  const copy = el("div");
  copy.appendChild(el("h3", null, "Installer"));
  copy.appendChild(el("p", "muted cardnote", "Install APK, OBB or XAPK files on the connected headset. Files are staged and hashed locally, reviewed, then installed for user 0 after confirmation. Critical system packages are blocked."));
  head.appendChild(copy);
  const actions = el("div", "appstoolactions");
  const discard = el("button", "toolbtn danger", "Discard staged files");
  discard.type = "button";
  discard.disabled = !!(appsInstallState.job && appsInstallState.job.status === "running");
  discard.title = discard.disabled ? "Cannot discard staged files while an install is running" : "Discard all staged files";
  discard.onclick = appsInstallDiscardAll;
  actions.appendChild(discard);
  head.appendChild(actions);
  card.appendChild(head);
  return card;
}

function renderInstallerTool(host) {
  host.innerHTML = "";
  if (OFFLINE) {
    const card = el("section", "card");
    card.appendChild(el("h3", null, "Installer"));
    card.appendChild(el("div", "muted", "The installer is not available in offline reports."));
    host.appendChild(card);
    return;
  }
  host.appendChild(installerHeaderCard());
  if (!appsInstallState.restored) appsInstallRestore();
  const card = el("section", "card");
  if (appsInstallState.view === "review") {
    card.appendChild(appsInstallReviewView());
  } else if (appsInstallState.view === "progress" || appsInstallState.view === "result") {
    card.appendChild(appsInstallProgressView());
  } else {
    card.appendChild(appsInstallFilesView());
  }
  host.appendChild(card);
}

function appsInstallFileInputs() {
  const wrap = el("span", "install-inputs");
  const files = document.createElement("input");
  files.type = "file";
  files.multiple = true;
  files.accept = ".apk,.obb,.xapk";
  files.hidden = true;
  files.onchange = () => {
    appsInstallAddFiles([...files.files].map(file => ({ file, relativePath: file.webkitRelativePath || "" })));
    files.value = "";
  };
  const folder = document.createElement("input");
  folder.type = "file";
  folder.multiple = true;
  folder.webkitdirectory = true;
  folder.hidden = true;
  folder.onchange = () => {
    appsInstallAddFiles([...folder.files].map(file => ({ file, relativePath: file.webkitRelativePath || "" })));
    folder.value = "";
  };
  wrap.appendChild(files);
  wrap.appendChild(folder);
  return { wrap, files, folder };
}

function appsInstallFilesView() {
  const wrap = el("div", "install-body");
  wrap.appendChild(textEl("p", "modal-desc", "Choose APK, OBB, or XAPK files, or drop a game folder. Split APKs are grouped by package; OBB files are matched to their package automatically. Installs target user 0."));
  const inputs = appsInstallFileInputs();
  const drop = el("div", "install-drop");
  drop.title = "Choose APK, OBB, or XAPK files";
  drop.appendChild(textEl("div", "install-drop-title", "Drop APK, XAPK, or OBB files here"));
  drop.appendChild(textEl("div", "muted", "A whole folder is fine; unrelated files are ignored."));
  const buttons = el("div", "install-drop-actions");
  const chooseFiles = el("button", "toolbtn", "Choose files");
  chooseFiles.type = "button";
  chooseFiles.onclick = event => { event.stopPropagation(); inputs.files.click(); };
  const chooseFolder = el("button", "toolbtn", "Choose folder");
  chooseFolder.type = "button";
  chooseFolder.onclick = event => { event.stopPropagation(); inputs.folder.click(); };
  buttons.appendChild(chooseFiles);
  buttons.appendChild(chooseFolder);
  drop.appendChild(buttons);
  drop.onclick = () => inputs.files.click();
  drop.addEventListener("dragover", event => {
    event.preventDefault();
    drop.classList.add("dragging");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
  drop.addEventListener("drop", event => {
    event.preventDefault();
    drop.classList.remove("dragging");
    appsInstallDrop(event);
  });
  wrap.appendChild(inputs.wrap);
  wrap.appendChild(drop);

  if (appsInstallState.notice) {
    wrap.appendChild(textEl("p", "install-note", appsInstallState.notice));
  }
  if (appsInstallState.error) {
    wrap.appendChild(textEl("p", "install-error", appsInstallState.error));
  }

  const pending = appsInstallState.uploads;
  if (pending.length) {
    const list = el("div", "install-list");
    pending.forEach(upload => {
      const row = el("div", "install-row upload");
      row.dataset.installUpload = upload.key;
      row.appendChild(textEl("span", "install-type", "UPLOAD"));
      const main = el("div", "install-main");
      main.appendChild(textEl("div", "install-name", upload.name));
      const track = el("div", "install-progress");
      const fill = el("div", "install-progress-fill");
      fill.style.width = Math.round((upload.progress || 0) * 100) + "%";
      track.appendChild(fill);
      main.appendChild(track);
      const label = el("div", "install-progress-label muted");
      label.textContent = upload.status === "error"
        ? upload.error
        : Math.round((upload.progress || 0) * 100) + "% of " + appsInstallSize(upload.size);
      main.appendChild(label);
      row.appendChild(main);
      const uploadActions = el("div", "install-upload-actions");
      if (upload.status === "error") {
        const retry = el("button", "toolbtn", "Retry");
        retry.type = "button";
        retry.onclick = () => {
          upload.status = "queued";
          upload.error = "";
          upload.progress = 0;
          renderInstaller();
          appsInstallPumpUploads();
        };
        uploadActions.appendChild(retry);
      }
      const removeUpload = el("button", "toolbtn danger", "Remove");
      removeUpload.type = "button";
      removeUpload.onclick = () => {
        upload.cancelled = true;
        if (upload.xhr) {
          try { upload.xhr.abort(); } catch (e) {}
        }
        appsInstallState.uploads = appsInstallState.uploads.filter(item => item !== upload);
        renderInstaller();
        appsInstallPumpUploads();
      };
      uploadActions.appendChild(removeUpload);
      row.appendChild(uploadActions);
      if (upload.status === "error") {
        row.appendChild(textEl("span", "badge bad", "Failed"));
      }
      list.appendChild(row);
    });
    wrap.appendChild(list);
  }

  if (appsInstallState.items.length) {
    const total = appsInstallState.items.reduce((sum, item) => sum + (Number(item.size) || 0), 0);
    const listHead = el("div", "install-listhead");
    listHead.appendChild(textEl("span", null, appsInstallState.items.length + " staged file" + (appsInstallState.items.length === 1 ? "" : "s") + " · " + appsInstallSize(total)));
    const clear = el("button", "toolbtn", "Remove all");
    clear.type = "button";
    clear.onclick = appsInstallRemoveAll;
    listHead.appendChild(clear);
    wrap.appendChild(listHead);
    const list = el("div", "install-list");
    let lastBundle = "";
    appsInstallState.items.forEach(item => {
      if (item.bundle_id && item.bundle_id !== lastBundle) {
        lastBundle = item.bundle_id;
        const bundleHead = el("div", "install-bundlehead");
        bundleHead.appendChild(textEl("span", null, "XAPK · " + (item.bundle_name || "bundle")));
        const removeBundle = el("button", "toolbtn", "Remove bundle");
        removeBundle.type = "button";
        removeBundle.onclick = () => appsInstallRemoveItem(item);
        bundleHead.appendChild(removeBundle);
        list.appendChild(bundleHead);
      }
      if (!item.bundle_id) lastBundle = "";
      const row = el("div", "install-row");
      const kind = item.kind === "obb" ? "OBB" : (item.readable === false ? "INVALID" : (item.split ? "SPLIT" : "APK"));
      row.appendChild(textEl(
        "span",
        "install-type " + (item.kind === "obb" ? "obb" : item.readable === false ? "bad" : "apk"),
        kind
      ));
      const main = el("div", "install-main");
      main.appendChild(textEl("div", "install-name", item.name));
      const meta = [];
      if (item.package) meta.push(item.package);
      else meta.push("package unknown");
      if (item.version_code != null) meta.push("v" + item.version_code);
      meta.push(appsInstallSize(item.size));
      if (item.sha256) meta.push("sha256 " + item.sha256.slice(0, 12) + "…");
      const metaEl = textEl("div", "install-meta", meta.join(" · "));
      if (item.sha256) metaEl.title = item.sha256;
      main.appendChild(metaEl);
      (item.warnings || []).forEach(warning => main.appendChild(textEl("div", "install-warning", warning)));
      if (item.kind === "obb") {
        const field = el("div", "install-pkgfield");
        field.appendChild(textEl("label", null, "Target package"));
        const input = document.createElement("input");
        input.type = "text";
        input.className = "install-pkginput";
        input.value = appsInstallState.obbPackages[item.id] || item.package || "";
        input.placeholder = "com.example.game";
        input.setAttribute("aria-label", "Target package for " + item.name);
        input.oninput = () => {
          appsInstallState.obbPackages[item.id] = input.value.trim();
        };
        field.appendChild(input);
        main.appendChild(field);
      }
      row.appendChild(main);
      const remove = el("button", "toolbtn danger", "Remove");
      remove.type = "button";
      remove.onclick = () => appsInstallRemoveItem(item);
      row.appendChild(remove);
      list.appendChild(row);
    });
    wrap.appendChild(list);
  }

  const options = el("div", "install-options");
  options.appendChild(el("div", "appsubhead", "Options"));
  const optionDefs = [
    ["replace", "Replace the existing app (adb -r)", true],
    ["allow_downgrade", "Allow a downgrade (adb -d)", false],
    ["grant_permissions", "Grant all runtime permissions (adb -g)", false],
  ];
  optionDefs.forEach(([key, label, defaultOn]) => {
    const check = el("label", "modal-check");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = appsInstallState.options[key] ?? defaultOn;
    box.onchange = () => { appsInstallState.options[key] = box.checked; };
    check.appendChild(box);
    check.appendChild(textEl("span", null, label));
    options.appendChild(check);
  });
  wrap.appendChild(options);
  wrap.appendChild(textEl("p", "muted install-safety", "APKs are not scanned for malware. Android verifies package signatures, but you should only install files you trust."));

  const actions = el("div", "modal-actions");
  if (appsInstallState.items.length || appsInstallState.uploads.length) {
    const discard = el("button", "toolbtn danger", "Discard staged files");
    discard.type = "button";
    discard.onclick = appsInstallDiscardAll;
    actions.appendChild(discard);
  }
  const review = el("button", "primary", appsInstallState.busy ? "Checking..." : "Review install");
  review.type = "button";
  review.disabled = appsInstallState.busy || !appsInstallState.items.length || appsInstallState.uploads.length > 0;
  review.onclick = appsInstallPreview;
  actions.appendChild(review);
  wrap.appendChild(actions);
  return wrap;
}

function appsInstallDrop(event) {
  const items = event.dataTransfer && event.dataTransfer.items;
  if (!items || !items.length || typeof items[0].webkitGetAsEntry !== "function") {
    const files = event.dataTransfer ? [...event.dataTransfer.files] : [];
    appsInstallAddFiles(files.map(file => ({ file, relativePath: file.webkitRelativePath || "" })));
    return;
  }
  const entries = [];
  for (const item of items) {
    const entry = item.webkitGetAsEntry();
    if (entry) entries.push(entry);
  }
  if (!entries.length) {
    const files = event.dataTransfer ? [...event.dataTransfer.files] : [];
    appsInstallAddFiles(files.map(file => ({ file, relativePath: file.webkitRelativePath || "" })));
    return;
  }
  const collected = [];
  Promise.all(entries.map(entry => appsInstallCollectEntry(entry, "", collected)))
    .then(() => appsInstallAddFiles(collected))
    .catch(error => showToast({ title: "Could not read the dropped folder", message: error.message || String(error), type: "error" }));
}

function appsInstallReadEntryFile(entry, prefix) {
  return new Promise((resolve, reject) => {
    entry.file(
      file => resolve({ file, relativePath: prefix + file.name }),
      reject
    );
  });
}

function appsInstallReadDirectory(reader) {
  return new Promise((resolve, reject) => {
    const all = [];
    const read = () => {
      reader.readEntries(batch => {
        if (!batch.length) {
          resolve(all);
          return;
        }
        all.push(...batch);
        read();
      }, reject);
    };
    read();
  });
}

async function appsInstallCollectEntry(entry, prefix, out) {
  if (entry.isFile) {
    out.push(await appsInstallReadEntryFile(entry, prefix));
    return;
  }
  if (entry.isDirectory) {
    const children = await appsInstallReadDirectory(entry.createReader());
    for (const child of children) {
      await appsInstallCollectEntry(child, prefix + entry.name + "/", out);
    }
  }
}

function appsInstallAddFiles(records) {
  let ignored = 0;
  let added = 0;
  records.forEach(record => {
    const file = record.file;
    if (!file) return;
    if (!file.size) {
      ignored++;
      return;
    }
    const name = file.name || "file";
    const dot = name.lastIndexOf(".");
    const suffix = dot >= 0 ? name.slice(dot).toLowerCase() : "";
    if (!INSTALL_ACCEPTED.has(suffix)) {
      ignored++;
      return;
    }
    const relativePath = record.relativePath || file.webkitRelativePath || "";
    const isObb = suffix === ".obb";
    const duplicate = appsInstallState.uploads.some(upload =>
      upload.name === name && upload.size === file.size
      && (!isObb || (upload.relativePath || "") === relativePath)
    ) || appsInstallState.items.some(item =>
      (item.name === name && item.size === file.size
        && (!isObb || (item.relative_path || "") === relativePath))
      || (item.bundle_id && item.bundle_name === name)
    );
    if (duplicate) {
      ignored++;
      return;
    }
    if (appsInstallState.items.length + appsInstallState.uploads.length >= 64) {
      ignored++;
      return;
    }
    const upload = {
      key: "u" + (++appsInstallState.seq),
      file,
      name,
      size: file.size,
      relativePath,
      progress: 0,
      status: "queued",
      error: "",
      xhr: null,
      cancelled: false,
    };
    appsInstallState.uploads.push(upload);
    added++;
  });
  if (ignored) {
    appsInstallState.notice = ignored + " file" + (ignored === 1 ? " was" : "s were")
      + " ignored (unsupported, duplicate, or over the 64-file batch limit).";
  } else if (added) {
    appsInstallState.notice = "";
  }
  if (added) {
    renderInstaller();
    appsInstallPumpUploads();
  } else if (ignored) {
    renderInstaller();
  }
}

function appsInstallPumpUploads() {
  while (appsInstallState.activeUploads < 2) {
    const next = appsInstallState.uploads.find(upload => upload.status === "queued");
    if (!next) break;
    appsInstallUpload(next);
  }
}

function appsInstallUpload(upload) {
  upload.status = "uploading";
  appsInstallState.activeUploads += 1;
  const xhr = new XMLHttpRequest();
  upload.xhr = xhr;
  const url = "/api/apps/install/stage?name=" + encodeURIComponent(upload.name)
    + "&path=" + encodeURIComponent(upload.relativePath || "");
  xhr.open("POST", url);
  xhr.setRequestHeader("X-GXR-Profiler-Token", API_TOKEN);
  xhr.setRequestHeader("Content-Type", "application/octet-stream");
  xhr.upload.onprogress = event => {
    if (event.lengthComputable) {
      upload.progress = event.loaded / event.total;
      const row = document.querySelector('[data-install-upload="' + upload.key + '"]');
      if (row) {
        const fill = row.querySelector(".install-progress-fill");
        if (fill) fill.style.width = Math.round(upload.progress * 100) + "%";
        const label = row.querySelector(".install-progress-label");
        if (label) label.textContent = Math.round(upload.progress * 100) + "% of " + appsInstallSize(upload.size);
      }
    }
  };
  xhr.upload.onload = () => {
    const row = document.querySelector('[data-install-upload="' + upload.key + '"]');
    const label = row && row.querySelector(".install-progress-label");
    if (label) label.textContent = "Processing on this PC…";
  };
  const finish = () => {
    appsInstallState.activeUploads = Math.max(0, appsInstallState.activeUploads - 1);
    upload.xhr = null;
  };
  xhr.onload = () => {
    finish();
    if (upload.cancelled) return;
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const result = JSON.parse(xhr.responseText || "{}");
        (result.files || []).forEach(item => {
          if (!appsInstallState.items.some(existing => existing.id === item.id)) {
            appsInstallState.items.push(item);
          }
        });
        if (result.warnings && result.warnings.length) {
          appsInstallState.notice = result.warnings.join(" ");
        }
        appsInstallState.uploads = appsInstallState.uploads.filter(item => item !== upload);
        appsInstallState.error = "";
      } catch (e) {
        upload.status = "error";
        upload.error = "the server returned an unreadable response";
      }
    } else {
      upload.status = "error";
      upload.error = appsInstallXhrError(xhr);
    }
    renderInstaller();
    appsInstallPumpUploads();
  };
  xhr.onerror = () => {
    finish();
    if (upload.cancelled) return;
    upload.status = "error";
    upload.error = "upload failed";
    renderInstaller();
    appsInstallPumpUploads();
  };
  xhr.onabort = () => {
    finish();
    upload.status = "cancelled";
    renderInstaller();
    appsInstallPumpUploads();
  };
  xhr.send(upload.file);
}

function appsInstallXhrError(xhr) {
  try {
    const data = JSON.parse(xhr.responseText || "{}");
    if (data && data.detail) return String(data.detail);
  } catch (e) {}
  return xhr.responseText || ("HTTP " + xhr.status);
}

async function appsInstallRemoveItem(item) {
  try {
    await jdel("/api/apps/install/stage/" + encodeURIComponent(item.bundle_id || item.id));
  } catch (e) {
    if (!/not found|already removed/i.test(e.message || String(e))) {
      showToast({ title: "Could not remove the file", message: e.message || String(e), type: "error" });
      return;
    }
  }
  const bundle = item.bundle_id;
  appsInstallState.items = appsInstallState.items.filter(existing => bundle ? existing.bundle_id !== bundle : existing.id !== item.id);
  Object.keys(appsInstallState.obbPackages).forEach(id => {
    if (!appsInstallState.items.some(existing => existing.id === id)) delete appsInstallState.obbPackages[id];
  });
  renderInstaller();
}

async function appsInstallRemoveAll() {
  if (!window.confirm("Remove all staged install files?")) return;
  appsInstallAbortUploads();
  appsInstallState.uploads = [];
  try {
    await jdel("/api/apps/install/stage");
  } catch (e) {
    showToast({ title: "Could not remove the staged files", message: e.message || String(e), type: "error" });
    return;
  }
  appsInstallState.items = [];
  appsInstallState.obbPackages = {};
  appsInstallState.notice = "";
  renderInstaller();
}

async function appsInstallPreview() {
  if (appsInstallState.busy || !appsInstallState.items.length || appsInstallState.uploads.length) return;
  appsInstallState.busy = true;
  appsInstallState.error = "";
  renderInstaller();
  try {
    const result = await jpost("/api/apps/install/preview", {
      items: appsInstallState.items.map(item => item.id),
      obb_packages: appsInstallState.obbPackages,
      options: appsInstallState.options,
    });
    appsInstallState.preview = result;
    appsInstallState.confirm = false;
    appsInstallState.view = "review";
  } catch (e) {
    appsInstallState.error = e.message || String(e);
    showToast({ title: "Could not review the install", message: appsInstallState.error, type: "error" });
  } finally {
    appsInstallState.busy = false;
    renderInstaller();
  }
}

function appsInstallReviewView() {
  const wrap = el("div", "install-body");
  const plan = appsInstallState.preview;
  if (!plan) {
    wrap.appendChild(textEl("p", "muted", "The install plan is no longer available."));
    return wrap;
  }
  wrap.appendChild(textEl("p", "modal-desc", "Review the files and commands. Nothing is installed until you press Install."));
  if (plan.errors && plan.errors.length) {
    const errors = el("div", "install-errors");
    plan.errors.forEach(error => errors.appendChild(textEl("p", "install-error", error)));
    wrap.appendChild(errors);
  }
  if (plan.warnings && plan.warnings.length) {
    const warnings = el("div", "install-warnings");
    plan.warnings.forEach(warning => warnings.appendChild(textEl("p", "install-warning", warning)));
    wrap.appendChild(warnings);
  }
  if (plan.groups && plan.groups.length) {
    plan.groups.forEach(group => {
      const box = el("div", "install-review-group");
      const title = el("div", "install-review-title");
      title.appendChild(textEl("b", null, group.package || "Selected APKs"));
      title.appendChild(textEl("span", "badge " + (group.split ? "sev-warning" : "good"), group.split ? "Split set" : "APK"));
      if (group.apk_count) title.appendChild(textEl("span", "muted", group.apk_count + " file" + (group.apk_count === 1 ? "" : "s")));
      box.appendChild(title);
      (group.files || []).forEach(file => {
        box.appendChild(textEl("div", "install-review-file", file.name + " · " + appsInstallSize(file.size)));
      });
      box.appendChild(copyablePre(group.command, "diag-evidence modal-command"));
      wrap.appendChild(box);
    });
  }
  if (plan.obb && plan.obb.length) {
    plan.obb.forEach(item => {
      const box = el("div", "install-review-group");
      const title = el("div", "install-review-title");
      title.appendChild(textEl("b", null, "OBB · " + item.package));
      title.appendChild(textEl("span", "muted", appsInstallSize(item.size)));
      box.appendChild(title);
      box.appendChild(textEl("div", "install-review-file", item.name));
      box.appendChild(textEl("div", "muted install-review-path", item.remote_path));
      box.appendChild(copyablePre(item.mkdir_command + "\n" + item.command, "diag-evidence modal-command"));
      wrap.appendChild(box);
    });
  }
  wrap.appendChild(textEl("p", "muted install-total", "Total staged size: " + appsInstallSize(plan.total_size || 0) + " · Installs target user 0."));
  const check = el("label", "modal-check");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = appsInstallState.confirm;
  box.onchange = () => {
    appsInstallState.confirm = box.checked;
    sync();
  };
  check.appendChild(box);
  check.appendChild(textEl("span", null, "I trust these files and understand they will be installed on the headset."));
  wrap.appendChild(check);
  const actions = el("div", "modal-actions");
  const back = el("button", "toolbtn", "Back");
  back.type = "button";
  back.onclick = () => {
    appsInstallState.view = "files";
    appsInstallState.error = "";
    renderInstaller();
  };
  const install = el("button", "primary", appsInstallState.busy ? "Starting..." : "Install");
  install.type = "button";
  function sync() {
    install.disabled = appsInstallState.busy || !plan.ok || !appsInstallState.confirm;
  }
  install.onclick = appsInstallStart;
  actions.appendChild(back);
  actions.appendChild(install);
  wrap.appendChild(actions);
  sync();
  return wrap;
}

async function appsInstallStart() {
  if (appsInstallState.busy || !appsInstallState.confirm) return;
  const plan = appsInstallState.preview;
  if (!plan || !plan.ok) return;
  appsInstallState.busy = true;
  appsInstallState.error = "";
  renderInstaller();
  try {
    const job = await jpost("/api/apps/install", {
      items: appsInstallState.items.map(item => item.id),
      obb_packages: appsInstallState.obbPackages,
      options: appsInstallState.options,
      confirm: true,
    });
    appsInstallState.job = job;
    appsInstallState.jobId = job.id;
    appsInstallState.view = "progress";
    appsInstallStartPolling();
  } catch (e) {
    appsInstallState.error = e.message || String(e);
    showToast({ title: "Install could not start", message: appsInstallState.error, type: "error" });
  } finally {
    appsInstallState.busy = false;
    renderInstaller();
  }
}

function appsInstallResultMessage(job) {
  const result = (job && job.result) || {};
  const parts = [];
  if (result.apk_count) parts.push(result.apk_count + " APK" + (result.apk_count === 1 ? "" : "s"));
  if (result.obb_count) parts.push(result.obb_count + " OBB" + (result.obb_count === 1 ? "" : "s"));
  const summary = parts.join(", ") || "Completed";
  const packages = (result.packages || []).join(", ");
  return packages ? packages + " — " + summary : summary;
}

function appsInstallStopPolling() {
  appsInstallState.pollSeq += 1;
  if (appsInstallState.pollTimer) {
    clearTimeout(appsInstallState.pollTimer);
    appsInstallState.pollTimer = null;
  }
}

function appsInstallStartPolling() {
  appsInstallStopPolling();
  const seq = appsInstallState.pollSeq;
  let pollFailures = 0;
  const tick = async () => {
    if (!appsInstallState.jobId || seq !== appsInstallState.pollSeq) return;
    try {
      const job = await jget("/api/apps/install/" + encodeURIComponent(appsInstallState.jobId));
      if (seq !== appsInstallState.pollSeq) return;
      pollFailures = 0;
      const changed = JSON.stringify(job) !== JSON.stringify(appsInstallState.job);
      appsInstallState.job = job;
      if (changed) {
        if (appsInstallState.view === "progress" && job.status !== "running") {
          appsInstallState.view = "result";
        }
        renderInstaller();
      }
      if (job.status === "running") {
        appsInstallState.pollTimer = setTimeout(tick, 900);
        return;
      }
      appsInstallStopPolling();
      if (job.status === "done") {
        appsInstallState.items = [];
        appsInstallState.uploads = [];
        appsInstallState.obbPackages = {};
        showToast({
          title: "Install completed",
          message: appsInstallResultMessage(job),
          type: "success",
        });
        appsFetch();
      } else {
        showToast({
          title: "Install failed",
          message: job.error || "The install did not complete.",
          type: "error",
          persistent: true,
        });
      }
      renderInstaller();
    } catch (e) {
      if (seq !== appsInstallState.pollSeq) return;
      pollFailures += 1;
      if (pollFailures >= 8) {
        appsInstallStopPolling();
        showToast({
          title: "Install status unavailable",
          message: e.message || String(e),
          type: "error",
          persistent: true,
        });
        return;
      }
      appsInstallState.pollTimer = setTimeout(tick, 1500);
    }
  };
  tick();
}

function appsInstallStepMark(status) {
  return ({ pending: "○", running: "…", done: "✓", error: "×" })[status] || "○";
}

function appsInstallProgressView() {
  const wrap = el("div", "install-body");
  const job = appsInstallState.job;
  if (!job) {
    wrap.appendChild(textEl("p", "muted", "No install job is available."));
    return wrap;
  }
  const summary = el("div", "install-result " + (job.status === "error" ? "failed" : job.status === "done" ? "done" : "running"));
  if (job.status === "done") {
    summary.appendChild(textEl("div", "install-result-title", "Install complete"));
    summary.appendChild(textEl("div", "install-result-text", appsInstallResultMessage(job)));
  } else if (job.status === "error") {
    summary.appendChild(textEl("div", "install-result-title", "Install failed"));
    summary.appendChild(textEl("div", "install-result-text", job.error || "The install did not complete."));
  } else {
    summary.appendChild(textEl("div", "install-result-title", "Installing…"));
    summary.appendChild(textEl("div", "install-result-text", "This can take several minutes for large OBB files. You can switch tabs; the install continues and reports through a notification."));
  }
  wrap.appendChild(summary);

  const steps = el("div", "install-steps");
  (job.steps || []).forEach(step => {
    const row = el("div", "install-step " + step.status);
    row.appendChild(textEl("span", "install-step-mark", appsInstallStepMark(step.status)));
    const body = el("div", "install-step-body");
    body.appendChild(textEl("div", "install-step-label", step.label));
    if (step.output) {
      body.appendChild(copyablePre(step.output, "diag-evidence install-output"));
    }
    row.appendChild(body);
    steps.appendChild(row);
  });
  wrap.appendChild(steps);

  if (job.status === "error" && job.error) {
    wrap.appendChild(copyablePre(job.error, "diag-evidence install-output"));
  }

  const actions = el("div", "modal-actions");
  if (job.status === "running") {
    const viewApps = el("button", "toolbtn", "View apps");
    viewApps.type = "button";
    viewApps.onclick = () => setToolTab("apps");
    actions.appendChild(viewApps);
  } else {
    if (job.status === "done" && job.result && job.result.packages && job.result.packages.length === 1) {
      const view = el("button", "toolbtn", "View package");
      view.type = "button";
      view.onclick = () => appsInstallViewPackage(job.result.packages[0]);
      actions.appendChild(view);
    }
    if (job.status === "done") {
      const done = el("button", "primary", "Done");
      done.type = "button";
      done.onclick = () => {
        appsInstallReset();
        renderInstaller();
      };
      actions.appendChild(done);
    } else {
      if (appsInstallState.items.length) {
        const retry = el("button", "toolbtn", "Retry");
        retry.type = "button";
        retry.onclick = () => {
          appsInstallState.job = null;
          appsInstallState.jobId = "";
          appsInstallState.view = "files";
          appsInstallPreview();
        };
        actions.appendChild(retry);
        const back = el("button", "toolbtn", "Back to files");
        back.type = "button";
        back.onclick = () => {
          appsInstallState.view = "files";
          renderInstaller();
        };
        actions.appendChild(back);
      }
      const discard = el("button", "toolbtn danger", "Discard files");
      discard.type = "button";
      discard.onclick = appsInstallDiscardAll;
      actions.appendChild(discard);
    }
  }
  wrap.appendChild(actions);
  return wrap;
}

async function appsInstallViewPackage(packageName) {
  await appsFetch();
  if (appsState.error) {
    showToast({
      title: "Could not refresh the package list",
      message: appsState.error,
      type: "error",
    });
    return;
  }
  const row = appsRows().find(item => item.package === packageName);
  if (!row) {
    showToast({
      title: "Package not found",
      message: packageName + " is not in the refreshed package list.",
      type: "warning",
    });
    return;
  }
  appsState.query = packageName;
  appsState.filter = "all";
  setToolTab("apps");
  selectApp(row);
}

