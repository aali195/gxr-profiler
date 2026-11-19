"use strict";

const COLORS = ["#4f9dff", "#ff7a59", "#39d353", "#c678dd", "#f0c000", "#33c7d4", "#ff5d8f", "#8f7bff"];
// Distinct colours for individual lines when a single run is shown.
const SERIES_COLORS = [
  "#4f9dff", "#ff7a59", "#39d353", "#c678dd", "#f0c000", "#33c7d4", "#ff5d8f", "#8f7bff",
  "#ffa657", "#7ee787", "#79c0ff", "#d2a8ff", "#ffd33d", "#56d4dd", "#ff9bce", "#a5d6ff",
];

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
const EXTRA_SECTIONS = new Set(["Media & display", "Audio", "Controllers", "Passthrough", "Raw thermal"]);
const EXTRA_ORDER = ["Media & display", "Audio", "Controllers", "Passthrough", "Raw thermal"];

function extraRank(section) {
  const i = EXTRA_ORDER.indexOf(section);
  return i < 0 ? EXTRA_ORDER.length : i;
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
      showToast({
        title: "Pin limit",
        message: "You can pin up to " + limit + " " + kind + " items. Unpin one to add another.",
        type: "warning",
      });
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

