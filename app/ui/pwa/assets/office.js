"use strict";

const USER_KEY = "fitclaw.userId";
const POLL_MS = 5000;

const state = {
  userId: localStorage.getItem(USER_KEY) || "fitclaw",
  agents: [],
  tasks: [],
  selectedAgent: null,
  pollTimer: null,
};

const dom = {};

window.addEventListener("DOMContentLoaded", () => {
  cacheDom();
  bindEvents();
  refresh().then(startPolling);
});

window.addEventListener("beforeunload", stopPolling);

function cacheDom() {
  dom.floor = document.getElementById("officeFloor");
  dom.queue = document.getElementById("officeQueue");
  dom.queueCount = document.getElementById("officeQueueCount");
  dom.refresh = document.getElementById("officeRefresh");
  dom.modal = document.getElementById("officeTaskModal");
  dom.modalTitle = document.getElementById("officeTaskTitle");
  dom.taskTitle = document.getElementById("officeTaskTitleInput");
  dom.taskDetail = document.getElementById("officeTaskDetail");
  dom.taskCancel = document.getElementById("officeTaskCancel");
  dom.taskSubmit = document.getElementById("officeTaskSubmit");
  dom.taskStatus = document.getElementById("officeTaskStatus");
}

function bindEvents() {
  dom.refresh.addEventListener("click", () => void refresh());
  dom.taskCancel.addEventListener("click", closeModal);
  dom.taskSubmit.addEventListener("click", () => void submitTask());
  dom.modal.addEventListener("click", (event) => {
    if (event.target === dom.modal) closeModal();
  });
}

function startPolling() {
  stopPolling();
  state.pollTimer = window.setInterval(() => void refresh(), POLL_MS);
}

function stopPolling() {
  if (state.pollTimer) window.clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function refresh() {
  try {
    const [agents, tasks] = await Promise.all([
      fetchJson("/api/v1/agents"),
      fetchJson("/api/v1/tasks?limit=25"),
    ]);
    state.agents = Array.isArray(agents) ? agents : [];
    state.tasks = Array.isArray(tasks) ? tasks : [];
    renderAll();
  } catch (error) {
    console.error("office refresh failed", error);
  }
}

function renderAll() {
  renderFloor();
  renderQueue();
}

function renderFloor() {
  dom.floor.innerHTML = "";
  if (!state.agents.length) {
    dom.floor.innerHTML = `<p class="kb-empty" style="grid-column:1/-1">No agents registered yet. Install the agent daemon on a PC and it will appear here.</p>`;
    return;
  }
  state.agents.forEach((agent) => {
    const status = (agent.status || "offline").toLowerCase();
    const node = document.createElement("article");
    node.className = `office-desk ${status}`;
    node.dataset.agent = agent.name;

    const currentTask = state.tasks.find(
      (task) => task.agent_name === agent.name && (task.status === "running" || task.status === "in_progress")
    );

    node.innerHTML = `
      <span class="office-status-badge"><span class="office-legend-dot ${status}"></span>${escapeHtml(status)}</span>
      <div class="office-desk-surface"></div>
      <div class="office-desk-monitor-stand"></div>
      <div class="office-desk-monitor"></div>
      <div class="office-worker">
        <div class="head"></div>
        <div class="body"></div>
        <div class="arms"><span class="arm"></span><span class="arm"></span></div>
      </div>
      <div class="office-plaque">
        <strong>${escapeHtml(agent.name)}</strong>
        <small>${currentTask ? escapeHtml(currentTask.title || currentTask.task_id) : "Tap to assign a task"}</small>
      </div>
    `;
    node.addEventListener("click", () => openModal(agent));
    dom.floor.appendChild(node);
  });
}

function renderQueue() {
  const active = state.tasks
    .filter((task) => ["queued", "running", "in_progress", "completed", "failed"].includes(task.status))
    .slice(0, 12);
  dom.queueCount.textContent = `${active.filter((t) => t.status === "running" || t.status === "in_progress").length} in flight`;
  if (!active.length) {
    dom.queue.innerHTML = `<li class="kb-empty">No tasks recorded yet.</li>`;
    return;
  }
  dom.queue.innerHTML = active
    .map((task) => {
      const status = (task.status || "queued").toLowerCase();
      const owner = task.agent_name || "unassigned";
      const updated = task.updated_at || task.created_at || null;
      return `
        <li>
          <span class="office-queue-state ${status === "in_progress" ? "running" : status}">${escapeHtml(status === "in_progress" ? "running" : status)}</span>
          <div>
            <div class="office-queue-title">${escapeHtml(task.title || task.task_id || "Untitled task")}</div>
            <div class="office-queue-meta">${escapeHtml(owner)}${updated ? ` · ${escapeHtml(formatDate(updated))}` : ""}</div>
          </div>
          <code>${escapeHtml(task.task_id || "")}</code>
        </li>`;
    })
    .join("");
}

function openModal(agent) {
  state.selectedAgent = agent;
  dom.modalTitle.textContent = `Assign to ${agent.name}`;
  dom.taskTitle.value = "";
  dom.taskDetail.value = "";
  dom.taskStatus.textContent = "";
  dom.taskStatus.removeAttribute("data-kind");
  dom.modal.hidden = false;
  dom.taskTitle.focus();
}

function closeModal() {
  dom.modal.hidden = true;
  state.selectedAgent = null;
}

async function submitTask() {
  if (!state.selectedAgent) return;
  const title = dom.taskTitle.value.trim();
  const detail = dom.taskDetail.value.trim();
  if (!title) {
    dom.taskStatus.textContent = "Title is required.";
    dom.taskStatus.dataset.kind = "error";
    return;
  }
  dom.taskSubmit.disabled = true;
  dom.taskStatus.textContent = "Dispatching…";
  dom.taskStatus.dataset.kind = "";
  try {
    await fetchJson("/api/v1/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        instructions: detail,
        agent_name: state.selectedAgent.name,
        platform_user_id: state.userId,
      }),
    });
    dom.taskStatus.textContent = `Task sent to ${state.selectedAgent.name}.`;
    dom.taskStatus.dataset.kind = "ok";
    await refresh();
    setTimeout(closeModal, 700);
  } catch (error) {
    dom.taskStatus.textContent = error.message || String(error);
    dom.taskStatus.dataset.kind = "error";
  } finally {
    dom.taskSubmit.disabled = false;
  }
}

async function fetchJson(url, options = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...options };
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

function formatDate(value) {
  try { return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return String(value); }
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
