const STORAGE_KEY = "fitclaw-mobile-agent-config";

const els = {
  serverUrl: document.getElementById("serverUrl"),
  authUsername: document.getElementById("authUsername"),
  sharedKey: document.getElementById("sharedKey"),
  agentName: document.getElementById("agentName"),
  displayLabel: document.getElementById("displayLabel"),
  autoHeartbeat: document.getElementById("autoHeartbeat"),
  autoControl: document.getElementById("autoControl"),
  statusBadge: document.getElementById("statusBadge"),
  lastAction: document.getElementById("lastAction"),
  lastHeartbeat: document.getElementById("lastHeartbeat"),
  healthState: document.getElementById("healthState"),
  lastCommand: document.getElementById("lastCommand"),
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
let controlTimer = null;
let commandLoopBusy = false;

function stripHtml(raw) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(raw, "text/html");
  const nodes = Array.from(doc.querySelectorAll("script,style,noscript"));
  nodes.forEach((node) => node.remove());
  return (doc.body?.textContent || doc.documentElement?.textContent || "")
    .replace(/\s+/g, " ")
    .trim();
}

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
  const value = rawValue.trim();
  if (!value) {
    return "";
  }

  try {
    const url = new URL(value);
    const normalizedPath = url.pathname.replace(/\/+$/, "") || "/";
    const knownUiPaths = new Set([
      "/app",
      "/control",
      "/docs",
      "/health",
      "/health/live",
      "/health/ready",
      "/finance",
      "/memorycore",
      "/transit-live",
      "/whatsapp-beta",
    ]);

    if (normalizedPath === "/" || knownUiPaths.has(normalizedPath)) {
      url.pathname = "";
      url.search = "";
      url.hash = "";
    } else {
      url.search = "";
      url.hash = "";
    }

    return url.toString().replace(/\/+$/, "");
  } catch {
    return value.replace(/\/+$/, "");
  }
}

function isAndroidShell() {
  const platform = window.Capacitor?.getPlatform?.();
  return platform === "android" || /android/i.test(navigator.userAgent || "");
}

function describeNetworkFailure(error, config, label) {
  const message = error instanceof Error ? error.message : String(error);
  const baseUrl = String(config?.serverUrl || "").trim();

  if (/failed to fetch/i.test(message)) {
    if (/^http:\/\/localhost(?::\d+)?$/i.test(baseUrl) || /^http:\/\/127\.0\.0\.1(?::\d+)?$/i.test(baseUrl)) {
      return `${label} failed: this phone cannot use \`${baseUrl}\` to reach your server. Use your VPS or LAN IP instead of localhost.`;
    }
    if (isAndroidShell() && /^http:\/\//i.test(baseUrl)) {
      return `${label} failed: this APK could not reach \`${baseUrl}\`. Older Android builds often block plain http traffic. Use the rebuilt APK with the cleartext fix, or switch the server URL to https.`;
    }
    return `${label} failed: the app could not reach \`${baseUrl}\`. Check that the phone can open that URL in its browser and that port 8000 is reachable from the phone's network.`;
  }

  return `${label} failed: ${message}`;
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
    els.autoControl.checked = saved.autoControl !== false;
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
    autoControl: els.autoControl.checked,
    capabilities: getCapabilities(),
  };
}

function saveConfig() {
  const config = readConfig();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  els.lastAction.textContent = "Config saved";
  log(`Saved config for agent ${config.agentName || "(unnamed)"}.`);
  configureHeartbeatLoop();
  configureControlLoop();
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
    control_actions: ["calendar_probe", "calendar_create", "browser_open_url", "browser_crawl"],
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

function getCapacitorBrowser() {
  return window.Capacitor?.Plugins?.Browser || null;
}

async function openExternalUrl(url) {
  const browser = getCapacitorBrowser();
  if (browser?.open) {
    await browser.open({ url });
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function buildGoogleCalendarUrl(payload) {
  const params = new URLSearchParams();
  params.set("action", "TEMPLATE");
  params.set("text", payload.title || "FitClaw Event");

  const startsAt = payload.starts_at ? new Date(payload.starts_at) : null;
  const endsAt = payload.ends_at ? new Date(payload.ends_at) : null;
  if (startsAt && !Number.isNaN(startsAt.getTime())) {
    const startStamp = startsAt.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    const endTarget = endsAt && !Number.isNaN(endsAt.getTime())
      ? endsAt
      : new Date(startsAt.getTime() + 60 * 60 * 1000);
    const endStamp = endTarget.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    params.set("dates", `${startStamp}/${endStamp}`);
  }

  if (payload.description) {
    params.set("details", payload.description);
  }
  if (payload.location) {
    params.set("location", payload.location);
  }
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function buildMobileCalendarProbe(config) {
  return {
    calendar_windows: [],
    has_google_calendar_window: false,
    has_outlook_window: false,
    outlook_onboarding_detected: false,
    outlook_available: false,
    outlook_executable: null,
    running_browsers: ["capacitor-browser"],
    recommended_provider: "google",
    reason: `This mobile agent can hand off calendar events to Google Calendar while the app stays open on ${config.displayLabel || config.agentName}.`,
    probed_at: new Date().toISOString(),
    mobile_agent: true,
  };
}

async function handleControlCommand(command) {
  const payload = command.payload_json || {};
  const action = payload.action || command.command_type;
  const config = readConfig();

  if (command.command_type !== "app_action") {
    throw new Error(`Unsupported mobile control command \`${command.command_type}\`.`);
  }

  if (action === "calendar_probe") {
    return buildMobileCalendarProbe(config);
  }

  if (action === "calendar_create") {
    const provider = String(payload.provider || "google").trim().toLowerCase();
    if (provider && provider !== "google") {
      throw new Error("This mobile agent currently supports Google Calendar handoff only.");
    }
    const url = buildGoogleCalendarUrl(payload);
    await openExternalUrl(url);
    return {
      ok: true,
      provider_used: "google",
      opened: true,
      saved: false,
      requires_user_confirmation: true,
      opened_url: url,
      mobile_agent: true,
    };
  }

  if (action === "browser_open_url") {
    const url = String(payload.url || "").trim();
    if (!url) {
      throw new Error("No URL was provided.");
    }
    await openExternalUrl(url);
    return {
      ok: true,
      action,
      url,
      mobile_agent: true,
    };
  }

  if (action === "browser_crawl") {
    const url = String(payload.url || "").trim();
    if (!url) {
      throw new Error("No URL was provided.");
    }
    const response = await fetch(url, { method: "GET" });
    if (!response.ok) {
      throw new Error(`Website crawl failed with HTTP ${response.status}.`);
    }
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const title = (doc.querySelector("title")?.textContent || "").trim();
    const metaDescription =
      (doc.querySelector('meta[name="description"]')?.getAttribute("content") || "").trim() ||
      (doc.querySelector('meta[property="og:description"]')?.getAttribute("content") || "").trim();
    const links = Array.from(doc.querySelectorAll("a[href]"))
      .map((node) => ({
        url: new URL(node.getAttribute("href"), response.url).toString(),
        text: (node.textContent || "").replace(/\s+/g, " ").trim(),
      }))
      .filter((item) => item.url)
      .slice(0, 10);
    const textExcerpt = stripHtml(html).slice(0, Number(payload.max_chars || 3200));
    return {
      ok: true,
      url,
      final_url: response.url,
      title,
      meta_description: metaDescription,
      text_excerpt: textExcerpt,
      top_links: links,
      mobile_agent: true,
      fetched_at: new Date().toISOString(),
    };
  }

  throw new Error(`Unsupported mobile app action \`${action}\`.`);
}

async function submitControlResult(commandId, status, resultJson = {}, errorText = null) {
  await fetchJson(`/api/v1/agent-control/${encodeURIComponent(commandId)}/result`, {
    method: "POST",
    body: JSON.stringify({
      status,
      result_json: resultJson,
      error_text: errorText,
    }),
  });
}

async function pollControlCommands() {
  if (commandLoopBusy) {
    return;
  }
  const config = readConfig();
  if (!config.agentName || !config.serverUrl || !config.sharedKey || !config.autoControl) {
    return;
  }

  commandLoopBusy = true;
  try {
    const command = await fetchJson(`/api/v1/agent-control/claim/${encodeURIComponent(config.agentName)}`, {
      method: "POST",
    });
    if (!command) {
      return;
    }

    const commandLabel = `${command.command_type}${command.payload_json?.action ? ` / ${command.payload_json.action}` : ""}`;
    els.lastCommand.textContent = commandLabel;
    els.lastAction.textContent = `Processing ${commandLabel}`;
    log(`Processing control command ${command.command_id}: ${commandLabel}`);

    try {
      const result = await handleControlCommand(command);
      await submitControlResult(command.command_id, "completed", result, null);
      els.lastAction.textContent = `Completed ${commandLabel}`;
      log(`Completed control command ${command.command_id}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await submitControlResult(command.command_id, "failed", {}, message);
      els.lastAction.textContent = `Failed ${commandLabel}`;
      log(`Control command ${command.command_id} failed: ${message}`);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log(`Control polling failed: ${message}`);
  } finally {
    commandLoopBusy = false;
  }
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
  els.lastCommand.textContent = "None yet";
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

function configureControlLoop() {
  if (controlTimer) {
    clearInterval(controlTimer);
    controlTimer = null;
  }

  if (!els.autoControl.checked) {
    log("Auto control handling is off.");
    return;
  }

  controlTimer = setInterval(() => {
    pollControlCommands().catch((error) => {
      log(`Auto control polling failed: ${error.message}`);
    });
  }, 12000);
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
    const config = readConfig();
    const message = describeNetworkFailure(error, config, label);
    els.lastAction.textContent = `${label} failed`;
    setStatus("badge-danger", "Needs attention");
    log(message);
  }
}

els.saveConfig.addEventListener("click", () => runAction(async () => saveConfig(), "Save"));
els.testServer.addEventListener("click", () => runAction(testServer, "Server test"));
els.registerAgent.addEventListener("click", () => runAction(registerAgent, "Register"));
els.sendHeartbeat.addEventListener("click", () => runAction(sendHeartbeat, "Heartbeat"));
els.openWebApp.addEventListener("click", () => runAction(async () => openWebApp(), "Open web app"));
els.removeAgent.addEventListener("click", () => runAction(removeAgent, "Remove agent"));
els.autoHeartbeat.addEventListener("change", configureHeartbeatLoop);
els.autoControl.addEventListener("change", configureControlLoop);
els.clearLog.addEventListener("click", () => {
  els.activityLog.textContent = "Activity log cleared.";
});

loadConfig();
configureHeartbeatLoop();
configureControlLoop();
pollControlCommands().catch(() => {});
log("Mobile agent companion loaded.");
