const storageKeys = {
  userId: "fitclaw_aiops_user_id",
  displayName: "fitclaw_aiops_display_name",
};

const dom = {
  body: document.body,
  waPageVersion: document.getElementById("waPageVersion"),
  waRefreshButton: document.getElementById("waRefreshButton"),
  waWarningText: document.getElementById("waWarningText"),
  waEnabledState: document.getElementById("waEnabledState"),
  waBridgeState: document.getElementById("waBridgeState"),
  waInboundState: document.getElementById("waInboundState"),
  waBlastState: document.getElementById("waBlastState"),
  waBridgeUrl: document.getElementById("waBridgeUrl"),
  waSenderPhone: document.getElementById("waSenderPhone"),
  waConnectedSender: document.getElementById("waConnectedSender"),
  waDefaultRecipient: document.getElementById("waDefaultRecipient"),
  waSenderCount: document.getElementById("waSenderCount"),
  waRecipientCount: document.getElementById("waRecipientCount"),
  waQrPanel: document.getElementById("waQrPanel"),
  waQrImage: document.getElementById("waQrImage"),
  waQrHint: document.getElementById("waQrHint"),
  waProfileForm: document.getElementById("waProfileForm"),
  waSenderPhoneInput: document.getElementById("waSenderPhoneInput"),
  waSenderLabelInput: document.getElementById("waSenderLabelInput"),
  waDefaultRecipientInput: document.getElementById("waDefaultRecipientInput"),
  waAllowedSendersInput: document.getElementById("waAllowedSendersInput"),
  waAllowedRecipientsInput: document.getElementById("waAllowedRecipientsInput"),
  waQuickTestButton: document.getElementById("waQuickTestButton"),
  waTestForm: document.getElementById("waTestForm"),
  waTestRecipient: document.getElementById("waTestRecipient"),
  waTestMessage: document.getElementById("waTestMessage"),
  waTestWarningAck: document.getElementById("waTestWarningAck"),
  waBlastForm: document.getElementById("waBlastForm"),
  waBlastRecipients: document.getElementById("waBlastRecipients"),
  waBlastMessage: document.getElementById("waBlastMessage"),
  waBlastWarningAck: document.getElementById("waBlastWarningAck"),
  waEvents: document.getElementById("waEvents"),

  waTabs: document.querySelectorAll(".wa-tab"),
  waConvoRefreshButton: document.getElementById("waConvoRefreshButton"),
  waConvoScroll: document.getElementById("waConvoScroll"),
  waConvoSearch: document.getElementById("waConvoSearch"),
  waBackButton: document.getElementById("waBackButton"),
  waChatAvatar: document.getElementById("waChatAvatar"),
  waChatTitle: document.getElementById("waChatTitle"),
  waChatSub: document.getElementById("waChatSub"),
  waChatEmpty: document.getElementById("waChatEmpty"),
  waMessageScroll: document.getElementById("waMessageScroll"),
  waMessageList: document.getElementById("waMessageList"),
  waComposer: document.getElementById("waComposer"),
  waAttachButton: document.getElementById("waAttachButton"),
  waFilePicker: document.getElementById("waFilePicker"),
  waUploadTray: document.getElementById("waUploadTray"),
  waMessageInput: document.getElementById("waMessageInput"),
  waSendButton: document.getElementById("waSendButton"),
};

const state = {
  version: "",
  status: null,
  tab: "chats",
  userId: "",
  conversations: [],
  searchQuery: "",
  activeChat: null,
  messages: [],
  sending: false,
  loadingMessages: false,
  pollTimer: null,
  pendingUploads: [],
};

window.addEventListener("load", () => {
  bootstrapUser();
  bindEvents();
  registerPWA();
  void boot();
});

function bootstrapUser() {
  state.userId = localStorage.getItem(storageKeys.userId) || `web-${createId()}`;
  localStorage.setItem(storageKeys.userId, state.userId);
}

async function boot() {
  await Promise.all([loadVersion(), loadStatus(), loadConversations()]);
  render();
  startPolling();
}

function bindEvents() {
  dom.waRefreshButton?.addEventListener("click", () => void refresh());
  dom.waProfileForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveProfile();
  });
  dom.waQuickTestButton?.addEventListener("click", () => {
    void saveProfile({ sendQuickTest: true });
  });
  dom.waTestForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void queueTestSend();
  });
  dom.waBlastForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void queueBlast();
  });

  dom.waTabs.forEach((tab) => {
    tab.addEventListener("click", () => setTab(tab.dataset.waTab));
  });

  dom.waConvoRefreshButton?.addEventListener("click", () => void loadConversations().then(renderConversations));
  dom.waConvoSearch?.addEventListener("input", (event) => {
    state.searchQuery = event.target.value.trim();
    renderConversations();
  });
  dom.waConvoSearch?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      startChatFromSearch();
    }
  });

  dom.waBackButton?.addEventListener("click", () => {
    document.body.classList.remove("wa-chat-open");
  });

  dom.waComposer?.addEventListener("submit", (event) => {
    event.preventDefault();
    void sendChatMessage();
  });

  dom.waMessageInput?.addEventListener("input", autoResizeTextarea);
  dom.waMessageInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void sendChatMessage();
    }
  });

  dom.waAttachButton?.addEventListener("click", () => dom.waFilePicker.click());
  dom.waFilePicker?.addEventListener("change", onFileSelection);
}

function setTab(tab) {
  const next = tab === "config" ? "config" : "chats";
  state.tab = next;
  document.body.setAttribute("data-wa-tab", next);
  dom.waTabs.forEach((btn) => {
    const active = btn.dataset.waTab === next;
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = window.setInterval(() => {
    if (document.hidden) return;
    void loadConversations().then(renderConversations);
    if (state.activeChat) {
      void loadMessages(state.activeChat.chat_jid, { silent: true });
    }
  }, 12000);
}

/* ═══════════════ STATUS / CONFIG ═══════════════ */

async function refresh() {
  await loadStatus();
  render();
}

async function loadVersion() {
  try {
    const meta = await fetchJson("/version");
    state.version = meta?.version || "";
  } catch (error) {
    console.error("Failed to load version", error);
    state.version = "";
  }
}

async function loadStatus() {
  try {
    state.status = await fetchJson("/api/v1/whatsapp/status");
  } catch (error) {
    console.error("Failed to load WhatsApp beta status", error);
    state.status = {
      enabled: false,
      bridge_reachable: false,
      inbound_enabled: false,
      blasting_enabled: false,
      warning: "Could not load WhatsApp beta status.",
      bridge_base_url: "-",
      allowlisted_senders: [],
      allowlisted_recipients: [],
      default_recipient: null,
      recent_events: [
        {
          kind: "status",
          status: "error",
          detail: error.message || String(error),
          created_at: new Date().toISOString(),
        },
      ],
    };
  }
}

function render() {
  renderStatus();
  renderConversations();
  renderActiveChat();
}

function renderStatus() {
  const status = state.status || {};
  dom.waPageVersion.textContent = state.version ? `WhatsApp beta | v${state.version}` : "WhatsApp beta";
  dom.waWarningText.textContent = status.warning || "Use a secondary number and keep volume low.";
  dom.waEnabledState.textContent = status.enabled ? "Beta enabled" : "Beta disabled";
  dom.waBridgeState.textContent = status.bridge_connected
    ? "Bridge connected"
    : status.bridge_pairing_required
      ? "QR pairing required"
      : status.bridge_reachable
        ? "Bridge reachable"
        : "Bridge not reachable";
  dom.waInboundState.textContent = status.inbound_enabled ? "Inbound relay on" : "Inbound relay off";
  dom.waBlastState.textContent = status.blasting_enabled ? "Blast beta on" : "Blast beta off";
  dom.waBridgeUrl.textContent = status.bridge_base_url || "-";
  dom.waSenderPhone.textContent = status.sender_phone || "-";
  dom.waConnectedSender.textContent = status.connected_sender_phone || status.connected_sender_jid || "-";
  dom.waDefaultRecipient.textContent = status.default_recipient || "-";
  dom.waSenderCount.textContent = String((status.allowlisted_senders || []).length);
  dom.waRecipientCount.textContent = String((status.allowlisted_recipients || []).length);
  renderQr(status);

  dom.waSenderPhoneInput.value = status.sender_phone || "";
  dom.waSenderLabelInput.value = status.sender_label || "";
  dom.waDefaultRecipientInput.value = status.default_recipient || "";
  dom.waAllowedSendersInput.value = (status.allowlisted_senders || []).join("\n");
  dom.waAllowedRecipientsInput.value = (status.allowlisted_recipients || []).join("\n");

  if (!dom.waTestRecipient.value && status.default_recipient) {
    dom.waTestRecipient.value = status.default_recipient;
  }

  renderEvents(status.recent_events || []);
}

function renderQr(status) {
  const pairingRequired = Boolean(status.bridge_pairing_required);
  const qrAvailable = Boolean(status.bridge_qr_available);
  if (!pairingRequired) {
    dom.waQrPanel.hidden = true;
    dom.waQrImage.removeAttribute("src");
    dom.waQrImage.hidden = true;
    dom.waQrHint.textContent = "Bridge is already paired.";
    return;
  }
  dom.waQrPanel.hidden = false;
  if (qrAvailable) {
    dom.waQrImage.hidden = false;
    dom.waQrImage.src = `/api/v1/whatsapp/qr?ts=${Date.now()}`;
    dom.waQrHint.textContent = "Open WhatsApp on the sender phone, tap Linked Devices, then scan this code.";
  } else {
    dom.waQrImage.removeAttribute("src");
    dom.waQrImage.hidden = true;
    dom.waQrHint.textContent =
      "Pairing is required, but the QR image is not ready yet. Refresh this page or restart the bridge if it stays empty.";
  }
}

function renderEvents(events) {
  dom.waEvents.innerHTML = "";
  if (!events.length) {
    dom.waEvents.innerHTML = `<div class="wa-empty">No WhatsApp beta events yet.</div>`;
    return;
  }
  events.forEach((entry) => {
    const article = document.createElement("article");
    article.className = "wa-event";
    const recipientSuffix = entry.recipient ? ` - ${escapeHtml(entry.recipient)}` : "";
    article.innerHTML = `
      <div class="wa-event-top">
        <span class="wa-event-kind">${escapeHtml(entry.kind || "event")}</span>
        <span class="wa-event-status">${escapeHtml(entry.status || "unknown")}</span>
      </div>
      <div class="wa-event-body">${escapeHtml(entry.detail || "")}</div>
      <div class="wa-event-kind" style="margin-top:0.45rem;">${escapeHtml(formatWhen(entry.created_at))}${recipientSuffix}</div>
    `;
    dom.waEvents.appendChild(article);
  });
}

/* ═══════════════ CONVERSATIONS ═══════════════ */

async function loadConversations() {
  try {
    const items = await fetchJson("/api/v1/whatsapp/conversations?limit=80");
    state.conversations = Array.isArray(items) ? items : [];
  } catch (error) {
    console.error("Failed to load conversations", error);
    state.conversations = [];
  }
}

function renderConversations() {
  dom.waConvoScroll.innerHTML = "";
  const query = state.searchQuery.toLowerCase();
  const list = state.conversations.filter((c) => {
    if (!query) return true;
    const haystack = `${c.display_name || ""} ${c.sender_key || ""} ${c.chat_jid || ""}`.toLowerCase();
    return haystack.includes(query);
  });

  if (!list.length) {
    const empty = document.createElement("div");
    empty.className = "wa-convo-empty";
    empty.textContent = state.conversations.length
      ? "No matching conversations. Press Enter to start a chat with this number."
      : "No WhatsApp conversations yet. Incoming chats will appear here.";
    dom.waConvoScroll.appendChild(empty);
    return;
  }

  list.forEach((convo) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "wa-convo-item";
    if (state.activeChat?.chat_jid === convo.chat_jid) item.classList.add("active");

    const initial = (convo.display_name || convo.sender_key || "#").trim().charAt(0).toUpperCase() || "#";
    const when = convo.last_message_at ? formatRelative(convo.last_message_at) : "";
    item.innerHTML = `
      <div class="wa-convo-avatar">${escapeHtml(initial)}</div>
      <div class="wa-convo-main">
        <span class="wa-convo-name">${escapeHtml(convo.display_name || convo.sender_key || convo.chat_jid)}</span>
        <span class="wa-convo-preview">${escapeHtml(convo.last_preview || "No messages yet")}</span>
      </div>
      <span class="wa-convo-meta">${escapeHtml(when)}</span>
    `;
    item.addEventListener("click", () => void selectChat(convo));
    dom.waConvoScroll.appendChild(item);
  });
}

async function selectChat(convo) {
  state.activeChat = convo;
  state.messages = [];
  dom.waChatEmpty.hidden = true;
  document.body.classList.add("wa-chat-open");
  renderActiveChat();
  renderConversations();
  await loadMessages(convo.chat_jid);
  dom.waMessageInput?.focus();
}

function startChatFromSearch() {
  const raw = (dom.waConvoSearch.value || "").trim();
  if (!raw) return;
  const digits = raw.replace(/[^\d]/g, "");
  if (!digits) return;
  const chatJid = `${digits}@s.whatsapp.net`;
  const convo = {
    chat_jid: chatJid,
    sender_key: digits,
    display_name: digits,
    last_preview: "",
    last_message_at: null,
    message_count: 0,
  };
  void selectChat(convo);
}

/* ═══════════════ MESSAGES ═══════════════ */

async function loadMessages(chatJid, options = {}) {
  if (!options.silent) {
    state.loadingMessages = true;
    renderMessages();
  }
  try {
    const items = await fetchJson(
      `/api/v1/whatsapp/conversations/${encodeURIComponent(chatJid)}/messages?limit=200`
    );
    state.messages = Array.isArray(items) ? items : [];
  } catch (error) {
    console.error("Failed to load messages", error);
    state.messages = [];
  } finally {
    state.loadingMessages = false;
    renderMessages();
    scrollToLatest();
  }
}

function renderActiveChat() {
  if (!state.activeChat) {
    dom.waChatTitle.textContent = "Select a conversation";
    dom.waChatSub.textContent = "Pick a chat from the list to see messages.";
    dom.waChatAvatar.textContent = "W";
    dom.waChatEmpty.hidden = false;
    dom.waMessageList.innerHTML = "";
    dom.waComposer.hidden = true;
    return;
  }
  dom.waComposer.hidden = false;
  dom.waChatEmpty.hidden = state.messages.length > 0;
  const name = state.activeChat.display_name || state.activeChat.sender_key || state.activeChat.chat_jid;
  dom.waChatTitle.textContent = name;
  dom.waChatSub.textContent = state.activeChat.chat_jid;
  dom.waChatAvatar.textContent = (name || "#").charAt(0).toUpperCase();
  renderMessages();
  renderUploadTray();
}

function renderMessages() {
  dom.waMessageList.innerHTML = "";
  if (!state.activeChat) return;
  if (state.loadingMessages && !state.messages.length) {
    const loading = document.createElement("div");
    loading.className = "wa-chat-empty";
    loading.style.margin = "auto";
    loading.innerHTML = `<p>Loading messages...</p>`;
    dom.waMessageList.appendChild(loading);
    return;
  }
  dom.waChatEmpty.hidden = state.messages.length > 0;
  state.messages.forEach((msg) => {
    const bubble = document.createElement("article");
    const isOutbound = msg.role === "assistant";
    bubble.className = `wa-bubble ${isOutbound ? "wa-bubble-outbound" : "wa-bubble-inbound"}`;

    const text = document.createElement("div");
    text.className = "wa-bubble-text";
    text.textContent = msg.content || "";
    bubble.appendChild(text);

    const attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
    if (attachments.length) {
      const wrap = document.createElement("div");
      wrap.className = "wa-bubble-attachments";
      attachments.forEach((att) => {
        const node = renderAttachmentNode(att);
        if (node) wrap.appendChild(node);
      });
      bubble.appendChild(wrap);
    }

    const time = document.createElement("div");
    time.className = "wa-bubble-time";
    time.textContent = formatShortTime(msg.created_at);
    bubble.appendChild(time);

    dom.waMessageList.appendChild(bubble);
  });
}

function renderAttachmentNode(att) {
  if (!att || !att.public_url) return null;
  const kind = (att.kind || "").toLowerCase();
  if (kind === "image" || kind === "photo") {
    const link = document.createElement("a");
    link.className = "wa-bubble-attachment";
    link.href = att.public_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    const img = document.createElement("img");
    img.src = att.public_url;
    img.alt = att.filename || "attachment";
    link.appendChild(img);
    return link;
  }
  const anchor = document.createElement("a");
  anchor.className = "wa-bubble-attachment";
  anchor.href = att.public_url;
  anchor.target = "_blank";
  anchor.rel = "noreferrer";
  anchor.textContent = att.filename || att.caption || "Open attachment";
  return anchor;
}

function scrollToLatest() {
  window.requestAnimationFrame(() => {
    dom.waMessageScroll.scrollTop = dom.waMessageScroll.scrollHeight;
  });
}

/* ═══════════════ COMPOSER ═══════════════ */

function autoResizeTextarea() {
  const el = dom.waMessageInput;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
}

async function onFileSelection(event) {
  const files = Array.from(event.target.files || []);
  dom.waFilePicker.value = "";
  if (!files.length) return;
  for (const file of files) {
    const upload = {
      localId: createId(),
      file,
      filename: file.name,
      size: file.size,
      type: file.type,
      preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      status: "uploading",
      asset: null,
      error: "",
    };
    state.pendingUploads.push(upload);
    renderUploadTray();
    try {
      const formData = new FormData();
      formData.append("user_id", state.userId);
      formData.append("file", file, file.name);
      const response = await fetch("/api/v1/uploads", { method: "POST", body: formData });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Upload failed ${response.status}`);
      }
      upload.asset = await response.json();
      upload.status = "ready";
    } catch (error) {
      upload.status = "error";
      upload.error = error.message || String(error);
    }
    renderUploadTray();
  }
}

function renderUploadTray() {
  if (!dom.waUploadTray) return;
  dom.waUploadTray.innerHTML = "";
  state.pendingUploads.forEach((upload) => {
    const pill = document.createElement("div");
    pill.className = `wa-upload-pill ${upload.status}`;

    const thumb = document.createElement("div");
    thumb.className = "wa-upload-thumb";
    if (upload.preview) {
      const img = document.createElement("img");
      img.src = upload.preview;
      img.alt = upload.filename;
      thumb.appendChild(img);
    } else {
      thumb.textContent = fileExtension(upload.filename) || "FILE";
    }

    const meta = document.createElement("div");
    meta.className = "wa-upload-meta";
    meta.innerHTML = `<strong>${escapeHtml(upload.filename)}</strong><span>${upload.status === "uploading" ? "Uploading..." : upload.status === "error" ? upload.error : formatBytes(upload.size)}</span>`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "wa-upload-remove";
    remove.innerHTML = "×";
    remove.addEventListener("click", () => {
      if (upload.preview) URL.revokeObjectURL(upload.preview);
      state.pendingUploads = state.pendingUploads.filter((item) => item.localId !== upload.localId);
      renderUploadTray();
    });

    pill.appendChild(thumb);
    pill.appendChild(meta);
    pill.appendChild(remove);
    dom.waUploadTray.appendChild(pill);
  });
}

async function sendChatMessage() {
  if (state.sending || !state.activeChat) return;
  const text = dom.waMessageInput.value.trim();
  const readyUploads = state.pendingUploads.filter((item) => item.status === "ready");
  if (!text && !readyUploads.length) return;

  state.sending = true;
  dom.waSendButton.disabled = true;

  const fullText = buildOutboundText(text, readyUploads);

  try {
    await fetchJson("/api/v1/whatsapp/chat-send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipient: state.activeChat.chat_jid,
        message: fullText,
        warning_acknowledged: true,
      }),
    });
    dom.waMessageInput.value = "";
    autoResizeTextarea();
    readyUploads.forEach((upload) => {
      if (upload.preview) URL.revokeObjectURL(upload.preview);
    });
    state.pendingUploads = state.pendingUploads.filter((item) => item.status !== "ready");
    renderUploadTray();
    await loadMessages(state.activeChat.chat_jid, { silent: true });
    void loadConversations().then(renderConversations);
  } catch (error) {
    alert(error.message || String(error));
  } finally {
    state.sending = false;
    dom.waSendButton.disabled = false;
  }
}

function buildOutboundText(text, uploads) {
  const parts = [];
  if (text) parts.push(text);
  if (uploads.length) {
    const urlLines = uploads
      .map((upload) => upload.asset?.public_url)
      .filter(Boolean)
      .map((url) => `- ${url}`);
    if (urlLines.length) {
      parts.push(["Files:", ...urlLines].join("\n"));
    }
  }
  return parts.join("\n\n") || "(empty)";
}

/* ═══════════════ CONFIG ACTIONS ═══════════════ */

async function saveProfile(options = {}) {
  const payload = {
    sender_phone: dom.waSenderPhoneInput.value.trim(),
    sender_label: dom.waSenderLabelInput.value.trim(),
    default_recipient: dom.waDefaultRecipientInput.value.trim(),
    allowed_senders: splitLines(dom.waAllowedSendersInput.value),
    allowed_recipients: splitLines(dom.waAllowedRecipientsInput.value),
  };
  try {
    state.status = await fetchJson("/api/v1/whatsapp/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderStatus();
    if (options.sendQuickTest) {
      await sendQuickTestFromProfile();
      return;
    }
    alert("Saved WhatsApp beta sender and recipient settings.");
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function queueTestSend() {
  const payload = {
    recipient: dom.waTestRecipient.value.trim(),
    message: dom.waTestMessage.value.trim() || defaultTestMessage(),
    warning_acknowledged: dom.waTestWarningAck.checked,
  };
  if (!payload.recipient || !payload.message) {
    alert("Please provide both a recipient and a message.");
    return;
  }
  try {
    const result = await fetchJson("/api/v1/whatsapp/test-send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    alert(result.message || "Sent test message.");
    await refresh();
  } catch (error) {
    alert(error.message || String(error));
  }
}

async function sendQuickTestFromProfile() {
  const recipient = dom.waDefaultRecipientInput.value.trim();
  if (!recipient) {
    alert("Save a default recipient first.");
    return;
  }
  const result = await fetchJson("/api/v1/whatsapp/test-send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recipient,
      message: defaultTestMessage(),
      warning_acknowledged: true,
    }),
  });
  alert(result.message || "Saved setup and sent a test message.");
  await refresh();
}

function defaultTestMessage() {
  return "Hello from FitClaw. This is a direct WhatsApp beta test message after saving your sender and recipient setup.";
}

async function queueBlast() {
  const recipients = dom.waBlastRecipients.value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);

  const payload = {
    recipients,
    message: dom.waBlastMessage.value.trim(),
    warning_acknowledged: dom.waBlastWarningAck.checked,
  };

  if (!payload.recipients.length || !payload.message) {
    alert("Please provide at least one recipient and a message.");
    return;
  }
  try {
    const result = await fetchJson("/api/v1/whatsapp/blast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    alert(result.message || "Queued beta blast.");
    await refresh();
  } catch (error) {
    alert(error.message || String(error));
  }
}

/* ═══════════════ UTILITIES ═══════════════ */

function formatWhen(value) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatShortTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatRelative(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) {
    return date.toLocaleDateString([], { weekday: "short" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
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

function fileExtension(filename) {
  const parts = String(filename || "").split(".");
  return parts.length > 1 ? parts.pop().toUpperCase().slice(0, 4) : "";
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;
    } catch (error) {
      try {
        detail = await response.text();
      } catch (innerError) {
        // ignore
      }
    }
    throw new Error(detail);
  }
  return response.json();
}

function splitLines(value) {
  return String(value || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function createId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function registerPWA() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/app-sw.js", { scope: "/" }).catch((error) => {
      console.error("Failed to register service worker", error);
    });
  }
}
