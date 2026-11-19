"use strict";

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
    showToast({
      title: "Nothing selected",
      message: "Select at least one run.",
      type: "warning",
    });
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
    showToast({
      title: "Report export failed",
      message: e.message || String(e),
      type: "error",
    });
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
    const label = sidebarOpen ? "Hide run list" : "Show run list";
    btn.textContent = sidebarOpen ? "‹" : "›";
    btn.title = label;
    btn.setAttribute("aria-label", label);
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
    [...chartRegistry, ...pinnedCharts, ...procCharts].forEach(ch => { try { ch.resize(); } catch (e) {} });
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

let sectionFilter = "All";
let sectionFilterKey = "";

function sectionFilterName(section) {
  return EXTRA_SECTIONS.has(section) ? "Extra" : section;
}

function sectionList(sections) {
  const out = [];
  (sections || []).forEach(name => {
    const key = sectionFilterName(name || "Other");
    if (!out.includes(key)) out.push(key);
  });
  return out;
}

function groupSectionList(group) {
  return sectionList([group.section || "Other", ...(group.extra_sections || [])]);
}

function rowSectionList(row) {
  const raw = Array.isArray(row.groupSections) && row.groupSections.length
    ? row.groupSections
    : [row.groupSection || "Other"];
  return sectionList(raw);
}

function sectionKeysFromRows(rows) {
  const keys = [];
  rows.forEach(r => {
    rowSectionList(r).forEach(key => {
      if (!keys.includes(key)) keys.push(key);
    });
  });
  return keys.filter(k => k !== "Extra").concat(keys.includes("Extra") ? ["Extra"] : []);
}

function groupHasSeries(group, datasets) {
  const hasValue = arr => Array.isArray(arr) && arr.some(v => v != null);
  if ((group.series || []).some(s => datasets.some(d => d.series && hasValue(d.series[s.col])))) return true;
  return (group.bands || []).some(bid =>
    datasets.some(d => d.series && (
      hasValue(d.series["band::" + bid + "::max"]) ||
      hasValue(d.series["band::" + bid + "::avg"])
    ))
  );
}

function sectionKeysFromGroups(datasets) {
  const keys = [];
  (SPEC.groups || []).forEach(g => {
    if (!groupHasSeries(g, datasets)) return;
    groupSectionList(g).forEach(key => {
      if (!keys.includes(key)) keys.push(key);
    });
  });
  return keys.filter(k => k !== "Extra").concat(keys.includes("Extra") ? ["Extra"] : []);
}

function prepareSectionFilter(viewKey, available) {
  if (sectionFilterKey !== viewKey) {
    sectionFilter = "All";
    sectionFilterKey = viewKey;
  }
  if (sectionFilter !== "All" && !available.includes(sectionFilter)) sectionFilter = "All";
}


function disposeChartsIn(node) {
  for (let i = chartRegistry.length - 1; i >= 0; i--) {
    const ch = chartRegistry[i];
    try {
      const dom = ch.getDom && ch.getDom();
      if (dom && node.contains(dom)) {
        ch.dispose();
        chartRegistry.splice(i, 1);
      }
    } catch (e) {}
  }
}

function renderSectionTabs(host, available, onSelect) {
  host.innerHTML = "";
  const bar = el("div", "subtabs");
  bar.setAttribute("role", "tablist");
  ["All", ...available].forEach(key => {
    const b = el("button", "subtab" + (sectionFilter === key ? " active" : ""), key);
    b.type = "button";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(sectionFilter === key));
    b.onclick = () => {
      if (sectionFilter === key) return;
      sectionFilter = key;
      onSelect();
    };
    bar.appendChild(b);
  });
  host.appendChild(bar);
}

function renderSectionBody(parent, datasets) {
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
  const activeExtra = sectionFilter === "Extra";
  const usePrimaryBuckets = sectionFilter === "All" || activeExtra;
  const orderedGroups = sectionFilter === "All" || activeExtra
    ? SPEC.groups
    : [...SPEC.groups].sort((a, b) => {
      const ap = sectionFilterName(a.section || "Other") === sectionFilter ? 0 : 1;
      const bp = sectionFilterName(b.section || "Other") === sectionFilter ? 0 : 1;
      return ap - bp;
    });
  orderedGroups.forEach(g => {
    if (sectionFilter !== "All" && !groupSectionList(g).includes(sectionFilter)) return;
    if (!groupHasSeries(g, datasets)) return;
    const primary = g.section || "Other";
    const extra = activeExtra && EXTRA_SECTIONS.has(primary);
    const s = usePrimaryBuckets ? primary : sectionFilter;
    const bucket = extra ? extraBySection : bySection;
    const seq = extra ? extraOrder : order;
    if (!bucket[s]) { bucket[s] = []; seq.push(s); }
    bucket[s].push(g);
  });

  const addSection = (title, groups, host) => {
    const sec = el("section", "group");
    const head = el("div", "grouphead");
    const collapsed = collapsedSections.has(title);
    const chev = el("span", "chev", collapsed ? "\u25b8" : "\u25be");
    head.appendChild(chev);
    head.appendChild(el("h2", null, title));
    const body = el("div", "groupbody");
    if (collapsed) body.style.display = "none";
    sec.appendChild(head);
    sec.appendChild(body);
    host.appendChild(sec);
    registerCollapse(sec, title, head, body, chev);
    groups.forEach(g => addGroupCard(body, g, datasets));
    return body;
  };

  order.forEach(title => addSection(title, bySection[title], parent));
  if (extraOrder.length) {
    extraOrder.sort((a, b) => extraRank(a) - extraRank(b));
    const body = addSection("Extra", [], parent);
    extraOrder.forEach(title => {
      const sub = el("div", "extrasub");
      const subhead = el("h3", "extrasubhead");
      const chev = el("span", "chev", "\u25be");
      subhead.appendChild(chev);
      subhead.appendChild(document.createTextNode(title));
      const subbody = el("div", "extrabody");
      extraBySection[title].forEach(g => addGroupCard(subbody, g, datasets));
      sub.appendChild(subhead);
      sub.appendChild(subbody);
      body.appendChild(sub);
      registerCollapse(sub, "extra:" + title, subhead, subbody, chev);
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
function renderSections(parent, datasets) {
  const available = sectionKeysFromGroups(datasets);
  prepareSectionFilter("view:" + datasets.map(d => d.label).join("|"), available);
  const tabs = el("div", "sectiontabs");
  const body = el("div", "sectionbody");
  parent.appendChild(tabs);
  parent.appendChild(body);
  const drawTabs = () => renderSectionTabs(tabs, available, () => { drawBody(); drawTabs(); });
  const drawBody = () => { disposeChartsIn(body); body.innerHTML = ""; renderSectionBody(body, datasets); };
  drawTabs();
  drawBody();
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

const PROC_FILTERS = [
  ["all", "All"], ["app", "Apps"], ["system", "System"],
  ["system-app", "System apps"], ["kernel", "Kernel"], ["isolated", "Isolated"],
];

function processFilterBar(opts) {
  const bar = el("div", "filterbar");
  const typeButtons = new Map();
  const update = () => {
    typeButtons.forEach((button, value) => {
      const on = opts.getType() === value;
      button.classList.toggle("active", on);
      button.setAttribute("aria-pressed", String(on));
    });
    const bgOn = opts.getBackground();
    bg.classList.toggle("active", bgOn);
    bg.setAttribute("aria-pressed", String(bgOn));
  };
  PROC_FILTERS.forEach(([value, label]) => {
    const button = el("button", "subtab" + (opts.getType() === value ? " active" : ""), label);
    button.type = "button";
    button.setAttribute("aria-pressed", String(opts.getType() === value));
    button.onclick = () => {
      if (opts.getType() === value) return;
      opts.setType(value);
      update();
      opts.onChange();
    };
    typeButtons.set(value, button);
    bar.appendChild(button);
  });
  const bg = el("button", "subtab" + (opts.getBackground() ? " active" : ""), "Background");
  bg.type = "button";
  bg.title = "Background/cached only";
  bg.setAttribute("aria-pressed", String(opts.getBackground()));
  bg.onclick = () => {
    opts.setBackground(!opts.getBackground());
    update();
    opts.onChange();
  };
  bar.appendChild(bg);
  const search = document.createElement("input");
  search.type = "search";
  search.className = "filtersearch";
  search.placeholder = "Search process or package...";
  search.setAttribute("aria-label", "Search processes");
  search.value = opts.getQuery();
  search.oninput = () => {
    opts.setQuery(search.value);
    opts.onChange();
  };
  bar.appendChild(search);
  return bar;
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
  th.appendChild(el("span", "procunit", col.unit || "\u00a0"));
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
  const head = el("div", "runhead processhead");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, "Processes"));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  head.appendChild(processFilterBar({
    getType: () => procType,
    setType: value => { procType = value; },
    getBackground: () => procBackground,
    setBackground: value => { procBackground = value; },
    getQuery: () => procQuery,
    setQuery: value => { procQuery = value; },
    onChange: () => render(),
  }));
  card.appendChild(head);

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
      const procClass = "proc-kind-" + procCategory(r);
      const tr = el("tr", "procrow " + procClass + (r.key === selectedProc ? " selected" : ""));
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

  render();
  return card;
}

function summaryRows(run) {
  const bandDef = id => (SPEC.bands || []).find(b => b.id === id) || { label: id, unit: "" };
  const rows = [];
  SPEC.groups.forEach(g => {
    const groupSection = g.section || "Other";
    const groupSections = [groupSection, ...(g.extra_sections || [])];
    g.series.forEach(s => {
      if (run.series[s.col]) {
        rows.push({ key: s.col, section: g.title, groupSection, groupSections, label: s.label, unit: s.unit, scale: s.scale ?? 1, decimals: s.decimals ?? null, arr: run.series[s.col] });
      }
    });
    (g.bands || []).forEach(bid => {
      const b = bandDef(bid);
      const mx = "band::" + bid + "::max", av = "band::" + bid + "::avg";
      const extra = { unit: b.unit, scale: b.scale ?? 1, decimals: b.decimals ?? 1 };
      if (run.series[mx]) rows.push({ key: mx, section: g.title, groupSection, groupSections, label: b.label + " (hottest)", ...extra, arr: run.series[mx] });
      if (run.series[av]) rows.push({ key: av, section: g.title, groupSection, groupSections, label: b.label + " (average)", ...extra, arr: run.series[av] });
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

function hottestRunSensor(series) {
  let best = null;
  const consider = (label, values) => {
    const value = _pick(values, "max");
    if (value != null && (!best || value > best.value)) best = { label, value };
  };
  Object.entries(series || {}).forEach(([key, values]) => {
    if (key.startsWith("t_")) {
      consider(key.slice(2), values);
    } else if (key.startsWith("band::") && key.endsWith("::max")) {
      const id = key.slice(6, -5);
      if (id === "cpu" || id === "gpu" || id === "npu") {
        consider({ cpu: "CPU", gpu: "GPU", npu: "NPU" }[id], values);
      }
    }
  });
  return best;
}

function keyStats(dataset) {
  const s = dataset.series || {};
  const last = col => lastVal(s[col]);
  const hottest = hottestRunSensor(s);
  const battery = last("batt_level");
  const items = [
    ["Thermal status", thermalStatusText(last("thermal_status"), _pick(s["thermal_status"], "max"))],
    ["Hottest sensor", hottest ? hottest.label + " · " + fmt(hottest.value, "°C", 1) : "--"],
    ["CPU peak", fmt(_pick(s["band::cpu::max"], "max"), "°C", 1)],
    ["GPU peak", fmt(_pick(s["band::gpu::max"], "max"), "°C", 1)],
    ["Surface peak", fmt(_pick(s["t_skin"], "max") ?? _pick(s["t_AP"], "max"), "°C", 1)],
    ["DDR/RAM peak", fmt(_pick(s["ddr_temp"], "max"), "°C", 1)],
    ["Rail 1 peak", fmt(_pick(s["max_ch1_power"], "max"), "W", 2)],
    ["WiFi peak", fmt(_pick(s["t_WIFI"], "max"), "°C", 1)],
    ["WiFi download", fmt(_pick(s["wifi_rx_mbps"], "avg"), "Mbps", 1)],
    ["Battery", battery == null ? "--" : Math.round(battery) + "%"],
    ["Battery temp", fmt(last("batt_temp"), "°C", 1)],
    ["Fan step", fanProfileLabel(_pick(s["fan_step"], "max"))],
    ["Fan max", fmt(_pick(s["fan_rpm"], "max"), "rpm", 0)],
    ["GPU busy", fmt(_pick(s["g_busy"], "avg"), "%")],
    ["XR fps", fmt(_pick(s["xr_fps"], "avg"), "fps", 0)],
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
    thermalStatus: null, thermalPeak: null,
  };
}

function _previewAdd(p, row, elapsed) {
  const raise = (key, value) => {
    if (typeof value === "number" && Number.isFinite(value) && (p[key] == null || value > p[key])) p[key] = value;
  };
  raise("cpuPeak", _rowMax(row, "t_CPU", 6));
  raise("gpuPeak", _rowMax(row, "t_GPU", 8));
  raise("surfacePeak", row.t_skin ?? row.t_AP);
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
  const titles = new Set((SPEC.groups || []).map(g => g.title));
  if ((SPEC.groups || []).some(g => EXTRA_SECTIONS.has(g.section))) titles.add("Extra");
  document.querySelectorAll("tr.tablesection[data-title]").forEach(sr => titles.add(sr.dataset.title));
  return Array.from(titles);
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
  const rows = summaryRows(run);
  const available = sectionKeysFromRows(rows);
  prepareSectionFilter("view:" + run.label, available);
  const tabsHost = el("div", "sectiontabs");
  card.appendChild(tabsHost);
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

  const main = rows.filter(r => !EXTRA_SECTIONS.has(r.groupSection));
  const extra = rows
    .filter(r => EXTRA_SECTIONS.has(r.groupSection))
    .sort((a, b) => extraRank(a.groupSection) - extraRank(b.groupSection));

  function render() {
    renderSectionTabs(tabsHost, available, () => render());
    const q = summaryTableQuery.trim().toLowerCase();
    const forceOpen = !!q || sectionFilter !== "All";
    const matches = r => !q || (r.label + " " + (r.unit || "") + " " + (r.section || "")).toLowerCase().includes(q);
    const matchSection = r => sectionFilter === "All" || rowSectionList(r).includes(sectionFilter);
    const sectionOrder = rowsForSection => {
      if (sectionFilter === "All" || sectionFilter === "Extra") return rowsForSection;
      return [...rowsForSection].sort((a, b) => {
        const ap = sectionFilterName(a.groupSection || "Other") === sectionFilter ? 0 : 1;
        const bp = sectionFilterName(b.groupSection || "Other") === sectionFilter ? 0 : 1;
        return ap - bp;
      });
    };
    const visibleMain = sectionOrder(main.filter(r => matchSection(r) && matches(r)));
    const visibleExtra = sectionOrder(extra.filter(r => matchSection(r) && matches(r)));
    host.innerHTML = "";
    count.textContent = (visibleMain.length + visibleExtra.length) + " metrics";
    if (!visibleMain.length && !visibleExtra.length) {
      host.appendChild(textEl("div", "muted", "No metrics match this filter/search."));
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
        t.appendChild(tableSectionHeader(r.section, 4, forceOpen));
        last = r.section;
      }
      addRow(r, forceOpen);
    });
    if (visibleExtra.length) {
      const h = extraTableHeader("Extra", 4, forceOpen);
      t.appendChild(h);
      last = null;
      visibleExtra.forEach(r => {
        if (r.section !== last) {
          t.appendChild(tableSectionHeader(r.section, 4, forceOpen));
          last = r.section;
        }
        addRow(r, forceOpen);
      });
      if (!forceOpen && collapsedTableSections.has("Extra")) {
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
  if (f.root_fan) on.push("root extras");
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
  const chev = el("span", "chev", "\u25be");
  head.appendChild(chev);
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, title));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  const clear = el("button", "toolbtn", "Clear");
  clear.type = "button";
  clear.title = "Clear pinned " + kind + " items";
  clear.onclick = (event) => {
    event.stopPropagation();
    clearPins(kind);
  };
  head.appendChild(clear);
  card.appendChild(head);
  const body = el("div", "pinned-body");
  card.appendChild(body);
  registerCollapse(card, "pinned:" + kind, head, body, chev);
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
        const name = textEl("button", "pinned-proc-name", pin.name || pin.key);
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
        showToast({
          title: "Delete failed",
          message: err.message || String(err),
          type: "error",
        });
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

function updateViewTools(tab) {
  const viewtools = document.getElementById("viewtools");
  if (!viewtools) return;
  const show = tab === "run" || tab === "compare";
  viewtools.querySelectorAll(".view-only").forEach(node => {
    node.style.display = show ? "" : "none";
  });
}

function setTab(tab) {
  if (findOpen) closeFind();
  if (tab !== "live") stopPreview();
  if (tab !== "run") runLoadToken += 1;
  if (tab !== "compare") compareRenderToken += 1;
  activeTab = tab;
  updateViewTools(tab);
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
  if (tab === "live") renderLiveView();
  else if (tab === "run") renderRunView();
  else if (tab === "compare") renderCompareView();
}

function registerCollapse(node, key, head, body, chev) {
  node.dataset.collapseKey = key;
  const sync = () => {
    const collapsed = collapsedSections.has(key);
    body.style.display = collapsed ? "none" : "";
    if (chev) chev.textContent = collapsed ? "\u25b8" : "\u25be";
    head.setAttribute("aria-expanded", String(!collapsed));
  };
  node._syncCollapse = sync;
  head.tabIndex = 0;
  head.setAttribute("role", "button");
  head.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      head.onclick();
    }
  };
  head.onclick = () => {
    if (findOpen) closeFind();
    const collapsed = !collapsedSections.has(key);
    if (collapsed) collapsedSections.add(key);
    else collapsedSections.delete(key);
    sync();
    if (!collapsed) resizeChartsSoon();
  };
  sync();
}

function allSectionTitles() {
  const set = new Set();
  let extra = false;
  (SPEC.groups || []).forEach(g => {
    groupSectionList(g).forEach(s => {
      if (s === "Extra") extra = true;
      else set.add(s);
    });
  });
  if (extra) set.add("Extra");
  document.querySelectorAll("[data-collapse-key]").forEach(node => set.add(node.dataset.collapseKey));
  return Array.from(set);
}

function applyCollapseToDom() {
  document.querySelectorAll("[data-collapse-key]").forEach(node => {
    if (typeof node._syncCollapse === "function") node._syncCollapse();
  });
  resizeChartsSoon();
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
  if (!OFFLINE) {
    try {
      const recording = await jget("/api/record/status");
      if (recording && recording.status === "recording" && recording.label) {
        beginLiveSession({ name: recording.label, duration: recording.duration || 0, profile: recording.profile || "" });
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
  } else {
    setTab("live");
  }
}

window.addEventListener("resize", () => { updateStickyOffsets(); resizeChartsSoon(); });
init();
