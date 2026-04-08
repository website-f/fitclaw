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
  pendingUploads: [],
  modelInfo: null,
  selectedModelKey: "",
  modelSwitching: false,
  modelSwitchTarget: null,
  agentSaveState: {},
  sending: false,
  installPrompt: null,
  sidebarOpen: false,
  inspectorOpen: false,
  historyPage: 0,
  historyPageSize: 8,
};

const dom = {
  appShell: document.getElementById("appShell"),
  sidebar: document.getElementById("sidebar"),
  inspector: document.getElementById("inspector"),
  backdrop: document.getElementById("drawerBackdrop"),
  inspectorFab: document.getElementById("inspectorFab"),
  modelSwitchModal: document.getElementById("modelSwitchModal"),
  modelSwitchTitle: document.getElementById("modelSwitchTitle"),
  modelSwitchDetail: document.getElementById("modelSwitchDetail"),
  sessionTitle: document.getElementById("sessionTitle"),
  connectionLabel: document.getElementById("connectionLabel"),
  modelPill: document.getElementById("modelPill"),
  promptDeck: document.getElementById("promptDeck"),
  showcaseList: document.getElementById("showcaseList"),
  quickChipRow: document.getElementById("quickChipRow"),
  uploadTray: document.getElementById("uploadTray"),
  historyList: document.getElementById("historyList"),
  messageScroll: document.getElementById("messageScroll"),
  messageList: document.getElementById("messageList"),
  welcomeState: document.getElementById("welcomeState"),
  composerForm: document.getElementById("composerForm"),
  filePicker: document.getElementById("filePicker"),
  messageInput: document.getElementById("messageInput"),
  attachButton: document.getElementById("attachButton"),
  sendButton: document.getElementById("sendButton"),
  clearDraftButton: document.getElementById("clearDraftButton"),
  newChatButton: document.getElementById("newChatButton"),
  installButton: document.getElementById("installButton"),
  refreshHistoryButton: document.getElementById("refreshHistoryButton"),
  refreshAgentsButton: document.getElementById("refreshAgentsButton"),
  refreshModelsButton: document.getElementById("refreshModelsButton"),
  agentList: document.getElementById("agentList"),
  modelSummary: document.getElementById("modelSummary"),
  modelSelect: document.getElementById("modelSelect"),
  applyModelButton: document.getElementById("applyModelButton"),
  modelDetails: document.getElementById("modelDetails"),
  modelList: document.getElementById("modelList"),
  actionStack: document.getElementById("actionStack"),
  displayNameInput: document.getElementById("displayNameInput"),
  profileKeyInput: document.getElementById("profileKeyInput"),
  saveProfileButton: document.getElementById("saveProfileButton"),
  openSidebarButton: document.getElementById("openSidebarButton"),
  closeSidebarButton: document.getElementById("closeSidebarButton"),
  closeInspectorButton: document.getElementById("closeInspectorButton"),
  suggestionCount: document.getElementById("suggestionCount"),
  messageTemplate: document.getElementById("messageTemplate"),
  historyFooter: document.getElementById("historyFooter"),
  historyPrevButton: document.getElementById("historyPrevButton"),
  historyNextButton: document.getElementById("historyNextButton"),
  historyPageLabel: document.getElementById("historyPageLabel"),
  clearAllHistoryButton: document.getElementById("clearAllHistoryButton"),
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
  scrollMessagesToBottom();
}

function bindEvents() {
  dom.composerForm.addEventListener("submit", onSubmitMessage);
  dom.clearDraftButton.addEventListener("click", clearComposerDraft);
  dom.attachButton.addEventListener("click", () => dom.filePicker.click());
  dom.filePicker.addEventListener("change", onFileSelection);
  dom.newChatButton.addEventListener("click", () => startNewChat(true));
  dom.refreshHistoryButton.addEventListener("click", (e) => {
    e.stopPropagation();
    void loadSessions().then(renderHistory);
  });
  dom.refreshAgentsButton.addEventListener("click", () => void refreshRuntimeData());
  dom.refreshModelsButton.addEventListener("click", () => void loadModelInfo().then(renderModelLibrary));
  dom.modelSelect.addEventListener("change", onModelSelectChange);
  dom.applyModelButton.addEventListener("click", () => void applySelectedModel());
  dom.saveProfileButton.addEventListener("click", saveProfile);
  dom.messageInput.addEventListener("input", autoResizeTextarea);
  dom.messageInput.addEventListener("keydown", onComposerKeyDown);
  dom.installButton.addEventListener("click", installApp);

  // History pagination & clear
  dom.historyPrevButton.addEventListener("click", () => { state.historyPage = Math.max(0, state.historyPage - 1); renderHistory(); });
  dom.historyNextButton.addEventListener("click", () => { state.historyPage += 1; renderHistory(); });
  dom.clearAllHistoryButton.addEventListener("click", () => void clearAllHistory());

  // Sidebar toggle (works at all screen sizes)
  dom.openSidebarButton.addEventListener("click", () => toggleDrawer("sidebar"));
  dom.closeSidebarButton.addEventListener("click", () => closeDrawer("sidebar"));

  // Inspector via FAB
  dom.inspectorFab.addEventListener("click", () => toggleDrawer("inspector"));
  dom.closeInspectorButton.addEventListener("click", () => closeDrawer("inspector"));

  // Backdrop
  dom.backdrop.addEventListener("click", closeAllDrawers);

  // Collapsible nav sections
  document.querySelectorAll(".nav-section-toggle").forEach((toggle) => {
    toggle.addEventListener("click", onNavSectionToggle);
  });

  // PWA install
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

  // Visual viewport for mobile keyboard
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", () => {
      document.documentElement.style.setProperty("--vvh", `${window.visualViewport.height}px`);
    });
    document.documentElement.style.setProperty("--vvh", `${window.visualViewport.height}px`);
  }
}

/* ─── Drawer management ─── */
function toggleDrawer(target) {
  if (target === "sidebar") {
    state.sidebarOpen ? closeDrawer("sidebar") : openDrawer("sidebar");
  } else {
    state.inspectorOpen ? closeDrawer("inspector") : openDrawer("inspector");
  }
}

function openDrawer(target) {
  // Close the other drawer first
  if (target === "sidebar" && state.inspectorOpen) closeDrawer("inspector");
  if (target === "inspector" && state.sidebarOpen) closeDrawer("sidebar");

  if (target === "sidebar") {
    state.sidebarOpen = true;
    dom.sidebar.classList.add("open");
  } else {
    state.inspectorOpen = true;
    dom.inspector.classList.add("open");
    dom.inspectorFab.classList.add("active");
  }
  dom.backdrop.hidden = false;
}

function closeDrawer(target) {
  if (target === "sidebar") {
    state.sidebarOpen = false;
    dom.sidebar.classList.remove("open");
  } else {
    state.inspectorOpen = false;
    dom.inspector.classList.remove("open");
    dom.inspectorFab.classList.remove("active");
  }
  if (!state.sidebarOpen && !state.inspectorOpen) {
    dom.backdrop.hidden = true;
  }
}

function closeAllDrawers() {
  closeDrawer("sidebar");
  closeDrawer("inspector");
}

/* ─── Collapsible nav sections ─── */
function onNavSectionToggle(event) {
  // Don't collapse if click was on a nested button (like Refresh)
  if (event.target.closest(".nav-action")) return;

  const toggle = event.currentTarget;
  const section = toggle.dataset.section;
  const body = document.getElementById(`${section}Body`);
  if (!body) return;

  const isOpen = body.classList.contains("open");
  body.classList.toggle("open", !isOpen);
  toggle.setAttribute("aria-expanded", String(!isOpen));
}

/* ─── Profile ─── */
function initializeProfile() {
  state.userId = localStorage.getItem(storageKeys.userId) || `web-${createId()}`;
  state.displayName = localStorage.getItem(storageKeys.displayName) || "FitClaw Operator";
  state.sessionId = localStorage.getItem(storageKeys.sessionId) || createSessionId();

  localStorage.setItem(storageKeys.userId, state.userId);
  localStorage.setItem(storageKeys.displayName, state.displayName);
  localStorage.setItem(storageKeys.sessionId, state.sessionId);
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

/* ─── Session management ─── */
function startNewChat(shouldFocus) {
  state.sessionId = createSessionId();
  state.messages = [];
  resetPendingUploads();
  persistSessionId();
  renderAll();
  closeDrawer("sidebar");
  if (shouldFocus) dom.messageInput.focus();
}

async function openSession(sessionId) {
  resetPendingUploads();
  state.sessionId = sessionId;
  persistSessionId();
  await loadCurrentSession();
  renderAll();
  scrollMessagesToBottom();
  closeDrawer("sidebar");
}

/* ─── Data loading ─── */
async function refreshRuntimeData() {
  await Promise.all([loadAgents(), loadModelInfo()]);
  renderAll();
}

async function loadModelInfo() {
  try {
    const response = await fetchJson("/api/v1/models");
    state.modelInfo = response;
    const active = response?.active;
    state.selectedModelKey = active ? `${active.provider}::${active.model}` : "";
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

/* ─── Composer ─── */
function clearComposerDraft() {
  dom.messageInput.value = "";
  resetPendingUploads();
  autoResizeTextarea();
  renderAll();
  dom.messageInput.focus();
}

function onComposerKeyDown(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  void submitComposerMessage();
}

async function onFileSelection(event) {
  const files = Array.from(event.target.files || []);
  dom.filePicker.value = "";
  if (!files.length) return;
  await uploadSelectedFiles(files);
}

async function onSubmitMessage(event) {
  event.preventDefault();
  await submitComposerMessage();
}

async function submitComposerMessage() {
  const text = dom.messageInput.value.trim();
  const readyUploads = state.pendingUploads.filter((item) => item.status === "ready");
  const hasUploadingFiles = state.pendingUploads.some((item) => item.status === "uploading");
  if (state.sending || hasUploadingFiles) return;
  if (!text && !readyUploads.length) return;
  await sendMessage(text, readyUploads);
}

async function sendMessage(text, attachments = []) {
  state.sending = true;
  dom.sendButton.disabled = true;

  const now = new Date().toISOString();
  const normalizedText = (text || "").trim();
  const outboundAttachments = attachments.map((item) => ({ ...item }));
  if (outboundAttachments.length) {
    state.pendingUploads = state.pendingUploads.filter((item) => !outboundAttachments.some((upload) => upload.localId === item.localId));
  }
  state.messages.push({
    id: `local-user-${createId()}`,
    session_id: state.sessionId,
    role: "user",
    content: normalizedText,
    created_at: now,
    attachments: outboundAttachments.map(toChatAttachment),
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
      text: normalizedText,
      attachment_asset_ids: outboundAttachments.map((item) => item.asset_id).filter(Boolean),
    };
    const response = await fetchJson("/api/v1/chat/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    removeThinkingMessage();
    state.sessionId = response.session_id || state.sessionId;
    persistSessionId();
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

    releaseUploadPreviews(outboundAttachments);
    await loadSessions();
    updateSessionHeader();
  } catch (error) {
    console.error("Send message failed", error);
    removeThinkingMessage();
    state.pendingUploads = [...outboundAttachments, ...state.pendingUploads];
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

/* ─── Rendering ─── */
function renderAll() {
  updateConnectionLabel();
  renderModelSwitchModal();
  renderProfile();
  updateSessionHeader();
  renderHistory();
  renderSuggestions();
  renderUploadTray();
  renderMessages();
  renderAgents();
  renderModelLibrary();
}

function renderProfile() {
  dom.displayNameInput.value = state.displayName;
  dom.profileKeyInput.value = state.userId;
}

function updateConnectionLabel() {
  const onlineAgents = state.agents.filter((agent) => agent.status === "online").length;
  const networkLabel = navigator.onLine ? "Connected" : "Offline shell";
  dom.connectionLabel.textContent = `${networkLabel} | ${onlineAgents} agent${onlineAgents === 1 ? "" : "s"} online`;
  if (state.modelInfo?.active) {
    dom.modelPill.textContent = `${state.modelInfo.active.provider} / ${state.modelInfo.active.model}`;
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
  if (!firstUser) return "";
  return firstUser.content.replace(/\s+/g, " ").slice(0, 80);
}

function renderHistory() {
  dom.historyList.innerHTML = "";

  if (!state.sessions.length) {
    dom.historyList.innerHTML = `<div class="empty-copy">No chat history yet.</div>`;
    dom.historyFooter.hidden = true;
    return;
  }

  const total = state.sessions.length;
  const pageSize = state.historyPageSize;
  const totalPages = Math.ceil(total / pageSize);
  state.historyPage = Math.min(state.historyPage, totalPages - 1);
  const start = state.historyPage * pageSize;
  const pageItems = state.sessions.slice(start, start + pageSize);

  pageItems.forEach((session) => {
    const row = document.createElement("div");
    row.className = `history-item${session.session_id === state.sessionId ? " active" : ""}`;

    const body = document.createElement("button");
    body.type = "button";
    body.className = "history-item-body";
    body.innerHTML = `<strong>${escapeHtml(session.title)}</strong><small>${escapeHtml(formatDateTime(session.last_message_at))}</small>`;
    body.addEventListener("click", () => void openSession(session.session_id));

    const del = document.createElement("button");
    del.type = "button";
    del.className = "history-delete";
    del.setAttribute("aria-label", "Delete chat");
    del.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`;
    del.addEventListener("click", (e) => { e.stopPropagation(); void deleteSession(session.session_id); });

    row.appendChild(body);
    row.appendChild(del);
    dom.historyList.appendChild(row);
  });

  // Pagination footer
  dom.historyFooter.hidden = false;
  dom.historyPrevButton.disabled = state.historyPage <= 0;
  dom.historyNextButton.disabled = state.historyPage >= totalPages - 1;
  dom.historyPageLabel.textContent = `${state.historyPage + 1}/${totalPages}`;
}

async function deleteSession(sessionId) {
  if (!confirm("Delete this chat?")) return;
  try {
    await fetchJson(`/api/v1/chat/sessions/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(state.userId)}`, { method: "DELETE" });
  } catch (error) {
    console.error("Delete session failed", error);
  }
  if (sessionId === state.sessionId) startNewChat(false);
  await loadSessions();
  renderHistory();
  updateSessionHeader();
}

async function clearAllHistory() {
  if (!confirm("Clear all chat history? This cannot be undone.")) return;
  try {
    await fetchJson(`/api/v1/chat/sessions?user_id=${encodeURIComponent(state.userId)}`, { method: "DELETE" });
  } catch (error) {
    console.error("Clear history failed", error);
  }
  state.historyPage = 0;
  startNewChat(false);
  await loadSessions();
  renderAll();
}

function renderSuggestions() {
  const suggestions = buildSuggestions();
  dom.suggestionCount.textContent = String(suggestions.length);

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
    button.addEventListener("click", () => void runSuggestion(item));
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
    button.addEventListener("click", () => void runSuggestion(item));
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
    button.addEventListener("click", () => void runSuggestion(item));
    dom.actionStack.appendChild(button);
  });
}

function runSuggestion(item) {
  const attachments = item.useAttachments
    ? state.pendingUploads.filter((upload) => upload.status === "ready")
    : [];
  if (item.useAttachments && !attachments.length) {
    dom.messageInput.focus();
    return Promise.resolve();
  }
  return sendMessage(item.prompt, attachments);
}

function buildSuggestions() {
  const firstOnline = state.agents.find((agent) => agent.status === "online");
  const firstAgentName = firstOnline?.name || "office-pc";

  const suggestions = [];
  if (state.pendingUploads.length) {
    suggestions.push(
      {
        title: "Describe upload",
        description: "Analyze the file or image currently attached in the composer.",
        prompt: "Describe this clearly and call out the important details.",
        useAttachments: true,
      },
      {
        title: "Summarize file",
        description: "Pull out the main points, actions, and risks from the uploaded file.",
        prompt: "Summarize this file and highlight any risks or next actions.",
        useAttachments: true,
      },
      {
        title: "Edit image",
        description: "Apply a quick deterministic image edit to the attached asset.",
        prompt: "Remove background and keep the subject clean.",
        useAttachments: true,
      },
      {
        title: "Rewrite file",
        description: "Create an edited version of the uploaded text document.",
        prompt: "Rewrite this file to be clearer and more concise.",
        useAttachments: true,
      }
    );
  }

  suggestions.push(
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
      title: "Check storage",
      description: "Inspect current disk usage and the biggest folders/files on that device.",
      prompt: `check storage on ${firstAgentName} and list top 10 biggest folders and files`,
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
    }
  );

  return suggestions;
}

function renderAgents() {
  dom.agentList.innerHTML = "";
  if (!state.agents.length) {
    dom.agentList.innerHTML = `<div class="empty-copy">No agents registered yet.</div>`;
    return;
  }

  const allModels = getAllModelChoices();
  const visionModels = allModels.filter((item) => item.modality === "vision" || item.provider === "gemini");

  state.agents.forEach((agent) => {
    const article = document.createElement("article");
    article.className = `agent-card${agent.status !== "online" ? " offline" : ""}`;
    const capabilityLine = Array.isArray(agent.capabilities_json) && agent.capabilities_json.length
      ? agent.capabilities_json.slice(0, 5).join(", ")
      : "Capabilities pending";
    const preferences = agent.model_preferences || {};
    const preferredText = preferences.preferred_text
      ? `${preferences.preferred_text.provider} / ${preferences.preferred_text.model}`
      : "runtime default";
    const preferredVision = preferences.preferred_vision
      ? `${preferences.preferred_vision.provider} / ${preferences.preferred_vision.model}`
      : "runtime vision default";
    const allowedPool = Array.isArray(preferences.allowed_models) && preferences.allowed_models.length
      ? preferences.allowed_models.map((item) => `${item.provider} / ${item.model}`).join(", ")
      : "All configured models";

    const head = document.createElement("div");
    head.className = "agent-head";
    head.innerHTML = `
      <strong>${escapeHtml(agent.name)}</strong>
      <div class="status-line">${escapeHtml(agent.status)}</div>
      <div class="agent-capability-line">${escapeHtml(capabilityLine)}</div>
      <div class="agent-model-summary">Text: ${escapeHtml(preferredText)}</div>
      <div class="agent-model-summary">Vision: ${escapeHtml(preferredVision)}</div>
      <div class="agent-model-summary">Allowed: ${escapeHtml(allowedPool)}</div>
    `;
    article.appendChild(head);

    if (allModels.length) {
      const editor = document.createElement("div");
      editor.className = "agent-model-editor";

      const row = document.createElement("div");
      row.className = "agent-model-row";

      const textField = document.createElement("label");
      textField.className = "field compact-field";
      textField.innerHTML = "<span>Preferred text model</span>";
      const textSelect = document.createElement("select");
      appendModelOptions(textSelect, allModels, buildModelRefKey(preferences.preferred_text), true, "Use runtime default");
      textField.appendChild(textSelect);

      const visionField = document.createElement("label");
      visionField.className = "field compact-field";
      visionField.innerHTML = "<span>Preferred vision model</span>";
      const visionSelect = document.createElement("select");
      appendModelOptions(visionSelect, visionModels, buildModelRefKey(preferences.preferred_vision), true, "Use vision default");
      visionField.appendChild(visionSelect);

      const allowedField = document.createElement("label");
      allowedField.className = "field compact-field";
      allowedField.innerHTML = "<span>Allowed models for this agent</span>";
      const allowedSelect = document.createElement("select");
      allowedSelect.className = "agent-multi-select";
      allowedSelect.multiple = true;
      const allowedKeys = new Set((preferences.allowed_models || []).map((item) => buildModelRefKey(item)));
      appendModelOptions(allowedSelect, allModels, "", false, "");
      Array.from(allowedSelect.options).forEach((option) => {
        option.selected = allowedKeys.has(option.value);
      });
      allowedField.appendChild(allowedSelect);

      row.appendChild(textField);
      row.appendChild(visionField);
      row.appendChild(allowedField);
      editor.appendChild(row);

      const actions = document.createElement("div");
      actions.className = "agent-model-actions";
      const saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.className = "ghost-button";
      saveButton.textContent = state.agentSaveState[agent.name] ? "Saving..." : "Save agent models";
      saveButton.disabled = Boolean(state.agentSaveState[agent.name]);
      saveButton.addEventListener("click", () => void saveAgentModelPreferences(
        agent.name,
        textSelect.value,
        visionSelect.value,
        Array.from(allowedSelect.selectedOptions).map((option) => option.value),
      ));
      actions.appendChild(saveButton);
      editor.appendChild(actions);

      article.appendChild(editor);
    }

    dom.agentList.appendChild(article);
  });
}

function renderModelLibrary() {
  dom.modelList.innerHTML = "";

  const modelInfo = state.modelInfo;
  if (!modelInfo) {
    dom.modelSummary.textContent = "Loading available models...";
    return;
  }

  const active = modelInfo.active
    ? `${modelInfo.active.provider} / ${modelInfo.active.model}`
    : "No active model selected";
  const installedCount = Array.isArray(modelInfo.installed_ollama_models)
    ? modelInfo.installed_ollama_models.length
    : 0;
  dom.modelSummary.textContent = `Active: ${active}. Local installed: ${installedCount}. Choose a profile below, then switch.`;

  const allModels = getAllModelChoices();
  if (!allModels.length) {
    dom.modelSelect.innerHTML = "";
    dom.applyModelButton.disabled = true;
    dom.modelDetails.innerHTML = "";
    return;
  }

  if (!findModelOptionByKey(state.selectedModelKey)) {
    const activeKey = modelInfo.active ? buildModelRefKey(modelInfo.active) : "";
    state.selectedModelKey = activeKey || buildModelRefKey(allModels[0]);
  }

  appendModelOptions(dom.modelSelect, allModels, state.selectedModelKey, false, "");
  dom.modelSelect.disabled = state.modelSwitching;
  dom.applyModelButton.disabled = state.modelSwitching || !state.selectedModelKey;
  dom.applyModelButton.textContent = state.modelSwitching ? "Switching..." : "Switch";
  renderSelectedModelDetails();

  const sections = new Map();
  allModels.forEach((item) => {
    const key = item.role_group_label || "General";
    if (!sections.has(key)) sections.set(key, []);
    sections.get(key).push(item);
  });

  sections.forEach((items, title) => {
    const group = document.createElement("section");
    group.className = "model-group";

    const heading = document.createElement("div");
    heading.className = "model-group-title";
    heading.textContent = title;
    group.appendChild(heading);

    items.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `model-item${item.active ? " active" : ""}`;
      button.disabled = state.modelSwitching;

      const tags = [];
      if (item.active) tags.push("active");
      if (item.installed && item.provider === "ollama") tags.push("installed");
      else if (!item.installed && item.provider === "ollama") tags.push("auto-pull");
      if (item.configured) tags.push("configured");
      if (item.recommended) tags.push("recommended");
      if (item.source === "cloud") tags.push("cloud");

      button.innerHTML = `
        <div class="model-item-main">
          <strong>${escapeHtml(item.label || item.model)}</strong>
          <span>${escapeHtml(`${item.provider} · ${item.summary}`)}</span>
        </div>
        <div class="model-badges">${tags.map((tag) => `<span class="model-badge">${escapeHtml(tag)}</span>`).join("")}</div>
      `;
      button.addEventListener("click", () => void selectModel(item.provider, item.model));
      group.appendChild(button);
    });

    dom.modelList.appendChild(group);
  });
}

function onModelSelectChange() {
  state.selectedModelKey = dom.modelSelect.value;
  renderSelectedModelDetails();
  renderModelLibrary();
}

async function applySelectedModel() {
  const selected = parseModelRefKey(state.selectedModelKey);
  if (!selected) return;
  await selectModel(selected.provider, selected.model);
}

async function selectModel(provider, model) {
  if (state.modelSwitching) return;
  if (state.modelInfo?.active?.provider === provider && state.modelInfo?.active?.model === model) {
    state.selectedModelKey = `${provider}::${model}`;
    renderModelLibrary();
    return;
  }

  state.modelSwitching = true;
  state.selectedModelKey = `${provider}::${model}`;
  state.modelSwitchTarget = { provider, model };
  dom.modelSummary.textContent = `Switching to ${provider} / ${model}...`;
  dom.modelPill.textContent = `Switching to ${provider} / ${model}...`;
  renderModelLibrary();
  renderModelSwitchModal();

  try {
    await fetchJson("/api/v1/models/select", {
      method: "POST",
      body: JSON.stringify({ provider, model, auto_pull: true }),
    });
    await loadModelInfo();
    renderAll();
  } catch (error) {
    console.error("Model switch failed", error);
    dom.modelSummary.textContent = `Model switch failed: ${error.message || String(error)}`;
    await loadModelInfo();
    updateConnectionLabel();
  } finally {
    state.modelSwitching = false;
    state.modelSwitchTarget = null;
    renderModelSwitchModal();
    renderModelLibrary();
  }
}

function renderModelSwitchModal() {
  const isOpen = Boolean(state.modelSwitching && state.modelSwitchTarget);
  dom.modelSwitchModal.hidden = !isOpen;
  document.body.classList.toggle("modal-open", isOpen);

  if (!isOpen) {
    return;
  }

  const item = findModelOptionByKey(buildModelRefKey(state.modelSwitchTarget));
  const label = item?.label || state.modelSwitchTarget.model;
  const provider = state.modelSwitchTarget.provider;
  const detailBits = [];

  if (item?.summary) {
    detailBits.push(item.summary);
  }
  if (provider === "ollama" && !item?.installed) {
    detailBits.push("This model is not local yet, so Ollama may need a moment to pull or warm it.");
  } else {
    detailBits.push("Please wait while the next model is loaded and warmed up.");
  }

  dom.modelSwitchTitle.textContent = `Switching to ${label}`;
  dom.modelSwitchDetail.textContent = detailBits.join(" ");
}

function renderSelectedModelDetails() {
  const item = findModelOptionByKey(state.selectedModelKey);
  if (!item) {
    dom.modelDetails.innerHTML = "";
    return;
  }

  const badges = [
    item.family,
    item.role_group_label,
    item.speed,
    item.source,
    item.resource_tier,
    ...(item.roles || []),
  ].filter(Boolean);

  dom.modelDetails.innerHTML = `
    <strong>${escapeHtml(item.label || item.model)}</strong>
    <p>${escapeHtml(item.summary || item.model)}</p>
    <div class="model-details-meta">
      ${badges.map((badge) => `<span class="model-badge">${escapeHtml(badge)}</span>`).join("")}
      ${item.cloud_auth_required ? `<span class="model-badge">requires Ollama cloud auth</span>` : ""}
      ${item.installed ? `<span class="model-badge">installed</span>` : ""}
      ${item.provider === "ollama" && !item.installed ? `<span class="model-badge">auto-pull on switch</span>` : ""}
    </div>
  `;
}

function getAllModelChoices() {
  if (!state.modelInfo) return [];
  return [...(state.modelInfo.ollama_choices || []), ...(state.modelInfo.gemini_choices || [])];
}

function appendModelOptions(selectNode, items, selectedKey, includeBlank, blankLabel) {
  selectNode.innerHTML = "";
  if (includeBlank) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = blankLabel || "None";
    selectNode.appendChild(option);
  }
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = buildModelRefKey(item);
    option.textContent = buildModelOptionLabel(item);
    option.selected = option.value === selectedKey;
    selectNode.appendChild(option);
  });
}

function buildModelOptionLabel(item) {
  const name = item.label || item.model;
  const role = item.role_group_label || item.role_group || "General";
  return `${name} · ${role} · ${item.provider}`;
}

function buildModelRefKey(modelRef) {
  if (!modelRef || !modelRef.provider || !modelRef.model) return "";
  return `${modelRef.provider}::${modelRef.model}`;
}

function parseModelRefKey(value) {
  if (!value || !value.includes("::")) return null;
  const [provider, ...rest] = value.split("::");
  const model = rest.join("::");
  if (!provider || !model) return null;
  return { provider, model };
}

function findModelOptionByKey(key) {
  if (!key) return null;
  return getAllModelChoices().find((item) => buildModelRefKey(item) === key) || null;
}

async function saveAgentModelPreferences(agentName, preferredTextKey, preferredVisionKey, allowedKeys) {
  state.agentSaveState[agentName] = true;
  renderAgents();

  const payload = {
    preferred_text: parseModelRefKey(preferredTextKey),
    preferred_vision: parseModelRefKey(preferredVisionKey),
    allowed_models: allowedKeys.map(parseModelRefKey).filter(Boolean),
  };

  try {
    const updated = await fetchJson(`/api/v1/agents/${encodeURIComponent(agentName)}/models`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    state.agents = state.agents.map((agent) => agent.name === agentName ? updated : agent);
  } catch (error) {
    console.error("Failed to save agent model preferences", error);
    alert(`Failed to save agent model preferences for ${agentName}: ${error.message || String(error)}`);
  } finally {
    state.agentSaveState[agentName] = false;
    renderAgents();
  }
}

function renderUploadTray() {
  dom.uploadTray.innerHTML = "";
  state.pendingUploads.forEach((upload) => {
    const card = document.createElement("article");
    card.className = `upload-pill${upload.status === "uploading" ? " uploading" : ""}${upload.status === "error" ? " error" : ""}`;

    const thumb = document.createElement("div");
    thumb.className = "upload-thumb";
    if (upload.preview_url && upload.kind === "image") {
      const image = document.createElement("img");
      image.src = upload.preview_url;
      image.alt = upload.original_filename || "Uploaded image";
      image.loading = "lazy";
      thumb.appendChild(image);
    } else {
      const label = document.createElement("span");
      label.textContent = upload.kind === "image" ? "IMG" : "FILE";
      thumb.appendChild(label);
    }

    const meta = document.createElement("div");
    meta.className = "upload-meta";
    meta.innerHTML = `
      <strong>${escapeHtml(upload.original_filename || "Attachment")}</strong>
      <span>${escapeHtml(describeUploadStatus(upload))}</span>
    `;

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "upload-remove";
    removeButton.textContent = "x";
    removeButton.disabled = upload.status === "uploading";
    removeButton.setAttribute("aria-label", `Remove ${upload.original_filename || "attachment"}`);
    removeButton.addEventListener("click", () => removePendingUpload(upload.localId));

    card.appendChild(thumb);
    card.appendChild(meta);
    card.appendChild(removeButton);
    dom.uploadTray.appendChild(card);
  });
}

function renderMessages() {
  dom.messageList.innerHTML = "";
  dom.welcomeState.classList.toggle("is-hidden", state.messages.length > 0);

  if (!state.messages.length) return;

  state.messages.forEach((message) => {
    const node = dom.messageTemplate.content.firstElementChild.cloneNode(true);
    const role = message.role === "user" ? "You" : message.pending ? "Thinking" : "FitClaw";
    node.classList.add(message.role === "user" ? "user" : "assistant");
    node.querySelector(".message-role").textContent = role;
    node.querySelector(".message-time").textContent = formatTime(message.created_at);

    const bubble = node.querySelector(".bubble");
    const attachments = message.attachments || [];
    if (message.pending) {
      bubble.innerHTML = `<div class="thinking-bubble"><span></span><span></span><span></span></div>`;
    } else if (!message.content && attachments.length) {
      bubble.classList.add("is-hidden");
    } else {
      bubble.textContent = message.content;
    }

    const attachmentStack = node.querySelector(".attachment-stack");
    attachments.forEach((attachment) => {
      const card = document.createElement("div");
      card.className = "attachment-card";
      const attachmentKind = String(attachment.kind || "document").toLowerCase();
      if ((attachmentKind === "photo" || attachmentKind === "image") && attachment.public_url) {
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
      } else {
        card.innerHTML = `<div class="attachment-label">${escapeHtml(attachment.filename || attachment.caption || "Attachment ready")}</div>`;
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

/* ─── PWA ─── */
async function installApp() {
  if (!state.installPrompt) return;
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

/* ─── Upload handling ─── */
async function uploadSelectedFiles(files) {
  const placeholders = files.map((file) => createUploadPlaceholder(file));
  state.pendingUploads.push(...placeholders);
  renderAll();

  await Promise.all(
    placeholders.map((placeholder, index) =>
      uploadSingleFile(files[index], placeholder.localId)
    )
  );
  renderAll();
}

async function uploadSingleFile(file, localId) {
  const formData = new FormData();
  formData.append("user_id", state.userId);
  formData.append("session_id", state.sessionId);
  formData.append("file", file, file.name);

  try {
    const response = await fetchJson("/api/v1/uploads", {
      method: "POST",
      body: formData,
    });
    replacePendingUpload(localId, {
      ...response,
      localId,
      status: "ready",
      preview_url: state.pendingUploads.find((item) => item.localId === localId)?.preview_url || null,
    });
  } catch (error) {
    replacePendingUpload(localId, {
      status: "error",
      error: error.message || String(error),
    });
  }
  renderAll();
}

function createUploadPlaceholder(file) {
  return {
    localId: `upload-${createId()}`,
    asset_id: null,
    kind: file.type.startsWith("image/") ? "image" : "document",
    original_filename: file.name,
    mime_type: file.type || "application/octet-stream",
    size_bytes: file.size,
    public_url: null,
    preview_url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
    status: "uploading",
    error: "",
  };
}

function replacePendingUpload(localId, nextValues) {
  state.pendingUploads = state.pendingUploads.map((item) => {
    if (item.localId !== localId) return item;
    return { ...item, ...nextValues };
  });
}

function removePendingUpload(localId) {
  const match = state.pendingUploads.find((item) => item.localId === localId);
  if (match?.preview_url) URL.revokeObjectURL(match.preview_url);
  state.pendingUploads = state.pendingUploads.filter((item) => item.localId !== localId);
  renderAll();
}

function resetPendingUploads() {
  releaseUploadPreviews(state.pendingUploads);
  state.pendingUploads = [];
  dom.filePicker.value = "";
}

function releaseUploadPreviews(uploads) {
  uploads.forEach((item) => {
    if (item.preview_url) URL.revokeObjectURL(item.preview_url);
  });
}

function toChatAttachment(upload) {
  return {
    kind: upload.kind === "image" ? "image" : "document",
    caption: upload.original_filename,
    filename: upload.original_filename,
    public_url: upload.public_url || upload.preview_url || null,
  };
}

function describeUploadStatus(upload) {
  if (upload.status === "uploading") return `Uploading ${formatBytes(upload.size_bytes || 0)}...`;
  if (upload.status === "error") return upload.error || "Upload failed";
  return `${upload.kind === "image" ? "Image" : "File"} | ${formatBytes(upload.size_bytes || 0)}`;
}

/* ─── Network ─── */
async function fetchJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return await response.json();
}

/* ─── Utilities ─── */
function createSessionId() {
  return `web:${state.userId}:${createId()}`;
}

function createId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
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
  if (!value) return "now";
  try { return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return "now"; }
}

function formatDateTime(value) {
  if (!value) return "recently";
  try {
    return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return "recently"; }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const decimals = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(decimals)} ${units[unitIndex]}`;
}
