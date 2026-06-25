"use strict";

const USER_KEY = "fitclaw.userId";

const state = {
  userId: localStorage.getItem(USER_KEY) || "fitclaw",
  windowDays: 30,
  data: null,
};

const dom = {};

window.addEventListener("DOMContentLoaded", () => {
  cacheDom();
  bindEvents();
  void refresh();
});

function cacheDom() {
  dom.window = document.getElementById("anWindow");
  dom.refresh = document.getElementById("anRefresh");
  dom.tokensToday = document.getElementById("anTokensToday");
  dom.tokensWeek = document.getElementById("anTokensWeek");
  dom.costToday = document.getElementById("anCostToday");
  dom.costMonth = document.getElementById("anCostMonth");
  dom.feedback = document.getElementById("anFeedback");
  dom.corrections = document.getElementById("anCorrections");
  dom.kb = document.getElementById("anKb");
  dom.kbBreakdown = document.getElementById("anKbBreakdown");
  dom.usageByModel = document.getElementById("anUsageByModel");
  dom.budgets = document.getElementById("anBudgets");
  dom.finance = document.getElementById("anFinance");
  dom.audit = document.getElementById("anAudit");
}

function bindEvents() {
  dom.window.addEventListener("change", () => {
    state.windowDays = parseInt(dom.window.value, 10) || 30;
    void refresh();
  });
  dom.refresh.addEventListener("click", () => void refresh());
}

async function refresh() {
  try {
    const response = await fetch(
      `/api/v1/analytics/overview?user_id=${encodeURIComponent(state.userId)}&days=${state.windowDays}`
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    renderAll();
  } catch (error) {
    console.error("analytics load failed", error);
    dom.audit.innerHTML = `<li class="kb-error">${escapeHtml(error.message || String(error))}</li>`;
  }
}

function renderAll() {
  if (!state.data) return;
  const { usage, feedback, knowledge, finance, budgets, audit } = state.data;

  const today = usage.today.total;
  const week = usage.week.total;
  const month = usage.month.total;
  dom.tokensToday.textContent = `${(today.input_tokens + today.output_tokens).toLocaleString()}`;
  dom.tokensWeek.textContent = `Week ${(week.input_tokens + week.output_tokens).toLocaleString()} · Month ${(month.input_tokens + month.output_tokens).toLocaleString()}`;
  dom.costToday.textContent = `$${(today.cost_cents / 100).toFixed(4)}`;
  dom.costMonth.textContent = `Month $${(month.cost_cents / 100).toFixed(4)}`;

  dom.feedback.textContent = `${feedback.up} · ${feedback.down}`;
  dom.corrections.textContent = `${feedback.corrections} correction${feedback.corrections === 1 ? "" : "s"}`;

  dom.kb.textContent = `${knowledge.documents} docs`;
  dom.kbBreakdown.textContent = `${knowledge.chunks} chunks · ${knowledge.by_department.length} departments`;

  renderUsageBars(usage.today.by_model);
  renderBudgets(budgets);
  renderFinance(finance);
  renderAudit(audit);
}

function renderUsageBars(byModel) {
  const entries = Object.entries(byModel || {});
  if (!entries.length) {
    dom.usageByModel.innerHTML = `<p class="kb-empty">No LLM calls logged today.</p>`;
    return;
  }
  const max = Math.max(...entries.map(([, v]) => v.input_tokens + v.output_tokens));
  dom.usageByModel.innerHTML = entries
    .sort((a, b) => (b[1].input_tokens + b[1].output_tokens) - (a[1].input_tokens + a[1].output_tokens))
    .map(([model, v]) => {
      const total = v.input_tokens + v.output_tokens;
      const pct = max > 0 ? Math.round((total / max) * 100) : 0;
      return `
        <div class="an-bar-row">
          <div class="an-bar-label">
            <strong>${escapeHtml(model)}</strong>
            <span>${v.calls} call${v.calls === 1 ? "" : "s"} · $${(v.cost_cents / 100).toFixed(4)}</span>
          </div>
          <div class="an-bar-track"><span class="an-bar-fill" style="width:${pct}%"></span></div>
          <div class="an-bar-total">${total.toLocaleString()}</div>
        </div>`;
    })
    .join("");
}

function renderBudgets(budgets) {
  if (!budgets.length) {
    dom.budgets.innerHTML = `<p class="kb-empty">No budgets configured. POST <code>/api/v1/budgets</code> to add one.</p>`;
    return;
  }
  dom.budgets.innerHTML = budgets
    .map((budget) => {
      const pct = Math.min(100, Math.round(budget.spent_pct));
      const overThreshold = budget.spent_pct >= budget.threshold_pct;
      return `
        <article class="an-budget ${overThreshold ? "is-warning" : ""}">
          <header>
            <strong>${escapeHtml(budget.scope === "user" ? "User" : budget.scope)} · ${escapeHtml(budget.period)}</strong>
            <span>${(budget.limit_cents / 100).toFixed(2)} ${escapeHtml(budget.currency)}</span>
          </header>
          <div class="an-budget-meter"><span style="width:${pct}%"></span></div>
          <small>${(budget.spent_cents / 100).toFixed(4)} spent · ${pct}% of cap · alerts at ${budget.threshold_pct}%</small>
        </article>`;
    })
    .join("");
}

function renderFinance(finance) {
  if (!finance.entries) {
    dom.finance.innerHTML = `<p class="kb-empty">No finance entries in this window.</p>`;
    return;
  }
  const total = (finance.total_cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const rows = (finance.by_category || [])
    .map((row) => `<li><strong>${escapeHtml(row.category)}</strong><span>${(row.cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${escapeHtml(finance.currency)}</span></li>`)
    .join("");
  dom.finance.innerHTML = `
    <p class="an-finance-total"><strong>${total} ${escapeHtml(finance.currency)}</strong> across ${finance.entries} entries</p>
    <ul class="an-finance-list">${rows || "<li>No category breakdown yet.</li>"}</ul>
  `;
}

function renderAudit(events) {
  if (!events.length) {
    dom.audit.innerHTML = `<li class="kb-empty">No audit events yet.</li>`;
    return;
  }
  dom.audit.innerHTML = events
    .map((event) => {
      const date = new Date(event.created_at).toLocaleString();
      return `
        <li>
          <span class="an-audit-action">${escapeHtml(event.action)}</span>
          <span class="an-audit-summary">${escapeHtml(event.summary)}</span>
          <small>${escapeHtml(event.source)}${event.actor ? ` · ${escapeHtml(event.actor)}` : ""} · ${escapeHtml(date)}</small>
        </li>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}
