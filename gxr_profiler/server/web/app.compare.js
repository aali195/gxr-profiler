"use strict";

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
    const groupSections = [groupSection, ...(g.extra_sections || [])];
    const push = (key, label, unit, getter, scale, decimals) => {
      const perRun = datasets.map(d => getter(d.series));
      if (perRun.some(a => a && a.some(x => x != null))) {
        out.push({ key, section: g.title, groupSection, groupSections, label, unit, scale, decimals, perRun });
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
  const rows = metricArrays(datasets);
  const available = sectionKeysFromRows(rows);
  prepareSectionFilter("view:" + datasets.map(d => d.label).join("|"), available);
  const tabsHost = el("div", "sectiontabs");
  card.appendChild(tabsHost);
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

  const main = rows.filter(m => !EXTRA_SECTIONS.has(m.groupSection));
  const extra = rows
    .filter(m => EXTRA_SECTIONS.has(m.groupSection))
    .sort((a, b) => extraRank(a.groupSection) - extraRank(b.groupSection));

  function render() {
    renderSectionTabs(tabsHost, available, () => render());
    const q = cmpTableQuery.trim().toLowerCase();
    const forceOpen = !!q || sectionFilter !== "All";
    const matches = m => !q || (m.label + " " + (m.unit || "") + " " + (m.section || "")).toLowerCase().includes(q);
    const matchSection = m => sectionFilter === "All" || rowSectionList(m).includes(sectionFilter);
    const sectionOrder = rowsForSection => {
      if (sectionFilter === "All" || sectionFilter === "Extra") return rowsForSection;
      return [...rowsForSection].sort((a, b) => {
        const ap = sectionFilterName(a.groupSection || "Other") === sectionFilter ? 0 : 1;
        const bp = sectionFilterName(b.groupSection || "Other") === sectionFilter ? 0 : 1;
        return ap - bp;
      });
    };
    const visibleMain = sectionOrder(main.filter(m => matchSection(m) && matches(m)));
    const visibleExtra = sectionOrder(extra.filter(m => matchSection(m) && matches(m)));
    host.innerHTML = "";
    count.textContent = (visibleMain.length + visibleExtra.length) + " metrics";
    if (!visibleMain.length && !visibleExtra.length) {
      host.appendChild(textEl("div", "muted", "No metrics match this filter/search."));
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
        t.appendChild(tableSectionHeader(m.section, 1 + datasets.length, forceOpen));
        last = m.section;
      }
      addRow(m, forceOpen);
    });
    if (visibleExtra.length) {
      const h = extraTableHeader("Extra", 1 + datasets.length, forceOpen);
      t.appendChild(h);
      last = null;
      visibleExtra.forEach(m => {
        if (m.section !== last) {
          t.appendChild(tableSectionHeader(m.section, 1 + datasets.length, forceOpen));
          last = m.section;
        }
        addRow(m, forceOpen);
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
  const head = el("div", "runhead processhead");
  const titleBox = el("div", "pickhead");
  titleBox.appendChild(el("h3", null, "Processes"));
  const count = el("span", "pickcount muted");
  titleBox.appendChild(count);
  head.appendChild(titleBox);
  head.appendChild(processFilterBar({
    getType: () => cmpProcType,
    setType: value => { cmpProcType = value; },
    getBackground: () => cmpProcBackground,
    setBackground: value => { cmpProcBackground = value; },
    getQuery: () => cmpProcQuery,
    setQuery: value => { cmpProcQuery = value; },
    onChange: () => render(),
  }));
  card.appendChild(head);

  const controls = el("div", "proccontrols cmpcontrols");
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
  controls.appendChild(sortRunSel);
  controls.appendChild(modeBtn);
  controls.appendChild(metricSel);
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
      const procClass = "proc-kind-" + procCategory(e);
      const tr = el("tr", "procrow " + procClass + (e.key === selectedCmpProc ? " selected" : ""));
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
          tr.appendChild(textEl("td", null, procCellText(r, metric)));
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

