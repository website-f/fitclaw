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
  appVersion: "",
  selectedModelKey: "",
  modelSwitching: false,
  modelSwitchTarget: null,
  agentSaveState: {},
  sending: false,
  installPrompt: null,
  installContext: "none",
  sidebarOpen: false,
  inspectorOpen: false,
  composerFocused: false,
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
  installHelpModal: document.getElementById("installHelpModal"),
  installHelpTitle: document.getElementById("installHelpTitle"),
  installHelpText: document.getElementById("installHelpText"),
  installHelpSteps: document.getElementById("installHelpSteps"),
  installHelpPrimaryButton: document.getElementById("installHelpPrimaryButton"),
  installHelpDismissButton: document.getElementById("installHelpDismissButton"),
  sessionTitle: document.getElementById("sessionTitle"),
  connectionLabel: document.getElementById("connectionLabel"),
  topbarNewChatButton: document.getElementById("topbarNewChatButton"),
  deleteChatButton: document.getElementById("deleteChatButton"),
  promptDeck: document.getElementById("promptDeck"),
  quickChipRow: document.getElementById("quickChipRow"),
  uploadTray: document.getElementById("uploadTray"),
  historyList: document.getElementById("historyList"),
  messageScroll: document.getElementById("messageScroll"),
  messageList: document.getElementById("messageList"),
  welcomeState: document.getElementById("welcomeState"),
  composerWrap: document.querySelector(".composer-wrap"),
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

  await Promise.all([loadAppMeta(), loadModelInfo(), loadAgents(), loadSessions()]);
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
  dom.topbarNewChatButton.addEventListener("click", () => startNewChat(true));
  dom.deleteChatButton.addEventListener("click", () => void deleteCurrentSession());
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
  dom.messageInput.addEventListener("focus", onComposerFocus);
  dom.messageInput.addEventListener("blur", onComposerBlur);
  dom.installButton.addEventListener("click", installApp);
  dom.installHelpPrimaryButton.addEventListener("click", hideInstallHelpModal);
  dom.installHelpDismissButton.addEventListener("click", hideInstallHelpModal);

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
    state.installContext = "prompt";
    updateInstallButtonVisibility();
  });
  window.addEventListener("appinstalled", () => {
    state.installPrompt = null;
    state.installContext = "installed";
    updateInstallButtonVisibility();
  });

  window.addEventListener("online", updateConnectionLabel);
  window.addEventListener("offline", updateConnectionLabel);
  window.addEventListener("keydown", onGlobalKeyDown);

  // Visual viewport for mobile keyboard
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", syncVisualViewport);
    window.visualViewport.addEventListener("scroll", syncVisualViewport);
  }
  state.installContext = getInstallContext();
  updateInstallButtonVisibility();
  syncVisualViewport();
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
  await Promise.all([loadAppMeta(), loadAgents(), loadModelInfo()]);
  renderAll();
}

async function loadAppMeta() {
  try {
    const response = await fetchJson("/");
    state.appVersion = response?.version || "";
  } catch (error) {
    console.error("Failed to load app meta", error);
    state.appVersion = "";
  }
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
    state.sessions = await fetchJson(`/api/v1/chat/sessions?user_id=${encodeURIComponent(state.userId)}&limit=1000`);
  } catch (error) {
    console.error("Failed to load sessions", error);
    state.sessions = [];
  }
}

async function loadCurrentSession() {
  const currentSummary = state.sessions.find((item) => item.session_id === state.sessionId);
  if (!state.sessionId) {
    startNewChat(false);
    return;
  }

  if (!currentSummary) {
    state.messages = [];
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

    state.sessionId = response.session_id || state.sessionId;
    persistSessionId();
    removeThinkingMessage();
    releaseUploadPreviews(outboundAttachments);
    await loadSessions();
    await loadCurrentSession();
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
  renderTopbarActions();
  renderHistory();
  renderSuggestions();
  renderUploadTray();
  renderMessages();
  renderAgents();
  renderModelLibrary();
}

function onGlobalKeyDown(event) {
  if (event.key !== "Escape") return;
  if (state.sidebarOpen || state.inspectorOpen) {
    closeAllDrawers();
  }
}

function renderProfile() {
  dom.displayNameInput.value = state.displayName;
  dom.profileKeyInput.value = state.userId;
}

function updateConnectionLabel() {
  const onlineAgents = state.agents.filter((agent) => agent.status === "online").length;
  const networkLabel = navigator.onLine ? "Connected" : "Offline shell";
  const versionLabel = state.appVersion ? ` | v${state.appVersion}` : "";
  dom.connectionLabel.textContent = `${networkLabel} | ${onlineAgents} agent${onlineAgents === 1 ? "" : "s"} online${versionLabel}`;
}

function updateSessionHeader() {
  const currentSummary = state.sessions.find((item) => item.session_id === state.sessionId);
  const title = currentSummary?.title || deriveTitleFromMessages() || "New conversation";
  dom.sessionTitle.textContent = title;
}

function renderTopbarActions() {
  const currentSummary = state.sessions.find((item) => item.session_id === state.sessionId);
  dom.deleteChatButton.disabled = !currentSummary;
  dom.deleteChatButton.classList.toggle("is-disabled", !currentSummary);
}

function deriveTitleFromMessages() {
  const firstUser = state.messages.find((message) => message.role === "user");
  if (!firstUser) return "";
  return firstUser.content.replace(/\s+/g, " ").slice(0, 80);
}

/* ══ History render state ══ */
const HISTORY_PAGE_SIZE = 6; // items revealed per batch

function renderHistory() {
  dom.historyList.innerHTML = "";
  state.historyRenderedCount = HISTORY_PAGE_SIZE; // reset per full re-render

  if (!state.sessions.length) {
    dom.historyList.innerHTML = `<div class="empty-copy" style="padding:.75rem .4rem;font-size:.82rem;color:var(--muted);">No chat history yet.</div>`;
    dom.historyFooter.hidden = true;
    return;
  }

  renderHistoryBatch(HISTORY_PAGE_SIZE);
  dom.historyFooter.hidden = !state.sessions.length;
}

/** Renders sessions[0..upTo] grouped, replacing previous content */
function renderHistoryBatch(upTo) {
  // Remove existing sentinel / loading indicator before re-rendering
  const existingSentinel = dom.historyList.querySelector(".history-sentinel");
  const existingLoader   = dom.historyList.querySelector(".history-loading-more");
  if (existingSentinel) existingSentinel.remove();
  if (existingLoader)   existingLoader.remove();

  const grouped = groupSessionsForHistory(state.sessions.slice(0, upTo));
  const hasMore = upTo < state.sessions.length;

  // Build or update groups
  dom.historyList.innerHTML = "";
  grouped.forEach((group) => {
    const section = document.createElement("section");
    section.className = "history-group";

    const heading = document.createElement("h4");
    heading.className = "history-group-label";
    heading.textContent = group.label;
    section.appendChild(heading);

    const stack = document.createElement("div");
    stack.className = "history-group-items";

    group.items.forEach((session) => {
      stack.appendChild(buildHistoryItem(session));
    });

    section.appendChild(stack);
    dom.historyList.appendChild(section);
  });

  if (hasMore) {
    attachHistorySentinel(upTo);
  }
}

/** Builds a single history row element */
function buildHistoryItem(session) {
  const row = document.createElement("div");
  row.className = `history-item${session.session_id === state.sessionId ? " active" : ""}`;

  const body = document.createElement("button");
  body.type = "button";
  body.className = "history-item-body";
  body.title = session.title;
  body.innerHTML = `
    <span class="history-item-icon" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M13.5 9.5A5.5 5.5 0 01 2.5 9.5C2.5 6.46 5.08 4 8 4s5.5 2.46 5.5 5.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
        <path d="M4.5 12.5l-.8 1.8 2-1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </span>
    <span class="history-item-title">${escapeHtml(session.title)}</span>
  `;
  body.addEventListener("click", () => void openSession(session.session_id));

  const del = document.createElement("button");
  del.type = "button";
  del.className = "history-delete";
  del.setAttribute("aria-label", `Delete ${session.title}`);
  del.innerHTML = `<svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>`;
  del.addEventListener("click", (e) => { e.stopPropagation(); void deleteSession(session.session_id); });

  row.appendChild(body);
  row.appendChild(del);
  return row;
}

/** Appends a sentinel div + IntersectionObserver to load more on scroll */
function attachHistorySentinel(currentlyShown) {
  // Loading indicator
  const loader = document.createElement("div");
  loader.className = "history-loading-more";
  loader.setAttribute("aria-hidden", "true");
  dom.historyList.appendChild(loader);

  // 1px sentinel just below the loader
  const sentinel = document.createElement("div");
  sentinel.className = "history-sentinel";
  dom.historyList.appendChild(sentinel);

  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries[0].isIntersecting) return;
      observer.disconnect();
      const nextBatch = currentlyShown + HISTORY_PAGE_SIZE;
      state.historyRenderedCount = nextBatch;
      renderHistoryBatch(nextBatch);
    },
    { root: dom.historyList, threshold: 0 }
  );
  observer.observe(sentinel);
}

function groupSessionsForHistory(sessions) {
  const todayStart = startOfLocalDay(new Date());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);
  const previousWeekStart = new Date(todayStart);
  previousWeekStart.setDate(previousWeekStart.getDate() - 7);

  const groups = [];
  const buckets = new Map();

  sessions.forEach((session) => {
    const lastMessageDate = new Date(session.last_message_at);
    const dayStart = startOfLocalDay(lastMessageDate);

    let label = formatMonthLabel(lastMessageDate);
    if (dayStart.getTime() >= todayStart.getTime()) {
      label = "Today";
    } else if (dayStart.getTime() >= yesterdayStart.getTime()) {
      label = "Yesterday";
    } else if (dayStart.getTime() >= previousWeekStart.getTime()) {
      label = "Previous 7 Days";
    }

    if (!buckets.has(label)) {
      const group = { label, items: [] };
      buckets.set(label, group);
      groups.push(group);
    }
    buckets.get(label).items.push(session);
  });

  return groups;
}

function startOfLocalDay(value) {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
}

function formatMonthLabel(value) {
  try {
    return new Date(value).toLocaleDateString([], { month: "long", year: "numeric" });
  } catch {
    return "Older";
  }
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
  renderAll();
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

async function deleteCurrentSession() {
  const currentSummary = state.sessions.find((item) => item.session_id === state.sessionId);
  if (!currentSummary) {
    startNewChat(true);
    return;
  }
  await deleteSession(currentSummary.session_id);
}

function renderSuggestions() {
  const suggestions = buildSuggestions();
  dom.suggestionCount.textContent = String(suggestions.length);

  renderSuggestionCollection(dom.promptDeck, suggestions.slice(0, 6), "prompt-card");
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
      title: "Summarize link",
      description: "Crawl a pasted URL and explain what the page actually contains.",
      prompt: "https://example.com summarize what this page says and the key takeaways",
    },
    {
      title: "Schedule meeting",
      description: "Create a calendar event directly from chat.",
      prompt: "schedule a meeting with the design team tomorrow at 3pm for 45 minutes",
    },
    {
      title: "Show calendar",
      description: "List your upcoming meetings and reminders.",
      prompt: "show my upcoming calendar events",
    },
    {
      title: "Weather tomorrow",
      description: "Ask for tomorrow's forecast with a concrete date.",
      prompt: "weather in Kuala Lumpur tomorrow",
    },
    {
      title: "Transit route",
      description: "Plan a Klang Valley rail trip using the official schedule feed.",
      prompt: "how do I go from Taman Bahagia to KLCC by LRT?",
    },
    {
      title: "Live buses",
      description: "Summarize the current official Rapid Bus KL live feed.",
      prompt: "show live buses in KL",
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
      bubble.classList.remove("is-hidden");
      bubble.replaceChildren(buildMessageContent(message));
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

function buildMessageContent(message) {
  const wrapper = document.createElement("div");
  wrapper.className = "rich-message";

  const text = String(message.content || "");
  if (!text.trim()) {
    return wrapper;
  }

  if ((message.provider || "") === "transit-route" || /^Best route on /im.test(text)) {
    return buildTransitRouteContent(text);
  }

  appendFormattedBlocks(wrapper, text);
  return wrapper;
}

function buildTransitRouteContent(text) {
  const wrapper = document.createElement("div");
  wrapper.className = "route-card";

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) {
    return wrapper;
  }

  const headerLine = lines[0];
  const durationLine = lines.find((line) => /^-\s*Estimated travel time:/i.test(line)) || "";
  const noteLines = lines.filter((line) => /^Note:/i.test(line));
  const stepLines = lines.filter((line) => /^-\s+/i.test(line) && !/^-\s*Estimated travel time:/i.test(line));

  const match = headerLine.match(/^Best route on\s+(.+?)\s+from\s+(.+?)\s+to\s+(.+?):?$/i);
  const title = document.createElement("div");
  title.className = "route-card-head";
  if (match) {
    const heading = document.createElement("h4");
    heading.textContent = `${beautifyLabel(match[2])} to ${beautifyLabel(match[3])}`;
    const network = document.createElement("p");
    network.textContent = `via ${beautifyLabel(match[1])}`;
    title.appendChild(heading);
    title.appendChild(network);
  } else {
    const heading = document.createElement("h4");
    heading.textContent = headerLine.replace(/:$/, "");
    title.appendChild(heading);
  }
  wrapper.appendChild(title);

  if (durationLine) {
    const meta = document.createElement("div");
    meta.className = "route-meta";
    const pill = document.createElement("span");
    pill.className = "route-pill";
    pill.textContent = durationLine.replace(/^-+\s*/i, "");
    meta.appendChild(pill);
    wrapper.appendChild(meta);
  }

  if (stepLines.length) {
    const trail = document.createElement("ol");
    trail.className = "route-trail";
    stepLines.forEach((line, index) => {
      const item = document.createElement("li");
      item.className = "route-step";

      const marker = document.createElement("span");
      marker.className = "route-step-index";
      marker.textContent = String(index + 1);

      const copy = document.createElement("div");
      copy.className = "route-step-copy";
      appendFormattedBlocks(copy, line.replace(/^-+\s*/i, ""));

      item.appendChild(marker);
      item.appendChild(copy);
      trail.appendChild(item);
    });
    wrapper.appendChild(trail);
  }

  if (noteLines.length) {
    const notes = document.createElement("div");
    notes.className = "route-notes";
    const heading = document.createElement("strong");
    heading.textContent = "Notes";
    notes.appendChild(heading);
    noteLines.forEach((line) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = line.replace(/^Note:\s*/i, "");
      notes.appendChild(paragraph);
    });
    wrapper.appendChild(notes);
  }

  return wrapper;
}

function appendFormattedBlocks(container, text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n");
  const codePattern = /```([\w.+-]*)\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codePattern.exec(normalized)) !== null) {
    const plainText = normalized.slice(lastIndex, match.index);
    appendTextBlocks(container, plainText);
    container.appendChild(buildCodeBlock(match[2], match[1]));
    lastIndex = match.index + match[0].length;
  }

  appendTextBlocks(container, normalized.slice(lastIndex));
}

function appendTextBlocks(container, text) {
  const blocks = String(text || "")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  blocks.forEach((block) => {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!lines.length) return;

    if (lines.every((line) => /^-\s+/.test(line))) {
      const list = document.createElement("ul");
      list.className = "message-list-block";
      lines.forEach((line) => {
        const item = document.createElement("li");
        appendInlineNodes(item, line.replace(/^-\s+/, ""));
        list.appendChild(item);
      });
      container.appendChild(list);
      return;
    }

    if (lines.every((line) => /^\d+\.\s+/.test(line))) {
      const list = document.createElement("ol");
      list.className = "message-list-block ordered";
      lines.forEach((line) => {
        const item = document.createElement("li");
        appendInlineNodes(item, line.replace(/^\d+\.\s+/, ""));
        list.appendChild(item);
      });
      container.appendChild(list);
      return;
    }

    if (/^#{1,4}\s+/.test(lines[0])) {
      const level = Math.min(4, (lines[0].match(/^#+/) || ["#"])[0].length);
      const heading = document.createElement(`h${Math.min(6, level + 2)}`);
      heading.className = "message-heading";
      appendInlineNodes(heading, lines[0].replace(/^#{1,4}\s+/, ""));
      container.appendChild(heading);
      const rest = lines.slice(1);
      if (rest.length) {
        const paragraph = document.createElement("p");
        paragraph.className = "message-paragraph";
        appendLinesWithBreaks(paragraph, rest);
        container.appendChild(paragraph);
      }
      return;
    }

    const paragraph = document.createElement("p");
    paragraph.className = "message-paragraph";
    appendLinesWithBreaks(paragraph, lines);
    container.appendChild(paragraph);
  });
}

function appendLinesWithBreaks(parent, lines) {
  lines.forEach((line, index) => {
    if (index > 0) parent.appendChild(document.createElement("br"));
    appendInlineNodes(parent, line);
  });
}

function appendInlineNodes(parent, text) {
  const tokenPattern = /(\*\*[^*]+?\*\*|`[^`]+`|https?:\/\/[^\s<]+|\/(?:transit-live|whatsapp-beta|memorycore|finance)[^\s<]*)/g;
  let lastIndex = 0;
  let match;

  while ((match = tokenPattern.exec(text)) !== null) {
    const plain = text.slice(lastIndex, match.index);
    if (plain) parent.appendChild(document.createTextNode(plain));

    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = token.slice(2, -2);
      parent.appendChild(strong);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      const code = document.createElement("code");
      code.className = "inline-code";
      code.textContent = token.slice(1, -1);
      parent.appendChild(code);
    } else {
      const link = document.createElement("a");
      link.href = token;
      if (/^https?:/i.test(token)) {
        link.target = "_blank";
        link.rel = "noreferrer";
      }
      link.textContent = token;
      parent.appendChild(link);
    }

    lastIndex = match.index + token.length;
  }

  const tail = text.slice(lastIndex);
  if (tail) parent.appendChild(document.createTextNode(tail));
}

function buildCodeBlock(codeText, language) {
  const wrapper = document.createElement("div");
  wrapper.className = "code-block";

  const header = document.createElement("div");
  header.className = "code-block-head";

  const label = document.createElement("span");
  label.className = "code-language";
  label.textContent = language || "code";

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-code-button";
  copyButton.textContent = "Copy";
  copyButton.addEventListener("click", () => void copyCodeBlock(codeText, copyButton));

  header.appendChild(label);
  header.appendChild(copyButton);

  const pre = document.createElement("pre");
  const code = document.createElement("code");
  code.textContent = codeText.replace(/\n$/, "");
  pre.appendChild(code);

  wrapper.appendChild(header);
  wrapper.appendChild(pre);
  return wrapper;
}

async function copyCodeBlock(codeText, button) {
  const original = button.textContent;
  try {
    await navigator.clipboard.writeText(codeText);
    button.textContent = "Copied";
  } catch (error) {
    console.error("Copy failed", error);
    button.textContent = "Copy failed";
  } finally {
    window.setTimeout(() => {
      button.textContent = original;
    }, 1500);
  }
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

function onComposerFocus() {
  state.composerFocused = true;
  document.body.classList.add("keyboard-open");
  closeAllDrawers();
  syncVisualViewport();
  scrollComposerIntoView();
}

function onComposerBlur() {
  state.composerFocused = false;
  window.setTimeout(() => {
    if (document.activeElement !== dom.messageInput) {
      document.body.classList.remove("keyboard-open");
      syncVisualViewport();
    }
  }, 120);
}

function syncVisualViewport() {
  const viewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
  const keyboardInset = window.visualViewport
    ? Math.max(0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop)
    : 0;

  document.documentElement.style.setProperty("--vvh", `${viewportHeight}px`);
  document.documentElement.style.setProperty("--keyboard-inset", `${keyboardInset}px`);

  if (state.composerFocused) {
    document.body.classList.add("keyboard-open");
    scrollComposerIntoView();
  }
}

function scrollComposerIntoView() {
  requestAnimationFrame(() => {
    dom.composerWrap?.scrollIntoView({ block: "end", inline: "nearest" });
    scrollMessagesToBottom();
  });
}

/* ─── PWA ─── */
async function installApp() {
  if (state.installPrompt) {
    await state.installPrompt.prompt();
    await state.installPrompt.userChoice;
    state.installPrompt = null;
    state.installContext = getInstallContext();
    updateInstallButtonVisibility();
    return;
  }

  if (state.installContext === "ios-manual") {
    showInstallHelpModal();
  }
}

function getInstallContext() {
  if (isStandaloneMode()) {
    return "installed";
  }
  if (state.installPrompt) {
    return "prompt";
  }
  if (isIOSDevice()) {
    return "ios-manual";
  }
  return "none";
}

function updateInstallButtonVisibility() {
  state.installContext = getInstallContext();

  if (state.installContext === "prompt") {
    dom.installButton.hidden = false;
    dom.installButton.textContent = "Install app";
    return;
  }

  if (state.installContext === "ios-manual") {
    dom.installButton.hidden = false;
    dom.installButton.textContent = "Add to Home Screen";
    return;
  }

  dom.installButton.hidden = true;
}

function showInstallHelpModal() {
  const inSafari = isSafariBrowser();
  dom.installHelpTitle.textContent = inSafari ? "Add this app to your Home Screen" : "Open in Safari to install";
  dom.installHelpText.textContent = inSafari
    ? "On iPhone and iPad, Safari does not show an automatic install popup. Use the Share menu to add this app to your Home Screen."
    : "This browser on iPhone does not expose a direct install popup here. Open this page in Safari, then use Share > Add to Home Screen.";
  dom.installHelpSteps.innerHTML = inSafari
    ? [
        "<li>Tap the Share button in Safari.</li>",
        "<li>Scroll down and choose Add to Home Screen.</li>",
        "<li>Tap Add to finish installing FitClaw.</li>",
      ].join("")
    : [
        "<li>Open this same page in Safari.</li>",
        "<li>Tap the Share button.</li>",
        "<li>Choose Add to Home Screen, then tap Add.</li>",
      ].join("");

  dom.installHelpModal.hidden = false;
}

function hideInstallHelpModal() {
  dom.installHelpModal.hidden = true;
}

function isStandaloneMode() {
  return window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone === true;
}

function isIOSDevice() {
  const ua = window.navigator.userAgent || "";
  return /iPhone|iPad|iPod/i.test(ua) || (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
}

function isSafariBrowser() {
  const ua = window.navigator.userAgent || "";
  return /Safari/i.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|DuckDuckGo|YaBrowser/i.test(ua);
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

async function fetchOptionalJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, headers });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return await response.json();
}

async function fetchText(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }
  return await response.text();
}

/* ─── Utilities ─── */
function createSessionId() {
  return `web:${state.userId}:${createId()}`;
}

function createId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function beautifyLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const mostlyUppercase = raw === raw.toUpperCase();
  if (!mostlyUppercase) return raw;
  return raw
    .toLowerCase()
    .split(/(\s+|-|\/)/)
    .map((part) => {
      if (/^\s+$/.test(part) || part === "-" || part === "/") return part;
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join("");
}

function linkifyText(value) {
  const escaped = escapeHtml(value).replace(/\n/g, "<br>");
  return escaped
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>')
    .replace(/(^|[\s>])(\/(?:transit-live|whatsapp-beta|memorycore|finance)(?:[^\s<]*)?)/g, '$1<a href="$2">$2</a>');
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
