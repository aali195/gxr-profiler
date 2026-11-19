"use strict";

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

