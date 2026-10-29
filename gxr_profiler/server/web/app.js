"use strict";

function showUiError(message) {
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

const COLORS = ["#4f9dff", "#ff7a59", "#39d353", "#c678dd", "#f0c000", "#33c7d4", "#ff5d8f", "#8f7bff"];
// Distinct colours for individual lines when a single run is shown.
const SERIES_COLORS = [
  "#4f9dff", "#ff7a59", "#39d353", "#c678dd", "#f0c000", "#33c7d4", "#ff5d8f", "#8f7bff",
  "#ffa657", "#7ee787", "#79c0ff", "#d2a8ff", "#ffd33d", "#56d4dd", "#ff9bce", "#a5d6ff",
];
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
let SPEC = null;
let RUNS = [];
let runSearch = "";
let runSort = "newest";
let sidebarOpen = true;
const RUN_SORTS = new Set(["newest", "oldest", "name-asc", "name-desc", "duration"]);
try {
  const savedSort = storedSetting("runSort");
  if (savedSort && RUN_SORTS.has(savedSort)) runSort = savedSort;
  sidebarOpen = storedSetting("sidebarOpen") !== "0";
} catch (e) {}
let activeTab = "live";
let currentRun = null;
let runLoadToken = 0;
let liveSession = null;
let liveHistory = [];
let previewState = null;
const PREVIEW_INTERVAL_MS = 2000;
let audioCtx = null;
let compareSelection = [];
let procSort = { key: "cpu_peak", dir: -1 };
let procQuery = "";
let procType = "all";
let procBackground = false;
let selectedProc = null;
let selectedCmpProc = null;
let procCache = null;
let cmpProcQuery = "";
let cmpProcType = "all";
let cmpProcBackground = false;
let cmpProcMetric = "cpu_peak";
let cmpProcMode = "full";
let cmpProcSortRun = "__max";
let cmpProcSort = { key: "field::cpu_peak", dir: -1 };
let cmpTableQuery = "";
let summaryTableQuery = "";
let graphQuery = "";
let pickQuery = "";
const procCharts = [];
const chartRegistry = [];
const pinnedCharts = [];
let pinnedRenderers = [];
const pins = { table: [], graph: [], process: [] };
const PIN_LIMITS = { table: 20, graph: 12, process: 6 };
const procSeriesCache = new Map();
const collapsedSections = new Set(["Extra"]);  // section titles hidden by the user; Extra starts closed
const combinedCharts = new Set();     // chart-group ids explicitly shown combined (default is split)
let yFromZero = true;                 // false = fit Y axis to the data (ECharts scale)
let resultsTab = "metadata";          // active Results sub-tab ("metadata" | "table" | "graphs" | "processes")
let findOpen = false;
let findHits = [];
let findIndex = -1;
let findSavedSections = null;
let findSavedTables = null;
let findTimer = null;
const collapsedTableSections = new Set(["Extra"]);  // table group headers hidden by the user; Extra starts closed
const EXTRA_SECTIONS = new Set(["Media & display", "Audio", "Cameras", "Controllers", "Passthrough", "Slow state"]);
const EXTRA_ORDER = ["Cameras", "Media & display", "Audio", "Controllers", "Passthrough", "Slow state"];

function extraRank(section) {
  const i = EXTRA_ORDER.indexOf(section);
  return i < 0 ? EXTRA_ORDER.length : i;
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

function findPin(kind, key) {
  return (pins[kind] || []).find(p => p.key === key) || null;
}

const PIN_ICON = '<svg class="pinicon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
  '<path fill="currentColor" d="M9.5 1.2a.8.8 0 0 1 1.1 0l4.2 4.2a.8.8 0 0 1 0 1.1l-1.6 1.6a.8.8 0 0 1-.9.2l-2.9 2.9.5 2.3a.8.8 0 0 1-1.4.7L5.9 10.6l-4 4a.65.65 0 0 1-.9-.9l4-4-3.6-3.6a.8.8 0 0 1 .7-1.4l2.3.5 2.9-2.9a.8.8 0 0 1 .2-.9l2-2Z"/></svg>';

function metricPinItem(m) {
  return {
    key: m.key, label: m.label, unit: m.unit || "", scale: m.scale ?? 1, decimals: m.decimals ?? null,
    section: m.section || "", groupSection: m.groupSection || "", groupId: m.groupId || "",
  };
}

function pinButton(kind, item) {
  const b = el("button", "pinbtn");
  b.type = "button";
  b.dataset.pinKind = kind;
  b.dataset.pinKey = item.key;
  b.dataset.pinLabel = item.label || item.name || item.key;
  const on = !!findPin(kind, item.key);
  b.classList.toggle("pinned", on);
  b.setAttribute("aria-pressed", String(on));
  b.setAttribute("aria-label", (on ? "Unpin " : "Pin ") + b.dataset.pinLabel);
  b.innerHTML = PIN_ICON;
  b.title = (on ? "Unpin " : "Pin ") + b.dataset.pinLabel;
  b.onclick = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    togglePin(kind, item);
  };
  b.onkeydown = (ev) => ev.stopPropagation();
  return b;
}

function syncPinButtons() {
  document.querySelectorAll("button.pinbtn[data-pin-kind]").forEach(b => {
    const on = !!findPin(b.dataset.pinKind, b.dataset.pinKey);
    b.classList.toggle("pinned", on);
    b.setAttribute("aria-pressed", String(on));
    b.setAttribute("aria-label", (on ? "Unpin " : "Pin ") + (b.dataset.pinLabel || b.dataset.pinKey));
    b.innerHTML = PIN_ICON;
    b.title = (on ? "Unpin " : "Pin ") + (b.dataset.pinLabel || b.dataset.pinKey);
  });
  document.querySelectorAll("[data-pin-row-kind]").forEach(node => {
    node.classList.toggle("pinned-row", !!findPin(node.dataset.pinRowKind, node.dataset.pinRowKey));
  });
  document.querySelectorAll("[data-pin-card-kind]").forEach(node => {
    node.classList.toggle("pinned", !!findPin(node.dataset.pinCardKind, node.dataset.pinCardKey));
  });
}

function refreshPins() {
  syncPinButtons();
  pinnedRenderers.forEach(fn => { try { fn(); } catch (e) {} });
}

function togglePin(kind, item) {
  if (!item || !item.key) return;
  const list = pins[kind] || (pins[kind] = []);
  const i = list.findIndex(p => p.key === item.key);
  if (i >= 0) {
    list.splice(i, 1);
  } else {
    const limit = PIN_LIMITS[kind] == null ? Infinity : PIN_LIMITS[kind];
    if (list.length >= limit) {
      alert("You can pin up to " + limit + " " + kind + " items. Unpin one to add another.");
      return;
    }
    list.push({ ...item });
  }
  refreshPins();
}

function clearPins(kind) {
  if (!pins[kind] || !pins[kind].length) return;
  pins[kind].length = 0;
  refreshPins();
}

function exportPins() {
  const copy = list => list.map(p => ({ ...p }));
  return { table: copy(pins.table), graph: copy(pins.graph), process: copy(pins.process) };
}

function loadPinsFrom(payload) {
  if (!payload || typeof payload !== "object") return;
  ["table", "graph", "process"].forEach(kind => {
    const items = Array.isArray(payload[kind]) ? payload[kind] : [];
    pins[kind] = items.filter(p => p && typeof p.key === "string").map(p => ({ ...p }));
  });
}

function parseIsoStart(value) {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function parseRunStart(dataset) {
  const meta = (dataset && dataset.meta) || {};
  const exact = parseIsoStart(meta.recording_started);
  if (exact != null) return exact;
  const ended = parseIsoStart(meta.ended);
  const duration = Number(meta.duration_actual_s);
  if (ended != null && meta.duration_actual_s != null && Number.isFinite(duration) && duration >= 0) {
    return ended - duration * 1000;
  }
  return parseIsoStart(meta.started);
}

function parseSummaryStart(run) {
  return parseRunStart({
    meta: {
      recording_started: run && run.recording_started,
      ended: run && run.ended,
      duration_actual_s: run && run.duration_actual_s,
      started: run && run.started,
    },
  });
}

function fmtStamp(ms, withDate) {
  const d = new Date(ms);
  if (!Number.isFinite(d.getTime())) return "";
  const p2 = n => String(n).padStart(2, "0");
  const time = p2(d.getHours()) + ":" + p2(d.getMinutes()) + ":" + p2(d.getSeconds());
  if (!withDate) return time;
  return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()) + " " + time;
}

function escHtml(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function axisTooltip(starts, unit) {
  return {
    trigger: "axis",
    extraCssText: "max-width:min(560px,80vw);white-space:normal;",
    formatter(params) {
      const list = Array.isArray(params) ? params : [params];
      if (!list.length) return "";
      const elapsed = Number(list[0].axisValue);
      const clockOf = p => {
        const start = starts ? starts[p.seriesName] : null;
        return start == null || !Number.isFinite(elapsed) ? null : fmtStamp(start + elapsed * 1000, true);
      };
      const clocks = list.map(clockOf).filter(Boolean);
      const unique = Array.from(new Set(clocks));
      const head = [];
      if (Number.isFinite(elapsed)) head.push(fmt(elapsed, "s", 1) + " elapsed");
      if (unique.length === 1) head.push(unique[0]);
      let html = '<div style="font-weight:600;margin-bottom:4px">' + head.map(escHtml).join(" · ") + "</div>";
      list.forEach(p => {
        const raw = Array.isArray(p.value) ? p.value[1] : p.value;
        const clock = unique.length > 1 ? clockOf(p) : null;
        html += '<div style="display:flex;gap:10px;justify-content:space-between">' +
          '<span style="min-width:0;overflow-wrap:anywhere">' + (p.marker || "") + escHtml(p.seriesName) + "</span>" +
          '<span style="flex:none;white-space:nowrap"><b>' + escHtml(fmt(raw, unit)) + "</b>" +
          (clock ? ' <span style="color:#8b949e">@ ' + escHtml(clock) + "</span>" : "") +
          "</span></div>";
      });
      return html;
    },
  };
}

function shortLegendLabel(name, max = 40) {
  const text = String(name || "");
  if (text.length <= max) return text;
  const cut = text.lastIndexOf(" · ");
  if (cut > 0) {
    const suffix = text.slice(cut);
    const room = max - suffix.length - 1;
    if (room >= 8) return text.slice(0, room) + "…" + suffix;
  }
  return text.slice(0, Math.max(1, max - 1)) + "…";
}

function legendFor(names) {
  return {
    type: "scroll", top: 0, data: names, icon: "roundRect", itemWidth: 14, itemHeight: 8,
    width: "96%", formatter: name => shortLegendLabel(name),
    textStyle: { color: "#e6edf3" }, inactiveColor: "#4b5563", pageTextStyle: { color: "#8b949e" },
  };
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

function reportName(labels) {
  const stem = labels.join("_vs_")
    .replace(/[\u0000-\u001f<>:"/\\|?*]+/g, "_")
    .slice(0, 100)
    .replace(/[. ]+$/g, "");
  return "gxr-profiler_" + (stem || "run") + ".html";
}

async function fetchReportBlob(labels, pinsPayload) {
  let q = labels.map(l => "labels=" + encodeURIComponent(l)).join("&");
  if (pinsPayload) q += "&pins=" + encodeURIComponent(JSON.stringify(pinsPayload));
  const r = await fetch("/api/report?" + q);
  if (!r.ok) throw new Error((await apiError(r)).slice(0, 200));
  return r.blob();
}

async function downloadReport(labels, btn) {
  if (!labels.length) {
    alert("Select at least one run.");
    return;
  }
  const pinsPayload = exportPins();
  const text = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "Exporting..."; }
  let saved = false;
  try {
    const api = window.pywebview && window.pywebview.api;
    if (api && typeof api.save_report === "function") {
      const res = await api.save_report(labels, pinsPayload);
      if (res && res.ok) {
        saved = true;
        return;
      }
      if (res && res.cancelled) return;
      throw new Error((res && res.error) || "save failed");
    }

    const filename = reportName(labels);
    if (window.showSaveFilePicker) {
      let handle = null;
      try {
        handle = await window.showSaveFilePicker({
          suggestedName: filename,
          types: [{ description: "HTML report", accept: { "text/html": [".html"] } }],
        });
      } catch (e) {
        if (e && e.name === "AbortError") return;
      }
      if (handle) {
        const blob = await fetchReportBlob(labels, pinsPayload);
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        saved = true;
        return;
      }
    }

    const blob = await fetchReportBlob(labels, pinsPayload);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    saved = true;
  } catch (e) {
    alert("Report export failed: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = !labels.length;
      btn.textContent = saved ? "Saved" : text;
      if (saved) setTimeout(() => { btn.textContent = text; }, 1500);
    }
  }
}

function disposeProcCharts() { while (procCharts.length) { try { procCharts.pop().dispose(); } catch (e) {} } }
function disposePinnedCharts() { while (pinnedCharts.length) { try { pinnedCharts.pop().dispose(); } catch (e) {} } }
function disposeCharts() {
  disposeProcCharts();
  disposePinnedCharts();
  while (chartRegistry.length) { try { chartRegistry.pop().dispose(); } catch (e) {} }
}

function bandIdsFor(group) { return group.bands || []; }

function buildSeries(group, runsData) {
  // One run -> colour every line distinctly. Several runs -> colour by run
  // (so before/after are distinguishable; within a run, bands use solid=max,
  // dashed=avg).
  const bandDef = id => (SPEC.bands || []).find(b => b.id === id) || {};
  const multi = runsData.length > 1;
  const series = [];
  const legend = [];
  const starts = {};
  let idx = 0;
  const add = (name, color, width, dashed, data, start) => {
    starts[name] = start;
    series.push({
      name, type: "line", showSymbol: false,
      lineStyle: { width, color, type: dashed ? "dashed" : "solid", opacity: dashed ? 0.75 : 1 },
      itemStyle: { color },
      data,
    });
    legend.push({ name, itemStyle: { color }, lineStyle: { color } });
  };
  runsData.forEach((run, ri) => {
    const runColor = COLORS[ri % COLORS.length];
    const runStart = parseRunStart(run);
    const colorFor = () => (multi ? runColor : SERIES_COLORS[idx++ % SERIES_COLORS.length]);
    group.series.forEach(s => {
      if (!run.series[s.col]) return;
      const scale = s.scale ?? 1;
      add(run.label + " · " + s.label, colorFor(), 1.5, false,
        run.elapsed.map((t, i) => [t, run.series[s.col][i] == null ? null : run.series[s.col][i] * scale]), runStart);
    });
    bandIdsFor(group).forEach(bid => {
      const mx = "band::" + bid + "::max", av = "band::" + bid + "::avg";
      const scale = bandDef(bid).scale ?? 1;
      if (run.series[mx]) add(run.label + " · " + bid + " (hottest)", colorFor(), 1.8, false,
        run.elapsed.map((t, i) => [t, run.series[mx][i] == null ? null : run.series[mx][i] * scale]), runStart);
      if (run.series[av]) add(run.label + " · " + bid + " (avg)", colorFor(), 1.1, true,
        run.elapsed.map((t, i) => [t, run.series[av][i] == null ? null : run.series[av][i] * scale]), runStart);
    });
  });
  return { series, legend, starts };
}

function groupMetrics(group) {
  const bandDef = id => (SPEC.bands || []).find(b => b.id === id) || { label: id, unit: "" };
  const out = [];
  group.series.forEach(s => {
    out.push({
      key: s.col, label: s.label, unit: s.unit, scale: s.scale ?? 1, decimals: s.decimals ?? null,
      section: group.title, groupId: group.id,
    });
  });
  (group.bands || []).forEach(bid => {
    const b = bandDef(bid);
    const extra = { unit: b.unit, scale: b.scale ?? 1, decimals: b.decimals ?? 1 };
    out.push({ key: "band::" + bid + "::max", label: b.label + " (hottest)", ...extra, section: group.title, groupId: group.id });
    out.push({ key: "band::" + bid + "::avg", label: b.label + " (average)", ...extra, section: group.title, groupId: group.id });
  });
  return out;
}

function metricSeriesFor(m, runsData, mi) {
  const multi = runsData.length > 1;
  const series = [];
  const starts = {};
  runsData.forEach((run, ri) => {
    const arr = run.series ? run.series[m.key] : null;
    if (!arr) return;
    const color = multi ? COLORS[ri % COLORS.length] : SERIES_COLORS[mi % SERIES_COLORS.length];
    const name = multi ? run.label : m.label;
    starts[name] = parseRunStart(run);
    series.push({
      name, type: "line", showSymbol: false,
      lineStyle: { width: 1.6, color }, itemStyle: { color },
      data: run.elapsed.map((t, i) => [t, arr[i] == null ? null : arr[i] * (m.scale ?? 1)]),
    });
  });
  return { series, starts };
}

function applyMetricChart(ch, m, runsData, mi) {
  const built = metricSeriesFor(m, runsData, mi);
  ch.setOption({
    backgroundColor: "transparent", tooltip: axisTooltip(built.starts, m.unit),
    grid: { left: 48, right: 14, top: 16, bottom: 28 },
    xAxis: { type: "value", name: "s", axisLine: { lineStyle: { color: "#30363d" } } },
    yAxis: yAxisFor(m.unit),
    series: built.series,
  });
  requestAnimationFrame(() => { try { ch.resize(); } catch (e) {} });
}

function miniStats(m, runsData, multi, mi) {
  const scale = m.scale ?? 1;
  const scaled = arr => (arr || []).map(v => (v == null ? null : v * scale));
  const fmtv = v => fmt(v, "", m.decimals);
  const wrap = el("div", "ministats");
  if (!multi) {
    const st = stat3(scaled((runsData[0] || {}).series ? runsData[0].series[m.key] : null));
    if (!st) return null;
    const line = el("div", "ministatline");
    ["Low", "Avg", "High"].forEach((label, i) => {
      if (i) line.appendChild(el("span", "ministatsep", "/"));
      line.appendChild(el("span", "ministatk", label));
      line.appendChild(el("span", "ministatv", fmtv([st.min, st.avg, st.max][i])));
    });
    wrap.appendChild(line);
    return wrap;
  }
  wrap.appendChild(el("div", "ministathead", "low / avg / high"));
  const stats = runsData.map(run => stat3(scaled(run.series ? run.series[m.key] : null)));
  const avgs = stats.map(s => (s ? s.avg : null));
  const valid = avgs.filter(v => Number.isFinite(v));
  const lo = valid.length ? Math.min(...valid) : null;
  const hi = valid.length ? Math.max(...valid) : null;
  runsData.forEach((run, ri) => {
    const st = stats[ri];
    if (!st) return;
    const line = el("div", "ministatline");
    const left = el("span", "ministatrun");
    left.title = run.label;
    const dot = el("span", "statdot");
    dot.style.background = COLORS[ri % COLORS.length];
    left.appendChild(dot);
    left.appendChild(document.createTextNode(run.label));
    const avgCls = compareClass(st.avg, lo, hi);
    const vals = el("span", "ministatvals");
    vals.appendChild(textEl("span", "ministatv", fmtv(st.min)));
    vals.appendChild(el("span", "ministatsep", "/"));
    const avg = textEl("span", "ministatv ministatavg" + (avgCls ? " " + avgCls : ""), fmtv(st.avg));
    if (avgCls) avg.title = avgCls === "cmp-low" ? "lowest average" : "highest average";
    vals.appendChild(avg);
    vals.appendChild(el("span", "ministatsep", "/"));
    vals.appendChild(textEl("span", "ministatv", fmtv(st.max)));
    line.appendChild(left);
    line.appendChild(vals);
    wrap.appendChild(line);
  });
  return wrap.childElementCount > 1 ? wrap : null;
}

function yAxisFor(unit) {
  return {
    type: "value", name: unit || "", scale: !yFromZero,
    splitLine: { lineStyle: { color: "#21262d" } },
  };
}

function alignFloatNav() {
  const y = document.getElementById("btn-yaxis");
  const nav = document.querySelector(".floatnav");
  if (!y || !nav) return;
  const rect = y.getBoundingClientRect();
  const width = nav.offsetWidth || 38;
  nav.style.right = Math.max(10, Math.round(window.innerWidth - (rect.left + rect.width / 2) - width / 2)) + "px";
}

function applySidebar() {
  document.documentElement.classList.toggle("sidebar-hidden", !sidebarOpen);
  const btn = document.getElementById("btn-sidebar");
  if (btn) {
    btn.textContent = sidebarOpen ? "Hide runs" : "Show runs";
    btn.title = sidebarOpen ? "Hide run list" : "Show run list";
    btn.setAttribute("aria-expanded", String(sidebarOpen));
  }
  setTimeout(() => { updateStickyOffsets(); resizeChartsSoon(); }, 0);
}

function updateStickyOffsets() {
  const tabs = document.getElementById("tabs");
  const inner = document.querySelector(".results .inner-tabs");
  const tableHead = document.querySelector(".sticky-table tr.tablehead th");
  const root = document.documentElement;
  root.style.setProperty("--tabs-h", ((tabs && tabs.offsetHeight) || 0) + "px");
  root.style.setProperty("--subtabs-h", ((inner && inner.offsetHeight) || 0) + "px");
  root.style.setProperty("--table-head-h", tableHead ? (tableHead.offsetHeight + 1) + "px" : "33px");
  alignFloatNav();
}

function resizeChartsSoon() {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    chartRegistry.forEach(ch => { try { ch.resize(); } catch (e) {} });
  }));
}

function applyYScale() {
  [...chartRegistry, ...procCharts].forEach(ch => {
    try { ch.setOption({ yAxis: { scale: !yFromZero } }); } catch (e) {}
  });
}

function chartOption(series, legend, unit, starts) {
  return {
    backgroundColor: "transparent", tooltip: axisTooltip(starts, unit),
    legend: legendFor(legend),
    grid: { left: 60, right: 22, top: 52, bottom: 40 },
    xAxis: { type: "value", name: "s", axisLine: { lineStyle: { color: "#30363d" } } },
    yAxis: yAxisFor(unit),
    series,
  };
}

function addGroupCard(parent, group, runsData) {
  const card = el("section", "card");
  const head = el("div", "charthead");
  head.appendChild(el("h3", null, group.title));
  const btn = el("button", "splitbtn", combinedCharts.has(group.id) ? "Split" : "Combine");
  head.appendChild(btn);
  card.appendChild(head);
  const pinRow = el("div", "pinchips");
  groupMetrics(group).forEach(m => {
    if (!runsData.some(run => run.series[m.key] && run.series[m.key].some(x => x != null))) return;
    const chip = el("span", "pinchip");
    chip.appendChild(pinButton("graph", m));
    chip.appendChild(textEl("span", "pinchip-label", m.label));
    pinRow.appendChild(chip);
  });
  card.appendChild(pinRow);
  const body = el("div", "chartbody");
  card.appendChild(body);
  parent.appendChild(card); // attach BEFORE init so containers have a size

  let charts = [];
  function clear() {
    charts.forEach(ch => {
      const i = chartRegistry.indexOf(ch);
      if (i >= 0) chartRegistry.splice(i, 1);
      try { ch.dispose(); } catch (e) {}
    });
    charts = [];
    body.innerHTML = "";
  }
  function init(div) {
    const ch = echarts.init(div, "dark");
    charts.push(ch);
    chartRegistry.push(ch);
    requestAnimationFrame(() => { try { ch.resize(); } catch (e) {} });
    return ch;
  }
  function render() {
    clear();
    pinRow.hidden = !combinedCharts.has(group.id);
    if (combinedCharts.has(group.id)) {
      const div = el("div", "chart");
      body.appendChild(div);
      const built = buildSeries(group, runsData);
      init(div).setOption(chartOption(built.series, built.legend, group.unit, built.starts));
      return;
    }
    const grid = el("div", "splitgrid");
    body.appendChild(grid);
    const multi = runsData.length > 1;
    groupMetrics(group).forEach((m, mi) => {
      if (!runsData.some(run => run.series[m.key] && run.series[m.key].some(x => x != null))) return;
      const box = el("div", "minicard");
      box.dataset.pinCardKind = "graph";
      box.dataset.pinCardKey = m.key;
      const title = el("div", "minititle");
      title.appendChild(pinButton("graph", m));
      title.appendChild(textEl("span", "minititle-text", m.label + (m.unit ? " (" + m.unit + ")" : "")));
      box.appendChild(title);
      const div = el("div", "minichart");
      box.appendChild(div);
      grid.appendChild(box);
      const ch = init(div);
      applyMetricChart(ch, m, runsData, mi);
      const stats = miniStats(m, runsData, multi, mi);
      if (stats) box.appendChild(stats);
    });
    syncPinButtons();
  }
  btn.onclick = (e) => {
    e.stopPropagation();
    if (findOpen) closeFind();
    if (combinedCharts.has(group.id)) combinedCharts.delete(group.id);
    else combinedCharts.add(group.id);
    btn.textContent = combinedCharts.has(group.id) ? "Split" : "Combine";
    render();
  };
  render();
  return card;
}

function renderSections(parent, datasets) {
  const graphControls = el("div", "proccontrols graphcontrols");
  const graphSearch = document.createElement("input");
  graphSearch.type = "search";
  graphSearch.placeholder = "Filter metric charts...";
  graphSearch.value = graphQuery;
  const graphCount = el("span", "muted tablecount");
  graphControls.appendChild(graphSearch);
  graphControls.appendChild(graphCount);
  parent.appendChild(graphControls);

  const order = [];
  const bySection = {};
  const extraOrder = [];
  const extraBySection = {};
  SPEC.groups.forEach(g => {
    const s = g.section || "Other";
    const extra = EXTRA_SECTIONS.has(s);
    const bucket = extra ? extraBySection : bySection;
    const seq = extra ? extraOrder : order;
    if (!bucket[s]) { bucket[s] = []; seq.push(s); }
    bucket[s].push(g);
  });

  const addSection = (title, groups, host) => {
    const sec = el("section", "group");
    const head = el("div", "grouphead");
    const collapsed = collapsedSections.has(title);
    head.appendChild(el("span", "chev", collapsed ? "\u25b8" : "\u25be"));
    head.appendChild(el("h2", null, title));
    const body = el("div", "groupbody");
    if (collapsed) body.style.display = "none";
    head.tabIndex = 0;
    head.setAttribute("role", "button");
    head.setAttribute("aria-expanded", String(!collapsed));
    head.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        head.onclick();
      }
    };
    head.onclick = () => {
      if (findOpen) closeFind();
      const now = collapsedSections.has(title);
      if (now) collapsedSections.delete(title);
      else collapsedSections.add(title);
      body.style.display = now ? "" : "none";
      head.setAttribute("aria-expanded", String(now));
      head.querySelector(".chev").textContent = now ? "\u25be" : "\u25b8";
      if (now) resizeChartsSoon();
    };
    sec.appendChild(head);
    sec.appendChild(body);
    host.appendChild(sec);
    groups.forEach(g => addGroupCard(body, g, datasets));
    return body;
  };

  order.forEach(title => addSection(title, bySection[title], parent));
  if (extraOrder.length) {
    extraOrder.sort((a, b) => extraRank(a) - extraRank(b));
    const body = addSection("Extra", [], parent);
    extraOrder.forEach(title => {
      const sub = el("div", "extrasub");
      sub.appendChild(el("h3", "extrasubhead", title));
      const subbody = el("div", "extrabody");
      extraBySection[title].forEach(g => addGroupCard(subbody, g, datasets));
      sub.appendChild(subbody);
      body.appendChild(sub);
    });
  }

  function applyGraphFilter() {
    const terms = graphQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let shownCards = 0;
    let shownGroups = 0;
    parent.querySelectorAll(".group").forEach(sec => {
      const sectionTitle = (sec.querySelector(".grouphead h2")?.textContent || "").toLowerCase();
      const sectionMatch = terms.length && terms.every(t => sectionTitle.includes(t));
      let visibleInSection = 0;
      sec.querySelectorAll(".card").forEach(card => {
        const hay = (card.textContent || "").toLowerCase();
        const show = !terms.length || sectionMatch || terms.every(t => hay.includes(t));
        card.style.display = show ? "" : "none";
        if (show) {
          visibleInSection++;
          shownCards++;
        }
      });
      sec.querySelectorAll(".extrasub").forEach(sub => {
        sub.style.display = sub.querySelector(".card:not([style*='display: none'])") ? "" : "none";
      });
      sec.style.display = visibleInSection ? "" : "none";
      if (visibleInSection) shownGroups++;
    });
    graphCount.textContent = shownCards + " charts · " + shownGroups + " groups";
    let empty = parent.querySelector(".graphempty");
    if (terms.length && !shownCards) {
      if (!empty) {
        empty = el("div", "muted graphempty", "No charts match this search.");
        parent.appendChild(empty);
      }
    } else if (empty) {
      empty.remove();
    }
    if (terms.length) resizeChartsSoon();
  }
  graphSearch.oninput = () => { graphQuery = graphSearch.value; applyGraphFilter(); };
  applyGraphFilter();
}

function displaySummary(d) {
  if (!d) return "";
  const parts = [];
  if (d.width && d.height) parts.push(d.width + "×" + d.height);
  if (d.refresh_hz) parts.push(d.refresh_hz + " Hz");
  if ((d.hdr_types || []).length) parts.push(d.hdr_types.join("/"));
  if (d.max_luminance_nits) parts.push(d.max_luminance_nits + " nits");
  if (d.bit_depth) parts.push(d.bit_depth + "-bit");
  return parts.join(" · ");
}

function formatBits(name) {
  if (/FLOAT/.test(name || "")) return 32;
  const m = /(\d+)_BIT/.exec(name || "");
  return m ? +m[1] : null;
}

function audioSummary(a) {
  if (!a) return "";
  const out = (a.outputs || []).find(x => /Speaker/i.test(x.name)) || (a.outputs || [])[0];
  const mic = (a.inputs || []).find(x => /Built-In Mic/i.test(x.name)) || (a.inputs || [])[0];
  const part = (d, label) => {
    if (!d) return null;
    const bits = Math.max(0, ...(d.formats || []).map(x => formatBits(x) || 0));
    const hz = Math.max(0, ...(d.rates_hz || [0]));
    return [label, hz ? Math.round(hz / 1000) + " kHz" : "", bits ? bits + "-bit" : ""].filter(Boolean).join(" ");
  };
  return [part(out, "Speaker"), part(mic, "Mic")].filter(Boolean).join(" · ");
}

function calibrationDate(value) {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? fmtStamp(ms, true) : String(value);
}

function regionSummary(di) {
  const r = (di && di.region) || {};
  let out = r.country || r.country_iso;
  if (r.country && r.country_iso) out += " (" + r.country_iso + ")";
  if (r.sales_code) out += " \u00b7 CSC " + r.sales_code;
  return out || null;
}

function regionShort(di) {
  const r = (di && di.region) || {};
  return [r.country_iso || r.country, r.sales_code].filter(Boolean).join(" \u00b7 ") || null;
}

function deviceCard(meta) {
  const di = (meta && meta.device_info) || {};
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Device"));
  const g = el("div", "grid2");
  const setup = di.first_setup || {};
  const setupText = setup.first_setup_at
    ? calibrationDate(setup.first_setup_at) + (setup.first_setup_days == null ? "" : " (" + setup.first_setup_days + " days)")
    : null;
  const rows = [
    ["Model", di.model], ["Region", regionSummary(di)],
    ["Build", di.build_display_id],
    ["Android", di.android ? di.android + " (SDK " + (di.sdk == null ? "?" : di.sdk) + ")" : null],
    ["SoC", di.soc], ["Manufactured", di.manufacture_date],
    ["First setup (approx.)", setupText],
    ["Panel", (di.panel || {}).active], ["Display", displaySummary(di.display)],
    ["Audio", audioSummary(di.audio)], ["Wi-Fi", (di.wifi || {}).standard_name],
    ["Root", (di.root || {}).manager], ["Security patch", di.security_patch],
  ];
  rows.forEach(([k, v]) => { g.appendChild(textEl("span", "k", k)); g.appendChild(textEl("span", null, v || "--")); });
  card.appendChild(g);
  return card;
}

function calibrationRows(meta) {
  const cal = ((meta && meta.device_info) || {}).calibration || {};
  const ipd = value => value == null || !Number.isFinite(Number(value)) ? null : Number(value).toFixed(2) + " mm";
  return [
    ["IPD measured", ipd(cal.ipd_mm)],
    ["IPD in use", ipd(cal.ipd_in_use_mm)],
    ["Eye tracking calibrated", calibrationDate(cal.eye_calibrated_at) || (cal.eye_calibration_needed ? "needs calibration" : null)],
    ["Face tracking calibrated", calibrationDate(cal.face_calibrated_at) || (cal.face_calibration_in_progress ? "in progress" : null)],
  ];
}

function boundaryRows(meta) {
  const b = ((meta && meta.device_info) || {}).boundary || {};
  const yn = value => value == null ? null : (value ? "yes" : "no");
  const status = b.consent_granted == null ? null
    : (!b.consent_granted ? "not configured" : (b.toggle_guardian ? "on (consent granted)" : "off (consent granted)"));
  const metres = value => value == null ? null : Number(value).toFixed(2) + " m";
  const mode = value => value == null ? null : "mode " + Math.round(value);
  return [
    ["Guardian", status],
    ["Boundary radius", metres(b.radius_m)],
    ["Placement mode", mode(b.placement_mode)],
    ["Position setup", b.position_setup_available == null ? null : (b.position_setup_available ? "available" : "unavailable")],
    ["Floor setup", mode(b.floor_setup_mode)],
    ["Floor offset", metres(b.floor_offset_m)],
    ["Radius control", yn(b.toggle_radius_available)],
  ];
}

function trackingRows(meta) {
  return [...calibrationRows(meta), ...boundaryRows(meta)];
}

function trackingCard(meta) {
  const cal = ((meta && meta.device_info) || {}).calibration || {};
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Input & boundary"));
  const split = el("div", "metasplit");

  const input = el("div", "metasection");
  input.appendChild(el("h4", null, "Input calibration"));
  const calGrid = el("div", "grid2");
  calibrationRows(meta).forEach(([k, v]) => {
    calGrid.appendChild(textEl("span", "k", k));
    calGrid.appendChild(textEl("span", null, v || "--"));
  });
  input.appendChild(calGrid);
  if (cal.ipd_mm == null && cal.eye_calibrated_at == null && cal.face_calibrated_at == null) {
    input.appendChild(el("div", "muted cardnote", "Record with --root to collect measured IPD and eye/face calibration dates."));
  }
  split.appendChild(input);

  const guard = el("div", "metasection");
  guard.appendChild(el("h4", null, "Guardian boundary"));
  const bGrid = el("div", "grid2");
  boundaryRows(meta).forEach(([k, v]) => {
    bGrid.appendChild(textEl("span", "k", k));
    bGrid.appendChild(textEl("span", null, v || "--"));
  });
  guard.appendChild(bGrid);
  guard.appendChild(el("div", "muted cardnote", "Guardian/boundary state from Android system settings."));
  split.appendChild(guard);

  card.appendChild(split);
  return card;
}

function timeToThrottle(elapsed, series) {
  const st = series["thermal_status"] || [];
  for (let i = 0; i < st.length && i < elapsed.length; i++) if (st[i] > 0) return fmt(elapsed[i]) + "s";
  return "never";
}

// ---- views ----------------------------------------------------------------
const PROC_COLS = [
  { key: "name", label: "Process", text: true },
  { key: "kind", label: "Type", text: true },
  { key: "oom_class", label: "OOM", text: true },
  { key: "cpu_last", label: "CPU now", unit: "%", decimals: 1 },
  { key: "cpu_peak", label: "CPU peak", unit: "%", decimals: 1 },
  { key: "cpu", label: "CPU 5m", unit: "%", decimals: 1 },
  { key: "cpu_time", label: "CPU time", unit: "s", decimals: 0 },
  { key: "rss_peak", label: "RSS peak", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "rss", label: "RSS avg", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "gpu_peak", label: "GPU peak", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "io_r_peak", label: "Disk rd", unit: "MB/s", scale: 1e-6, decimals: 1 },
  { key: "io_w_peak", label: "Disk wr", unit: "MB/s", scale: 1e-6, decimals: 1 },
  { key: "rx_peak", label: "Net Rx", unit: "MB/s", scale: 1e-6, decimals: 2 },
  { key: "tx_peak", label: "Net Tx", unit: "MB/s", scale: 1e-6, decimals: 2 },
  { key: "state", label: "State", text: true },
  { key: "threads", label: "Threads", decimals: 0 },
];

const CMP_FULL_FIELDS = [
  { key: "cpu_now", label: "CPU now", unit: "%", decimals: 1 },
  { key: "cpu_peak", label: "CPU peak", unit: "%", decimals: 1 },
  { key: "cpu", label: "CPU 5m", unit: "%", decimals: 1 },
  { key: "cpu_time", label: "CPU time", unit: "s", decimals: 0 },
  { key: "rss_peak", label: "RSS peak", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "rss", label: "RSS avg", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "gpu_peak", label: "GPU peak", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "io_r_peak", label: "Disk rd", unit: "MB/s", scale: 1e-6, decimals: 1 },
  { key: "io_w_peak", label: "Disk wr", unit: "MB/s", scale: 1e-6, decimals: 1 },
  { key: "rx_peak", label: "Net Rx", unit: "MB/s", scale: 1e-6, decimals: 2 },
  { key: "tx_peak", label: "Net Tx", unit: "MB/s", scale: 1e-6, decimals: 2 },
  { key: "oom_class", label: "OOM", text: true },
  { key: "state", label: "State", text: true },
  { key: "threads", label: "Threads", decimals: 0 },
];


const CMP_PROC_METRICS = [
  { key: "cpu_peak", label: "CPU peak", unit: "%", decimals: 1 },
  { key: "cpu_now", label: "CPU now", unit: "%", decimals: 1 },
  { key: "cpu", label: "CPU 5m", unit: "%", decimals: 1 },
  { key: "rss_peak", label: "RSS peak", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "rss", label: "RSS avg", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "gpu_peak", label: "GPU peak", unit: "MB", scale: 1 / 1024, decimals: 0 },
  { key: "io_r_peak", label: "Disk read", unit: "MB/s", scale: 1e-6, decimals: 1 },
  { key: "io_w_peak", label: "Disk write", unit: "MB/s", scale: 1e-6, decimals: 1 },
  { key: "rx_peak", label: "Net Rx", unit: "MB/s", scale: 1e-6, decimals: 2 },
  { key: "tx_peak", label: "Net Tx", unit: "MB/s", scale: 1e-6, decimals: 2 },
  { key: "threads", label: "Threads", decimals: 0 },
];

function procCategory(r) {
  const kind = r.kind || "unknown";
  if (kind === "app" && r.pkg_system) return "system-app";
  return kind;
}

function procKindLabel(r) {
  const cat = procCategory(r);
  return ({ "system-app": "System app", kernel: "Kernel", system: "System", app: "App", isolated: "Isolated" })[cat] || "Unknown";
}

function procOomLabel(r) {
  const c = r.oom_class || "";
  return c ? c[0].toUpperCase() + c.slice(1) : "--";
}

function procMatches(r) {
  if (procType !== "all" && procCategory(r) !== procType) return false;
  if (procBackground && !["background", "cached"].includes(r.oom_class)) return false;
  const q = procQuery.trim().toLowerCase();
  if (!q) return true;
  return (r.name + " " + (r.package || "") + " " + (r.uid == null ? "" : r.uid)).toLowerCase().includes(q);
}

function procSortValue(r, col) {
  if (col.key === "kind") return procCategory(r);
  if (col.key === "oom_class") return r.oom_class || "";
  return r[col.key];
}

function procSortRows(rows) {
  const col = PROC_COLS.find(c => c.key === procSort.key) || PROC_COLS[4];
  const dir = procSort.dir || -1;
  const cmp = (a, b) => {
    const av = procSortValue(a, col), bv = procSortValue(b, col);
    const an = av == null || av === "";
    const bn = bv == null || bv === "";
    if (an && bn) return String(a.name || "").localeCompare(String(b.name || ""));
    if (an) return 1;
    if (bn) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  };
  return rows.slice().sort(cmp);
}

function procCellText(r, col) {
  if (col.key === "name") return r.name || "--";
  if (col.key === "kind") return procKindLabel(r);
  if (col.key === "oom_class") return procOomLabel(r);
  const v = r[col.key];
  if (v == null || v === "") return "--";
  if (col.text) return String(v);
  const n = Number(v) * (col.scale == null ? 1 : col.scale);
  if (!Number.isFinite(n)) return "--";
  return fmt(n, "", col.decimals) + (col.unit === "%" ? "%" : "");
}

function setProcHeader(th, col) {
  th.textContent = "";
  const label = el("span", "prochead-label");
  label.appendChild(document.createTextNode(col.label));
  if (procSort.key === col.key) {
    label.appendChild(el("span", "sortarrow", procSort.dir < 0 ? "▼" : "▲"));
  }
  th.appendChild(label);
  if (col.unit) th.appendChild(el("span", "procunit", col.unit));
}

async function fetchProcRows(label) {
  const rows = await jget("/api/runs/" + encodeURIComponent(label) + "/procs");
  if (!Array.isArray(rows)) throw new Error("invalid process data");
  return rows;
}

async function loadProcSeries(label) {
  if (procSeriesCache.has(label)) return procSeriesCache.get(label);
  try {
    const data = await jget("/api/runs/" + encodeURIComponent(label) + "/procs/series");
    procSeriesCache.set(label, data || {});
  } catch (e) {
    procSeriesCache.set(label, {});
  }
  return procSeriesCache.get(label);
}

function procStableKey(p) {
  return [p.name || "", p.uid == null ? "" : p.uid, p.package || ""].join("|");
}

function procPinItem(p) {
  return {
    key: procStableKey(p), name: p.name || "", uid: p.uid == null ? null : p.uid,
    package: p.package || "", kind: p.kind || "",
  };
}

function findProcForPin(rows, pin) {
  const list = rows || [];
  const exact = list.find(r => procStableKey(r) === pin.key);
  if (exact) return exact;
  if (pin.package) {
    const byPackage = list.filter(r => r.package === pin.package);
    if (byPackage.length === 1) return byPackage[0];
  }
  if (pin.name) {
    const byName = list.filter(r => r.name === pin.name);
    if (byName.length === 1) return byName[0];
  }
  return null;
}

async function getProcData(label) {
  if (procCache && procCache.label === label) return procCache;
  const base = "/api/runs/" + encodeURIComponent(label);
  const [rows, series] = await Promise.all([
    jget(base + "/procs"),
    jget(base + "/procs/series").catch(() => ({})),
  ]);
  const run = RUNS.find(r => r.label === label);
  procCache = { label, rows: rows || [], series: series || {}, start: parseSummaryStart(run) };
  return procCache;
}

const PROC_CHART_GROUPS = [
  { id: "cpu", title: "CPU", unit: "%", metrics: [{ key: "cpu", label: "CPU", decimals: 1 }] },
  { id: "rss", title: "Memory", unit: "MB", metrics: [{ key: "rss", label: "RSS", scale: 1 / 1024, decimals: 0 }] },
  {
    id: "io", title: "Disk I/O", unit: "MB/s", hint: "read solid · write dashed",
    metrics: [
      { key: "io_r", label: "read", scale: 1e-6, decimals: 1 },
      { key: "io_w", label: "write", scale: 1e-6, decimals: 1, dashed: true },
    ],
  },
  {
    id: "net", title: "Network", unit: "MB/s", hint: "Rx solid · Tx dashed",
    metrics: [
      { key: "net_rx", label: "Rx", scale: 1e-6, decimals: 2 },
      { key: "net_tx", label: "Tx", scale: 1e-6, decimals: 2, dashed: true },
    ],
  },
];

function procChartTitle(def) {
  const title = el("div", "minihead", def.title + (def.unit ? " (" + def.unit + ")" : ""));
  if (def.hint) title.appendChild(textEl("span", "minihead-note", " · " + def.hint));
  return title;
}

function procChartStats(def, runsData, multi) {
  const blocks = def.metrics.map((m, mi) => {
    const stats = miniStats(m, runsData, multi, mi);
    if (!stats) return null;
    if (def.metrics.length === 1) return stats;
    const head = stats.querySelector(".ministathead");
    if (head) head.remove();
    const block = el("div", "ministatmetric");
    block.appendChild(el("div", "ministatmetrick", m.label));
    block.appendChild(stats);
    return block;
  }).filter(Boolean);
  if (!blocks.length) return null;
  if (blocks.length === 1) return blocks[0];
  const wrap = el("div", "ministats procmerge-stats");
  if (multi) wrap.appendChild(el("div", "ministathead", "low / avg / high"));
  const grid = el("div", "procmerge-grid");
  blocks.forEach(block => grid.appendChild(block));
  wrap.appendChild(grid);
  return wrap;
}

function procChartOption(def, lines, starts) {
  return {
    backgroundColor: "transparent",
    tooltip: axisTooltip(starts, def.unit),
    grid: { left: 48, right: 14, top: 16, bottom: 28 },
    xAxis: { type: "value", name: "s", axisLine: { lineStyle: { color: "#30363d" } } },
    yAxis: yAxisFor(def.unit),
    series: lines,
  };
}

function renderProcChart(host, data, onClear) {
  disposeProcCharts();
  host.innerHTML = "";
  if (!selectedProc) {
    host.appendChild(el("div", "muted procchart-hint", "Select a process row to chart its CPU, memory, disk and network over the run."));
    return;
  }
  const row = data.rows.find(r => r.key === selectedProc);
  const series = (data.series || {})[selectedProc];
  if (!row || !series) {
    host.appendChild(el("div", "muted procchart-hint", "No per-process timeline data for this older capture."));
    return;
  }
  const head = el("div", "charthead");
  const box = el("div", "procchart-title");
  box.appendChild(textEl("h3", null, row.name));
  const sub = el("div", "muted procsub");
  sub.textContent = [procKindLabel(row), row.package || "", row.uid == null ? "" : "UID " + row.uid].filter(Boolean).join(" · ");
  box.appendChild(sub);
  head.appendChild(box);
  const close = el("button", "toolbtn", "Clear");
  close.type = "button";
  close.onclick = () => { selectedProc = null; if (onClear) onClear(); else renderProcChart(host, data); };
  head.appendChild(close);
  host.appendChild(head);

  const grid = el("div", "proccharts");
  host.appendChild(grid);
  const statsRuns = [{ label: row.name || "process", series, elapsed: series.elapsed }];
  let shown = 0;
  PROC_CHART_GROUPS.forEach((def, di) => {
    const available = def.metrics.filter(m => (series[m.key] || []).some(v => v != null));
    if (!available.length) return;
    shown++;
    const card = el("div", "procchart-box");
    card.appendChild(procChartTitle(def));
    const div = el("div", "procchart");
    card.appendChild(div);
    grid.appendChild(card);
    const starts = {};
    const lines = available.map((m, mi) => {
      const arr = series[m.key];
      const scale = m.scale ?? 1;
      const points = (series.elapsed || []).map((t, idx) => [t, arr[idx] == null ? null : arr[idx] * scale]);
      const sparse = points.filter(p => p[1] != null).length <= 2;
      starts[m.label] = data.start;
      const color = SERIES_COLORS[mi % SERIES_COLORS.length];
      return {
        name: m.label, type: "line", showSymbol: sparse, symbolSize: sparse ? 5 : 0, connectNulls: false,
        lineStyle: { width: 1.6, color, type: m.dashed ? "dashed" : "solid" },
        itemStyle: { color }, data: points,
      };
    });
    const ch = echarts.init(div, "dark");
    procCharts.push(ch);
    ch.setOption(procChartOption(def, lines, starts));
    const stats = procChartStats(def, statsRuns, false);
    if (stats) card.appendChild(stats);
    requestAnimationFrame(() => { try { ch.resize(); } catch (e) {} });
  });
  if (!shown) {
    grid.remove();
    host.appendChild(el("div", "muted procchart-hint", "This process has no timeline metrics."));
  }
}

async function processesCard(label) {
  let data;
  try {
    data = await getProcData(label);
  } catch (e) {
    return null;
  }
  if (!data.rows.length) return null;
  const card = el("section", "card process-card");
  const head = el("div", "runhead");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, "Processes"));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  card.appendChild(head);

  const controls = el("div", "proccontrols");
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Search process or package...";
  search.value = procQuery;
  const typeSel = document.createElement("select");
  [["all", "All processes"], ["app", "Apps"], ["system", "System"], ["system-app", "System apps"], ["kernel", "Kernel"], ["isolated", "Isolated"]].forEach(([v, l]) => {
    const o = document.createElement("option"); o.value = v; o.textContent = l; typeSel.appendChild(o);
  });
  typeSel.value = procType;
  const bg = document.createElement("label");
  bg.className = "proc-check";
  const bgInput = document.createElement("input");
  bgInput.type = "checkbox";
  bgInput.checked = procBackground;
  bg.appendChild(bgInput);
  bg.appendChild(document.createTextNode(" Background/cached only"));
  controls.appendChild(search);
  controls.appendChild(typeSel);
  controls.appendChild(bg);
  card.appendChild(controls);

  const chartHost = el("div", "proc-chart-host");
  card.appendChild(chartHost);
  let procChartKey;
  const wrap = el("div", "proctable-wrap");
  const t = el("table", "proctable");
  const thead = el("thead");
  const htr = el("tr");
  const procThs = {};
  PROC_COLS.forEach(col => {
    const th = el("th", "procsort");
    setProcHeader(th, col);
    th.title = "Sort by " + col.label;
    th.onclick = () => {
      if (procSort.key === col.key) procSort.dir *= -1;
      else procSort = { key: col.key, dir: col.text ? 1 : -1 };
      render();
    };
    th.tabIndex = 0;
    th.setAttribute("role", "button");
    th.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); th.onclick(); }
    };
    procThs[col.key] = th;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  t.appendChild(thead);
  const tbody = el("tbody");
  t.appendChild(tbody);
  wrap.appendChild(t);
  card.appendChild(wrap);

  const legacy = data.rows.every(r => r.cpu_now == null);
  if (legacy) {
    card.appendChild(el("div", "muted cardnote", "This older capture only has top-process data. New recordings capture all non-kernel processes."));
  } else if (!data.rows.some(r => r.io_r_peak != null)) {
    card.appendChild(el("div", "muted cardnote", "Disk I/O columns require recording with root extras enabled."));
  }

  function render() {
    const filtered = procSortRows(data.rows.filter(procMatches));
    count.textContent = filtered.length + " / " + data.rows.length + " processes";
    PROC_COLS.forEach(col => {
      const th = procThs[col.key];
      if (!th) return;
      setProcHeader(th, col);
    });
    tbody.innerHTML = "";
    filtered.forEach(r => {
      const tr = el("tr", "procrow" + (r.key === selectedProc ? " selected" : ""));
      tr.dataset.pinRowKind = "process";
      tr.dataset.pinRowKey = procStableKey(r);
      const nameTd = el("td", "procname-cell");
      const nameLine = el("div", "procname-line");
      nameLine.appendChild(pinButton("process", procPinItem(r)));
      const name = el("div", "procname-main");
      name.textContent = r.name || "--";
      nameLine.appendChild(name);
      const sub = el("div", "procsub");
      sub.textContent = "PID " + (r.pid == null ? "--" : r.pid) + " · UID " + (r.uid == null ? "--" : r.uid);
      nameTd.appendChild(nameLine);
      nameTd.appendChild(sub);
      if (r.package) {
        const pkg = el("div", "procpackage");
        pkg.textContent = r.package;
        nameTd.appendChild(pkg);
      }
      tr.appendChild(nameTd);
      if (findPin("process", procStableKey(r))) tr.classList.add("pinned-row");
      PROC_COLS.slice(1).forEach(col => {
        const td = el("td", col.key === "kind" || col.key === "oom_class" ? "procbadgecell" : "");
        if (col.key === "kind" || col.key === "oom_class") {
          const b = el("span", "procbadge " + (col.key === "kind" ? "kind-" + procCategory(r) : "oom-" + (r.oom_class || "unknown")));
          b.textContent = procCellText(r, col);
          td.appendChild(b);
        } else {
          td.textContent = procCellText(r, col);
        }
        tr.appendChild(td);
      });
      tr.onclick = () => {
        selectedProc = r.key;
        render();
      };
      tr.tabIndex = 0;
      tr.setAttribute("role", "button");
      tr.onkeydown = (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          tr.onclick();
        }
      };
      tbody.appendChild(tr);
    });
    if (!filtered.length) {
      const tr = el("tr");
      const td = el("td", "muted", "No processes match these filters.");
      td.colSpan = PROC_COLS.length;
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
    if (selectedProc !== procChartKey) {
      renderProcChart(chartHost, data, render);
      procChartKey = selectedProc;
    }
  }

  search.oninput = () => { procQuery = search.value; render(); };
  typeSel.onchange = () => { procType = typeSel.value; render(); };
  bgInput.onchange = () => { procBackground = bgInput.checked; render(); };
  render();
  return card;
}

function summaryRows(run) {
  const bandDef = id => (SPEC.bands || []).find(b => b.id === id) || { label: id, unit: "" };
  const rows = [];
  SPEC.groups.forEach(g => {
    const groupSection = g.section || "Other";
    g.series.forEach(s => {
      if (run.series[s.col]) {
        rows.push({ key: s.col, section: g.title, groupSection, label: s.label, unit: s.unit, scale: s.scale ?? 1, decimals: s.decimals ?? null, arr: run.series[s.col] });
      }
    });
    (g.bands || []).forEach(bid => {
      const b = bandDef(bid);
      const mx = "band::" + bid + "::max", av = "band::" + bid + "::avg";
      const extra = { unit: b.unit, scale: b.scale ?? 1, decimals: b.decimals ?? 1 };
      if (run.series[mx]) rows.push({ key: mx, section: g.title, groupSection, label: b.label + " (hottest)", ...extra, arr: run.series[mx] });
      if (run.series[av]) rows.push({ key: av, section: g.title, groupSection, label: b.label + " (average)", ...extra, arr: run.series[av] });
    });
  });
  return rows;
}

function _pick(arr, agg) {
  const a = (arr || []).filter(x => x != null);
  if (!a.length) return null;
  if (agg === "max") return Math.max(...a);
  if (agg === "min") return Math.min(...a);
  return a.reduce((s, x) => s + x, 0) / a.length;
}

function lastVal(arr) {
  const a = (arr || []).filter(x => x != null);
  return a.length ? a[a.length - 1] : null;
}

function fanProfileLabel(value) {
  return value == null ? "--" : "step " + Math.round(value);
}

function thermalStatusText(current, peak) {
  const c = typeof current === "number" && Number.isFinite(current) ? Math.round(current) : null;
  const p = typeof peak === "number" && Number.isFinite(peak) ? Math.round(peak) : null;
  if (c == null && p == null) return "--";
  if (c == null) return "peak " + p;
  if (p == null) return "level " + c;
  return "level " + c + " (peak " + p + ")";
}

function keyStats(dataset) {
  const s = dataset.series || {};
  const items = [
    ["CPU peak", fmt(_pick(s["band::cpu::max"], "max"), "°C", 1)],
    ["GPU peak", fmt(_pick(s["band::gpu::max"], "max"), "°C", 1)],
    ["Surface peak", fmt(_pick(s["t_skin"], "max"), "°C", 1)],
    ["WiFi peak", fmt(_pick(s["t_WIFI"], "max"), "°C", 1)],
    ["GPU busy", fmt(_pick(s["g_busy"], "avg"), "%")],
    ["XR fps", fmt(_pick(s["xr_fps"], "avg"), "fps", 0)],
    ["Fan profile", fanProfileLabel(_pick(s["fan_step"], "max"))],
    ["Fan max", fmt(_pick(s["fan_rpm"], "max"), "rpm", 0)],
    ["Download", fmt(_pick(s["wifi_rx_mbps"], "avg"), "Mbps", 1)],
    ["Thermal status", thermalStatusText(lastVal(s["thermal_status"]), _pick(s["thermal_status"], "max"))],
    ["Throttle", timeToThrottle(dataset.elapsed, s)],
  ];
  return items;
}

function _rowMax(row, prefix, count) {
  let best = null;
  for (let i = 0; i < count; i++) {
    const v = row[prefix + i];
    if (typeof v === "number" && Number.isFinite(v) && (best == null || v > best)) best = v;
  }
  return best;
}

function _previewNew() {
  return {
    cpuPeak: null, gpuPeak: null, surfacePeak: null, wifiPeak: null, fanMax: null,
    fanProfile: null, gpuBusySum: 0, gpuBusyN: 0, xrSum: 0, xrN: 0, downloadSum: 0, downloadN: 0,
    thermalStatus: null, thermalPeak: null, throttleAt: null,
  };
}

function _previewAdd(p, row, elapsed) {
  const raise = (key, value) => {
    if (typeof value === "number" && Number.isFinite(value) && (p[key] == null || value > p[key])) p[key] = value;
  };
  raise("cpuPeak", _rowMax(row, "t_CPU", 6));
  raise("gpuPeak", _rowMax(row, "t_GPU", 8));
  raise("surfacePeak", row.t_skin);
  raise("wifiPeak", row.t_WIFI);
  raise("fanProfile", row.fan_step);
  raise("fanMax", row.fan_rpm);
  if (typeof row.thermal_status === "number" && Number.isFinite(row.thermal_status)) {
    p.thermalStatus = row.thermal_status;
    raise("thermalPeak", row.thermal_status);
  }
  const add = (sumKey, nKey, value) => {
    if (typeof value === "number" && Number.isFinite(value)) {
      p[sumKey] += value;
      p[nKey] += 1;
    }
  };
  add("gpuBusySum", "gpuBusyN", row.g_busy);
  add("xrSum", "xrN", row.xr_fps);
  add("downloadSum", "downloadN", row.wifi_rx_mbps);
  if (p.throttleAt == null && typeof row.thermal_status === "number" && row.thermal_status > 0) {
    p.throttleAt = elapsed;
  }
}

function previewStats(session) {
  const p = session.preview || _previewNew();
  const avg = (sumKey, nKey) => p[nKey] ? p[sumKey] / p[nKey] : null;
  return [
    ["CPU peak", fmt(p.cpuPeak, "°C", 1)],
    ["GPU peak", fmt(p.gpuPeak, "°C", 1)],
    ["Surface peak", fmt(p.surfacePeak, "°C", 1)],
    ["WiFi peak", fmt(p.wifiPeak, "°C", 1)],
    ["GPU busy", fmt(avg("gpuBusySum", "gpuBusyN"), "%")],
    ["XR fps", fmt(avg("xrSum", "xrN"), "fps", 0)],
    ["Fan profile", fanProfileLabel(p.fanProfile)],
    ["Fan max", fmt(p.fanMax, "rpm", 0)],
    ["Download", fmt(avg("downloadSum", "downloadN"), "Mbps", 1)],
    ["Thermal status", thermalStatusText(p.thermalStatus, p.thermalPeak)],
    ["Throttle", p.throttleAt == null ? "never" : fmt(p.throttleAt) + "s"],
  ];
}

function stateGroups(run) {
  const s = run.series || {};
  const m = run.meta || {};
  const ss = m.start_state || {};
  const es = m.end_state || {};
  const last = col => lastVal(s[col]);
  const max = col => _pick(s[col], "max");
  const onoff = v => (v == null ? "--" : (v ? "on" : "off"));
  const yesno = v => (v == null ? "--" : (v ? "yes" : "no"));
  const pct = v => (v == null ? "--" : Math.round(v * 100) + "%");

  const lowPower = ss.low_power != null ? ss.low_power : (ss.psm != null ? ss.psm : last("psm"));
  const hands = ss.hand_tracking_active != null ? ss.hand_tracking_active : es.hand_tracking_active;
  const ctrl = ss.controllers_active != null ? ss.controllers_active : es.controllers_active;
  const ctrlL = last("ctrl_left_battery"), ctrlR = last("ctrl_right_battery");
  const pt = ss.passthrough != null ? ss.passthrough : es.passthrough;
  const ptMode = last("passthrough_mode") || ss.passthrough_mode || es.passthrough_mode;
  const ctrlBatt = (ctrlL == null && ctrlR == null) ? "--"
    : "L " + (ctrlL == null ? "--" : Math.round(ctrlL) + "%") + " / R " + (ctrlR == null ? "--" : Math.round(ctrlR) + "%");
  const acv = last("batt_ac");
  const ac = acv != null ? !!acv : (ss.batt_ac != null ? !!ss.batt_ac : null);
  const batt = last("batt_level") ?? ss.batt_level ?? es.batt_level;
  const status = last("batt_status");
  const statusName = { 1: "unknown", 2: "charging", 3: "discharging", 4: "not charging", 5: "full" }[status];
  const thermal = max("thermal_status");
  const btOn = last("bt_on");
  const btState = last("bt_state");
  const locOn = last("loc_enabled");
  const locModeName = last("loc_mode_name");
  const locProviders = last("loc_providers");
  const btText = btOn == null
    ? (btState || "--")
    : ((btOn ? "on" : "off") + (btState && btState !== "ON" && btState !== "OFF" ? " (" + btState + ")" : ""));
  const locText = locOn == null
    ? "--"
    : (locOn ? ((locModeName || "on") + (locProviders ? " (" + locProviders + ")" : "")) : "off");
  const mediaActive = last("media_active");
  const mediaPollOk = last("media_poll_ok");
  const mediaSampleStale = mediaPollOk === 0;
  const mediaStale = mediaActive !== 1 || mediaSampleStale;
  const app = last("media_app");
  const codec = last("media_codec");
  const mime = last("media_mime");
  const profile = last("media_profile");
  const codecsSeen = last("media_codecs");
  const w = last("media_w"), h = last("media_h");
  const hw = last("media_hw_dec"), sw = last("media_sw_dec");
  const path = hw && sw ? "hardware + software" : hw ? "hardware" : sw ? "software"
    : (codec && /^(c2\.qti\.|omx\.(qcom|qti)\.)/i.test(codec) ? "hardware"
      : codec && /^(c2\.android\.|omx\.google\.)/i.test(codec) ? "software" : null);
  const mediaDepth = last("media_bit_depth");
  const hdrOut = (v => (v == null ? null : v > 0))(last("hdr_active"));
  const streamHdr = (v => (v == null ? null : v > 0))(last("media_hdr_format"));
  const dispDepth = last("disp_bit_depth");
  const displayStale = mediaSampleStale;
  const outActive = last("audio_out_active");
  const inActive = last("audio_in_active");
  const outDevice = last("audio_out_device");
  const outBits = last("audio_out_bits");
  const outRate = last("audio_out_rate");
  const inDevice = last("audio_in_device");
  const inBits = last("audio_in_bits");
  const inRate = last("audio_in_rate");
  const volume = last("audio_out_volume_pct");
  const muted = last("audio_out_mute");
  const writeMs = last("audio_out_write_ms");
  const underruns = max("audio_out_underruns");
  const acodec = last("audio_codec");
  const acodecMime = last("audio_codec_mime");
  const acodecApp = last("audio_codec_app");
  const acodecAge = last("audio_codec_age_s");
  const acodecFresh = acodecAge == null || acodecAge <= 300;
  const codecText = acodec && acodecFresh
    ? acodec + (acodecMime ? " (" + acodecMime + ")" : "")
    : null;
  const audioSampleStale = mediaSampleStale;
  const audioStale = outActive !== 1 || audioSampleStale;
  const audioApp = last("audio_app") || (acodecFresh ? acodecApp : null);
  const outParts = [outDevice, outBits != null ? Math.round(outBits) + "-bit" : null,
    outRate != null ? (outRate / 1000).toFixed(1) + " kHz" : null].filter(Boolean);
  const inParts = [inDevice, inBits != null ? Math.round(inBits) + "-bit" : null,
    inRate != null ? (inRate / 1000).toFixed(1) + " kHz" : null].filter(Boolean);

  const groups = [
    { title: "Session", items: [
      ["Power saving", onoff(lowPower)],
      ["Hand tracking", onoff(hands)],
      ["Controllers", ctrl == null ? "--" : (ctrl ? "in use" : "idle")],
      ["Passthrough", pt == null ? "--" : ((pt ? "on" : "off") + (ptMode ? " (" + ptMode + ")" : ""))],
      ["Bluetooth", btText],
      ["Location", locText],
    ] },
    { title: "Battery & thermal", items: [
      ["On AC", yesno(ac)],
      ["Battery", batt == null ? "--" : Math.round(batt) + "%"],
      ["Charging", statusName || "--"],
      ["Controller battery", ctrlBatt],
      ["Thermal status", thermal == null ? "--" : "level " + Math.round(thermal)],
    ] },
    { title: "Media decode", items: [
      ["Status", mediaSampleStale ? "unavailable (last seen)" : (mediaActive == null ? "not captured" : (mediaActive ? "active" : "idle"))],
      ["App", app, mediaStale],
      ["Decoder", codec, mediaStale],
      ["Codec", mime, mediaStale],
      ["Profile", profile == null ? "--" : Math.round(profile), mediaStale],
      ["Decoders seen", codecsSeen, mediaStale],
      ["Resolution", w && h ? Math.round(w) + "×" + Math.round(h) : "--", mediaStale],
      ["Decode path", path, mediaStale],
      ["Stream bit depth", mediaDepth == null ? "--" : Math.round(mediaDepth) + "-bit", mediaStale],
      ["HDR stream", yesno(streamHdr), mediaStale],
    ] },
    { title: "Display", items: [
      ["Active bit depth", dispDepth == null ? "--" : Math.round(dispDepth) + "-bit", displayStale],
      ["Color mode", last("disp_color_mode"), displayStale],
      ["HDR output", yesno(hdrOut), displayStale],
      ["Brightness", pct(last("disp_brightness")), displayStale],
      ["SDR brightness", pct(last("disp_sdr_brightness")), displayStale],
    ] },
    { title: "Audio", items: [
      ["App", audioApp, audioStale],
      ["Playback", outActive == null ? "--" : (outActive ? "playing" : "idle"), audioSampleStale],
      ["Output", outActive == null ? "--" : (outActive ? (outParts.join(" · ") || "active") : "off"), audioSampleStale],
      ["Volume", volume == null ? "--" : Math.round(volume) + "%" + (muted ? " (muted)" : ""), audioSampleStale],
      ["Write latency", writeMs == null ? "--" : Math.round(writeMs) + " ms", audioStale],
      ["Underruns", underruns == null ? "--" : Math.round(underruns), audioStale],
      ["Microphone", inActive == null ? "--" : (inActive ? (inParts.join(" · ") || "active") : "off"), audioSampleStale],
      ["Mic mute", yesno(last("audio_mic_mute")), audioSampleStale],
      ["Source codec", codecText, audioStale],
    ] },
  ];
  groups.forEach(g => g.items.forEach(it => { if (it[1] == null || it[1] === "") it[1] = "--"; }));
  return groups;
}

function stateCard(run, title, groupTitles) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, title));
  const wanted = new Set(groupTitles || []);
  const wrap = el("div", "states");
  stateGroups(run).forEach(g => {
    if (wanted.size && !wanted.has(g.title)) return;
    const box = el("div", "stategroup");
    box.appendChild(el("h4", null, g.title));
    const grid = el("div", "stategrid");
    g.items.forEach(([k, v, stale]) => {
      grid.appendChild(textEl("span", "k", k));
      const value = textEl("span", stale ? "stale" : null, v);
      if (stale) value.title = "Last seen; current media/audio state is idle or unavailable";
      grid.appendChild(value);
    });
    box.appendChild(grid);
    wrap.appendChild(box);
  });
  card.appendChild(wrap);
  return card;
}

function modesCard(run) {
  return stateCard(run, "Modes & input", ["Session"]);
}

function batteryCard(run) {
  return stateCard(run, "Battery & thermal", ["Battery & thermal"]);
}

function mediaStateCard(run) {
  return stateCard(run, "Media, display & audio", ["Media decode", "Display", "Audio"]);
}

function compareStateCard(datasets, title, groupTitles) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, title));
  if (!datasets.length) return card;
  const t = el("table");
  const head = el("tr");
  head.appendChild(el("th", null, "State"));
  datasets.forEach(d => head.appendChild(textEl("th", null, d.label)));
  t.appendChild(head);
  const groups = datasets.map(d => stateGroups(d));
  const wanted = new Set(groupTitles || []);
  groups[0].forEach((g, gi) => {
    if (wanted.size && !wanted.has(g.title)) return;
    t.appendChild(tableSectionHeader(g.title, datasets.length + 1));
    g.items.forEach(([k], ii) => {
      const tr = el("tr");
      tr.appendChild(textEl("td", null, k));
      datasets.forEach((d, di) => {
        const item = groups[di][gi].items[ii];
        const td = textEl("td", item[2] ? "stale" : null, item[1]);
        if (item[2]) td.title = "Last seen; current media/audio state is idle or unavailable";
        tr.appendChild(td);
      });
      t.appendChild(tr);
    });
  });
  card.appendChild(t);
  return card;
}

function compareModesCard(datasets) {
  return compareStateCard(datasets, "Modes & input", ["Session"]);
}

function compareBatteryCard(datasets) {
  return compareStateCard(datasets, "Battery & thermal", ["Battery & thermal"]);
}

function compareMediaStateCard(datasets) {
  return compareStateCard(datasets, "Media, display & audio", ["Media decode", "Display", "Audio"]);
}

function chips(items) {
  const w = el("div", "chips");
  items.forEach(([k, v]) => {
    const chip = el("span", "chip");
    chip.appendChild(textEl("span", "k", k));
    chip.appendChild(document.createTextNode(" "));
    chip.appendChild(textEl("b", null, v));
    w.appendChild(chip);
  });
  return w;
}

function runLegend(datasets, label) {
  const wrap = el("div", "cmp-legend graph-runlegend");
  if (label) wrap.appendChild(textEl("span", "muted", label));
  datasets.forEach((d, i) => {
    const item = el("span", "cmplegenditem");
    const dot = el("span", "statdot");
    dot.style.background = COLORS[i % COLORS.length];
    item.appendChild(dot);
    item.appendChild(document.createTextNode(d.label));
    wrap.appendChild(item);
  });
  return wrap;
}

function resultsSection(items, defaultId, title, subtitle) {
  const card = el("section", "card results");
  const header = el("div", "results-header");
  const heading = el("h3", "results-title");
  heading.textContent = title || "Results";
  header.appendChild(heading);
  if (subtitle) {
    const note = el("div", "results-note muted");
    note.textContent = subtitle;
    header.appendChild(note);
  }
  card.appendChild(header);
  const bar = el("div", "inner-tabs");
  const body = el("div", "results-body");
  card.appendChild(bar);
  card.appendChild(body);
  let active = items.some(i => i.id === resultsTab) ? resultsTab : (defaultId || items[0].id);
  let syncToken = 0;
  const buttons = {};
  items.forEach(it => {
    const b = el("button", "innertab", it.label);
    b.onclick = () => { if (active !== it.id) { active = it.id; resultsTab = it.id; sync(); } };
    buttons[it.id] = b;
    bar.appendChild(b);
  });
  function sync() {
    disposeCharts();
    pinnedRenderers = [];
    const my = ++syncToken;
    body.innerHTML = "";
    items.forEach(it => buttons[it.id].classList.toggle("active", it.id === active));
    const it = items.find(x => x.id === active) || items[0];
    it.render(body, () => my === syncToken && active === it.id);
  }
  sync();
  return card;
}

function tableSectionHeader(title, colspan, forceOpen = false) {
  const sr = el("tr", "tablesection");
  sr.dataset.title = title;
  const td = el("td");
  td.colSpan = colspan;
  td.style.background = "#1c2230";
  td.style.color = "#9fd0ff";
  const collapsed = !forceOpen && collapsedTableSections.has(title);
  const chev = el("span", "tchev", collapsed ? "\u25b8" : "\u25be");
  const strong = el("b");
  strong.textContent = title;
  td.appendChild(chev);
  td.appendChild(strong);
  sr.appendChild(td);
  sr.tabIndex = 0;
  sr.setAttribute("role", "button");
  sr.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      sr.onclick();
    }
  };
  sr.onclick = () => {
    if (findOpen) closeFind();
    const collapse = !collapsedTableSections.has(title);
    if (collapse) collapsedTableSections.add(title);
    else collapsedTableSections.delete(title);
    chev.textContent = collapse ? "\u25b8" : "\u25be";
    let row = sr.nextElementSibling;
    while (row && !row.classList.contains("tablesection")) {
      row.style.display = collapse ? "none" : "";
      row = row.nextElementSibling;
    }
  };
  return sr;
}

function extraTableHeader(title, colspan, forceOpen = false) {
  const sr = el("tr", "tablesection extra");
  sr.dataset.title = title;
  const td = el("td");
  td.colSpan = colspan;
  td.style.background = "#171d27";
  td.style.color = "#e6edf3";
  const collapsed = !forceOpen && collapsedTableSections.has(title);
  const chev = el("span", "tchev", collapsed ? "\u25b8" : "\u25be");
  const strong = el("b");
  strong.textContent = title;
  td.appendChild(chev);
  td.appendChild(strong);
  sr.appendChild(td);
  sr.tabIndex = 0;
  sr.setAttribute("role", "button");
  sr.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      sr.onclick();
    }
  };
  sr.onclick = () => {
    if (findOpen) closeFind();
    const collapse = !collapsedTableSections.has(title);
    if (collapse) collapsedTableSections.add(title);
    else collapsedTableSections.delete(title);
    chev.textContent = collapse ? "\u25b8" : "\u25be";
    let row = sr.nextElementSibling;
    while (row) {
      row.style.display = collapse ? "none" : "";
      row = row.nextElementSibling;
    }
    if (!collapse) applyTableCollapseToDom();
  };
  return sr;
}

function allTableTitles() {
  const titles = (SPEC.groups || []).map(g => g.title);
  if ((SPEC.groups || []).some(g => EXTRA_SECTIONS.has(g.section))) titles.push("Extra");
  return titles;
}

function applyTableCollapseToDom() {
  const headers = Array.from(document.querySelectorAll("tr.tablesection"));
  // Normal group headers first, then the Extra wrapper last, so a collapsed
  // Extra cannot be undone by a group header that follows it.
  headers.filter(sr => !sr.classList.contains("extra")).forEach(sr => {
    const title = sr.dataset.title || "";
    const collapsed = collapsedTableSections.has(title);
    const chev = sr.querySelector(".tchev");
    if (chev) chev.textContent = collapsed ? "\u25b8" : "\u25be";
    let row = sr.nextElementSibling;
    while (row && !row.classList.contains("tablesection")) {
      row.style.display = collapsed ? "none" : "";
      row = row.nextElementSibling;
    }
  });
  headers.filter(sr => sr.classList.contains("extra")).forEach(sr => {
    const title = sr.dataset.title || "";
    const collapsed = collapsedTableSections.has(title);
    const chev = sr.querySelector(".tchev");
    if (chev) chev.textContent = collapsed ? "\u25b8" : "\u25be";
    if (collapsed) {
      let row = sr.nextElementSibling;
      while (row) {
        row.style.display = "none";
        row = row.nextElementSibling;
      }
    }
  });
}

function quickSummaryCard(run) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Quick summary"));
  card.appendChild(chips(keyStats(run)));
  return card;
}

function summaryTableCard(run) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Full table  (min / average / max)"));
  const controls = el("div", "proccontrols tablecontrols");
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Search metrics...";
  search.value = summaryTableQuery;
  const count = el("span", "muted tablecount");
  controls.appendChild(search);
  controls.appendChild(count);
  card.appendChild(controls);
  const host = el("div");
  card.appendChild(host);

  const rows = summaryRows(run);
  const main = rows.filter(r => !EXTRA_SECTIONS.has(r.groupSection));
  const extra = rows
    .filter(r => EXTRA_SECTIONS.has(r.groupSection))
    .sort((a, b) => extraRank(a.groupSection) - extraRank(b.groupSection));

  function render() {
    const q = summaryTableQuery.trim().toLowerCase();
    const matches = r => !q || (r.label + " " + (r.unit || "") + " " + (r.section || "")).toLowerCase().includes(q);
    const visibleMain = main.filter(matches);
    const visibleExtra = extra.filter(matches);
    host.innerHTML = "";
    count.textContent = (visibleMain.length + visibleExtra.length) + " metrics";
    if (!visibleMain.length && !visibleExtra.length) {
      host.appendChild(textEl("div", "muted", "No metrics match this search."));
      return;
    }
    const t = el("table", "sticky-table");
    const head = el("tr", "tablehead");
    ["Metric", "Min", "Average", "Max"].forEach(h => head.appendChild(el("th", null, h)));
    t.appendChild(head);
    const addRow = (r, forceOpen) => {
      const a = r.arr.filter(x => x != null);
      const mn = a.length ? Math.min(...a) : null;
      const mx = a.length ? Math.max(...a) : null;
      const av = a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
      const row = el("tr");
      row.dataset.pinRowKind = "table";
      row.dataset.pinRowKey = r.key;
      if (!forceOpen && collapsedTableSections.has(r.section)) row.style.display = "none";
      const scale = r.scale ?? 1;
      const labelCell = el("td", "pinned-name-cell");
      labelCell.appendChild(pinButton("table", metricPinItem(r)));
      labelCell.appendChild(document.createTextNode(r.label + (r.unit ? " (" + r.unit + ")" : "")));
      row.appendChild(labelCell);
      row.appendChild(textEl("td", null, fmt(mn == null ? null : mn * scale, "", r.decimals)));
      row.appendChild(textEl("td", null, fmt(av == null ? null : av * scale, "", r.decimals)));
      row.appendChild(textEl("td", null, fmt(mx == null ? null : mx * scale, "", r.decimals)));
      t.appendChild(row);
      if (findPin("table", r.key)) row.classList.add("pinned-row");
    };
    let last = null;
    visibleMain.forEach(r => {
      if (r.section !== last) {
        t.appendChild(tableSectionHeader(r.section, 4, !!q));
        last = r.section;
      }
      addRow(r, !!q);
    });
    if (visibleExtra.length) {
      const h = extraTableHeader("Extra", 4, !!q);
      t.appendChild(h);
      last = null;
      visibleExtra.forEach(r => {
        if (r.section !== last) {
          t.appendChild(tableSectionHeader(r.section, 4, !!q));
          last = r.section;
        }
        addRow(r, !!q);
      });
      if (!q && collapsedTableSections.has("Extra")) {
        let row = h.nextElementSibling;
        while (row) {
          row.style.display = "none";
          row = row.nextElementSibling;
        }
      }
    }
    host.appendChild(t);
  }

  search.oninput = () => { summaryTableQuery = search.value; render(); };
  render();
  return card;
}

function featureList(f) {
  if (!f) return "--";
  const on = [];
  if (f.logcat) on.push("logcat");
  if (f.root_fan) on.push("fan/root");
  if (f.sensors) on.push("sensors");
  if (f.processes) on.push("processes");
  if (f.process_io) on.push("disk I/O");
  return on.length ? on.join(", ") : "poll only";
}

function runMetaCard(run) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Run metadata"));
  const head = el("div", "runhead");
  const title = el("h2");
  title.textContent = run.label;
  head.appendChild(title);
  const editBtn = el("button", "toolbtn", "Edit");
  const exportBtn = el("button", "toolbtn", "Export HTML");
  exportBtn.title = "Download a self-contained HTML report";
  exportBtn.onclick = (e) => {
    e.stopPropagation();
    downloadReport([run.label], exportBtn);
  };
  const actions = el("div", "runactions");
  if (!OFFLINE) {
    actions.appendChild(exportBtn);
    actions.appendChild(editBtn);
  }
  head.appendChild(actions);
  card.appendChild(head);

  const note = el("div", "runnotes");
  note.textContent = run.meta.notes || "No notes.";
  card.appendChild(note);

  const meta = run.meta || {};
  const info = el("div", "grid2");
  const rows = [
    ["Started", meta.started],
    ["Recording started", meta.recording_started || "--"],
    ["Duration", (meta.duration_actual_s ?? meta.duration_s) != null ? fmt(meta.duration_actual_s ?? meta.duration_s) + " s" : "--"],
    ["Rows", meta.rows],
    ["Interval", meta.interval_s ? meta.interval_s + " s" : "--"],
    ["Schema / tool", (meta.schema_version ? "v" + meta.schema_version : "?") + " / " + (meta.tool_version || "?")],
    ["Features", featureList(meta.features)],
  ];
  rows.forEach(([k, v]) => {
    info.appendChild(textEl("span", "k", k));
    info.appendChild(textEl("span", null, v == null || v === "" ? "--" : String(v)));
  });
  card.appendChild(info);

  const form = el("div", "editform");
  form.style.display = "none";
  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = run.label;
  const notesInput = document.createElement("textarea");
  notesInput.rows = 3;
  notesInput.value = run.meta.notes || "";
  form.appendChild(el("label", null, "Name"));
  form.appendChild(nameInput);
  form.appendChild(el("label", null, "Notes"));
  form.appendChild(notesInput);
  const row = el("div", "editrow");
  const saveBtn = el("button", "primary", "Save");
  saveBtn.type = "button";
  const cancelBtn = el("button", "toolbtn", "Cancel");
  cancelBtn.type = "button";
  const msg = el("span", "muted");
  row.appendChild(saveBtn);
  row.appendChild(cancelBtn);
  row.appendChild(msg);
  form.appendChild(row);
  card.appendChild(form);

  editBtn.onclick = () => {
    form.style.display = "";
    editBtn.style.display = "none";
    nameInput.focus();
  };
  cancelBtn.onclick = () => {
    form.style.display = "none";
    editBtn.style.display = "";
    nameInput.value = run.label;
    notesInput.value = run.meta.notes || "";
    msg.textContent = "";
  };
  saveBtn.onclick = async () => {
    const body = { name: nameInput.value.trim(), notes: notesInput.value };
    let resp;
    try {
      resp = await fetch("/api/runs/" + encodeURIComponent(run.label), {
        method: "PATCH", headers: { "Content-Type": "application/json", "X-GXR-Profiler-Token": API_TOKEN }, body: JSON.stringify(body),
      });
    } catch (e) {
      msg.textContent = "Error: " + e;
      return;
    }
    if (!resp.ok) {
      msg.textContent = (await apiError(resp)).slice(0, 200);
      return;
    }
    const res = await resp.json();
    compareSelection = compareSelection.map(x => (x === run.label ? res.label : x));
    await loadRuns();
    await showRun(res.label);
  };
  return card;
}

function pinnedCardShell(kind, title) {
  const card = el("section", "card pinned-card");
  const head = el("div", "charthead pinned-head");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, title));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  const clear = el("button", "toolbtn", "Clear");
  clear.type = "button";
  clear.title = "Clear pinned " + kind + " items";
  clear.onclick = () => clearPins(kind);
  head.appendChild(clear);
  card.appendChild(head);
  const body = el("div", "pinned-body");
  card.appendChild(body);
  return { card, body, count, clear };
}

function pinnedTableCard(datasets) {
  const shell = pinnedCardShell("table", "Pinned metrics");
  const render = () => {
    shell.card.hidden = pins.table.length === 0;
    shell.count.textContent = pins.table.length ? pins.table.length + " pinned" : "";
    shell.clear.disabled = pins.table.length === 0;
    shell.body.innerHTML = "";
    if (!pins.table.length) return;
    const multi = datasets.length > 1;
    const t = el("table", "pinned-table");
    const head = el("tr");
    head.appendChild(el("th", null, "Metric"));
    if (multi) datasets.forEach(d => head.appendChild(textEl("th", null, d.label)));
    else ["Min", "Average", "Max"].forEach(h => head.appendChild(el("th", null, h)));
    t.appendChild(head);
    pins.table.forEach(pin => {
      const tr = el("tr");
      const nameCell = el("td", "pinned-name-cell");
      nameCell.appendChild(pinButton("table", pin));
      nameCell.appendChild(document.createTextNode(pin.label + (pin.unit ? " (" + pin.unit + ")" : "")));
      tr.appendChild(nameCell);
      const scale = pin.scale ?? 1;
      if (multi) {
        datasets.forEach(d => {
          const arr = (d.series || {})[pin.key];
          const st = arr ? stat3(arr) : null;
          const cell = st
            ? fmt(st.min * scale, "", pin.decimals) + " / " + fmt(st.avg * scale, "", pin.decimals) + " / " + fmt(st.max * scale, "", pin.decimals)
            : "--";
          tr.appendChild(textEl("td", st ? null : "pinned-missing", cell));
        });
      } else {
        const arr = ((datasets[0] || {}).series || {})[pin.key];
        const st = arr ? stat3(arr) : null;
        [st && st.min, st && st.avg, st && st.max].forEach(v =>
          tr.appendChild(textEl("td", st ? null : "pinned-missing", fmt(v == null ? null : v * scale, "", pin.decimals))));
      }
      t.appendChild(tr);
    });
    shell.body.appendChild(t);
  };
  pinnedRenderers.push(render);
  render();
  return shell.card;
}

function pinnedGraphsCard(datasets) {
  const shell = pinnedCardShell("graph", "Pinned graphs");
  const render = () => {
    shell.card.hidden = pins.graph.length === 0;
    shell.count.textContent = pins.graph.length ? pins.graph.length + " pinned" : "";
    shell.clear.disabled = pins.graph.length === 0;
    disposePinnedCharts();
    shell.body.innerHTML = "";
    if (!pins.graph.length) return;
    const grid = el("div", "pinned-graphgrid");
    pins.graph.forEach((pin, idx) => {
      const box = el("div", "minicard pinned-minicard");
      const title = el("div", "minititle pinned-minititle");
      title.appendChild(pinButton("graph", pin));
      title.appendChild(textEl("span", "minititle-text", pin.label + (pin.unit ? " (" + pin.unit + ")" : "")));
      box.appendChild(title);
      const hasData = datasets.some(d => (d.series || {})[pin.key] && d.series[pin.key].some(v => v != null));
      if (!hasData) {
        box.appendChild(el("div", "muted pinned-empty", "Not captured in this run."));
      } else {
        const div = el("div", "minichart");
        box.appendChild(div);
        const ch = echarts.init(div, "dark");
        pinnedCharts.push(ch);
        applyMetricChart(ch, pin, datasets, idx);
      }
      const stats = miniStats(pin, datasets, datasets.length > 1, idx);
      if (stats) box.appendChild(stats);
      grid.appendChild(box);
    });
    shell.body.appendChild(grid);
  };
  pinnedRenderers.push(render);
  render();
  return shell.card;
}

const PROCESS_PIN_METRICS = [
  { key: "cpu_peak", label: "CPU peak", unit: "%", decimals: 1 },
  { key: "cpu", label: "CPU 5m", unit: "%", decimals: 1 },
  { key: "rss_peak", label: "RSS peak", unit: "MB", decimals: 0, scale: 1 / 1024 },
  { key: "gpu_peak", label: "GPU peak", unit: "MB", decimals: 0, scale: 1 / 1024 },
  { key: "io_r_peak", label: "Disk read", unit: "MB/s", decimals: 1, scale: 1e-6 },
  { key: "io_w_peak", label: "Disk write", unit: "MB/s", decimals: 1, scale: 1e-6 },
];

function renderPinnedProcessCharts(host, labels, matches, seriesByLabel, datasets) {
  const multi = labels.length > 1;
  const statsRuns = [];
  labels.forEach((label, i) => {
    const row = matches[i];
    const s = row ? (seriesByLabel[i] || {})[row.key] : null;
    if (s) statsRuns.push({ label, series: s, elapsed: s.elapsed });
  });
  let shown = 0;
  PROC_CHART_GROUPS.forEach((def, di) => {
    const starts = {};
    const lines = [];
    labels.forEach((label, i) => {
      const row = matches[i];
      if (!row) return;
      const s = (seriesByLabel[i] || {})[row.key];
      if (!s) return;
      const start = parseRunStart(datasets[i]);
      def.metrics.forEach((m, mi) => {
        if (!(s[m.key] || []).some(v => v != null)) return;
        const name = multi ? label + " · " + m.label : m.label;
        starts[name] = start;
        const scale = m.scale ?? 1;
        const points = (s.elapsed || []).map((t, idx) => [t, s[m.key][idx] == null ? null : s[m.key][idx] * scale]);
        const sparse = points.filter(p => p[1] != null).length <= 2;
        const color = multi ? COLORS[i % COLORS.length] : SERIES_COLORS[mi % SERIES_COLORS.length];
        lines.push({
          name, type: "line", showSymbol: sparse, symbolSize: sparse ? 5 : 0, connectNulls: false,
          lineStyle: { width: 1.6, color, type: m.dashed ? "dashed" : "solid" },
          itemStyle: { color }, data: points,
        });
      });
    });
    if (!lines.length) return;
    shown++;
    const box = el("div", "procchart-box");
    box.appendChild(procChartTitle(def));
    const div = el("div", "procchart");
    box.appendChild(div);
    host.appendChild(box);
    const ch = echarts.init(div, "dark");
    pinnedCharts.push(ch);
    ch.setOption(procChartOption(def, lines, starts));
    const stats = procChartStats(def, statsRuns, multi);
    if (stats) box.appendChild(stats);
    requestAnimationFrame(() => { try { ch.resize(); } catch (e) {} });
  });
  if (!shown) host.appendChild(el("div", "muted pinned-empty", "No process timeline data for the selected run(s)."));
}

function pinnedProcessesCard(datasets) {
  const shell = pinnedCardShell("process", "Pinned processes");
  let token = 0;
  const render = async () => {
    const my = ++token;
    shell.card.hidden = pins.process.length === 0;
    shell.count.textContent = pins.process.length ? pins.process.length + " pinned" : "";
    shell.clear.disabled = pins.process.length === 0;
    disposePinnedCharts();
    shell.body.innerHTML = "";
    if (!pins.process.length) return;
    shell.body.appendChild(el("div", "muted pinned-loading", "Loading pinned processes..."));
    const labels = datasets.map(d => d.label);
    const loaded = await Promise.all(labels.map(async label => {
      if (datasets.length === 1) {
        try {
          const data = await getProcData(label);
          return { rows: data.rows || [], series: data.series || {} };
        } catch (e) {
          return { rows: [], series: {} };
        }
      }
      const [rows, series] = await Promise.all([
        fetchProcRows(label).catch(() => []),
        loadProcSeries(label),
      ]);
      return { rows: rows || [], series: series || {} };
    }));
    if (my !== token || !shell.body.isConnected) return;
    shell.body.innerHTML = "";
    const rowsByLabel = loaded.map(d => d.rows);
    const seriesByLabel = loaded.map(d => d.series);
    if (datasets.length > 1) shell.body.appendChild(runLegend(datasets, "Runs"));
    pins.process.forEach(pin => {
      const matches = labels.map((label, i) => findProcForPin(rowsByLabel[i], pin));
      const first = matches.find(Boolean);
      const block = el("div", "pinned-proc");
      const head = el("div", "pinned-proc-head");
      head.appendChild(pinButton("process", pin));
      if (first) {
        const name = el("button", "pinned-proc-name", pin.name || pin.key);
        name.type = "button";
        name.title = "Open process charts";
        name.onclick = () => {
          if (activeTab === "compare") {
            selectedCmpProc = procStableKey(first);
            renderCompareBody();
          } else {
            selectedProc = first.key;
            renderRunView();
          }
        };
        head.appendChild(name);
      } else {
        head.appendChild(textEl("b", "pinned-proc-name", pin.name || pin.key));
      }
      block.appendChild(head);
      const subParts = [pin.package, pin.uid == null ? "" : "UID " + pin.uid].filter(Boolean);
      if (subParts.length) block.appendChild(textEl("div", "muted procsub", subParts.join(" · ")));

      const t = el("table", "pinned-proc-table");
      const htr = el("tr");
      htr.appendChild(el("th", null, "Run"));
      PROCESS_PIN_METRICS.forEach(m => htr.appendChild(textEl("th", null, m.label + (m.unit ? " (" + m.unit + ")" : ""))));
      t.appendChild(htr);
      labels.forEach((label, i) => {
        const row = matches[i];
        const tr = el("tr");
        tr.appendChild(textEl("td", row ? null : "pinned-missing", row ? label : label + " (not present)"));
        PROCESS_PIN_METRICS.forEach(m => {
          const v = row ? row[m.key] : null;
          const scaled = v == null ? null : v * (m.scale ?? 1);
          tr.appendChild(textEl("td", row ? null : "pinned-missing", fmt(scaled, "", m.decimals)));
        });
        t.appendChild(tr);
      });
      block.appendChild(t);

      const missing = labels.filter((label, i) => !matches[i]);
      if (!first) block.appendChild(el("div", "muted pinned-empty", "Not present in the selected run(s)."));
      else if (missing.length) block.appendChild(el("div", "muted pinned-empty", "Not present in: " + missing.join(", ")));

      const chartHost = el("div", "proccharts pinned-proc-charts");
      block.appendChild(chartHost);
      if (first) renderPinnedProcessCharts(chartHost, labels, matches, seriesByLabel, datasets);
      shell.body.appendChild(block);
    });
  };
  pinnedRenderers.push(render);
  render();
  return shell.card;
}

async function renderRunView() {
  if (findOpen) closeFind();
  const v = document.getElementById("view");
  disposeCharts();
  v.innerHTML = "";
  if (!currentRun) {
    v.appendChild(el("section", "card", "<h3>Select a run</h3><p class='muted'>Pick a run from the left.</p>"));
    updateStickyOffsets();
    return;
  }
  v.appendChild(resultsSection([
    { id: "metadata", label: "Metadata", render: host => host.appendChild(runMetadataPane(currentRun)) },
    {
      id: "table",
      label: "Full table",
      render: host => {
        host.appendChild(pinnedTableCard([currentRun]));
        host.appendChild(summaryTableCard(currentRun));
      },
    },
    {
      id: "graphs",
      label: "Graphs",
      render: host => {
        host.appendChild(pinnedGraphsCard([currentRun]));
        renderSections(host, [currentRun]);
      },
    },
    {
      id: "processes",
      label: "Processes",
      render: (host, isActive) => {
        host.appendChild(pinnedProcessesCard([currentRun]));
        host.appendChild(el("div", "muted proc-loading", "Loading processes..."));
        processesCard(currentRun.label).then(pc => {
          if (!isActive()) return;
          const loading = host.querySelector(".proc-loading");
          if (loading) loading.remove();
          if (pc) host.appendChild(pc);
          else host.appendChild(el("div", "muted", "No process data for this run (record with --processes)."));
        });
      },
    },
  ], "metadata", currentRun.label, (currentRun.meta && currentRun.meta.notes) || ""));
  updateStickyOffsets();
}

function runMetadataPane(run) {
  const box = el("div", "metatab");
  box.appendChild(quickSummaryCard(run));
  const top = el("div", "twocol");
  top.appendChild(runMetaCard(run));
  top.appendChild(deviceCard(run.meta));
  box.appendChild(top);
  const stateTop = el("div", "twocol");
  stateTop.appendChild(modesCard(run));
  stateTop.appendChild(batteryCard(run));
  box.appendChild(stateTop);
  box.appendChild(trackingCard(run.meta));
  box.appendChild(mediaStateCard(run));
  return box;
}

function stat3(arr) {
  const a = (arr || []).filter(x => x != null);
  if (!a.length) return null;
  return { min: Math.min(...a), avg: a.reduce((s, x) => s + x, 0) / a.length, max: Math.max(...a) };
}

function compareClass(value, lo, hi) {
  if (!Number.isFinite(value) || !Number.isFinite(lo) || !Number.isFinite(hi) || lo === hi) return "";
  if (value === lo) return "cmp-low";
  if (value === hi) return "cmp-high";
  return "";
}

function metricArrays(datasets) {
  const bandDef = id => (SPEC.bands || []).find(b => b.id === id) || { label: id, unit: "" };
  const out = [];
  SPEC.groups.forEach(g => {
    const groupSection = g.section || "Other";
    const push = (key, label, unit, getter, scale, decimals) => {
      const perRun = datasets.map(d => getter(d.series));
      if (perRun.some(a => a && a.some(x => x != null))) {
        out.push({ key, section: g.title, groupSection, label, unit, scale, decimals, perRun });
      }
    };
    g.series.forEach(s => push(s.col, s.label, s.unit, ser => ser[s.col], s.scale ?? 1, s.decimals ?? null));
    (g.bands || []).forEach(bid => {
      const b = bandDef(bid);
      const extra = [b.scale ?? 1, b.decimals ?? 1];
      push("band::" + bid + "::max", b.label + " (hottest)", b.unit, ser => ser["band::" + bid + "::max"], ...extra);
      push("band::" + bid + "::avg", b.label + " (average)", b.unit, ser => ser["band::" + bid + "::avg"], ...extra);
    });
  });
  return out;
}

function compareQuickSummaryCard(datasets) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Quick summary"));
  if (!datasets.length) return card;
  const wrap = el("div", "table-scroll");
  const t = el("table", "quicksummary");
  const head = el("tr");
  head.appendChild(el("th", null, "Run"));
  keyStats(datasets[0]).forEach(([label]) => head.appendChild(el("th", null, label)));
  t.appendChild(head);
  datasets.forEach(d => {
    const tr = el("tr");
    tr.appendChild(textEl("td", "quicksummary-run", d.label));
    keyStats(d).forEach(([, value]) => tr.appendChild(textEl("td", null, value)));
    t.appendChild(tr);
  });
  wrap.appendChild(t);
  card.appendChild(wrap);
  return card;
}

function compareTableCard(datasets) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Full table  (min / average / max)"));
  card.appendChild(el("div", "muted cmp-legend", "Per metric: blue = lowest average, orange = highest average across runs."));
  const controls = el("div", "proccontrols tablecontrols");
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Search metrics...";
  search.value = cmpTableQuery;
  const count = el("span", "muted tablecount");
  controls.appendChild(search);
  controls.appendChild(count);
  card.appendChild(controls);
  const host = el("div");
  card.appendChild(host);

  const rows = metricArrays(datasets);
  const main = rows.filter(m => !EXTRA_SECTIONS.has(m.groupSection));
  const extra = rows
    .filter(m => EXTRA_SECTIONS.has(m.groupSection))
    .sort((a, b) => extraRank(a.groupSection) - extraRank(b.groupSection));

  function render() {
    const q = cmpTableQuery.trim().toLowerCase();
    const matches = m => !q || (m.label + " " + (m.unit || "") + " " + (m.section || "")).toLowerCase().includes(q);
    const visibleMain = main.filter(matches);
    const visibleExtra = extra.filter(matches);
    host.innerHTML = "";
    count.textContent = (visibleMain.length + visibleExtra.length) + " metrics";
    if (!visibleMain.length && !visibleExtra.length) {
      host.appendChild(textEl("div", "muted", "No metrics match this search."));
      return;
    }
    const t = el("table", "sticky-table");
    const head = el("tr", "tablehead");
    head.appendChild(el("th", null, "Metric"));
    datasets.forEach(d => head.appendChild(textEl("th", null, d.label)));
    t.appendChild(head);
    const addRow = (m, forceOpen) => {
      const tr = el("tr");
      tr.dataset.pinRowKind = "table";
      tr.dataset.pinRowKey = m.key;
      if (!forceOpen && collapsedTableSections.has(m.section)) tr.style.display = "none";
      const labelCell = el("td", "pinned-name-cell");
      labelCell.appendChild(pinButton("table", metricPinItem(m)));
      labelCell.appendChild(document.createTextNode(m.label + (m.unit ? " (" + m.unit + ")" : "")));
      tr.appendChild(labelCell);
      const stats = m.perRun.map(stat3);
      const avgs = stats.map(s => (s ? s.avg : null));
      const valid = avgs.filter(v => Number.isFinite(v));
      const lo = valid.length ? Math.min(...valid) : null;
      const hi = valid.length ? Math.max(...valid) : null;
      const scale = m.scale ?? 1;
      datasets.forEach((d, i) => {
        const s = stats[i];
        const cls = s ? compareClass(avgs[i], lo, hi) : "";
        const cell = s
          ? fmt(s.min * scale, "", m.decimals) + " / " + fmt(s.avg * scale, "", m.decimals) + " / " + fmt(s.max * scale, "", m.decimals)
          : "--";
        const td = textEl("td", cls || null, cell);
        if (cls) td.title = cls === "cmp-low" ? "lowest average" : "highest average";
        tr.appendChild(td);
      });
      t.appendChild(tr);
      if (findPin("table", m.key)) tr.classList.add("pinned-row");
    };
    let last = null;
    visibleMain.forEach(m => {
      if (m.section !== last) {
        t.appendChild(tableSectionHeader(m.section, 1 + datasets.length, !!q));
        last = m.section;
      }
      addRow(m, !!q);
    });
    if (visibleExtra.length) {
      const h = extraTableHeader("Extra", 1 + datasets.length, !!q);
      t.appendChild(h);
      last = null;
      visibleExtra.forEach(m => {
        if (m.section !== last) {
          t.appendChild(tableSectionHeader(m.section, 1 + datasets.length, !!q));
          last = m.section;
        }
        addRow(m, !!q);
      });
      if (!q && collapsedTableSections.has("Extra")) {
        let row = h.nextElementSibling;
        while (row) {
          row.style.display = "none";
          row = row.nextElementSibling;
        }
      }
    }
    host.appendChild(t);
  }

  search.oninput = () => { cmpTableQuery = search.value; render(); };
  render();
  return card;
}

function compareDevicesCard(datasets) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Device metadata"));
  const t = el("table");
  const head = el("tr");
  ["Run", "Model", "Region", "Android", "Build", "SoC", "Manufactured", "First setup", "Panel", "Wi-Fi", "Root"].forEach(h =>
    head.appendChild(el("th", null, h)));
  t.appendChild(head);
  datasets.forEach(d => {
    const di = (d.meta && d.meta.device_info) || {};
    const setup = di.first_setup || {};
    const tr = el("tr");
    [
      d.label, di.model, regionShort(di), di.android, di.build_display_id, di.soc, di.manufacture_date,
      setup.first_setup_at ? calibrationDate(setup.first_setup_at) : null,
      (di.panel || {}).active, (di.wifi || {}).standard_name, (di.root || {}).manager,
    ].forEach(v => tr.appendChild(textEl("td", null, v == null ? "--" : String(v))));
    t.appendChild(tr);
  });
  const wrap = el("div", "table-scroll");
  wrap.appendChild(t);
  card.appendChild(wrap);
  return card;
}

function compareTrackingCard(datasets) {
  const card = el("section", "card");
  card.appendChild(el("h3", null, "Input & boundary"));
  const t = el("table");
  const head = el("tr");
  head.appendChild(el("th", null, "Metric"));
  datasets.forEach(d => head.appendChild(el("th", null, d.label)));
  t.appendChild(head);
  const base = trackingRows(((datasets[0] || {}).meta) || {});
  base.forEach(([label]) => {
    const tr = el("tr");
    tr.appendChild(textEl("td", null, label));
    datasets.forEach(d => {
      const value = (trackingRows(d.meta).find(([k]) => k === label) || [])[1];
      tr.appendChild(textEl("td", null, value == null ? "--" : String(value)));
    });
    t.appendChild(tr);
  });
  const wrap = el("div", "table-scroll");
  wrap.appendChild(t);
  card.appendChild(wrap);
  return card;
}

function cmpMetric() {
  return CMP_PROC_METRICS.find(m => m.key === cmpProcMetric) || CMP_PROC_METRICS[0];
}

function cmpProcMatches(e) {
  if (cmpProcType !== "all" && procCategory(e) !== cmpProcType) return false;
  if (cmpProcBackground && !["background", "cached"].includes(e.oom_class)) return false;
  const q = cmpProcQuery.trim().toLowerCase();
  return !q || (e.name + " " + (e.package || "") + " " + (e.uid == null ? "" : e.uid)).toLowerCase().includes(q);
}

function setCmpHeader(th, label, sub, active) {
  th.textContent = "";
  const main = el("span", "prochead-label");
  main.appendChild(document.createTextNode(label));
  if (active) main.appendChild(el("span", "sortarrow", cmpProcSort.dir < 0 ? "▼" : "▲"));
  th.appendChild(main);
  if (sub) th.appendChild(el("span", "procunit", sub));
}

async function compareProcessesCard(labels) {
  const lists = await Promise.all(labels.map(l => fetchProcRows(l)));
  if (!lists.some(l => l && l.length)) return null;
  const metric = cmpMetric();
  if (!CMP_PROC_METRICS.some(m => m.key === cmpProcMetric)) cmpProcMetric = CMP_PROC_METRICS[0].key;
  const entries = new Map();
  lists.forEach((rows, ri) => {
    (rows || []).forEach(r => {
      // PID is run-local; compare the same logical process across runs.
      const k = [r.name || "", r.uid == null ? "" : r.uid, r.package || ""].join("|");
      let e = entries.get(k);
      if (!e) {
        e = {
          key: k, name: r.name, uid: r.uid, kind: r.kind, package: r.package,
          pkg_system: r.pkg_system, oom_class: r.oom_class, byRun: {}, byRunKey: {},
        };
        entries.set(k, e);
      }
      e.byRun[labels[ri]] = r;
      e.byRunKey[labels[ri]] = r.key;
      if (r.package) e.package = r.package;
      if (r.pkg_system) e.pkg_system = true;
    });
  });
  if (selectedCmpProc && !entries.has(selectedCmpProc)) selectedCmpProc = null;
  const card = el("section", "card process-card");
  const head = el("div", "runhead");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, "Processes"));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  card.appendChild(head);

  const controls = el("div", "proccontrols");
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "Search process or package...";
  search.value = cmpProcQuery;
  const typeSel = document.createElement("select");
  [["all", "All processes"], ["app", "Apps"], ["system", "System"], ["system-app", "System apps"], ["kernel", "Kernel"], ["isolated", "Isolated"]].forEach(([v, l]) => {
    const o = document.createElement("option"); o.value = v; o.textContent = l; typeSel.appendChild(o);
  });
  typeSel.value = cmpProcType;
  const sortRunSel = document.createElement("select");
  sortRunSel.title = "Sort full field columns by this run";
  const maxOpt = document.createElement("option");
  maxOpt.value = "__max";
  maxOpt.textContent = "Sort by: max across runs";
  sortRunSel.appendChild(maxOpt);
  labels.forEach(l => {
    const o = document.createElement("option");
    o.value = l;
    o.textContent = "Sort by: " + l;
    sortRunSel.appendChild(o);
  });
  if (cmpProcSortRun !== "__max" && !labels.includes(cmpProcSortRun)) cmpProcSortRun = "__max";
  sortRunSel.value = cmpProcSortRun;
  sortRunSel.onchange = () => {
    cmpProcSortRun = sortRunSel.value;
    cmpProcSort = { key: "field::cpu_peak", dir: -1 };
    render();
  };
  const modeBtn = el("button", "toolbtn");
  modeBtn.type = "button";
  const metricSel = document.createElement("select");
  CMP_PROC_METRICS.forEach(m => {
    const o = document.createElement("option");
    o.value = m.key;
    o.textContent = m.label + (m.unit ? " (" + m.unit + ")" : "");
    metricSel.appendChild(o);
  });
  metricSel.value = cmpProcMetric;
  const bg = document.createElement("label");
  bg.className = "proc-check";
  const bgInput = document.createElement("input");
  bgInput.type = "checkbox";
  bgInput.checked = cmpProcBackground;
  bg.appendChild(bgInput);
  bg.appendChild(document.createTextNode(" Background/cached only"));
  controls.appendChild(search);
  controls.appendChild(typeSel);
  controls.appendChild(sortRunSel);
  controls.appendChild(modeBtn);
  controls.appendChild(metricSel);
  controls.appendChild(bg);
  card.appendChild(controls);

  const procChartHost = el("div", "proc-chart-host cmp-proc-chart-host");
  if (labels.length > 1) card.appendChild(runLegend(labels.map(label => ({ label })), "Runs"));
  card.appendChild(procChartHost);
  const chartCache = new Map();
  let chartToken = 0;

  async function loadRunSeries(label) {
    if (chartCache.has(label)) return chartCache.get(label);
    try {
      const data = await jget("/api/runs/" + encodeURIComponent(label) + "/procs/series");
      chartCache.set(label, data || {});
      return chartCache.get(label);
    } catch (e) {
      chartCache.set(label, {});
      return {};
    }
  }

  async function renderCmpProcCharts() {
    const token = ++chartToken;
    disposeProcCharts();
    procChartHost.innerHTML = "";
    if (!selectedCmpProc) {
      procChartHost.appendChild(el("div", "muted procchart-hint", "Select a process row to compare CPU, memory, disk and network over time."));
      return;
    }
    const entry = entries.get(selectedCmpProc);
    if (!entry) return;
    procChartHost.appendChild(el("div", "muted procchart-hint", "Loading process timelines..."));
    const seriesByLabel = await Promise.all(labels.map(loadRunSeries));
    if (token !== chartToken) return;
    const multi = labels.length > 1;
    const statsRuns = [];
    labels.forEach((label, i) => {
      const rkey = entry.byRunKey[label];
      const s = rkey && seriesByLabel[i] ? seriesByLabel[i][rkey] : null;
      if (s) statsRuns.push({ label, series: s, elapsed: s.elapsed });
    });
    procChartHost.innerHTML = "";
    const chartHead = el("div", "charthead");
    const chartTitle = el("div", "procchart-title");
    chartTitle.appendChild(textEl("h3", null, entry.name || "--"));
    const chartSub = el("div", "muted procsub");
    chartSub.textContent = [entry.package || "", entry.uid == null ? "" : "UID " + entry.uid].filter(Boolean).join(" · ");
    chartTitle.appendChild(chartSub);
    chartHead.appendChild(chartTitle);
    const clear = el("button", "toolbtn", "Clear");
    clear.type = "button";
    clear.onclick = () => {
      chartToken += 1;
      selectedCmpProc = null;
      disposeProcCharts();
      procChartHost.innerHTML = "";
      procChartHost.appendChild(el("div", "muted procchart-hint", "Select a process row to compare CPU, memory, disk and network over time."));
      render();
    };
    chartHead.appendChild(clear);
    procChartHost.appendChild(chartHead);
    const grid = el("div", "proccharts");
    procChartHost.appendChild(grid);
    let shown = 0;
    PROC_CHART_GROUPS.forEach((def, di) => {
      const starts = {};
      const lines = [];
      labels.forEach((label, i) => {
        const rkey = entry.byRunKey[label];
        const s = rkey && seriesByLabel[i] ? seriesByLabel[i][rkey] : null;
        if (!s) return;
        const start = parseSummaryStart(RUNS.find(r => r.label === label));
        def.metrics.forEach((m, mi) => {
          if (!(s[m.key] || []).some(v => v != null)) return;
          const name = multi ? label + " · " + m.label : m.label;
          starts[name] = start;
          const scale = m.scale ?? 1;
          const points = (s.elapsed || []).map((t, idx) => [t, s[m.key][idx] == null ? null : s[m.key][idx] * scale]);
          const sparse = points.filter(p => p[1] != null).length <= 2;
          const color = multi ? COLORS[i % COLORS.length] : SERIES_COLORS[mi % SERIES_COLORS.length];
          lines.push({
            name, type: "line", showSymbol: sparse, symbolSize: sparse ? 5 : 0, connectNulls: false,
            lineStyle: { width: 1.6, color, type: m.dashed ? "dashed" : "solid" },
            itemStyle: { color }, data: points,
          });
        });
      });
      if (!lines.length) return;
      shown++;
      const card = el("div", "procchart-box");
      card.appendChild(procChartTitle(def));
      const div = el("div", "procchart");
      card.appendChild(div);
      grid.appendChild(card);
      const ch = echarts.init(div, "dark");
      procCharts.push(ch);
      ch.setOption(procChartOption(def, lines, starts));
      const stats = procChartStats(def, statsRuns, multi);
      if (stats) card.appendChild(stats);
      requestAnimationFrame(() => { try { ch.resize(); } catch (e) {} });
    });
    if (!shown) procChartHost.appendChild(el("div", "muted procchart-hint", "No timeline series for this process in the selected runs."));
  }

  const wrap = el("div", "proctable-wrap");
  const t = el("table", "proctable cmpproc");
  const thead = el("thead");
  t.appendChild(thead);
  const tbody = el("tbody");
  t.appendChild(tbody);
  wrap.appendChild(t);
  card.appendChild(wrap);
  if (!lists.some(rows => rows.some(r => r.cpu_now != null))) {
    card.appendChild(el("div", "muted cardnote", "These are older top-process captures."));
  }

  function value(e, key) {
    if (key === "name") return e.name || "";
    if (key === "kind") return procCategory(e);
    if (key === "max") {
      const vals = labels.map(l => {
        const r = e.byRun[l];
        return r && r[metric.key] != null ? r[metric.key] : null;
      }).filter(v => v != null);
      return vals.length ? Math.max(...vals) : null;
    }
    if (key.startsWith("field::")) {
      const fieldKey = key.slice(7);
      const f = CMP_FULL_FIELDS.find(x => x.key === fieldKey);
      if (!f) return null;
      if (cmpProcSortRun !== "__max") {
        const r = e.byRun[cmpProcSortRun];
        return r && r[f.key] != null && r[f.key] !== "" ? r[f.key] : null;
      }
      const values = labels.map(l => {
        const r = e.byRun[l];
        return r && r[f.key] != null && r[f.key] !== "" ? r[f.key] : null;
      }).filter(v => v != null);
      if (!values.length) return null;
      if (f.text) return String(values[0]);
      return Math.max(...values.map(Number));
    }
    const r = e.byRun[key];
    return r && r[metric.key] != null ? r[metric.key] : null;
  }

  function render() {
    const rows = Array.from(entries.values()).filter(cmpProcMatches);
    rows.sort((a, b) => {
      const av = value(a, cmpProcSort.key), bv = value(b, cmpProcSort.key);
      const an = av == null || av === "", bn = bv == null || bv === "";
      if (an && bn) return String(a.name).localeCompare(String(b.name));
      if (an) return 1;
      if (bn) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * cmpProcSort.dir;
      return String(av).localeCompare(String(bv)) * cmpProcSort.dir;
    });
    count.textContent = rows.length + " / " + entries.size + " processes";
    modeBtn.textContent = cmpProcMode === "full" ? "Compact metric view" : "All fields";
    metricSel.hidden = cmpProcMode === "full";
    sortRunSel.hidden = cmpProcMode !== "full";

    thead.innerHTML = "";
    const htr = el("tr");
    const baseDefs = [{ key: "name", label: "Process" }, { key: "kind", label: "Type" }];
    baseDefs.forEach(col => {
      const th = el("th", "procsort");
      th.onclick = () => {
        if (cmpProcSort.key === col.key) cmpProcSort.dir *= -1;
        else cmpProcSort = { key: col.key, dir: 1 };
        render();
      };
      th.tabIndex = 0;
      th.setAttribute("role", "button");
      th.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); th.onclick(); }
      };
      setCmpHeader(th, col.label, "", cmpProcSort.key === col.key);
      htr.appendChild(th);
    });
    if (cmpProcMode === "full") {
      CMP_FULL_FIELDS.forEach(f => {
        const key = "field::" + f.key;
        const th = el("th", "procsort");
        th.title = "Sort by " + f.label;
        th.onclick = () => {
          if (cmpProcSort.key === key) cmpProcSort.dir *= -1;
          else cmpProcSort = { key, dir: -1 };
          render();
        };
        th.tabIndex = 0;
        th.setAttribute("role", "button");
        th.onkeydown = (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); th.onclick(); }
        };
        setCmpHeader(th, f.label, f.unit || "", cmpProcSort.key === key);
        htr.appendChild(th);
      });
      thead.appendChild(htr);
      t.classList.add("cmpfull");
    } else {
      labels.forEach(l => {
        const th = el("th", "procsort");
        th.title = "Sort by " + metric.label + " for " + l;
        th.onclick = () => {
          if (cmpProcSort.key === l) cmpProcSort.dir *= -1;
          else cmpProcSort = { key: l, dir: -1 };
          render();
        };
        th.tabIndex = 0;
        th.setAttribute("role", "button");
        th.onkeydown = (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); th.onclick(); }
        };
        setCmpHeader(th, l, metric.label + (metric.unit ? " · " + metric.unit : ""), cmpProcSort.key === l);
        htr.appendChild(th);
      });
      thead.appendChild(htr);
      t.classList.remove("cmpfull");
    }

    tbody.innerHTML = "";
    rows.forEach(e => {
      const tr = el("tr", "procrow" + (e.key === selectedCmpProc ? " selected" : ""));
      tr.dataset.pinRowKind = "process";
      tr.dataset.pinRowKey = e.key;
      const td = el("td", "procname-cell");
      const nameLine = el("div", "procname-line");
      nameLine.appendChild(pinButton("process", procPinItem(e)));
      const nm = el("div", "procname-main");
      nm.textContent = e.name || "--";
      nameLine.appendChild(nm);
      const sub = el("div", "procsub");
      sub.textContent = "UID " + (e.uid == null ? "--" : e.uid);
      td.appendChild(nameLine);
      td.appendChild(sub);
      if (e.package) {
        const pkg = el("div", "procpackage");
        pkg.textContent = e.package;
        td.appendChild(pkg);
      }
      tr.appendChild(td);
      if (findPin("process", e.key)) tr.classList.add("pinned-row");
      const kindTd = el("td", "procbadgecell");
      const b = el("span", "procbadge kind-" + procCategory(e));
      b.textContent = procKindLabel(e);
      kindTd.appendChild(b);
      tr.appendChild(kindTd);
      tr.onclick = () => {
        selectedCmpProc = e.key;
        render();
        renderCmpProcCharts();
      };
      tr.onkeydown = (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          tr.onclick();
        }
      };
      tr.tabIndex = 0;
      tr.setAttribute("role", "button");
      if (cmpProcMode === "full") {
        CMP_FULL_FIELDS.forEach(f => {
          const td = el("td", "cmpmulticell");
          const values = el("div", "cmpvalues");
          labels.forEach((l, i) => {
            const r = e.byRun[l] || {};
            const line = el("div", "cmpval");
            const dot = el("span", "statdot");
            dot.style.background = COLORS[i % COLORS.length];
            line.appendChild(dot);
            line.appendChild(document.createTextNode(procCellText(r, f)));
            line.title = l;
            values.appendChild(line);
          });
          td.appendChild(values);
          tr.appendChild(td);
        });
      } else {
        labels.forEach(l => {
          const r = e.byRun[l] || {};
          tr.appendChild(el("td", null, procCellText(r, metric)));
        });
      }
      tbody.appendChild(tr);
    });
    if (!rows.length) {
      const tr = el("tr");
      const td = el("td", "muted", "No processes match these filters.");
      td.colSpan = 2 + (cmpProcMode === "full" ? CMP_FULL_FIELDS.length : labels.length);
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
  }

  search.oninput = () => { cmpProcQuery = search.value; render(); };
  typeSel.onchange = () => { cmpProcType = typeSel.value; render(); };
  bgInput.onchange = () => { cmpProcBackground = bgInput.checked; render(); };
  metricSel.onchange = () => {
    cmpProcMetric = metricSel.value;
    cmpProcSort = { key: "max", dir: -1 };
    render();
  };
  modeBtn.onclick = () => {
    cmpProcMode = cmpProcMode === "full" ? "metric" : "full";
    cmpProcSort = cmpProcMode === "full" ? { key: "field::cpu_peak", dir: -1 } : { key: "max", dir: -1 };
    render();
  };
  render();
  renderCmpProcCharts();
  return card;
}

function renderCompareView() {
  if (findOpen) closeFind();
  const v = document.getElementById("view");
  disposeCharts();
  v.innerHTML = "";

  compareSelection = compareSelection.slice(0, 6);
  const pick = el("section", "card");
  const head = el("div", "runhead");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, "Compare runs"));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  const actions = el("div", "runactions");
  const clearBtn = el("button", "toolbtn", "Clear");
  clearBtn.type = "button";
  actions.appendChild(clearBtn);
  const exportBtn = el("button", "toolbtn", "Export HTML");
  exportBtn.title = "Download a self-contained HTML report";
  exportBtn.disabled = !compareSelection.length;
  exportBtn.onclick = () => downloadReport(compareSelection.slice(0, 6), exportBtn);
  if (!OFFLINE) actions.appendChild(exportBtn);
  head.appendChild(actions);
  pick.appendChild(head);

  const pickControls = el("div", "proccontrols pickcontrols");
  const pickSearch = document.createElement("input");
  pickSearch.type = "search";
  pickSearch.placeholder = "Filter runs...";
  pickSearch.value = pickQuery;
  const pickShown = el("span", "muted tablecount");
  pickControls.appendChild(pickSearch);
  pickControls.appendChild(pickShown);
  pick.appendChild(pickControls);

  const grid = el("div", "pickgrid");
  const sorted = RUNS.slice().sort(runComparator());
  const pickHaystack = r => [
    runHaystack(r), r.profile, runDateLabel(r), runLengthLabel(r), runProfileLabel(r),
  ].join(" ").toLowerCase();
  if (!sorted.length) {
    grid.appendChild(el("div", "muted", "No runs yet."));
  }
  sorted.forEach(r => {
    const tile = el("label", "pickitem" + (compareSelection.includes(r.label) ? " selected" : ""));
    tile.dataset.search = pickHaystack(r);
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "pickbox";
    cb.value = r.label;
    cb.checked = compareSelection.includes(r.label);
    const body = el("div", "pickbody");
    const title = el("div", "picktitle");
    const name = textEl("span", "pickname", r.label);
    name.title = "Open run results";
    name.tabIndex = 0;
    name.setAttribute("role", "button");
    name.onclick = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      currentRun = null;
      showRun(r.label).then(ok => { if (ok) setTab("run"); });
    };
    name.onkeydown = (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        ev.stopPropagation();
        name.onclick(ev);
      }
    };
    title.appendChild(name);
    const badges = el("span", "pickbadges");
    badges.innerHTML = runBadgeHtml(r);
    title.appendChild(badges);
    body.appendChild(title);
    const meta = runSummaryNode(r, "pickmeta");
    if (meta) body.appendChild(meta);
    if (r.notes) body.appendChild(textEl("div", "picknote", r.notes));
    cb.onchange = () => {
      const selected = Array.from(grid.querySelectorAll("input:checked")).map(x => x.value);
      if (selected.length > 6) {
        cb.checked = false;
        count.textContent = "Up to 6 runs";
        return;
      }
      compareSelection = selected;
      sync();
    };
    tile.appendChild(cb);
    tile.appendChild(body);
    grid.appendChild(tile);
  });
  pick.appendChild(grid);

  function applyPickFilter() {
    const q = pickQuery.trim().toLowerCase();
    const terms = q.split(/\s+/).filter(Boolean);
    let shown = 0;
    grid.querySelectorAll(".pickitem").forEach(tile => {
      const hay = tile.dataset.search || "";
      const visible = !terms.length || terms.every(term => hay.includes(term));
      tile.style.display = visible ? "" : "none";
      if (visible) shown++;
    });
    pickShown.textContent = shown + " runs";
  }
  pickSearch.oninput = () => { pickQuery = pickSearch.value; applyPickFilter(); };
  applyPickFilter();

  const rm = el("div");
  rm.id = "compare-runmeta";
  pick.appendChild(rm);
  v.appendChild(pick);

  const host = el("div");
  host.id = "compare-body";
  v.appendChild(host);

  function sync() {
    if (findOpen) closeFind();
    grid.querySelectorAll(".pickitem").forEach(tile => {
      const cb = tile.querySelector("input");
      tile.classList.toggle("selected", cb.checked);
      const maxed = !cb.checked && compareSelection.length >= 6;
      cb.disabled = maxed;
      tile.classList.toggle("maxed", maxed);
    });
    count.textContent = compareSelection.length + " / 6 selected";
    clearBtn.disabled = !compareSelection.length;
    exportBtn.disabled = !compareSelection.length;
    renderCompareBody();
  }

  clearBtn.onclick = () => {
    compareSelection = [];
    grid.querySelectorAll("input").forEach(cb => { cb.checked = false; });
    sync();
  };
  sync();
}

let compareRenderToken = 0;

async function renderCompareBody() {
  const host = document.getElementById("compare-body");
  if (!host) return;
  const token = ++compareRenderToken;
  disposeCharts();
  host.innerHTML = "";
  const rm = document.getElementById("compare-runmeta");
  if (rm) rm.innerHTML = "";
  const labels = compareSelection.slice(0, 6);
  if (labels.length < 1) {
    host.appendChild(el("section", "card", "<div class='muted'>Select one or more runs above.</div>"));
    updateStickyOffsets();
    return;
  }
  let datasets;
  try {
    datasets = await Promise.all(labels.map(async l => {
      const d = await jget("/api/runs/" + encodeURIComponent(l));
      return { label: l, elapsed: d.elapsed, series: d.series, meta: d.meta };
    }));
  } catch (e) {
    if (token !== compareRenderToken) return;
    host.appendChild(textEl("section", "card muted", "Could not load the selected runs: " + (e.message || e)));
    updateStickyOffsets();
    return;
  }
  if (token !== compareRenderToken) return; // newer selection superseded this render

  if (rm) {
    datasets.forEach(d => {
      const m = d.meta || {};
      const line = el("div", "runmetaline clickable");
      line.title = "Open run results";
      line.tabIndex = 0;
      line.setAttribute("role", "button");
      line.onclick = () => { currentRun = null; showRun(d.label).then(ok => { if (ok) setTab("run"); }); };
      line.onkeydown = (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          line.onclick();
        }
      };
      const b = textEl("b", null, d.label);
      line.appendChild(b);
      const bits = [];
      if (m.started) bits.push(m.started.slice(0, 19).replace("T", " "));
      if (m.rows != null) bits.push(m.rows + " rows");
      if (m.notes) bits.push(m.notes);
      line.appendChild(textEl("span", "muted", bits.length ? "  |  " + bits.join("  |  ") : ""));
      rm.appendChild(line);
    });
  }

  host.appendChild(resultsSection([
    { id: "metadata", label: "Metadata", render: h => h.appendChild(compareMetadataPane(datasets)) },
    {
      id: "table",
      label: "Full table",
      render: h => {
        h.appendChild(pinnedTableCard(datasets));
        h.appendChild(compareTableCard(datasets));
      },
    },
    {
      id: "graphs",
      label: "Graphs",
      render: h => {
        if (datasets.length > 1) h.appendChild(runLegend(datasets, "Runs"));
        h.appendChild(pinnedGraphsCard(datasets));
        renderSections(h, datasets);
      },
    },
    {
      id: "processes",
      label: "Processes",
      render: (h, isActive) => {
        h.appendChild(pinnedProcessesCard(datasets));
        h.appendChild(el("div", "muted proc-loading", "Loading process comparison..."));
        compareProcessesCard(labels).then(pc => {
          if (!isActive()) return;
          const loading = h.querySelector(".proc-loading");
          if (loading) loading.remove();
          if (pc) h.appendChild(pc);
          else h.appendChild(el("div", "muted", "No process data for the selected runs."));
        }).catch(err => {
          if (!isActive()) return;
          const loading = h.querySelector(".proc-loading");
          if (loading) loading.remove();
          h.appendChild(textEl("div", "muted", "Could not load processes: " + (err.message || err)));
        });
      },
    },
  ], "metadata", labels.length === 1 ? labels[0] : "Compare: " + labels.join(" vs "), labels.length === 1 ? "" : labels.length + " runs compared"));
  updateStickyOffsets();
}

function compareMetadataPane(datasets) {
  const box = el("div", "metatab");
  box.appendChild(compareQuickSummaryCard(datasets));
  box.appendChild(compareDevicesCard(datasets));
  box.appendChild(compareTrackingCard(datasets));
  box.appendChild(compareModesCard(datasets));
  box.appendChild(compareBatteryCard(datasets));
  box.appendChild(compareMediaStateCard(datasets));
  return box;
}

function previewHottestSensor(metrics) {
  let best = null;
  Object.entries(metrics || {}).forEach(([key, value]) => {
    if (!key.startsWith("t_") || typeof value !== "number" || !Number.isFinite(value)) return;
    if (!best || value > best.value) best = { key: key.slice(2), value };
  });
  return best;
}

function renderPreviewMetrics(host, metrics) {
  host.innerHTML = "";
  const charging = { 1: "unknown", 2: "charging", 3: "discharging", 4: "not charging", 5: "full" };
  const hottest = previewHottestSensor(metrics);
  const items = [
    ["Thermal status", thermalStatusText(metrics.thermal_status, metrics.thermal_status)],
    ["Worst severity", metrics.thermal_max_sev == null ? "--" : "level " + Math.round(metrics.thermal_max_sev)],
    ["CPU hottest", fmt(_rowMax(metrics, "t_CPU", 6), "°C", 1)],
    ["GPU hottest", fmt(_rowMax(metrics, "t_GPU", 8), "°C", 1)],
    ["Surface", fmt(metrics.t_skin ?? metrics.t_AP, "°C", 1)],
    ["WiFi", fmt(metrics.t_WIFI, "°C", 1)],
    ["Hottest sensor", hottest ? hottest.key + " · " + fmt(hottest.value, "°C", 1) : "--"],
    ["Battery", metrics.batt_level == null ? "--" : Math.round(metrics.batt_level) + "%"],
    ["Battery temp", fmt(metrics.batt_temp, "°C", 1)],
    ["Battery state", charging[metrics.batt_status] || (metrics.batt_ac ? "on AC" : "--")],
  ];
  const kpis = el("div", "livekpis previewkpis");
  items.forEach(([k, v]) => {
    const box = el("div", "livekpi");
    box.appendChild(textEl("span", "k", k));
    box.appendChild(textEl("span", "v", v));
    kpis.appendChild(box);
  });
  host.appendChild(kpis);
}

function stopPreview(keepCard) {
  const state = previewState;
  previewState = null;
  if (state) {
    state.token += 1;
    if (state.timer) clearInterval(state.timer);
  }
  if (!keepCard) {
    const host = document.getElementById("preview-host");
    if (host) host.innerHTML = "";
  }
  const btn = document.getElementById("live-preview-btn");
  if (btn) {
    btn.textContent = "Preview headset";
    btn.classList.remove("active");
    btn.setAttribute("aria-pressed", "false");
  }
}

async function previewTick(state) {
  if (previewState !== state || state.busy) return;
  state.busy = true;
  const my = ++state.token;
  const body = document.getElementById("preview-body");
  const status = document.getElementById("preview-status");
  try {
    const metrics = await jget("/api/preview");
    if (previewState !== state || my !== state.token) return;
    if (body) renderPreviewMetrics(body, metrics || {});
    if (status) status.textContent = "updated " + new Date().toLocaleTimeString();
  } catch (e) {
    if (previewState !== state) return;
    if (body) {
      body.innerHTML = "";
      body.appendChild(textEl("div", "formerror", "Preview failed: " + (e.message || e)));
    }
    if (status) status.textContent = "unavailable";
    stopPreview(true);
  } finally {
    state.busy = false;
  }
}

function startPreview() {
  if (previewState) {
    stopPreview();
    return;
  }
  if (liveSession && liveSession.status === "recording") return;
  const host = document.getElementById("preview-host");
  const btn = document.getElementById("live-preview-btn");
  if (!host || !btn) return;
  const state = { timer: null, token: 0, busy: false };
  previewState = state;
  btn.textContent = "Stop preview";
  btn.classList.add("active");
  btn.setAttribute("aria-pressed", "true");
  host.innerHTML = "";
  const card = el("section", "card preview-card");
  const head = el("div", "charthead");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, "Headset preview"));
  titleBox.appendChild(el("span", "pickcount muted", "Manual · not saved"));
  head.appendChild(titleBox);
  const actions = el("div", "runactions");
  const status = textEl("span", "livestatus", "starting");
  status.id = "preview-status";
  const stop = el("button", "toolbtn", "Stop");
  stop.type = "button";
  stop.onclick = () => stopPreview();
  actions.appendChild(status);
  actions.appendChild(stop);
  head.appendChild(actions);
  card.appendChild(head);
  card.appendChild(el("p", "muted cardnote", "Lightweight preview: battery and thermal sensors only. Nothing is written to disk."));
  const body = el("div", "preview-body");
  body.id = "preview-body";
  body.appendChild(el("div", "muted preview-loading", "Reading headset..."));
  card.appendChild(body);
  host.appendChild(card);
  state.timer = setInterval(() => previewTick(state), PREVIEW_INTERVAL_MS);
  previewTick(state);
}

function renderLiveView() {
  if (findOpen) closeFind();
  if (previewState) stopPreview();
  const v = document.getElementById("view");
  disposeCharts();
  v.innerHTML = "";
  const session = liveSession;
  const body = (session && session.body) || {};

  const layout = el("div", "twocol");
  const mainCard = el("section", "card");
  mainCard.appendChild(el("h3", null, "New recording"));
  mainCard.appendChild(el("p", "muted cardnote", "Start a fresh 1 Hz capture. The run is saved by name in the runs folder."));
  const f = el("form", "recordform");
  f.onsubmit = (e) => e.preventDefault();
  f.innerHTML = `
    <div class="recordgrid">
      <div class="field wide"><label for="r-name">Name</label><input id="r-name" type="text" value="run" autocomplete="off" /></div>
      <div class="field"><label for="r-duration">Duration</label><input id="r-duration" type="number" value="60" min="0" step="1" /><span class="fieldhint">Seconds; 0 = manual stop</span></div>
      <div class="field"><label for="r-cooldown">Cooldown target (°C)</label><input id="r-cooldown" type="number" value="" min="0" step="0.5" placeholder="e.g. 36" /><span class="fieldhint">Optional; starts at or below the target. Set max wait in Advanced (0 = unlimited).</span></div>
      <div class="field"><label for="r-sensor">Cooldown sensor</label><select id="r-sensor"></select><span class="fieldhint" id="r-sensor-hint">AP = application processor</span></div>
      <div class="field"><label for="r-cooldown-max-wait">Cooldown max wait</label><input id="r-cooldown-max-wait" type="number" min="0" step="5" value="0" /><span class="fieldhint">Seconds; 0 = wait indefinitely</span></div>
      <div class="field wide"><label for="r-notes">Notes</label><input id="r-notes" type="text" value="" autocomplete="off" /></div>
    </div>`;
  const sensorSel = f.querySelector("#r-sensor");
  ((SPEC && SPEC.cooldown_sensors) || [{ id: "AP", label: "Application processor" }]).forEach(s => {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.label + " (" + s.id + ")";
    sensorSel.appendChild(o);
  });
  sensorSel.value = body.sensor || "AP";
  const cooldownWaitInput = f.querySelector("#r-cooldown-max-wait");
  const actions = el("div", "recordactions");
  const startBtn = el("button", "primary", "Start recording"); startBtn.type = "button"; startBtn.id = "live-start-btn";
  const previewBtn = el("button", "toolbtn", "Preview headset"); previewBtn.type = "button"; previewBtn.id = "live-preview-btn";
  previewBtn.title = "Read battery and thermal sensors without saving a run";
  previewBtn.setAttribute("aria-pressed", "false");
  previewBtn.onclick = () => { if (previewState) stopPreview(); else startPreview(); };
  const startError = el("span", "formerror");
  startError.setAttribute("role", "alert");
  actions.appendChild(startBtn);
  if (!OFFLINE) actions.appendChild(previewBtn);
  actions.appendChild(el("span", "recordhint muted", "Polls at 1 Hz."));
  actions.appendChild(startError);
  f.appendChild(actions);
  mainCard.appendChild(f);

  const optCard = el("section", "card");
  optCard.appendChild(el("h3", null, "Capture options"));
  optCard.appendChild(el("p", "muted cardnote", "Standard is tuned for low overhead. Detailed and Everything trade more device CPU for more context."));
  const profileBar = el("div", "profilebar");
  profileBar.innerHTML = `
    <label for="r-profile">Profile</label>
    <select id="r-profile">
      <option value="standard">Standard · low overhead</option>
      <option value="detailed">Detailed</option>
      <option value="everything">Everything · highest overhead</option>
      <option value="custom">Custom</option>
    </select>
    <span id="r-profile-note" class="muted">Core 1 Hz, processes 10 s, media 30 s, state 5 s.</span>`;
  optCard.appendChild(profileBar);
  const optGrid = el("div", "optgrid");
  optGrid.innerHTML = `
    <label class="optitem"><input class="optbox" id="r-root" type="checkbox" />
      <span class="optbody"><span class="opttitle">Root extras</span><span class="optdesc">Fan RPM/PWM and active panel. Uses read-only su and may prompt.</span></span></label>
    <label class="optitem"><input class="optbox" id="r-sensors" type="checkbox" />
      <span class="optbody"><span class="opttitle">Sensor service</span><span class="optdesc">Android SensorService summary: active clients, rates and counts.</span></span></label>
    <label class="optitem"><input class="optbox" id="r-processes" type="checkbox" />
      <span class="optbody"><span class="opttitle">Per-process snapshot</span><span class="optdesc">All non-kernel processes: CPU, RSS, GPU memory, package/type/OOM and network; disk I/O with root.</span></span></label>
    <label class="optitem"><input class="optbox" id="r-processes-kernel" type="checkbox" />
      <span class="optbody"><span class="opttitle">Include kernel threads</span><span class="optdesc">Also capture kernel worker threads. Much noisier and larger; off by default.</span></span></label>
    <label class="optitem"><input class="optbox" id="r-process-io" type="checkbox" />
      <span class="optbody"><span class="opttitle">Per-process disk I/O</span><span class="optdesc">Read cumulative read/write counters. Requires root extras and processes.</span></span></label>`;
  optCard.appendChild(optGrid);
  const advanced = el("details", "advanced-card");
  advanced.innerHTML = `
    <summary>Cadence intervals <span class="muted">(advanced)</span></summary>
    <div class="cadencegrid">
      <label class="field"><span>Process interval</span><input id="r-processes-interval" type="number" min="1" step="1" value="10" /><span class="fieldhint">10 s low overhead · 5 s higher</span></label>
      <label class="field"><span>Sensor interval</span><input id="r-sensors-interval" type="number" min="1" step="1" value="10" /><span class="fieldhint">off low · 10 s medium · 5 s high</span></label>
      <label class="field"><span>Media interval</span><input id="r-media-interval" type="number" min="1" step="1" value="30" /><span class="fieldhint">30 s low · 10 s higher</span></label>
      <label class="field"><span>State interval</span><input id="r-state-interval" type="number" min="1" step="1" value="5" /><span class="fieldhint">5 s low · 1 s higher</span></label>
      <label class="field"><span>Radio interval</span><input id="r-radio-interval" type="number" min="1" step="1" value="30" /><span class="fieldhint">30 s low · 5 s higher</span></label>
    </div>
    <p class="cardnote">Faster sampling increases adbd/sh CPU overhead. The README has the measured profile estimate.</p>`;
  optCard.appendChild(advanced);
  optGrid.querySelectorAll("input[type=checkbox]").forEach(cb => {
    const item = cb.closest(".optitem");
    const sync = () => item.classList.toggle("selected", cb.checked);
    cb.addEventListener("change", sync);
    sync();
  });

  layout.appendChild(mainCard);
  layout.appendChild(optCard);
  v.appendChild(layout);

  const previewHost = el("div", "preview-host");
  previewHost.id = "preview-host";
  v.appendChild(previewHost);

  const liveRuns = el("div", "liveruns");
  if (session) {
    liveRuns.appendChild(renderLiveCard(session));
    liveHistory.slice(1).forEach(previous => liveRuns.appendChild(renderHistoryCard(previous)));
  } else {
    liveRuns.appendChild(renderLiveCard(null));
  }
  v.appendChild(liveRuns);
  updateLiveCard();
  updateStickyOffsets();

  const profileSel = document.getElementById("r-profile");
  const profileNote = document.getElementById("r-profile-note");
  const liveBoxes = {
    processes: "r-processes",
    processes_kernel: "r-processes-kernel",
    process_io: "r-process-io",
    sensors: "r-sensors",
    root: "r-root",
  };
  const liveIntervals = {
    processes_interval: "r-processes-interval",
    sensors_interval: "r-sensors-interval",
    media_interval: "r-media-interval",
    state_interval: "r-state-interval",
    radio_interval: "r-radio-interval",
  };
  const profileNotes = {
    standard: "Core 1 Hz, processes 10 s, media 30 s, state 5 s.",
    detailed: "Processes 5 s, sensors 10 s, media 10 s, state 5 s.",
    everything: "All sources, kernel threads, root I/O; highest overhead.",
  };
  function syncLiveOptions() {
    optGrid.querySelectorAll("input[type=checkbox]").forEach(cb => {
      cb.closest(".optitem").classList.toggle("selected", cb.checked);
    });
  }
  function syncProcessIo() {
    const root = document.getElementById("r-root");
    const io = document.getElementById("r-process-io");
    if (!root || !io) return;
    if (!root.checked) io.checked = false;
    io.disabled = !root.checked;
    syncLiveOptions();
  }
  function applyLiveProfile(name) {
    const p = SPEC && SPEC.capture_profiles ? SPEC.capture_profiles[name] : null;
    if (!p) return;
    Object.entries(liveBoxes).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el) el.checked = !!p[key];
    });
    Object.entries(liveIntervals).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el) el.value = p[key];
    });
    profileNote.textContent = profileNotes[name] || "";
    syncLiveOptions();
    syncProcessIo();
  }
  profileSel.onchange = () => applyLiveProfile(profileSel.value);
  Object.values(liveBoxes).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", () => {
      profileSel.value = "custom";
      profileNote.textContent = "Custom intervals/options.";
      if (id === "r-root") syncProcessIo();
    });
  });
  Object.values(liveIntervals).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", () => { profileSel.value = "custom"; profileNote.textContent = "Custom intervals/options."; });
  });
  if (body && Object.keys(body).length) {
    profileSel.value = body.profile || "custom";
    Object.entries(liveBoxes).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el) el.checked = !!body[key];
    });
    Object.entries(liveIntervals).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el && body[key] != null) el.value = body[key];
    });
    syncLiveOptions();
    syncProcessIo();
  } else {
    profileSel.value = "standard";
    applyLiveProfile("standard");
  }

  if (body.name != null) document.getElementById("r-name").value = body.name;
  if (body.duration != null) document.getElementById("r-duration").value = body.duration;
  if (body.cooldown != null) document.getElementById("r-cooldown").value = body.cooldown;
  if (body.notes != null) document.getElementById("r-notes").value = body.notes;
  if (body.sensor != null) sensorSel.value = body.sensor;
  if (body.cooldown_max_wait != null) cooldownWaitInput.value = body.cooldown_max_wait;
  if (session && session.status === "recording") {
    startBtn.disabled = true;
    previewBtn.disabled = true;
    previewBtn.title = "Preview is unavailable while recording";
  }

  startBtn.onclick = async () => {
    let request;
    try {
      request = {
        name: document.getElementById("r-name").value || "run",
        duration: parseFloat(document.getElementById("r-duration").value) || 0,
        cooldown: parseFloat(document.getElementById("r-cooldown").value) || null,
        sensor: sensorSel.value || "AP",
        cooldown_max_wait: parseFloat(cooldownWaitInput.value) || 0,
        notes: document.getElementById("r-notes").value || "",
        root: document.getElementById("r-root").checked,
        sensors: document.getElementById("r-sensors").checked,
        sensors_interval: parseFloat(document.getElementById("r-sensors-interval").value) || 10,
        processes: document.getElementById("r-processes").checked,
        processes_interval: parseFloat(document.getElementById("r-processes-interval").value) || 10,
        processes_kernel: document.getElementById("r-processes-kernel").checked,
        process_io: document.getElementById("r-process-io").checked,
        media_interval: parseFloat(document.getElementById("r-media-interval").value) || 30,
        state_interval: parseFloat(document.getElementById("r-state-interval").value) || 5,
        radio_interval: parseFloat(document.getElementById("r-radio-interval").value) || 30,
        profile: document.getElementById("r-profile").value,
      };
    } catch (e) {
      startError.textContent = "Could not read form: " + (e.message || e);
      return;
    }
    startBtn.disabled = true;
    startError.textContent = "";
    stopPreview();
    ensureAudio();
    try {
      await jpost("/api/record", request);
    } catch (e) {
      startBtn.disabled = false;
      startError.textContent = "Could not start: " + e.message;
      return;
    }
    beginLiveSession(request);
    renderLiveView();
  };
}

function beginLiveSession(body) {
  stopPreview();
  if (liveSession && liveSession.es) liveSession.es.close();
  const session = {
    name: body.name,
    body,
    duration: body.duration || 0,
    status: "recording",
    startedAt: Date.now(),
    elapsed: 0,
    rows: 0,
    lastSeq: 0,
    lastRow: {},
    preview: _previewNew(),
    es: null,
    pinged: false,
  };
  liveSession = session;
  liveHistory.unshift(session);
  const es = new EventSource("/api/record/stream");
  session.es = es;
  es.onmessage = (ev) => {
    if (liveSession !== session) return;
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    const seq = Number(ev.lastEventId) || Number(msg.seq) || 0;
    if (seq && seq <= session.lastSeq) return;
    if (seq) session.lastSeq = seq;
    session.elapsed = msg.elapsed || 0;
    session.rows = msg.rows || session.rows + 1;
    session.lastRow = msg.row || {};
    _previewAdd(session.preview, session.lastRow, session.elapsed);
    updateLiveCard();
  };
  es.addEventListener("status", (ev) => {
    if (liveSession !== session) return;
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    session.status = msg.status;
    if (msg.rows != null) session.rows = msg.rows;
    if (session.status === "done" || session.status === "error") {
      es.close();
      if (session.status === "done" && !session.pinged) {
        session.pinged = true;
        playPing();
      }
      loadRuns();
    }
    updateLiveCard();
  });
  updateLiveCard();
}

async function stopLiveSession() {
  if (!liveSession) return;
  const btn = document.getElementById("live-stop");
  if (btn) btn.disabled = true;
  try {
    await jpost("/api/record/stop");
  } catch (e) {
    if (btn) btn.disabled = false;
    const label = document.getElementById("live-status");
    if (label) label.textContent = "stop failed";
  }
}

function renderLiveCard(session) {
  const card = el("section", "card");
  if (!session) {
    card.appendChild(el("h3", null, "Live capture"));
    card.appendChild(el("div", "live-empty", "Nothing recording. Start a run to stream a quick live summary here."));
    return card;
  }
  const head = el("div", "charthead");
  head.appendChild(textEl("h3", null, "Current run: " + session.name));
  const status = textEl("span", "livestatus", session.status);
  status.id = "live-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  head.appendChild(status);
  const stop = el("button", "toolbtn", "Stop");
  stop.type = "button";
  stop.id = "live-stop";
  stop.onclick = stopLiveSession;
  head.appendChild(stop);
  card.appendChild(head);

  const progress = el("div", "liveprogress");
  const line = el("div", "liveprogressrow");
  const label = el("span", "muted", "elapsed");
  label.id = "live-progress-label";
  const rows = el("span", "muted", "");
  rows.id = "live-rows";
  line.appendChild(label);
  line.appendChild(rows);
  const track = el("div", "progresstrack");
  const fill = el("div", "progressfill");
  fill.id = "live-progress-fill";
  track.appendChild(fill);
  progress.appendChild(line);
  progress.appendChild(track);
  card.appendChild(progress);

  const kpis = el("div", "livekpis");
  kpis.id = "live-kpis";
  card.appendChild(kpis);
  updateLiveCard();
  return card;
}

function updateLiveCard() {
  if (activeTab !== "live" || !liveSession) return;
  const session = liveSession;
  const status = document.getElementById("live-status");
  const stop = document.getElementById("live-stop");
  const label = document.getElementById("live-progress-label");
  const rows = document.getElementById("live-rows");
  const fill = document.getElementById("live-progress-fill");
  const kpis = document.getElementById("live-kpis");
  const startBtn = document.getElementById("live-start-btn");
  if (!status || !fill || !kpis) return;
  status.textContent = session.status;
  status.className = "livestatus " + session.status;
  if (stop) stop.style.display = session.status === "recording" ? "" : "none";
  if (startBtn) startBtn.disabled = session.status === "recording";

  const elapsed = session.elapsed || 0;
  const duration = session.duration || 0;
  fill.classList.remove("indeterminate", "done");
  if (duration > 0) {
    fill.style.width = Math.min(100, (elapsed / duration) * 100) + "%";
  } else if (session.status === "recording") {
    fill.style.width = "100%";
    fill.classList.add("indeterminate");
  } else {
    fill.style.width = session.status === "done" ? "100%" : "0%";
  }
  if (session.status === "done") fill.classList.add("done");
  if (label) label.textContent = duration > 0 ? elapsed.toFixed(1) + " / " + duration.toFixed(0) + " s" : elapsed.toFixed(1) + " s";
  if (rows) rows.textContent = session.rows + " rows";

  kpis.innerHTML = liveSummaryHtml(session);
}

function liveSummaryHtml(session) {
  return previewStats(session).map(([k, v]) => "<div class='livekpi'><span class='k'>" + escHtml(k) + "</span><span class='v'>" + escHtml(v) + "</span></div>").join("");
}

function renderHistoryCard(session) {
  const card = el("section", "card livehistory");
  const head = el("div", "charthead");
  head.appendChild(textEl("h3", null, "Previous run: " + session.name));
  head.appendChild(el("span", "livestatus " + session.status, session.status));
  if (session.startedAt) head.appendChild(el("span", "muted", new Date(session.startedAt).toLocaleTimeString()));
  card.appendChild(head);
  const progress = el("div", "liveprogress");
  const line = el("div", "liveprogressrow");
  line.appendChild(el("span", "muted", session.elapsed.toFixed(1) + " s"));
  line.appendChild(el("span", "muted", session.rows + " rows"));
  const track = el("div", "progresstrack");
  const fill = el("div", "progressfill" + (session.status === "done" ? " done" : ""));
  fill.style.width = session.status === "done" ? "100%" : "0%";
  track.appendChild(fill);
  progress.appendChild(line);
  progress.appendChild(track);
  card.appendChild(progress);
  const kpis = el("div", "livekpis");
  kpis.innerHTML = liveSummaryHtml(session);
  card.appendChild(kpis);
  if (session.status === "done" && session.name) {
    card.classList.add("clickable");
    card.title = "Open run results";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.onclick = async () => { if (await showRun(session.name)) setTab("run"); };
    card.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        card.onclick();
      }
    };
  }
  return card;
}

function ensureAudio() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
  } catch (e) {
    audioCtx = null;
  }
}

function playPing() {
  if (!audioCtx) return;
  const now = audioCtx.currentTime;
  [880, 1318.5].forEach((freq, i) => {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, now + i * 0.14);
    gain.gain.exponentialRampToValueAtTime(0.18, now + i * 0.14 + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.14 + 0.13);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start(now + i * 0.14);
    osc.stop(now + i * 0.14 + 0.14);
  });
}

// ---- runs list ------------------------------------------------------------
function runTime(r) {
  const t = Date.parse(r.recording_started || r.started || "");
  return Number.isNaN(t) ? 0 : t;
}

function runDateLabel(r) {
  const t = runTime(r);
  if (!t) return "";
  const d = new Date(t);
  const p2 = n => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate());
}

function runLengthLabel(r) {
  const raw = r.duration_actual_s ?? r.duration_s;
  if (raw == null || !Number.isFinite(Number(raw)) || Number(raw) < 0) return "";
  const total = Math.round(Number(raw));
  if (total < 60) return total + "s";
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes < 60) return seconds ? minutes + "m " + seconds + "s" : minutes + "m";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? hours + "h " + rest + "m" : hours + "h";
}

function runProfileLabel(r) {
  const profile = String(r.profile || "").toLowerCase();
  const labels = { standard: "Standard", detailed: "Detailed", everything: "Everything", custom: "Custom" };
  if (labels[profile]) return labels[profile];
  return profile ? profile.charAt(0).toUpperCase() + profile.slice(1) : "Legacy";
}

function runSummaryNode(r, cls) {
  const date = runDateLabel(r);
  const length = runLengthLabel(r);
  const depth = runProfileLabel(r);
  if (!date && !length && !depth) return null;
  const line = el("div", cls);
  const add = (text, strong) => {
    if (!text) return;
    if (line.childElementCount) line.appendChild(el("span", "runmeta-sep", " · "));
    line.appendChild(textEl("span", strong ? "runmeta-strong" : "", text));
  };
  add(date, false);
  add(length, true);
  add(depth, true);
  line.title = [date, length, depth].filter(Boolean).join(" · ");
  return line;
}

function compareRunNames(a, b) {
  return String(a.label || "").localeCompare(String(b.label || ""), undefined, { numeric: true, sensitivity: "base" });
}

function runComparator() {
  const byName = compareRunNames;
  const cmps = {
    newest: (a, b) => runTime(b) - runTime(a) || byName(a, b),
    oldest: (a, b) => runTime(a) - runTime(b) || byName(a, b),
    "name-asc": byName,
    "name-desc": (a, b) => byName(b, a),
    duration: (a, b) => ((b.duration_actual_s ?? b.duration_s ?? 0) - (a.duration_actual_s ?? a.duration_s ?? 0)) || byName(a, b),
  };
  return cmps[runSort] || cmps.newest;
}

function runHaystack(r) {
  return [
    r.label, r.notes, r.device_model, r.build, r.panel,
    r.power_saving != null ? (r.power_saving ? "power saving power-save" : "normal") : "",
    r.hand_tracking ? "hands" : "",
    r.controllers ? "controllers" : "",
    r.passthrough ? "passthrough" : "",
    r.started ? String(r.started).slice(0, 10) : "",
  ].join(" ").toLowerCase();
}

function visibleRuns() {
  const terms = runSearch.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return RUNS
    .filter(r => !terms.length || terms.every(t => runHaystack(r).includes(t)))
    .slice()
    .sort(runComparator());
}

function runBadgeHtml(r) {
  const badges = [];
  if (r.power_saving != null) badges.push("<span class='badge " + (r.power_saving ? "bad" : "good") + "'>" + (r.power_saving ? "power-save" : "normal") + "</span>");
  if (r.hand_tracking) badges.push("<span class='badge'>hands</span>");
  if (r.controllers) badges.push("<span class='badge'>controllers</span>");
  if (r.passthrough) badges.push("<span class='badge'>passthrough</span>");
  return badges.join("");
}

function renderRunList() {
  const list = document.getElementById("runlist");
  const previousScroll = list.scrollTop;
  list.innerHTML = "";
  const items = visibleRuns();
  if (!items.length) {
    list.appendChild(el("div", "muted runempty", RUNS.length ? "No runs match." : "No runs yet."));
    list.scrollTop = previousScroll;
    return;
  }
  items.forEach(r => {
    const item = el("div", "runitem" + (currentRun && currentRun.label === r.label ? " active" : ""));
    item.innerHTML = "<div class='l'></div><div class='runbadges'></div>";
    item.querySelector(".l").textContent = r.label;
    const badges = item.querySelector(".runbadges");
    badges.innerHTML = runBadgeHtml(r);
    if (!badges.childElementCount) badges.remove();
    const meta = runSummaryNode(r, "runmeta");
    if (meta) item.appendChild(meta);
    if (r.notes) {
      const n = el("div", "m note");
      n.textContent = r.notes;
      item.appendChild(n);
    }
    if (!OFFLINE) {
    const del = el("button", "rundel", "×");
    del.type = "button";
    del.title = "Delete run";
    del.setAttribute("aria-label", "Delete run " + r.label);
    del.onkeydown = (ev) => {
      ev.stopPropagation();
    };
    del.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm('Delete run "' + r.label + '"?\n\nThis removes its CSV, events, processes and metadata.')) return;
      try {
        await jdel("/api/runs/" + encodeURIComponent(r.label));
      } catch (err) {
        alert("Delete failed: " + err.message);
        return;
      }
      const wasCurrent = currentRun && currentRun.label === r.label;
      compareSelection = compareSelection.filter(x => x !== r.label);
      if (wasCurrent) currentRun = null;
      await loadRuns();
      if (wasCurrent) {
        const next = visibleRuns();
        if (next.length) await showRun(next[0].label);
        else renderRunView();
        setTab("run");
      } else if (activeTab === "compare") {
        renderCompareView();
      }
    };
    item.appendChild(del);
    }
    item.title = "Open run results";
    item.tabIndex = 0;
    item.setAttribute("role", "button");
    item.onclick = async () => { currentRun = null; if (await showRun(r.label)) setTab("run"); };
    item.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        item.onclick();
      }
    };
    list.appendChild(item);
  });
  list.scrollTop = previousScroll;
}

async function showRun(label) {
  if (findOpen) closeFind();
  const token = ++runLoadToken;
  let d;
  try {
    d = await jget("/api/runs/" + encodeURIComponent(label));
  } catch (e) {
    showUiError("Could not load run: " + (e.message || e));
    return false;
  }
  if (token !== runLoadToken) return;
  const changedRun = !currentRun || currentRun.label !== label;
  if (changedRun) {
    procQuery = "";
    procType = "all";
    procBackground = false;
    selectedProc = null;
    procCache = null;
    if (!pins.table.length && !pins.graph.length && !pins.process.length) resultsTab = "metadata";
  }
  currentRun = { label, meta: d.meta, elapsed: d.elapsed, series: d.series };
  renderRunList();
  if (activeTab === "run") renderRunView();
  return true;
}

async function loadRuns() {
  try {
    RUNS = await jget("/api/runs");
  } catch (e) {
    showUiError("Could not load runs: " + (e.message || e));
    RUNS = [];
  }
  procSeriesCache.clear();
  renderRunList();
}

function setTab(tab) {
  if (findOpen) closeFind();
  if (tab !== "live") stopPreview();
  if (tab !== "run") runLoadToken += 1;
  if (tab !== "compare") compareRenderToken += 1;
  activeTab = tab;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
  if (tab === "live") renderLiveView();
  else if (tab === "run") renderRunView();
  else if (tab === "compare") renderCompareView();
}

function allSectionTitles() {
  const set = new Set();
  let extra = false;
  (SPEC.groups || []).forEach(g => {
    const s = g.section || "Other";
    if (EXTRA_SECTIONS.has(s)) extra = true;
    else set.add(s);
  });
  if (extra) set.add("Extra");
  return Array.from(set);
}

function applyCollapseToDom() {
  document.querySelectorAll(".group").forEach(sec => {
    const titleEl = sec.querySelector(".grouphead h2");
    const body = sec.querySelector(".groupbody");
    const chev = sec.querySelector(".chev");
    if (!titleEl || !body) return;
    const collapsed = collapsedSections.has(titleEl.textContent);
    body.style.display = collapsed ? "none" : "";
    if (chev) chev.textContent = collapsed ? "\u25b8" : "\u25be";
  });
  resizeChartsSoon();
}

function clearFindHits() {
  const root = document.getElementById("view");
  if (root) {
    const parents = new Set();
    root.querySelectorAll("mark.findhit").forEach(mark => {
      const parent = mark.parentNode;
      if (!parent) return;
      parents.add(parent);
      mark.replaceWith(document.createTextNode(mark.textContent));
    });
    parents.forEach(parent => parent.normalize());
  }
  findHits = [];
  findIndex = -1;
}

function updateFindCount() {
  const count = document.getElementById("find-count");
  if (!count) return;
  const query = (document.getElementById("find-input") || {}).value || "";
  if (!query.trim()) count.textContent = "";
  else if (!findHits.length) count.textContent = "0 results";
  else count.textContent = (findIndex + 1) + " / " + findHits.length + (findHits.length >= 500 ? "+" : "");
}

function setActiveFind() {
  findHits.forEach((hit, i) => hit.classList.toggle("active", i === findIndex));
  if (findIndex >= 0 && findHits[findIndex]) {
    findHits[findIndex].scrollIntoView({ block: "center", behavior: "smooth" });
  }
  updateFindCount();
}

function highlightFind(rawQuery) {
  if (!findOpen) return;
  clearFindHits();
  const query = (rawQuery || "").trim();
  const root = document.getElementById("view");
  if (!query || !root) { updateFindCount(); return; }
  const needle = query.toLowerCase();
  const nodes = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent || parent.closest("script, style, textarea, input, select, canvas, mark")) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (findHits.length >= 500) break;
    const text = node.nodeValue;
    const lower = text.toLowerCase();
    let start = 0;
    let index = lower.indexOf(needle, start);
    if (index < 0) continue;
    const fragment = document.createDocumentFragment();
    while (index >= 0 && findHits.length < 500) {
      if (index > start) fragment.appendChild(document.createTextNode(text.slice(start, index)));
      const mark = document.createElement("mark");
      mark.className = "findhit";
      mark.textContent = text.slice(index, index + query.length);
      fragment.appendChild(mark);
      findHits.push(mark);
      start = index + query.length;
      index = lower.indexOf(needle, start);
    }
    if (start < text.length) fragment.appendChild(document.createTextNode(text.slice(start)));
    node.parentNode.replaceChild(fragment, node);
  }
  findIndex = findHits.length ? 0 : -1;
  setActiveFind();
}

function findNext(direction) {
  if (!findHits.length) return;
  findIndex = (findIndex + direction + findHits.length) % findHits.length;
  setActiveFind();
}

function openFind() {
  const bar = document.getElementById("findbar");
  const input = document.getElementById("find-input");
  if (!bar || !input) return;
  if (!findOpen) {
    findSavedSections = new Set(collapsedSections);
    findSavedTables = new Set(collapsedTableSections);
    collapsedSections.clear();
    collapsedTableSections.clear();
    applyCollapseToDom();
    applyTableCollapseToDom();
    findOpen = true;
  }
  bar.hidden = false;
  input.focus();
  input.select();
  highlightFind(input.value);
}

function closeFind() {
  if (!findOpen) return;
  clearTimeout(findTimer);
  clearFindHits();
  findOpen = false;
  const bar = document.getElementById("findbar");
  if (bar) bar.hidden = true;
  const count = document.getElementById("find-count");
  if (count) count.textContent = "";
  if (findSavedSections) {
    collapsedSections.clear();
    findSavedSections.forEach(title => collapsedSections.add(title));
  }
  if (findSavedTables) {
    collapsedTableSections.clear();
    findSavedTables.forEach(title => collapsedTableSections.add(title));
  }
  findSavedSections = null;
  findSavedTables = null;
  applyCollapseToDom();
  applyTableCollapseToDom();
}

function initFind() {
  const bar = document.getElementById("findbar");
  const input = document.getElementById("find-input");
  const button = document.getElementById("btn-find");
  if (!bar || !input) return;
  if (button) button.onclick = openFind;
  input.addEventListener("input", () => {
    clearTimeout(findTimer);
    findTimer = setTimeout(() => { if (findOpen) highlightFind(input.value); }, 80);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      findNext(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeFind();
    }
  });
  const prev = document.getElementById("find-prev");
  const next = document.getElementById("find-next");
  const close = document.getElementById("find-close");
  if (prev) prev.onclick = () => findNext(-1);
  if (next) next.onclick = () => findNext(1);
  if (close) close.onclick = closeFind;
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      openFind();
    } else if (e.key === "Escape" && findOpen) {
      e.preventDefault();
      closeFind();
    }
  });
}

async function init() {
  applySidebar();
  initFind();
  SPEC = await jget("/api/spec");
  if (OFFLINE && OFFLINE.pins) {
    loadPinsFrom(OFFLINE.pins);
    if (pins.graph.length) resultsTab = "graphs";
    else if (pins.table.length) resultsTab = "table";
    else if (pins.process.length) resultsTab = "processes";
  }
  await loadRuns();
  const knownRuns = new Set(RUNS.map(r => r.label));
  compareSelection = compareSelection.filter(label => knownRuns.has(label));
  let resumedRecording = false;
  if (!OFFLINE) {
    try {
      const recording = await jget("/api/record/status");
      if (recording && recording.status === "recording" && recording.label) {
        beginLiveSession({ name: recording.label, duration: recording.duration || 0, profile: recording.profile || "" });
        resumedRecording = true;
      }
    } catch (e) {
      showUiError("Could not read recording status: " + (e.message || e));
    }
  }
  if (OFFLINE) {
    document.body.classList.add("offline");
    const rec = document.getElementById("btn-record");
    if (rec) rec.remove();
    const recTab = document.querySelector('.tab[data-tab="live"]');
    if (recTab) recTab.remove();
    const h1 = document.querySelector("aside h1");
    if (h1) h1.innerHTML = "GXR Profiler <small>offline report</small>";
  }
  document.querySelectorAll(".tab").forEach(t => t.onclick = () => setTab(t.dataset.tab));
  const recBtn = document.getElementById("btn-record");
  if (recBtn) recBtn.onclick = () => setTab("live");
  const byId = id => document.getElementById(id);
  if (byId("btn-sidebar")) {
    byId("btn-sidebar").onclick = () => {
      sidebarOpen = !sidebarOpen;
      try { localStorage.setItem("gxr-profiler.sidebarOpen", sidebarOpen ? "1" : "0"); } catch (e) {}
      applySidebar();
    };
  }
  const searchEl = byId("run-search");
  const sortEl = byId("run-sort");
  if (sortEl) sortEl.value = runSort;
  if (searchEl) {
    searchEl.value = runSearch;
    let searchTimer = null;
    searchEl.oninput = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        runSearch = searchEl.value;
        renderRunList();
      }, 120);
    };
  }
  if (sortEl) {
    sortEl.onchange = () => {
      runSort = RUN_SORTS.has(sortEl.value) ? sortEl.value : "newest";
      try { localStorage.setItem("gxr-profiler.runSort", runSort); } catch (e) {}
      renderRunList();
    };
  }
  const yb = byId("btn-yaxis");
  if (yb) {
    yb.onclick = () => {
      yFromZero = !yFromZero;
      yb.textContent = yFromZero ? "Y: 0-based" : "Y: fit data";
      applyYScale();
      alignFloatNav();
    };
  }
  if (byId("btn-collapse")) {
    byId("btn-collapse").onclick = () => {
      if (findOpen) closeFind();
      allSectionTitles().forEach(t => collapsedSections.add(t));
      allTableTitles().forEach(t => collapsedTableSections.add(t));
      applyCollapseToDom();
      applyTableCollapseToDom();
    };
  }
  if (byId("btn-expand")) {
    byId("btn-expand").onclick = () => {
      if (findOpen) closeFind();
      collapsedSections.clear();
      collapsedTableSections.clear();
      applyCollapseToDom();
      applyTableCollapseToDom();
    };
  }
  const mainEl = document.querySelector("main");
  if (byId("btn-top")) byId("btn-top").onclick = () => mainEl && mainEl.scrollTo({ top: 0, behavior: "smooth" });
  if (byId("btn-bottom")) {
    byId("btn-bottom").onclick = () => mainEl && mainEl.scrollTo({ top: mainEl.scrollHeight, behavior: "smooth" });
  }
  const first = visibleRuns()[0];
  if (OFFLINE && OFFLINE.compare && OFFLINE.compare.length) {
    compareSelection = OFFLINE.compare.slice();
    if (first) await showRun(first.label);
    setTab("compare");
  } else if (OFFLINE && first) {
    await showRun(first.label);
    setTab("run");
  } else if (OFFLINE) {
    setTab("run");
  } else if (resumedRecording) {
    setTab("live");
  } else {
    setTab("live");
  }
}

window.addEventListener("resize", () => { updateStickyOffsets(); chartRegistry.forEach(c => { try { c.resize(); } catch (e) {} }); });
init();
