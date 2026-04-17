const dom = {
  body: document.body,
  statusPill: document.getElementById("cdStatusPill"),
  refreshButton: document.getElementById("cdRefreshButton"),
  summaryTotal: document.getElementById("cdSummaryTotal"),
  summaryCount: document.getElementById("cdSummaryCount"),
  categoryGrid: document.getElementById("cdCategoryGrid"),
  detailPanel: document.getElementById("cdDetailPanel"),
  backButton: document.getElementById("cdBackButton"),
  detailEyebrow: document.getElementById("cdDetailEyebrow"),
  detailTitle: document.getElementById("cdDetailTitle"),
  detailPath: document.getElementById("cdDetailPath"),
  detailTotalSize: document.getElementById("cdDetailTotalSize"),
  detailCount: document.getElementById("cdDetailCount"),
  selectAll: document.getElementById("cdSelectAll"),
  selectClear: document.getElementById("cdSelectClear"),
  deleteSelected: document.getElementById("cdDeleteSelected"),
  removeAll: document.getElementById("cdRemoveAll"),
  itemList: document.getElementById("cdItemList"),
  pager: document.getElementById("cdPager"),
  pagerPrev: document.getElementById("cdPagerPrev"),
  pagerNext: document.getElementById("cdPagerNext"),
  pagerLabel: document.getElementById("cdPagerLabel"),
};

const state = {
  categories: [],
  activeKey: "",
  activeCategory: null,
  selection: new Set(),
  page: 0,
  pageSize: 25,
};

const ICONS = {
  calendar_invites: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 3.5h10c.6 0 1 .4 1 1v8.5c0 .6-.4 1-1 1H3c-.6 0-1-.4-1-1V4.5c0-.6.4-1 1-1zM5 2v3.5M11 2v3.5M2 7h12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  device_artifacts: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="9" rx="1" stroke="currentColor" stroke-width="1.3"/><path d="M6 14h4M8 12v2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  tmp_tests: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 2h8M6 2v3L3 13.5c-.2.6.2 1 .9 1h8.2c.7 0 1.1-.4.9-1L10 5V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  uploads: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 10v3h10v-3M8 2v8M5 5l3-3 3 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

window.addEventListener("load", () => {
  bindEvents();
  registerPWA();
  void loadCategories();
});

function bindEvents() {
  dom.refreshButton?.addEventListener("click", () => void loadCategories());
  dom.backButton?.addEventListener("click", () => showOverview());

  dom.selectAll?.addEventListener("change", (event) => {
    const visible = getPageItems();
    if (event.target.checked) {
      visible.forEach((item) => state.selection.add(item.name));
    } else {
      visible.forEach((item) => state.selection.delete(item.name));
    }
    renderDetail();
  });

  dom.selectClear?.addEventListener("click", () => {
    state.selection.clear();
    renderDetail();
  });

  dom.deleteSelected?.addEventListener("click", () => void deleteSelected());
  dom.removeAll?.addEventListener("click", () => void removeAll());

  dom.pagerPrev?.addEventListener("click", () => {
    if (state.page > 0) {
      state.page -= 1;
      renderDetail();
    }
  });
  dom.pagerNext?.addEventListener("click", () => {
    const items = state.activeCategory?.items || [];
    const maxPage = Math.max(0, Math.ceil(items.length / state.pageSize) - 1);
    if (state.page < maxPage) {
      state.page += 1;
      renderDetail();
    }
  });
}

async function loadCategories() {
  dom.statusPill.textContent = "Loading...";
  try {
    const data = await fetchJson("/api/v1/clear-data?preview_limit=2000");
    state.categories = Array.isArray(data) ? data : [];
    if (state.activeKey) {
      const next = state.categories.find((cat) => cat.key === state.activeKey);
      state.activeCategory = next || null;
      if (!next) state.activeKey = "";
    }
    renderSummary();
    renderCategories();
    if (state.activeCategory) {
      state.selection.clear();
      renderDetail();
    }
    dom.statusPill.textContent = "Ready";
  } catch (error) {
    console.error("Failed to load clear-data categories", error);
    dom.statusPill.textContent = "Failed to load";
    dom.categoryGrid.innerHTML = `<div class="cd-empty">Could not load storage data: ${escapeHtml(error.message || String(error))}</div>`;
  }
}

function renderSummary() {
  const total = state.categories.reduce((sum, cat) => sum + (cat.total_bytes || 0), 0);
  const items = state.categories.reduce((sum, cat) => sum + (cat.item_count || 0), 0);
  dom.summaryTotal.textContent = formatBytes(total);
  dom.summaryCount.textContent = `${items} item${items === 1 ? "" : "s"} across ${state.categories.length} categor${state.categories.length === 1 ? "y" : "ies"}`;
}

function renderCategories() {
  dom.categoryGrid.innerHTML = "";
  state.categories.forEach((cat) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "cd-category-card";
    card.innerHTML = `
      <div class="cd-cat-head">
        <div class="cd-cat-icon">${ICONS[cat.key] || ICONS.uploads}</div>
        <strong class="cd-cat-total">${escapeHtml(formatBytes(cat.total_bytes || 0))}</strong>
      </div>
      <h3>${escapeHtml(cat.label)}</h3>
      <p>${escapeHtml(cat.description)}</p>
      <span class="cd-cat-count">${cat.item_count || 0} item${cat.item_count === 1 ? "" : "s"}${cat.exists ? "" : " · missing"}</span>
    `;
    card.addEventListener("click", () => openCategory(cat.key));
    dom.categoryGrid.appendChild(card);
  });
}

function openCategory(key) {
  state.activeKey = key;
  state.activeCategory = state.categories.find((cat) => cat.key === key) || null;
  state.selection.clear();
  state.page = 0;
  document.body.setAttribute("data-cd-category", key);
  dom.detailPanel.hidden = false;
  renderDetail();
  dom.detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showOverview() {
  state.activeKey = "";
  state.activeCategory = null;
  state.selection.clear();
  document.body.setAttribute("data-cd-category", "");
  dom.detailPanel.hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function getPageItems() {
  const items = state.activeCategory?.items || [];
  const start = state.page * state.pageSize;
  return items.slice(start, start + state.pageSize);
}

function renderDetail() {
  if (!state.activeCategory) return;
  const cat = state.activeCategory;
  dom.detailEyebrow.textContent = cat.exists ? "Category" : "Missing folder";
  dom.detailTitle.textContent = cat.label;
  dom.detailPath.textContent = cat.path;
  dom.detailTotalSize.textContent = formatBytes(cat.total_bytes || 0);
  dom.detailCount.textContent = `${cat.item_count || 0} item${cat.item_count === 1 ? "" : "s"}`;
  dom.removeAll.disabled = !cat.item_count;

  dom.itemList.innerHTML = "";
  const items = cat.items || [];
  const totalShown = items.length;
  const total = cat.item_count || totalShown;
  const pageSize = state.pageSize;
  const maxPage = Math.max(0, Math.ceil(totalShown / pageSize) - 1);
  if (state.page > maxPage) state.page = maxPage;
  const slice = getPageItems();

  if (!slice.length) {
    const empty = document.createElement("div");
    empty.className = "cd-empty";
    empty.textContent = cat.exists
      ? "This folder is empty. Nothing to clean up here."
      : "This folder does not exist yet.";
    dom.itemList.appendChild(empty);
    dom.pager.hidden = true;
    dom.selectAll.checked = false;
    dom.deleteSelected.disabled = true;
    return;
  }

  slice.forEach((item) => {
    const row = document.createElement("div");
    row.className = `cd-item${state.selection.has(item.name) ? " selected" : ""}`;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selection.has(item.name);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selection.add(item.name);
      else state.selection.delete(item.name);
      row.classList.toggle("selected", checkbox.checked);
      dom.deleteSelected.disabled = state.selection.size === 0;
      syncSelectAll();
    });

    const icon = document.createElement("div");
    icon.className = "cd-item-icon";
    icon.innerHTML = item.is_dir
      ? `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 4h3l1.5 1.5H12c.5 0 1 .5 1 1v4c0 .5-.5 1-1 1H2c-.5 0-1-.5-1-1V5c0-.5.5-1 1-1z" stroke="currentColor" stroke-width="1.2"/></svg>`
      : `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 1h5.5L12 4.5V13H3z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 1v4h4" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>`;

    const name = document.createElement("div");
    name.className = "cd-item-name";
    name.innerHTML = `<strong>${escapeHtml(item.name)}</strong><span>${item.is_dir ? "Folder" : "File"}${item.modified_at ? " · " + escapeHtml(formatWhen(item.modified_at)) : ""}</span>`;

    const size = document.createElement("span");
    size.className = "cd-item-size";
    size.textContent = formatBytes(item.size_bytes || 0);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "cd-item-delete";
    del.setAttribute("aria-label", `Delete ${item.name}`);
    del.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;
    del.addEventListener("click", () => void deleteEntries([item.name]));

    row.appendChild(checkbox);
    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(size);
    row.appendChild(del);
    dom.itemList.appendChild(row);
  });

  // Pager
  if (totalShown <= pageSize) {
    dom.pager.hidden = true;
  } else {
    dom.pager.hidden = false;
    dom.pagerPrev.disabled = state.page <= 0;
    dom.pagerNext.disabled = state.page >= maxPage;
    dom.pagerLabel.textContent = `${state.page + 1} / ${maxPage + 1}`;
  }

  dom.deleteSelected.disabled = state.selection.size === 0;
  syncSelectAll();

  // Hint if total count exceeds what we fetched
  if (total > totalShown) {
    const note = document.createElement("div");
    note.className = "cd-empty";
    note.style.marginTop = "0.4rem";
    note.textContent = `Showing the first ${totalShown} of ${total} items. Use Remove all to wipe everything.`;
    dom.itemList.appendChild(note);
  }
}

function syncSelectAll() {
  const visible = getPageItems();
  if (!visible.length) {
    dom.selectAll.checked = false;
    dom.selectAll.indeterminate = false;
    return;
  }
  const selectedCount = visible.filter((item) => state.selection.has(item.name)).length;
  dom.selectAll.checked = selectedCount === visible.length;
  dom.selectAll.indeterminate = selectedCount > 0 && selectedCount < visible.length;
}

async function deleteEntries(names) {
  if (!state.activeCategory) return;
  if (!names.length) return;
  const label = names.length === 1 ? names[0] : `${names.length} items`;
  if (!confirm(`Delete ${label} from ${state.activeCategory.label}? This cannot be undone.`)) return;

  try {
    await fetchJson(`/api/v1/clear-data/${encodeURIComponent(state.activeKey)}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names }),
    });
    names.forEach((name) => state.selection.delete(name));
    await loadCategories();
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function deleteSelected() {
  const names = Array.from(state.selection);
  if (!names.length) return;
  await deleteEntries(names);
}

async function removeAll() {
  if (!state.activeCategory) return;
  if (!confirm(`Remove ALL ${state.activeCategory.item_count} items from ${state.activeCategory.label}? This cannot be undone.`)) return;
  try {
    await fetchJson(`/api/v1/clear-data/${encodeURIComponent(state.activeKey)}`, { method: "DELETE" });
    state.selection.clear();
    await loadCategories();
  } catch (error) {
    alert(error.message || String(error));
  }
}

/* ═══════════════ UTILITIES ═══════════════ */

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const decimals = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(decimals)} ${units[unitIndex]}`;
}

function formatWhen(epochSeconds) {
  if (!epochSeconds) return "";
  const date = new Date(Number(epochSeconds) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;
    } catch (error) {
      try { detail = await response.text(); } catch (innerError) { /* ignore */ }
    }
    throw new Error(detail);
  }
  return response.json();
}

function registerPWA() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/app-sw.js", { scope: "/" }).catch((error) => {
      console.error("Failed to register service worker", error);
    });
  }
}
