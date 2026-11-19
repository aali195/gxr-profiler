"use strict";

const TOAST_DEFAULT_MS = 7000;
const TOAST_WARNING_MS = 10000;
const TOAST_LONG_MS = 15000;
const TOAST_MAX_VISIBLE = 4;
const toastState = { seq: 0, items: new Map() };

function setToastOpen() {
  if (document.body) {
    document.body.classList.toggle("toast-open", toastState.items.size > 0);
  }
}

function scrollToLatestToast() {
  if ([...toastState.items.values()].some(item => item.hovered || item.focused)) return;
  const region = toastRegion();
  region.scrollTop = region.scrollHeight;
}

function toastRegion() {
  let region = document.getElementById("toast-region");
  if (!region) {
    region = document.createElement("div");
    region.id = "toast-region";
    region.className = "toast-region";
    region.setAttribute("role", "region");
    region.setAttribute("aria-label", "Notifications");
    document.body.appendChild(region);
  }
  return region;
}

function toastDefaultTitle(type) {
  return ({
    success: "Done",
    error: "Something went wrong",
    warning: "Warning",
    info: "Notice",
  })[type] || "Notice";
}

function startToast(entry) {
  if (entry.persistent || entry.remaining <= 0 || entry.timer || entry.hovered || entry.focused) return;
  entry.startedAt = Date.now();
  entry.timer = setTimeout(() => dismissToast(entry.id), entry.remaining);
}

function pauseToast(entry) {
  if (!entry.timer) return;
  clearTimeout(entry.timer);
  entry.timer = null;
  entry.remaining = Math.max(0, entry.remaining - (Date.now() - entry.startedAt));
  entry.startedAt = 0;
}

function resumeToast(entry) {
  if (entry.persistent || entry.hovered || entry.focused || entry.timer) return;
  if (entry.remaining <= 0) {
    dismissToast(entry.id);
    return;
  }
  startToast(entry);
}

function dismissToast(id) {
  const entry = toastState.items.get(id);
  if (!entry) return;
  toastState.items.delete(id);
  setToastOpen();
  if (entry.timer) {
    clearTimeout(entry.timer);
    entry.timer = null;
  }
  entry.el.classList.add("leaving");
  setTimeout(() => entry.el.remove(), 180);
}

function trimToasts() {
  const live = [...toastState.items.values()];
  if (live.length <= TOAST_MAX_VISIBLE) return;
  const newestId = Math.max(...live.map(item => item.id));
  const removable = live
    .filter(item => !item.persistent && !item.hovered && !item.focused && item.id !== newestId)
    .sort((a, b) => a.id - b.id);
  removable.slice(0, live.length - TOAST_MAX_VISIBLE).forEach(item => dismissToast(item.id));
}

function showToast({ title, message, type = "info", duration, persistent = false } = {}) {
  const kind = ["success", "error", "warning", "info"].includes(type) ? type : "info";
  const keep = persistent || kind === "error";
  const text = message == null ? "" : String(message);
  const long = text.length > 400 || text.split("\n").length > 8;
  const durationMs = keep
    ? 0
    : (duration ?? (kind === "warning" ? TOAST_WARNING_MS : long ? TOAST_LONG_MS : TOAST_DEFAULT_MS));
  const key = [kind, title || "", text].join("\n");
  const existing = [...toastState.items.values()].find(item => item.key === key);
  if (existing) {
    pauseToast(existing);
    existing.persistent = keep;
    existing.remaining = durationMs;
    existing.titleEl.textContent = title || toastDefaultTitle(kind);
    existing.body.textContent = text;
    existing.body.hidden = !text;
    existing.body.tabIndex = long ? 0 : -1;
    existing.text = text;
    existing.copyBtn.hidden = !text;
    existing.el.classList.remove("leaving");
    if (!existing.hovered && !existing.focused && !existing.el.contains(document.activeElement)) {
      toastRegion().appendChild(existing.el);
      scrollToLatestToast();
    }
    if (!keep) startToast(existing);
    return existing.id;
  }
  const id = ++toastState.seq;
  const el = document.createElement("article");
  el.className = "toast toast-" + kind;
  el.dataset.toastId = String(id);
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.setAttribute("aria-atomic", "true");
  const head = document.createElement("div");
  head.className = "toast-head";
  const titleEl = document.createElement("div");
  titleEl.className = "toast-title";
  titleEl.textContent = title || toastDefaultTitle(kind);
  const copyBtn = copyButton(() => entry.text, "toast-copy", "Copy");
  copyBtn.hidden = !text;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast-close";
  close.setAttribute("aria-label", "Dismiss notification");
  close.textContent = "×";
  head.appendChild(titleEl);
  head.appendChild(copyBtn);
  head.appendChild(close);
  const body = document.createElement("pre");
  body.className = "toast-body";
  body.textContent = text;
  body.hidden = !text;
  body.tabIndex = long ? 0 : -1;
  el.appendChild(head);
  el.appendChild(body);
  const entry = {
    id,
    key,
    el,
    titleEl,
    body,
    text,
    copyBtn,
    persistent: keep,
    remaining: durationMs,
    timer: null,
    startedAt: 0,
    hovered: false,
    focused: false,
  };
  close.onclick = () => dismissToast(id);
  el.addEventListener("mouseenter", () => {
    entry.hovered = true;
    pauseToast(entry);
  });
  el.addEventListener("mouseleave", () => {
    entry.hovered = false;
    resumeToast(entry);
  });
  el.addEventListener("focusin", () => {
    entry.focused = true;
    pauseToast(entry);
  });
  el.addEventListener("focusout", event => {
    if (!el.contains(event.relatedTarget)) {
      entry.focused = false;
      resumeToast(entry);
    }
  });
  toastState.items.set(id, entry);
  toastRegion().appendChild(el);
  trimToasts();
  setToastOpen();
  scrollToLatestToast();
  if (!keep) startToast(entry);
  return id;
}

async function copyText(text) {
  const value = text == null ? "" : String(text);
  if (!value) throw new Error("Nothing to copy");
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (e) {
      // Fall through to the legacy path.
    }
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-1000px";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  area.setSelectionRange(0, value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } finally {
    area.remove();
  }
  if (!ok) throw new Error("Clipboard unavailable");
}

function copyButton(textOrGetter, className = "", label = "Copy") {
  const btn = el("button", "copybtn" + (className ? " " + className : ""), label);
  btn.type = "button";
  btn.title = label;
  btn.setAttribute("aria-label", label);
  const original = label;
  btn.onclick = async event => {
    event.stopPropagation();
    try {
      const value = typeof textOrGetter === "function" ? textOrGetter() : textOrGetter;
      await copyText(value);
      btn.textContent = "Copied";
      btn.classList.add("copied");
      clearTimeout(btn._copyTimer);
      btn._copyTimer = setTimeout(() => {
        btn.textContent = original;
        btn.classList.remove("copied");
      }, 1500);
    } catch (e) {
      showToast({
        title: "Copy failed",
        message: e.message || String(e),
        type: "error",
      });
    }
  };
  return btn;
}

function copyablePre(text, className = "diag-evidence", label = "Copy") {
  const wrap = el("div", "copyblock");
  const pre = el("pre", className);
  pre.textContent = text;
  wrap.appendChild(pre);
  wrap.appendChild(copyButton(text, "copyblock-btn", label));
  return wrap;
}

function showUiError(message) {
  try {
    showToast({
      title: "UI error",
      message: "JS error: " + message,
      type: "error",
      persistent: true,
    });
    return;
  } catch (e) {}
  const v = document.getElementById("view");
  if (!v) return;
  const box = document.createElement("section");
  box.className = "card";
  box.style.borderColor = "#ff7a59";
  box.textContent = "JS error: " + message;
  v.prepend(box);
}

window.addEventListener("error", (e) => showUiError(e.message || String(e.error || "unknown error")));
window.addEventListener("unhandledrejection", (e) => {
  const reason = e.reason;
  showUiError((reason && (reason.message || reason)) || "unhandled promise rejection");
});

const OFFLINE = window.GXR_PROFILER_OFFLINE || null;
const API_TOKEN = (document.querySelector('meta[name="gxr-profiler-token"]') || {}).content || "";
function storedSetting(name) {
  try {
    const value = localStorage.getItem("gxr-profiler." + name);
    return value != null ? value : localStorage.getItem("xrbench." + name);
  } catch (e) {
    return null;
  }
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

function textEl(tag, cls, text) {
  const e = el(tag, cls);
  e.textContent = text == null ? "" : String(text);
  return e;
}

function fmtStamp(ms, withDate) {
  const d = new Date(ms);
  if (!Number.isFinite(d.getTime())) return "";
  const p2 = n => String(n).padStart(2, "0");
  const time = p2(d.getHours()) + ":" + p2(d.getMinutes()) + ":" + p2(d.getSeconds());
  if (!withDate) return time;
  return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()) + " " + time;
}

function fmt(v, unit, decimals) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  let s;
  if (decimals != null) {
    const n = Number(v);
    s = decimals === 0 ? Math.round(n).toLocaleString() : n.toFixed(decimals);
  } else if (Math.abs(v) >= 1000) {
    s = Math.round(v).toLocaleString();
  } else {
    s = (Math.round(v * 10) / 10).toString();
  }
  if (!unit) return s;
  const tight = unit === "%" || unit === "°C" || unit === "dBm";
  return s + (tight ? "" : " ") + unit;
}

function escHtml(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

async function apiError(response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text);
    if (data && data.detail) return String(data.detail);
  } catch (e) {}
  return text || ("HTTP " + response.status);
}

async function jget(url) {
  if (OFFLINE) {
    if (url === "/api/spec") return OFFLINE.spec;
    if (url === "/api/runs") return OFFLINE.runs;
    let m = url.match(/^\/api\/runs\/([^/]+)\/procs\/series$/);
    if (m) return (OFFLINE.proc_series || {})[decodeURIComponent(m[1])] || {};
    m = url.match(/^\/api\/runs\/([^/]+)\/procs$/);
    if (m) return OFFLINE.procs[decodeURIComponent(m[1])] || [];
    m = url.match(/^\/api\/runs\/([^/]+)$/);
    if (m) {
      const label = decodeURIComponent(m[1]);
      const dataset = OFFLINE.datasets[label];
      if (!dataset) throw new Error("run not found: " + label);
      return dataset;
    }
    throw new Error("offline report: unsupported request " + url);
  }
  const r = await fetch(url);
  if (!r.ok) throw new Error(await apiError(r));
  return r.json();
}
async function jpost(url, body) {
  if (OFFLINE) throw new Error("This is an offline report.");
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-GXR-Profiler-Token": API_TOKEN }, body: JSON.stringify(body || {}) });
  if (!r.ok) throw new Error(await apiError(r));
  return r.json();
}
async function jdel(url) {
  if (OFFLINE) throw new Error("This is an offline report.");
  const r = await fetch(url, { method: "DELETE", headers: { "X-GXR-Profiler-Token": API_TOKEN } });
  if (!r.ok) throw new Error((await apiError(r)).slice(0, 200));
  return r.json().catch(() => ({}));
}
