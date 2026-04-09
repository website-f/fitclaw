const STORAGE_KEY = "fitclaw-mobile-agent-config";

const els = {
  serverUrl: document.getElementById("serverUrl"),
  authUsername: document.getElementById("authUsername"),
  sharedKey: document.getElementById("sharedKey"),
  agentName: document.getElementById("agentName"),
  displayLabel: document.getElementById("displayLabel"),
  autoHeartbeat: document.getElementById("autoHeartbeat"),
  statusBadge: document.getElementById("statusBadge"),
  lastAction: document.getElementById("lastAction"),
  lastHeartbeat: document.getElementById("lastHeartbeat"),
  healthState: document.getElementById("healthState"),
  activityLog: document.getElementById("activityLog"),
  capabilities: document.getElementById("capabilities"),
  saveConfig: document.getElementById("saveConfig"),
  testServer: document.getElementById("testServer"),
  registerAgent: document.getElementById("registerAgent"),
  sendHeartbeat: document.getElementById("sendHeartbeat"),
  openWebApp: document.getElementById("openWebApp"),
  removeAgent: document.getElementById("removeAgent"),
  clearLog: document.getElementById("clearLog"),
};

let heartbeatTimer = null;

function nowLabel() {
  return new Date().toLocaleString();
}

function log(message) {
  els.activityLog.textContent = `[${nowLabel()}] ${message}\n${els.activityLog.textContent}`.trim();
}

function setStatus(kind, text) {
  els.statusBadge.textContent = text;
  els.statusBadge.className = `badge ${kind}`;
}

function getCapabilities() {
  return Array.from(els.capabilities.querySelectorAll("input:checked")).map((input) => input.value);
}

function authHeader(config) {
  return `Basic ${btoa(`${config.authUsername}:${config.sharedKey}`)}`;
}

function normalizeBaseUrl(rawValue) {
  return rawValue.trim().replace(/\/+$/, "");
}

function loadConfig() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    const defaultName = `mobile-${(navigator.platform || "device").toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Math.random().toString(36).slice(2, 7)}`;
    els.serverUrl.value = saved.serverUrl || "http://84.46.249.133:8000";
    els.authUsername.value = saved.authUsername || "agent";
    els.sharedKey.value = saved.sharedKey || "";
    els.agentName.value = saved.agentName || defaultName;
    els.displayLabel.value = saved.displayLabel || (navigator.userAgentData?.platform || navigator.platform || "Mobile device");
    els.autoHeartbeat.checked = saved.autoHeartbeat !== false;
    const enabled = new Set(saved.capabilities || getCapabilities());
    els.capabilities.querySelectorAll("input").forEach((input) => {
      input.checked = enabled.has(input.value);
    });
    if (saved.lastHeartbeat) {
      els.lastHeartbeat.textContent = saved.lastHeartbeat;
    }
  } catch {
    log("Could not load saved config. Using defaults instead.");
  }
}

function readConfig() {
  return {
    serverUrl: normalizeBaseUrl(els.serverUrl.value),
    authUsername: els.authUsername.value.trim() || "agent",
    sharedKey: els.sharedKey.value.trim(),
    agentName: els.agentName.value.trim(),
    displayLabel: els.displayLabel.value.trim(),
    autoHeartbeat: els.autoHeartbeat.checked,
    capabilities: getCapabilities(),
  };
}

function saveConfig() {
  const config = readConfig();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  els.lastAction.textContent = "Config saved";
  log(`Saved config for agent ${config.agentName || "(unnamed)"}.`);
  configureHeartbeatLoop();
  return config;
}

async function fetchJson(path, options = {}) {
  const config = readConfig();
  if (!config.serverUrl) {
    throw new Error("Add the server URL first.");
  }
  if (!config.sharedKey) {
    throw new Error("Add the shared key first.");
  }

  const headers = new Headers(options.headers || {});
  headers.set("Authorization", authHeader(config));
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${config.serverUrl}${path}`, {
    ...options,
    headers,
  });

  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }

  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload?.detail || JSON.stringify(payload);
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return payload;
}

async function buildMetadata() {
  const config = readConfig();
  const metadata = {
    platform: navigator.userAgentData?.platform || navigator.platform || "unknown",
    shell: "capacitor-mobile-agent",
    display_label: config.displayLabel || config.agentName,
    user_agent: navigator.userAgent,
    registered_from: "mobile_wrapper",
  };

  if ("geolocation" in navigator) {
    try {
      const position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: false,
          timeout: 5000,
          maximumAge: 300000,
        });
      });
      metadata.location = {
        latitude: Number(position.coords.latitude.toFixed(6)),
        longitude: Number(position.coords.longitude.toFixed(6)),
      };
    } catch {
      metadata.location = null;
    }
  }

  return metadata;
}

async function testServer() {
  const config = saveConfig();
  if (!config.serverUrl) {
    throw new Error("Add the server URL first.");
  }

  const response = await fetch(`${config.serverUrl}/health/live`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Health check failed with ${response.status}.`);
  }

  const payload = await response.json();
  els.healthState.textContent = payload.status || "ok";
  els.lastAction.textContent = "Server health checked";
  setStatus("badge-success", "Server reachable");
  log(`Server responded to /health/live with status ${payload.status || "ok"}.`);
}

async function registerAgent() {
  const config = saveConfig();
  if (!config.agentName) {
    throw new Error("Add the agent name first.");
  }

  const payload = await fetchJson("/api/v1/agents/register", {
    method: "POST",
    body: JSON.stringify({
      name: config.agentName,
      capabilities_json: config.capabilities,
      metadata_json: await buildMetadata(),
    }),
  });

  els.lastAction.textContent = "Agent registered";
  setStatus("badge-success", "Registered");
  log(`Registered agent ${payload.name} with ${payload.capabilities_json.length} capabilities.`);
  await sendHeartbeat();
}

async function sendHeartbeat() {
  const config = saveConfig();
  if (!config.agentName) {
    throw new Error("Add the agent name first.");
  }

  const payload = await fetchJson("/api/v1/agents/heartbeat", {
    method: "POST",
    body: JSON.stringify({
      name: config.agentName,
      status: "online",
      metadata_json: await buildMetadata(),
    }),
  });

  const label = new Date(payload.last_heartbeat_at || Date.now()).toLocaleString();
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      ...config,
      lastHeartbeat: label,
    }),
  );
  els.lastHeartbeat.textContent = label;
  els.lastAction.textContent = "Heartbeat sent";
  setStatus("badge-success", "Online");
  log(`Heartbeat accepted for ${payload.name}.`);
}

async function removeAgent() {
  const config = readConfig();
  if (!config.agentName) {
    throw new Error("Add the agent name first.");
  }
  const confirmed = window.confirm(
    `Remove ${config.agentName} from the server and clear the saved mobile agent setup on this device?`,
  );
  if (!confirmed) {
    return;
  }

  await fetchJson(`/api/v1/agents/${encodeURIComponent(config.agentName)}?purge_related=false`, {
    method: "DELETE",
  });

  localStorage.removeItem(STORAGE_KEY);
  els.lastHeartbeat.textContent = "Never";
  els.lastAction.textContent = "Agent removed";
  setStatus("badge-idle", "Removed");
  log(`Removed agent ${config.agentName} and cleared saved config.`);
  loadConfig();
}

function configureHeartbeatLoop() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }

  if (!els.autoHeartbeat.checked) {
    log("Auto heartbeat is off.");
    return;
  }

  heartbeatTimer = setInterval(() => {
    sendHeartbeat().catch((error) => {
      setStatus("badge-danger", "Heartbeat failed");
      log(`Auto heartbeat failed: ${error.message}`);
    });
  }, 60000);
}

function openWebApp() {
  const config = readConfig();
  if (!config.serverUrl) {
    throw new Error("Add the server URL first.");
  }
  window.location.href = `${config.serverUrl}/app`;
}

async function runAction(action, label) {
  try {
    await action();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    els.lastAction.textContent = `${label} failed`;
    setStatus("badge-danger", "Needs attention");
    log(`${label} failed: ${message}`);
  }
}

els.saveConfig.addEventListener("click", () => runAction(async () => saveConfig(), "Save"));
els.testServer.addEventListener("click", () => runAction(testServer, "Server test"));
els.registerAgent.addEventListener("click", () => runAction(registerAgent, "Register"));
els.sendHeartbeat.addEventListener("click", () => runAction(sendHeartbeat, "Heartbeat"));
els.openWebApp.addEventListener("click", () => runAction(async () => openWebApp(), "Open web app"));
els.removeAgent.addEventListener("click", () => runAction(removeAgent, "Remove agent"));
els.autoHeartbeat.addEventListener("change", configureHeartbeatLoop);
els.clearLog.addEventListener("click", () => {
  els.activityLog.textContent = "Activity log cleared.";
});

loadConfig();
configureHeartbeatLoop();
log("Mobile agent companion loaded.");
