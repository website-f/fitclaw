const dom = {
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
};

const state = {
  version: "",
  status: null,
};

window.addEventListener("load", () => {
  bindEvents();
  registerPWA();
  void boot();
});

async function boot() {
  await Promise.all([loadVersion(), loadStatus()]);
  render();
}

function bindEvents() {
  dom.waRefreshButton.addEventListener("click", () => void refresh());
  dom.waProfileForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveProfile();
  });
  dom.waQuickTestButton?.addEventListener("click", () => {
    void saveProfile({ sendQuickTest: true });
  });
  dom.waTestForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void queueTestSend();
  });
  dom.waBlastForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void queueBlast();
  });
}

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
    render();
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

function formatWhen(value) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
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

function registerPWA() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/app-sw.js", { scope: "/" }).catch((error) => {
      console.error("Failed to register service worker", error);
    });
  }
}
