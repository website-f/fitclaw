const storageKeys = {
  userId: "fitclaw_aiops_user_id",
  displayName: "fitclaw_aiops_display_name",
  sessionId: "fitclaw_aiops_session_id",
};

const state = {
  userId: "",
  displayName: "",
  sessionId: "",
  sessions: [],
  messages: [],
  agents: [],
  modelInfo: null,
  sending: false,
  installPrompt: null,
  sidebarOpen: false,
  inspectorOpen: false,
};

const dom = {
  appShell: document.getElementById("appShell"),
  sidebar: document.getElementById("sidebar"),
  inspector: document.getElementById("inspector"),
  backdrop: document.getElementById("drawerBackdrop"),
  sessionTitle: document.getElementById("sessionTitle"),
  connectionLabel: document.getElementById("connectionLabel"),
  modelPill: document.getElementById("modelPill"),
  promptDeck: document.getElementById("promptDeck"),
  showcaseList: document.getElementById("showcaseList"),
  quickChipRow: document.getElementById("quickChipRow"),
  historyList: document.getElementById("historyList"),
  messageScroll: document.getElementById("messageScroll"),
  messageList: document.getElementById("messageList"),
  welcomeState: document.getElementById("welcomeState"),
  composerForm: document.getElementById("composerForm"),
  messageInput: document.getElementById("messageInput"),
  sendButton: document.getElementById("sendButton"),
  clearDraftButton: document.getElementById("clearDraftButton"),
  newChatButton: document.getElementById("newChatButton"),
  installButton: document.getElementById("installButton"),
  refreshHistoryButton: document.getElementById("refreshHistoryButton"),
  refreshAgentsButton: document.getElementById("refreshAgentsButton"),
  agentList: document.getElementById("agentList"),
  actionStack: document.getElementById("actionStack"),
  displayNameInput: document.getElementById("displayNameInput"),
  profileKeyInput: document.getElementById("profileKeyInput"),
  saveProfileButton: document.getElementById("saveProfileButton"),
  openSidebarButton: document.getElementById("openSidebarButton"),
  closeSidebarButton: document.getElementById("closeSidebarButton"),
  openInspectorButton: document.getElementById("openInspectorButton"),
  closeInspectorButton: document.getElementById("closeInspectorButton"),
  suggestionCount: document.getElementById("suggestionCount"),
  messageTemplate: document.getElementById("messageTemplate"),
};

window.addEventListener("load", () => {
  bindEvents();
  initializeProfile();
  registerPWA();
  void boot();
});

async function boot() {
  renderProfile();
  renderSuggestions();
  renderAgents();
  renderMessages();
  updateSessionHeader();

  await Promise.all([loadModelInfo(), loadAgents(), loadSessions()]);
  await loadCurrentSession();
  renderAll();
}

function bindEvents() {
  dom.composerForm.addEventListener("submit", onSubmitMessage);
  dom.clearDraftButton.addEventListener("click", () => {
    dom.messageInput.value = "";
    autoResizeTextarea();
    dom.messageInput.focus();
  });
  dom.newChatButton.addEventListener("click", () => {
    startNewChat(true);
  });
  dom.refreshHistoryButton.addEventListener("click", () => void loadSessions().then(renderHistory));
  dom.refreshAgentsButton.addEventListener("click", () => void refreshRuntimeData());
  dom.saveProfileButton.addEventListener("click", saveProfile);
  dom.messageInput.addEventListener("input", autoResizeTextarea);
  dom.installButton.addEventListener("click", installApp);
  dom.openSidebarButton?.addEventListener("click", () => setDrawerState("sidebar", true));
  dom.closeSidebarButton?.addEventListener("click", () => setDrawerState("sidebar", false));
  dom.openInspectorButton?.addEventListener("click", () => setDrawerState("inspector", true));
  dom.closeInspectorButton?.addEventListener("click", () => setDrawerState("inspector", false));
  dom.backdrop.addEventListener("click", () => {
    setDrawerState("sidebar", false);
    setDrawerState("inspector", false);
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.installPrompt = event;
    dom.installButton.hidden = false;
  });
  window.addEventListener("appinstalled", () => {
    state.installPrompt = null;
    dom.installButton.hidden = true;
  });
  window.addEventListener("online", updateConnectionLabel);
  window.addEventListener("offline", updateConnectionLabel);
}

function initializeProfile() {
  state.userId = localStorage.getItem(storageKeys.userId) || `web-${createId()}`;
  state.displayName = localStorage.getItem(storageKeys.displayName) || "FitClaw Operator";
  state.sessionId = localStorage.getItem(storageKeys.sessionId) || createSessionId();

  localStorage.setItem(storageKeys.userId, state.userId);
  localStorage.setItem(storageKeys.displayName, state.displayName);
  localStorage.setItem(storageKeys.sessionId, state.sessionId);
}

async function refreshRuntimeData() {
  await Promise.all([loadAgents(), loadModelInfo()]);
  renderAll();
}

async function loadModelInfo() {
  try {
    const response = await fetchJson("/api/v1/models");
    state.modelInfo = response;
  } catch (error) {
    console.error("Failed to load models", error);
  }
}

async function loadAgents() {
  try {
    state.agents = await fetchJson("/api/v1/control/agents");
  } catch (error) {
    console.error("Failed to load agents", error);
    state.agents = [];
  }
}

async function loadSessions() {
  try {
    state.sessions = await fetchJson(`/api/v1/chat/sessions?user_id=${encodeURIComponent(state.userId)}`);
  } catch (error) {
    console.error("Failed to load sessions", error);
    state.sessions = [];
  }
}

async function loadCurrentSession() {
  const currentSummary = state.sessions.find((item) => item.session_id === state.sessionId);
  if (!currentSummary && state.sessions.length > 0) {
    state.sessionId = state.sessions[0].session_id;
    persistSessionId();
  }

  if (!state.sessionId) {
    startNewChat(false);
    return;
  }

  try {
    state.messages = await fetchJson(
      `/api/v1/chat/sessions/${encodeURIComponent(state.sessionId)}/messages?user_id=${encodeURIComponent(state.userId)}`
    );
  } catch (error) {
    console.error("Failed to load session messages", error);
    state.messages = [];
  }
}

function saveProfile() {
  const nextName = dom.displayNameInput.value.trim() || "FitClaw Operator";
  const nextUserId = dom.profileKeyInput.value.trim() || state.userId;
  state.displayName = nextName;
  state.userId = nextUserId;
  localStorage.setItem(storageKeys.displayName, state.displayName);
  localStorage.setItem(storageKeys.userId, state.userId);
  startNewChat(false);
  void loadSessions().then(() => loadCurrentSession()).then(renderAll);
}

function persistSessionId() {
  localStorage.setItem(storageKeys.sessionId, state.sessionId);
}

function startNewChat(shouldFocus) {
  state.sessionId = createSessionId();
  state.messages = [];
  persistSessionId();
  renderAll();
  if (shouldFocus) {
    dom.messageInput.focus();
  }
}

async function openSession(sessionId) {
  state.sessionId = sessionId;
  persistSessionId();
  await loadCurrentSession();
  renderAll();
  setDrawerState("sidebar", false);
}

async function onSubmitMessage(event) {
  event.preventDefault();
  const text = dom.messageInput.value.trim();
  if (!text || state.sending) {
    return;
  }
  await sendMessage(text);
}

async function sendMessage(text) {
  state.sending = true;
  dom.sendButton.disabled = true;

  const now = new Date().toISOString();
  state.messages.push({
    id: `local-user-${createId()}`,
    session_id: state.sessionId,
    role: "user",
    content: text,
    created_at: now,
    attachments: [],
  });
  state.messages.push(createThinkingMessage());

  dom.messageInput.value = "";
  autoResizeTextarea();
  renderAll();
  scrollMessagesToBottom();

  try {
    const payload = {
      user_id: state.userId,
      username: state.displayName,
      session_id: state.sessionId,
      text,
    };
    const response = await fetchJson("/api/v1/chat/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    removeThinkingMessage();
    state.messages.push({
      id: `local-assistant-${createId()}`,
      session_id: response.session_id || state.sessionId,
      role: "assistant",
      content: response.reply,
      created_at: new Date().toISOString(),
      provider: response.provider,
      attachments: response.attachments || [],
      handled_as_task_command: response.handled_as_task_command,
      handled_as_agent_command: response.handled_as_agent_command,
    });

    await loadSessions();
    updateSessionHeader();
  } catch (error) {
    console.error("Send message failed", error);
    removeThinkingMessage();
    state.messages.push({
      id: `local-error-${createId()}`,
      session_id: state.sessionId,
      role: "assistant",
      content: `I could not reach the server right now.\n\n${error.message || String(error)}`,
      created_at: new Date().toISOString(),
      provider: "client-error",
      attachments: [],
    });
  } finally {
    state.sending = false;
    dom.sendButton.disabled = false;
    renderAll();
    scrollMessagesToBottom();
  }
}

function removeThinkingMessage() {
  state.messages = state.messages.filter((message) => !message.pending);
}

function createThinkingMessage() {
  return {
    id: `thinking-${createId()}`,
    role: "assistant",
    content: "",
    created_at: new Date().toISOString(),
    pending: true,
    attachments: [],
  };
}

function renderAll() {
  updateConnectionLabel();
  renderProfile();
  updateSessionHeader();
  renderHistory();
  renderSuggestions();
  renderMessages();
  renderAgents();
}

function renderProfile() {
  dom.displayNameInput.value = state.displayName;
  dom.profileKeyInput.value = state.userId;
}

function updateConnectionLabel() {
  const onlineAgents = state.agents.filter((agent) => agent.status === "online").length;
  const networkLabel = navigator.onLine ? "Connected" : "Offline shell";
  dom.connectionLabel.textContent = `${networkLabel} • ${onlineAgents} agent${onlineAgents === 1 ? "" : "s"} online`;
  if (state.modelInfo?.active) {
    dom.modelPill.textContent = `${state.modelInfo.active.provider} · ${state.modelInfo.active.model}`;
  } else {
    dom.modelPill.textContent = navigator.onLine ? "Model loading..." : "Waiting for server";
  }
}

function updateSessionHeader() {
  const currentSummary = state.sessions.find((item) => item.session_id === state.sessionId);
  const title = currentSummary?.title || deriveTitleFromMessages() || "New conversation";
  dom.sessionTitle.textContent = title;
}

function deriveTitleFromMessages() {
  const firstUser = state.messages.find((message) => message.role === "user");
  if (!firstUser) {
    return "";
  }
  return firstUser.content.replace(/\s+/g, " ").slice(0, 80);
}

function renderHistory() {
  dom.historyList.innerHTML = "";
  if (!state.sessions.length) {
    dom.historyList.innerHTML = `<div class="empty-copy">No chat history yet. Start with a suggestion or type your first message.</div>`;
    return;
  }

  state.sessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item${session.session_id === state.sessionId ? " active" : ""}`;
    button.innerHTML = `
      <strong>${escapeHtml(session.title)}</strong>
      <small>${escapeHtml(session.preview || "No preview yet")}</small>
      <small>${formatDateTime(session.last_message_at)}</small>
    `;
    button.addEventListener("click", () => void openSession(session.session_id));
    dom.historyList.appendChild(button);
  });
}

function renderSuggestions() {
  const suggestions = buildSuggestions();
  dom.suggestionCount.textContent = `${suggestions.length} ideas`;

  renderSuggestionCollection(dom.promptDeck, suggestions.slice(0, 6), "prompt-card");
  renderSuggestionCollection(dom.showcaseList, suggestions.slice(0, 3), "showcase-card");
  renderChipRow(suggestions.slice(0, 6));
  renderActionStack(suggestions.slice(0, 6));
}

function renderSuggestionCollection(container, suggestions, className) {
  container.innerHTML = "";
  suggestions.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.innerHTML = `
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.description)}</span>
      <em>${escapeHtml(item.prompt)}</em>
    `;
    button.addEventListener("click", () => void sendMessage(item.prompt));
    container.appendChild(button);
  });
}

function renderChipRow(suggestions) {
  dom.quickChipRow.innerHTML = "";
  suggestions.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.textContent = item.title;
    button.addEventListener("click", () => void sendMessage(item.prompt));
    dom.quickChipRow.appendChild(button);
  });
}

function renderActionStack(suggestions) {
  dom.actionStack.innerHTML = "";
  suggestions.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action-item";
    button.innerHTML = `<strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.description)}</small>`;
    button.addEventListener("click", () => void sendMessage(item.prompt));
    dom.actionStack.appendChild(button);
  });
}

function buildSuggestions() {
  const firstOnline = state.agents.find((agent) => agent.status === "online");
  const firstAgentName = firstOnline?.name || "office-pc";

  const suggestions = [
    {
      title: "List agents",
      description: "See every registered device and worker in one glance.",
      prompt: "list agents",
    },
    {
      title: "Verify current agent",
      description: "Confirm heartbeat, capabilities, and platform details.",
      prompt: `verify ${firstAgentName}`,
    },
    {
      title: "Capture screenshot",
      description: "Pull the current desktop view into the conversation.",
      prompt: `take a screenshot from ${firstAgentName}`,
    },
    {
      title: "Show processes",
      description: "Inspect active processes on your chosen machine.",
      prompt: `show processes on ${firstAgentName}`,
    },
    {
      title: "Show windows",
      description: "List visible windows on an online desktop agent.",
      prompt: `show windows on ${firstAgentName}`,
    },
    {
      title: "Codex in VS Code",
      description: "Send a code task to the device-side Codex runner.",
      prompt: `run this prompt inside vscode codex on ${firstAgentName} in C:\\projects\\repo: summarize the current codebase and suggest the next three fixes`,
    },
    {
      title: "Daily report",
      description: "Generate a compact operational summary for today.",
      prompt: "give me a daily health and task summary",
    },
    {
      title: "Model check",
      description: "See which active model is powering the system.",
      prompt: "what model are you using right now?",
    },
  ];

  return suggestions;
}

function renderAgents() {
  dom.agentList.innerHTML = "";
  if (!state.agents.length) {
    dom.agentList.innerHTML = `<div class="empty-copy">No agents registered yet. Install one desktop agent and it will appear here.</div>`;
    return;
  }

  state.agents.forEach((agent) => {
    const article = document.createElement("article");
    article.className = `agent-card${agent.status !== "online" ? " offline" : ""}`;
    const capabilityLine = Array.isArray(agent.capabilities_json) && agent.capabilities_json.length
      ? agent.capabilities_json.slice(0, 5).join(", ")
      : "Capabilities pending";
    article.innerHTML = `
      <strong>${escapeHtml(agent.name)}</strong>
      <div class="status-line">${escapeHtml(agent.status)}</div>
      <span>${escapeHtml(capabilityLine)}</span>
    `;
    dom.agentList.appendChild(article);
  });
}

function renderMessages() {
  dom.messageList.innerHTML = "";
  dom.welcomeState.classList.toggle("is-hidden", state.messages.length > 0);

  if (!state.messages.length) {
    return;
  }

  state.messages.forEach((message) => {
    const node = dom.messageTemplate.content.firstElementChild.cloneNode(true);
    const role = message.role === "user" ? "You" : message.pending ? "Thinking" : "FitClaw";
    node.classList.add(message.role === "user" ? "user" : "assistant");
    node.querySelector(".message-role").textContent = role;
    node.querySelector(".message-time").textContent = formatTime(message.created_at);

    const bubble = node.querySelector(".bubble");
    if (message.pending) {
      bubble.innerHTML = `<div class="thinking-bubble"><span></span><span></span><span></span></div>`;
    } else {
      bubble.textContent = message.content;
    }

    const attachmentStack = node.querySelector(".attachment-stack");
    const attachments = message.attachments || [];
    attachments.forEach((attachment) => {
      const card = document.createElement("div");
      card.className = "attachment-card";
      if (attachment.kind === "photo" && attachment.public_url) {
        card.innerHTML = `
          <img src="${attachment.public_url}" alt="${escapeHtml(attachment.caption || "Screenshot")}" loading="lazy" />
          <div class="bubble-meta">
            <span>${escapeHtml(attachment.caption || "Screenshot")}</span>
          </div>
        `;
      } else if (attachment.public_url) {
        const link = document.createElement("a");
        link.href = attachment.public_url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = attachment.filename || attachment.caption || "Open attachment";
        card.appendChild(link);
      }
      attachmentStack.appendChild(card);
    });

    dom.messageList.appendChild(node);
  });
}

function scrollMessagesToBottom() {
  requestAnimationFrame(() => {
    dom.messageScroll.scrollTop = dom.messageScroll.scrollHeight;
  });
}

function autoResizeTextarea() {
  dom.messageInput.style.height = "auto";
  dom.messageInput.style.height = `${Math.min(dom.messageInput.scrollHeight, 192)}px`;
}

function setDrawerState(target, isOpen) {
  if (window.innerWidth > 1080) {
    return;
  }

  if (target === "sidebar") {
    state.sidebarOpen = isOpen;
    dom.sidebar.classList.toggle("open", isOpen);
  }
  if (target === "inspector") {
    state.inspectorOpen = isOpen;
    dom.inspector.classList.toggle("open", isOpen);
  }

  const anyOpen = state.sidebarOpen || state.inspectorOpen;
  dom.backdrop.hidden = !anyOpen;
}

async function installApp() {
  if (!state.installPrompt) {
    return;
  }
  await state.installPrompt.prompt();
  await state.installPrompt.userChoice;
  state.installPrompt = null;
  dom.installButton.hidden = true;
}

function registerPWA() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/app-sw.js", { scope: "/" }).catch((error) => {
      console.error("Service worker registration failed", error);
    });
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return await response.json();
}

function createSessionId() {
  return `web:${state.userId}:${createId()}`;
}

function createId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatTime(value) {
  if (!value) {
    return "now";
  }
  try {
    return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "now";
  }
}

function formatDateTime(value) {
  if (!value) {
    return "recently";
  }
  try {
    return new Date(value).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "recently";
  }
}
