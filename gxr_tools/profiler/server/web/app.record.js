"use strict";

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
  const hottest = previewHottestSensor(metrics);
  const items = [
    ["Thermal status", thermalStatusText(metrics.thermal_status, null)],
    ["Hottest sensor", hottest ? hottest.key + " · " + fmt(hottest.value, "°C", 1) : "--"],
    ["CPU hottest", fmt(_rowMax(metrics, "t_CPU", 6), "°C", 1)],
    ["GPU hottest", fmt(_rowMax(metrics, "t_GPU", 8), "°C", 1)],
    ["Surface", fmt(metrics.t_skin ?? metrics.t_AP, "°C", 1)],
    ["DDR/RAM", fmt(metrics.ddr_temp, "°C", 1)],
    ["Rail 1", fmt(metrics.max_ch1_power, "W", 2)],
    ["WiFi", fmt(metrics.t_WIFI, "°C", 1)],
    ["WiFi download", fmt(metrics.wifi_rx_mbps, "Mbps", 1)],
    ["Battery", metrics.batt_level == null ? "--" : Math.round(metrics.batt_level) + "%"],
    ["Battery temp", fmt(metrics.batt_temp, "°C", 1)],
    ["Fan step", fanProfileLabel(metrics.fan_step)],
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
  const status = textEl("span", "livestatus", "connecting");
  status.id = "preview-status";
  const stop = el("button", "toolbtn", "Stop");
  stop.type = "button";
  stop.onclick = () => stopPreview();
  actions.appendChild(status);
  actions.appendChild(stop);
  head.appendChild(actions);
  card.appendChild(head);
  card.appendChild(el("p", "muted cardnote", "Lightweight preview: thermal, power, fan and Wi-Fi samples. Nothing is written to disk."));
  const body = el("div", "preview-body");
  body.id = "preview-body";
  body.appendChild(el("div", "muted preview-loading", "Waiting for headset (retrying for up to 30s)..."));
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
  const startStatus = el("span", "muted formstatus");
  startStatus.setAttribute("role", "status");
  actions.appendChild(startBtn);
  if (!OFFLINE) actions.appendChild(previewBtn);
  actions.appendChild(el("span", "recordhint muted", "Polls at 1 Hz."));
  actions.appendChild(startStatus);
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
      <span class="optbody"><span class="opttitle">Root extras</span><span class="optdesc">Fan RPM/PWM, active panel and calibration metadata. Uses read-only su and may prompt.</span></span></label>
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
      startStatus.className = "formerror";
      startStatus.textContent = "Could not read form: " + (e.message || e);
      return;
    }
    startBtn.disabled = true;
    startStatus.className = "muted formstatus";
    startStatus.textContent = "Connecting to headset (retrying if needed)...";
    stopPreview();
    ensureAudio();
    try {
      await jpost("/api/record", request);
    } catch (e) {
      startBtn.disabled = false;
      startStatus.className = "formerror";
      startStatus.textContent = "Could not start: " + e.message;
      return;
    }
    startStatus.textContent = "";
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
    if (msg.elapsed != null) session.elapsed = msg.elapsed;
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
    const reachedEnd = session.status === "done" && elapsed >= duration - 0.25;
    const pct = reachedEnd ? 100 : Math.min(100, (elapsed / duration) * 100);
    fill.style.width = pct + "%";
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
