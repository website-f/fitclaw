const chatStorageKey = "fitclaw_aiops_user_id";
const financeScopeStorageKey = "fitclaw_finance_scope";
const financeDisplayCurrencyStorageKey = "fitclaw_finance_display_currency";

const dom = {
  refreshButton: document.getElementById("refreshButton"),
  todayTotal: document.getElementById("todayTotal"),
  monthTotal: document.getElementById("monthTotal"),
  monthCount: document.getElementById("monthCount"),
  statusText: document.getElementById("statusText"),
  scopeText: document.getElementById("scopeText"),
  entryList: document.getElementById("entryList"),
  entryListOverview: document.getElementById("entryListOverview"),
  ruleList: document.getElementById("ruleList"),
  categoryRuleForm: document.getElementById("categoryRuleForm"),
  categoryKeywordInput: document.getElementById("categoryKeywordInput"),
  categoryValueInput: document.getElementById("categoryValueInput"),
  thresholdRuleForm: document.getElementById("thresholdRuleForm"),
  thresholdScopeInput: document.getElementById("thresholdScopeInput"),
  thresholdCategoryInput: document.getElementById("thresholdCategoryInput"),
  thresholdAmountInput: document.getElementById("thresholdAmountInput"),
  displayCurrencySelect: document.getElementById("displayCurrencySelect"),
  fxAsOfText: document.getElementById("fxAsOfText"),
};

const state = {
  userId: normalizeLedgerUserId(localStorage.getItem(financeScopeStorageKey) || "all"),
  ruleUserId: normalizeRuleOwnerId(localStorage.getItem(chatStorageKey) || "web-finance"),
  overview: null,
  rules: [],
  whatsappOwnerId: "",
  displayCurrency: String(localStorage.getItem(financeDisplayCurrencyStorageKey) || "MYR").toUpperCase(),
};

window.addEventListener("load", () => {
  bindEvents();
  registerPWA();
  void initialize();
});

function bindEvents() {
  dom.refreshButton.addEventListener("click", () => void loadAll());
  dom.categoryRuleForm.addEventListener("submit", onCreateCategoryRule);
  dom.thresholdRuleForm.addEventListener("submit", onCreateThresholdRule);
  dom.displayCurrencySelect.addEventListener("change", () => {
    state.displayCurrency = String(dom.displayCurrencySelect.value || "MYR").toUpperCase();
    localStorage.setItem(financeDisplayCurrencyStorageKey, state.displayCurrency);
    void loadAll();
  });
}

async function initialize() {
  await resolveFinanceContext();
  await loadAll();
}

async function resolveFinanceContext() {
  localStorage.setItem(financeScopeStorageKey, state.userId);
  try {
    const whatsappStatus = await fetchJson("/api/v1/whatsapp/status");
    const defaultRecipient = String(whatsappStatus.default_recipient || "").trim();
    if (defaultRecipient) {
      state.whatsappOwnerId = `whatsapp:${defaultRecipient}`;
      if (!state.ruleUserId || state.ruleUserId === "web-finance") {
        state.ruleUserId = state.whatsappOwnerId;
      }
    }
  } catch (error) {
    console.debug("Finance context could not load WhatsApp status.", error);
  }
  updateScopeText();
  dom.displayCurrencySelect.value = state.displayCurrency;
}

async function loadAll() {
  setStatus("Loading...");
  updateScopeText();
  try {
    const [overview, rules] = await Promise.all([
      fetchJson(
        `/api/v1/finance/overview?user_id=${encodeURIComponent(state.userId)}&display_currency=${encodeURIComponent(state.displayCurrency)}`
      ),
      fetchJson(`/api/v1/finance/rules?user_id=${encodeURIComponent(state.userId)}`),
    ]);
    state.overview = overview;
    state.displayCurrency = String(overview.display_currency || state.displayCurrency || "MYR").toUpperCase();
    dom.displayCurrencySelect.value = state.displayCurrency;
    localStorage.setItem(financeDisplayCurrencyStorageKey, state.displayCurrency);
    state.rules = rules;
    render();
    setStatus("Ready");
  } catch (error) {
    console.error(error);
    setStatus(`Failed to load finance data: ${error.message}`);
  }
}

function render() {
  const overview = state.overview || {};
  const displayCurrency = String(overview.display_currency || state.displayCurrency || "MYR").toUpperCase();
  dom.todayTotal.textContent = formatCurrency(overview.today_total_cents || 0, displayCurrency);
  dom.monthTotal.textContent = formatCurrency(overview.month_total_cents || 0, displayCurrency);
  dom.monthCount.textContent = String(overview.month_entry_count || 0);
  if (dom.fxAsOfText) {
    dom.fxAsOfText.textContent = overview.fx_as_of === "fallback"
      ? "FX source: fallback rates (live rate service unavailable)."
      : overview.fx_as_of
      ? `FX rates last updated: ${overview.fx_as_of} (base USD)`
      : "FX rates unavailable, conversion falls back to original values.";
  }

  renderEntries(overview.recent_entries || [], displayCurrency, overview.fx_rates || {});
  renderRules(state.rules || []);
  updateScopeText();
}

function renderEntries(entries, displayCurrency, fxRates) {
  const emptyHtml = '<div class="empty-state">No finance entries yet. Send a receipt in chat and it can land here automatically.</div>';
  if (!entries.length) {
    if (dom.entryList) dom.entryList.innerHTML = emptyHtml;
    if (dom.entryListOverview) dom.entryListOverview.innerHTML = emptyHtml;
    return;
  }
  const renderEntry = (entry) => `
    <article class="entry-item">
      <h3>${escapeHtml(entry.title)}</h3>
      <div class="entry-meta">
        <span>${escapeHtml(entry.merchant_name || "Unknown merchant")}</span>
        <span>${formatEntryAmount(entry, displayCurrency, fxRates)}</span>
        <span>${escapeHtml(entry.category || "Uncategorized")}</span>
        <span>${formatDate(entry.occurred_at)}</span>
      </div>
      <div class="row-actions">
        <button class="danger-button" type="button" data-entry-id="${entry.entry_id}">Delete</button>
      </div>
    </article>
  `;
  if (dom.entryList) dom.entryList.innerHTML = entries.map(renderEntry).join("");
  if (dom.entryListOverview) dom.entryListOverview.innerHTML = entries.slice(0, 5).map(renderEntry).join("");

  document.querySelectorAll("[data-entry-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm(`Delete finance entry ${button.dataset.entryId}?`)) return;
      await fetch(`/api/v1/finance/entries/${encodeURIComponent(button.dataset.entryId)}?user_id=${encodeURIComponent(state.userId)}`, {
        method: "DELETE",
        cache: "no-store",
      });
      await loadAll();
    });
  });
}

function formatEntryAmount(entry, displayCurrency, fxRates) {
  const sourceCurrency = String(entry.currency || displayCurrency || "MYR").toUpperCase();
  const convertedCents = convertAmountCents(entry.amount_cents || 0, sourceCurrency, displayCurrency, fxRates);
  if (convertedCents == null) {
    return `${formatCurrency(entry.amount_cents || 0, sourceCurrency)} (conversion unavailable)`;
  }
  const convertedLabel = formatCurrency(convertedCents, displayCurrency);
  if (sourceCurrency === displayCurrency) {
    return convertedLabel;
  }
  return `${convertedLabel} (${formatCurrency(entry.amount_cents || 0, sourceCurrency)})`;
}

function convertAmountCents(amountCents, sourceCurrency, targetCurrency, fxRates) {
  if (sourceCurrency === targetCurrency) return Number(amountCents || 0);
  const sourceRate = Number(fxRates[sourceCurrency]);
  const targetRate = Number(fxRates[targetCurrency]);
  if (!Number.isFinite(sourceRate) || sourceRate <= 0 || !Number.isFinite(targetRate) || targetRate <= 0) {
    return null;
  }
  const usdValue = Number(amountCents || 0) / sourceRate;
  return Math.round(usdValue * targetRate);
}

function renderRules(rules) {
  if (!rules.length) {
    dom.ruleList.innerHTML = '<div class="empty-state">No finance rules yet. Create one below for auto-categories or spend alerts.</div>';
    return;
  }
  dom.ruleList.innerHTML = rules.map((rule) => `
    <article class="rule-item">
      <h3>${escapeHtml(rule.name)}</h3>
      <div class="rule-meta">
        <span>${escapeHtml(rule.kind)}</span>
        <span>${escapeHtml(JSON.stringify(rule.criteria_json || {}))}</span>
        <span>${escapeHtml(JSON.stringify(rule.action_json || {}))}</span>
      </div>
      <div class="row-actions">
        <button class="danger-button" type="button" data-rule-id="${rule.rule_id}">Delete</button>
      </div>
    </article>
  `).join("");

  dom.ruleList.querySelectorAll("[data-rule-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm(`Delete finance rule ${button.dataset.ruleId}?`)) return;
      await fetch(`/api/v1/finance/rules/${encodeURIComponent(button.dataset.ruleId)}?user_id=${encodeURIComponent(state.userId)}`, {
        method: "DELETE",
      });
      await loadAll();
    });
  });
}

async function onCreateCategoryRule(event) {
  event.preventDefault();
  const keyword = dom.categoryKeywordInput.value.trim();
  const category = dom.categoryValueInput.value.trim();
  if (!keyword || !category) {
    setStatus("Enter both a merchant keyword and category.");
    return;
  }
  await postJson("/api/v1/finance/rules", {
    user_id: state.ruleUserId,
    name: `Auto category: ${keyword} -> ${category}`,
    kind: "category_keyword",
    criteria_json: { merchant_keyword: keyword },
    action_json: { set_category: category },
  });
  dom.categoryRuleForm.reset();
  await loadAll();
}

async function onCreateThresholdRule(event) {
  event.preventDefault();
  const scope = dom.thresholdScopeInput.value.trim();
  const category = dom.thresholdCategoryInput.value.trim();
  const amount = Number.parseFloat(dom.thresholdAmountInput.value.trim());
  if (!Number.isFinite(amount) || amount <= 0) {
    setStatus("Enter a valid threshold amount.");
    return;
  }
  await postJson("/api/v1/finance/rules", {
    user_id: state.ruleUserId,
    name: `${scope} spending alert${category ? ` for ${category}` : ""}`,
    kind: "threshold",
    criteria_json: {
      scope,
      category: category || null,
      threshold_cents: Math.round(amount * 100),
    },
    action_json: { type: "warn" },
  });
  dom.thresholdRuleForm.reset();
  await loadAll();
}

async function fetchJson(url) {
  const response = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    throw new Error(await response.text() || `HTTP ${response.status}`);
  }
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await response.text() || `HTTP ${response.status}`);
  }
  return response.json();
}

function formatCurrency(amountCents, currency) {
  const value = (amountCents || 0) / 100;
  const prefix = String(currency || "MYR").toUpperCase() === "MYR" ? "RM" : String(currency || "MYR").toUpperCase();
  return `${prefix} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(value) {
  if (!value) return "Unknown date";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function setStatus(message) {
  dom.statusText.textContent = message;
}

function updateScopeText() {
  if (!dom.scopeText) return;
  const scopeLabel = formatScopeLabel(state.userId);
  const ownerLabel = formatOwnerLabel(state.ruleUserId);
  dom.scopeText.textContent = state.userId === "all"
    ? `Viewing all saved finance sources. New rules save to ${ownerLabel}.`
    : `Viewing finance source: ${scopeLabel}. New rules save to ${ownerLabel}.`;
}

function normalizeLedgerUserId(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return "all";
  const lowered = normalized.toLowerCase();
  if (lowered === "all" || lowered === "*" || lowered === "web-finance") return "all";
  if (lowered.startsWith("web-") || lowered.startsWith("web:")) return "all";
  return normalized;
}

function normalizeRuleOwnerId(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return "web-finance";
  const lowered = normalized.toLowerCase();
  if (lowered === "all" || lowered === "*") return "web-finance";
  return normalized;
}

function formatScopeLabel(userId) {
  if (!userId || userId === "all") return "all finance sources";
  if (userId.startsWith("whatsapp:")) return `WhatsApp ${userId.slice("whatsapp:".length)}`;
  if (userId.startsWith("telegram:")) return `Telegram ${userId.slice("telegram:".length)}`;
  if (userId.startsWith("web-") || userId === "web-finance") return "this web app";
  return userId;
}

function formatOwnerLabel(userId) {
  if (!userId || userId === "web-finance") return "this web app";
  if (userId.startsWith("whatsapp:")) return `WhatsApp ${userId.slice("whatsapp:".length)}`;
  if (userId.startsWith("telegram:")) return `Telegram ${userId.slice("telegram:".length)}`;
  return userId;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function registerPWA() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/app-sw.js").catch(() => {});
}
