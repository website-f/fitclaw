/* ── DOM references ── */
const dom = {
  /* sidebar / shell */
  sidebar:             document.getElementById("controlSidebar"),
  sidebarToggle:       document.getElementById("sidebarToggle"),
  sidebarToggleDesktop:document.getElementById("sidebarToggleDesktop"),
  closeSidebar:        document.getElementById("closeSidebar"),
  sidebarBackdrop:     document.getElementById("sidebarBackdrop"),

  /* main tabs */
  tabBar:              document.getElementById("tabBar"),

  /* sub-tabs inside Live panel */
  subTabBar:           document.getElementById("subTabBar"),

  /* provider / controls */
  providerSelect:      document.getElementById("providerSelect"),
  filterInput:         document.getElementById("filterInput"),
  radiusSelect:        document.getElementById("radiusSelect"),
  refreshLiveButton:   document.getElementById("refreshLiveButton"),
  useLocationButton:   document.getElementById("useLocationButton"),
  centerMapButton:     document.getElementById("centerMapButton"),
  centerMapButton2:    document.getElementById("centerMapButton2"),
  autoRefreshStatus:   document.getElementById("autoRefreshStatus"),

  /* location */
  locationDot:         document.getElementById("locationDot"),
  locationText:        document.getElementById("locationText"),

  /* hero stats */
  feedLabel:           document.getElementById("feedLabel"),
  vehicleCount:        document.getElementById("vehicleCount"),
  feedTimestamp:       document.getElementById("feedTimestamp"),

  /* provider notes */
  providerNotes:       document.getElementById("providerNotes"),

  /* live feed — vehicles sub-panel */
  vehicleCardGrid:     document.getElementById("vehicleCardGrid"),

  /* nearby sub-panel */
  nearbyMeta:          document.getElementById("nearbyMeta"),
  nearbyRoutes:        document.getElementById("nearbyRoutes"),
  nearbyVehicles:      document.getElementById("nearbyVehicles"),

  /* route planner */
  routeForm:           document.getElementById("routeForm"),
  originInput:         document.getElementById("originInput"),
  destinationInput:    document.getElementById("destinationInput"),
  networkSelect:       document.getElementById("networkSelect"),
  routeSubmitButton:   document.getElementById("routeSubmitButton"),
  routeResult:         document.getElementById("routeResult"),

  /* all-vehicles table */
  vehicleTableBody:    document.getElementById("vehicleTableBody"),
};

const state = {
  providers:              [],
  liveFeed:               null,
  nearby:                 null,
  map:                    null,
  vehicleMarkers:         new Map(),
  userMarker:             null,
  userAccuracyCircle:     null,
  refreshTimer:           null,
  refreshCountdownTimer:  null,
  nextRefreshAt:          0,
  filterDebounceTimer:    null,
  userLocation:           null,
  activeTab:              "live",
  activeSubTab:           "vehicles",
};

const LIVE_REFRESH_MS     = 35_000;
const MARKER_ANIMATION_MS = 14_000;

/* ════════════════════════════════════════
   Boot
   ════════════════════════════════════════ */

window.addEventListener("load", () => {
  bindEvents();
  initMap();           // map is always in the live tab — init immediately
  void boot();
});

async function boot() {
  await loadProviders();
  chooseInitialProvider();
  await Promise.all([loadRoute(), loadLiveFeed()]);
  scheduleRefresh();
  requestUserLocation({ forcePrompt: false });
}

/* ════════════════════════════════════════
   Event binding
   ════════════════════════════════════════ */

function bindEvents() {
  /* sidebar drawer — both mobile & desktop toggle buttons */
  [dom.sidebarToggle, dom.sidebarToggleDesktop].forEach((btn) => {
    if (btn) btn.addEventListener("click", openSidebar);
  });
  if (dom.closeSidebar)    dom.closeSidebar.addEventListener("click",    closeSidebar);
  if (dom.sidebarBackdrop) dom.sidebarBackdrop.addEventListener("click", closeSidebar);

  /* main tabs */
  dom.tabBar.addEventListener("click", onTabClick);

  /* sub-tabs (Vehicles / Nearby) */
  dom.subTabBar.addEventListener("click", onSubTabClick);

  /* provider / controls */
  dom.providerSelect.addEventListener("change", () => void loadLiveFeed());
  dom.filterInput.addEventListener("input", onFilterChanged);
  dom.radiusSelect.addEventListener("change", () => void loadNearby());
  dom.refreshLiveButton.addEventListener("click", () => void refreshAll());
  dom.useLocationButton.addEventListener("click", () => requestUserLocation({ forcePrompt: true }));
  if (dom.centerMapButton)  dom.centerMapButton.addEventListener("click",  centerMapOnBestTarget);
  if (dom.centerMapButton2) dom.centerMapButton2.addEventListener("click", centerMapOnBestTarget);

  /* route planner */
  dom.routeForm.addEventListener("submit", onPlanRoute);

  /* nearby route chip clicks — switch to vehicles sub-tab and load */
  dom.nearbyRoutes.addEventListener("click", onNearbyRouteClick);
}

/* ════════════════════════════════════════
   Sidebar drawer
   ════════════════════════════════════════ */

function openSidebar() {
  dom.sidebar.classList.add("open");
  dom.sidebarBackdrop.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeSidebar() {
  dom.sidebar.classList.remove("open");
  dom.sidebarBackdrop.hidden = true;
  document.body.style.overflow = "";
}

/* ════════════════════════════════════════
   Main Tabs
   ════════════════════════════════════════ */

function onTabClick(event) {
  const tab = event.target.closest(".tab");
  if (!tab) return;
  const key = tab.dataset.tab;
  if (!key || key === state.activeTab) return;
  activateTab(key);
}

function activateTab(key) {
  state.activeTab = key;

  dom.tabBar.querySelectorAll(".tab").forEach((btn) => {
    const active = btn.dataset.tab === key;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const active = panel.id === `panel-${key}`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });

  /* Invalidate map size whenever the live tab is shown */
  if (key === "live" && state.map) {
    requestAnimationFrame(() => state.map.invalidateSize());
  }
}

/* ════════════════════════════════════════
   Sub-tabs (Vehicles / Nearby)
   ════════════════════════════════════════ */

function onSubTabClick(event) {
  const btn = event.target.closest(".sub-tab");
  if (!btn) return;
  const key = btn.dataset.subtab;
  if (!key || key === state.activeSubTab) return;
  activateSubTab(key);
}

function activateSubTab(key) {
  state.activeSubTab = key;

  dom.subTabBar.querySelectorAll(".sub-tab").forEach((btn) => {
    const active = btn.dataset.subtab === key;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });

  document.querySelectorAll(".sub-panel").forEach((panel) => {
    const active = panel.id === `sub-${key}`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

/* ════════════════════════════════════════
   Map initialisation
   ════════════════════════════════════════ */

function initMap() {
  state.map = L.map("liveMap", {
    zoomControl: true,
    attributionControl: true,
  }).setView([3.139, 101.6869], 11);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
  }).addTo(state.map);
}

/* ════════════════════════════════════════
   Providers
   ════════════════════════════════════════ */

async function loadProviders() {
  const providers = await fetchJson("/api/v1/transit/providers");
  state.providers = providers;
  dom.providerSelect.innerHTML = "";
  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value       = provider.key;
    option.textContent = provider.label + (provider.live_supported ? "" : " (static only)");
    option.disabled    = !provider.live_supported;
    dom.providerSelect.appendChild(option);
  });
}

function chooseInitialProvider() {
  const current = state.providers.find((p) => p.key === dom.providerSelect.value);
  if (current?.live_supported) return;
  const preferred = state.providers.find((p) => p.key === "prasarana:rapid-bus-kl" && p.live_supported);
  const fallback  = state.providers.find((p) => p.live_supported);
  if (preferred)     dom.providerSelect.value = preferred.key;
  else if (fallback) dom.providerSelect.value = fallback.key;
}

/* ════════════════════════════════════════
   Live feed
   ════════════════════════════════════════ */

async function refreshAll() {
  state.nextRefreshAt = Date.now() + LIVE_REFRESH_MS;
  renderAutoRefreshStatus("Refreshing…");
  await Promise.all([loadLiveFeed(), loadNearby()]);
  renderAutoRefreshStatus();
}

async function loadLiveFeed() {
  const providerKey = dom.providerSelect.value;
  if (!providerKey) return;

  const provider = state.providers.find((p) => p.key === providerKey);
  dom.providerNotes.textContent  = provider?.notes || "Official Malaysia GTFS realtime feed.";
  dom.feedLabel.textContent      = provider?.label || providerKey;
  dom.vehicleCardGrid.innerHTML  = `<p class="empty-state">Loading live positions…</p>`;
  dom.vehicleTableBody.innerHTML = `<tr><td colspan="6" class="empty-state">Loading live positions…</td></tr>`;

  try {
    state.liveFeed = await fetchJson(`/api/v1/transit/live?provider_key=${encodeURIComponent(providerKey)}`);
    renderLiveVehicles();
  } catch (error) {
    state.liveFeed = null;
    clearVehicleMarkers();
    dom.vehicleCount.textContent   = "0";
    dom.feedTimestamp.textContent  = "--";
    dom.vehicleCardGrid.innerHTML  = `<p class="empty-state">${escapeHtml(error.message || String(error))}</p>`;
    dom.vehicleTableBody.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(error.message || String(error))}</td></tr>`;
  }
}

/* ════════════════════════════════════════
   Render live vehicles
   ════════════════════════════════════════ */

function renderLiveVehicles() {
  const vehicles = Array.isArray(state.liveFeed?.vehicles) ? state.liveFeed.vehicles : [];
  const filter   = dom.filterInput.value.trim().toLowerCase();
  const filtered = filter
    ? vehicles.filter((item) => {
        const h = `${item.route_label || ""} ${item.route_id || ""} ${item.vehicle_id || ""} ${item.license_plate || ""}`.toLowerCase();
        return h.includes(filter);
      })
    : vehicles;

  dom.vehicleCount.textContent  = String(filtered.length);
  dom.feedTimestamp.textContent = state.liveFeed?.feed_timestamp ? formatDateTime(state.liveFeed.feed_timestamp) : "--";

  const provider      = state.providers.find((p) => p.key === state.liveFeed?.provider_key);
  const providerLabel = provider?.label || state.liveFeed?.label || state.liveFeed?.provider_key || "--";
  const mode          = provider?.mode || "bus";

  if (!filtered.length) {
    dom.vehicleCardGrid.innerHTML  = `<p class="empty-state">No vehicles matched this filter.</p>`;
    dom.vehicleTableBody.innerHTML = `<tr><td colspan="6" class="empty-state">No vehicles matched this filter.</td></tr>`;
    clearVehicleMarkers();
    renderMapMarkers([]);
    return;
  }

  /* Vehicle cards */
  dom.vehicleCardGrid.innerHTML = filtered.slice(0, 120).map((item) => {
    const id     = escapeHtml(item.license_plate || item.vehicle_id || "vehicle");
    const route  = escapeHtml(item.route_label   || item.route_id   || item.trip_id  || "—");
    const isRail = mode === "rail";
    const moving = item.speed_kph && Number(item.speed_kph) > 0;
    const speed  = item.speed_kph ? `${Number(item.speed_kph).toFixed(0)} km/h · ` : "";
    return `
      <article class="vehicle-card">
        <div class="vehicle-card-header">
          <span class="vehicle-id">
            <span class="vehicle-dot${isRail ? " rail" : ""}${moving ? " moving" : ""}"></span>${id}
          </span>
          <span class="vehicle-mode-badge${isRail ? " rail" : ""}">${isRail ? "RAIL" : "BUS"}</span>
        </div>
        <div class="vehicle-route">${route}</div>
        <div class="vehicle-meta">${speed}${item.timestamp ? formatDateTime(item.timestamp) : "Live"}</div>
      </article>`;
  }).join("");

  /* All-vehicles table */
  dom.vehicleTableBody.innerHTML = filtered.slice(0, 120).map((item) => `
    <tr>
      <td>${escapeHtml(item.license_plate || item.vehicle_id || "vehicle")}</td>
      <td>${escapeHtml(item.route_label   || item.route_id   || item.trip_id || "—")}</td>
      <td class="hide-sm">${escapeHtml(providerLabel)}</td>
      <td class="hide-md">${Number(item.latitude).toFixed(5)}</td>
      <td class="hide-md">${Number(item.longitude).toFixed(5)}</td>
      <td>${escapeHtml(item.timestamp ? formatDateTime(item.timestamp) : "--")}</td>
    </tr>`).join("");

  renderMapMarkers(filtered, mode);
}

/* ════════════════════════════════════════
   Nearby transit
   ════════════════════════════════════════ */

async function loadNearby() {
  if (!state.userLocation) {
    state.nearby = null;
    dom.nearbyMeta.textContent   = "Location is required to load nearby buses and trains.";
    dom.nearbyRoutes.innerHTML   = `<p class="empty-state">Enable location to list routes and vehicles near you.</p>`;
    dom.nearbyVehicles.innerHTML = `<p class="empty-state">Nearby vehicles will appear here after location is available.</p>`;
    return;
  }

  const params = new URLSearchParams({
    latitude:      String(state.userLocation.latitude),
    longitude:     String(state.userLocation.longitude),
    radius_meters: String(Number(dom.radiusSelect.value || 1000)),
    mode:          "bus",
  });
  const query = dom.filterInput.value.trim();
  if (query) params.set("query", query);

  dom.nearbyMeta.textContent   = "Scanning nearby live bus providers…";
  dom.nearbyRoutes.innerHTML   = `<p class="empty-state">Checking official live feeds near your location…</p>`;
  dom.nearbyVehicles.innerHTML = `<p class="empty-state">Fetching nearby live vehicles…</p>`;

  try {
    state.nearby = await fetchJson(`/api/v1/transit/nearby?${params.toString()}`);
    renderNearby();
  } catch (error) {
    state.nearby = null;
    dom.nearbyMeta.textContent   = error.message || "Unable to load nearby transit.";
    dom.nearbyRoutes.innerHTML   = `<p class="empty-state">${escapeHtml(error.message || String(error))}</p>`;
    dom.nearbyVehicles.innerHTML = `<p class="empty-state">Nearby vehicles are unavailable right now.</p>`;
  }
}

function renderNearby() {
  const nearby = state.nearby;
  if (!nearby) {
    dom.nearbyMeta.textContent   = "Nearby transit is unavailable.";
    dom.nearbyRoutes.innerHTML   = `<p class="empty-state">No nearby routes available right now.</p>`;
    dom.nearbyVehicles.innerHTML = `<p class="empty-state">No nearby vehicles available right now.</p>`;
    return;
  }

  dom.nearbyMeta.textContent = nearby.vehicle_count > 0
    ? `${nearby.vehicle_count} live vehicle${nearby.vehicle_count === 1 ? "" : "s"} within ${formatMeters(nearby.radius_meters)}.`
    : `No live buses found within ${formatMeters(nearby.radius_meters)}.`;

  dom.nearbyRoutes.innerHTML = !nearby.routes.length
    ? `<p class="empty-state">No nearby routes matched your current filter.</p>`
    : nearby.routes.map((route) => `
        <button
          type="button"
          class="route-chip"
          data-provider-key="${escapeHtml(route.provider_key)}"
          data-route-query="${escapeHtml(route.route_label || route.route_id || "")}"
        >
          <span class="route-chip-title">${escapeHtml(route.route_label)}</span>
          <span class="route-chip-meta">${escapeHtml(route.provider_label)} · ${route.vehicle_count} live · nearest ${formatMeters(route.nearest_distance_meters)}</span>
        </button>`).join("");

  dom.nearbyVehicles.innerHTML = !nearby.vehicles.length
    ? `<p class="empty-state">No nearby vehicles matched this search.</p>`
    : nearby.vehicles.slice(0, 12).map((item) => `
        <article class="nearby-vehicle-card">
          <div>
            <strong>${escapeHtml(item.license_plate || item.vehicle_id || "vehicle")}</strong>
            <p>${escapeHtml(item.route_label || item.route_id || item.trip_id || "live nearby vehicle")}</p>
          </div>
          <div class="nearby-vehicle-meta">
            <span>${escapeHtml(item.provider_label)}</span>
            <span>${formatMeters(item.distance_meters)}</span>
          </div>
        </article>`).join("");
}

/* ════════════════════════════════════════
   Nearby route chip → switch provider + filter
   ════════════════════════════════════════ */

function onNearbyRouteClick(event) {
  const button = event.target.closest(".route-chip");
  if (!button) return;
  if (button.dataset.providerKey) dom.providerSelect.value = button.dataset.providerKey;
  if (button.dataset.routeQuery)  dom.filterInput.value    = button.dataset.routeQuery;

  /* Switch to Vehicles sub-tab so user can immediately see the filtered cards */
  activateSubTab("vehicles");
  void loadLiveFeed();
}

/* ════════════════════════════════════════
   Map markers
   ════════════════════════════════════════ */

function renderMapMarkers(vehicles, mode = "bus") {
  if (!state.map) return;
  const nextKeys = new Set();
  const bounds   = [];

  vehicles.slice(0, 200).forEach((item) => {
    const label      = item.route_label || item.route_id || item.trip_id || "live vehicle";
    const vehicleName= item.license_plate || item.vehicle_id || "vehicle";
    const markerKey  = buildVehicleKey(item);
    const popupHtml  =
      `<strong>${escapeHtml(vehicleName)}</strong><br>` +
      `${escapeHtml(label)}<br>` +
      (item.speed_kph ? `${escapeHtml(String(item.speed_kph))} km/h<br>` : "") +
      `${escapeHtml(item.timestamp ? formatDateTime(item.timestamp) : "Live position")}`;
    const targetLatLng = [item.latitude, item.longitude];
    nextKeys.add(markerKey);

    const existing = state.vehicleMarkers.get(markerKey);
    if (!existing) {
      const marker = L.marker(targetLatLng, {
        icon: buildVehicleIcon({ label, mode, bearing: item.bearing, moving: false }),
      }).addTo(state.map);
      marker.bindPopup(popupHtml);
      state.vehicleMarkers.set(markerKey, { marker, mode });
    } else {
      animateMarkerUpdate(existing.marker, targetLatLng, { label, mode, bearing: item.bearing, popupHtml });
      existing.mode = mode;
    }
    bounds.push([item.latitude, item.longitude]);
  });

  /* Remove stale markers */
  Array.from(state.vehicleMarkers.entries()).forEach(([key, entry]) => {
    if (nextKeys.has(key)) return;
    cancelMarkerAnimation(entry.marker);
    entry.marker.remove();
    state.vehicleMarkers.delete(key);
  });

  fitMapToCurrentContext(bounds);
}

function buildVehicleIcon({ label, mode, bearing, moving }) {
  const dir   = Number.isFinite(Number(bearing)) ? `transform:rotate(${Number(bearing)}deg);` : "";
  const glyph = mode === "rail" ? "🚆" : "🚌";
  return L.divIcon({
    className: "vehicle-marker-shell",
    html: `
      <div class="vehicle-marker ${mode === "rail" ? "rail" : "bus"}${moving ? " is-moving" : ""}">
        <div class="vehicle-marker-glyph" style="${dir}">${glyph}</div>
        <div class="vehicle-marker-label">${escapeHtml(shortenLabel(label, 18))}</div>
      </div>`,
    iconSize:    [80, 34],
    iconAnchor:  [40, 17],
    popupAnchor: [0, -16],
  });
}

function clearVehicleMarkers() {
  state.vehicleMarkers.forEach((entry) => {
    cancelMarkerAnimation(entry.marker);
    entry.marker.remove();
  });
  state.vehicleMarkers = new Map();
}

function fitMapToCurrentContext(vehicleBounds = []) {
  if (!state.map) return;
  const points = [...vehicleBounds];
  if (state.userLocation) points.push([state.userLocation.latitude, state.userLocation.longitude]);
  if (points.length === 1)     state.map.setView(points[0], 14);
  else if (points.length > 1)  state.map.fitBounds(points, { padding: [32, 32], maxZoom: 15 });
}

/* ════════════════════════════════════════
   User location
   ════════════════════════════════════════ */

function requestUserLocation({ forcePrompt }) {
  if (!("geolocation" in navigator)) {
    setLocationStatus("Geolocation not supported by this browser.", false);
    return;
  }
  setLocationStatus(forcePrompt ? "Requesting location access…" : "Detecting your location…", false);

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.userLocation = {
        latitude:  pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy:  pos.coords.accuracy,
      };
      setLocationStatus(`Near ${state.userLocation.latitude.toFixed(4)}, ${state.userLocation.longitude.toFixed(4)}`, true);
      if (!dom.originInput.value.trim()) {
        dom.originInput.value = `${state.userLocation.latitude.toFixed(5)}, ${state.userLocation.longitude.toFixed(5)}`;
      }
      renderUserLocation();
      void loadNearby();
    },
    (error) => {
      const denied = error.code === error.PERMISSION_DENIED;
      setLocationStatus(
        denied && !forcePrompt
          ? "Location off — tap 'Use Location' to enable."
          : `Unavailable: ${error.message || "permission denied"}`,
        false
      );
    },
    { enableHighAccuracy: true, timeout: forcePrompt ? 10_000 : 7_000, maximumAge: 60_000 }
  );
}

function setLocationStatus(text, active) {
  dom.locationText.textContent = text;
  dom.locationDot?.classList.toggle("active", active);
}

function renderUserLocation() {
  if (!state.userLocation || !state.map) return;
  const latLng = [state.userLocation.latitude, state.userLocation.longitude];
  if (state.userMarker) {
    state.userMarker.setLatLng(latLng);
  } else {
    state.userMarker = L.marker(latLng, {
      icon: L.divIcon({
        className: "vehicle-marker-shell",
        html: `<div class="user-location-pin"><div class="user-location-core"></div></div>`,
        iconSize:   [26, 26],
        iconAnchor: [13, 13],
      }),
    }).addTo(state.map);
    state.userMarker.bindPopup("Your current location");
  }
  if (state.userAccuracyCircle) {
    state.userAccuracyCircle.setLatLng(latLng);
    state.userAccuracyCircle.setRadius(Math.max(20, state.userLocation.accuracy || 20));
  } else {
    state.userAccuracyCircle = L.circle(latLng, {
      radius:      Math.max(20, state.userLocation.accuracy || 20),
      color:       "#38bdf8",
      weight:      1,
      fillColor:   "#38bdf8",
      fillOpacity: 0.1,
    }).addTo(state.map);
  }
}

function centerMapOnBestTarget() {
  /* Make sure the live tab is visible so the map is rendered */
  if (state.activeTab !== "live") activateTab("live");

  requestAnimationFrame(() => {
    state.map.invalidateSize();
    if (state.userLocation) {
      state.map.setView([state.userLocation.latitude, state.userLocation.longitude], 14);
      state.userMarker?.openPopup();
    } else if (state.vehicleMarkers.size) {
      fitMapToCurrentContext(
        Array.from(state.vehicleMarkers.values()).map(({ marker }) => {
          const { lat, lng } = marker.getLatLng();
          return [lat, lng];
        })
      );
    }
  });
}

/* ════════════════════════════════════════
   Route planner
   ════════════════════════════════════════ */

async function onPlanRoute(event) {
  event.preventDefault();
  await loadRoute();
}

async function loadRoute() {
  const origin      = dom.originInput.value.trim();
  const destination = dom.destinationInput.value.trim();
  const network     = dom.networkSelect.value;
  if (!origin || !destination) return;

  dom.routeSubmitButton.disabled = true;
  dom.routeResult.innerHTML = `<p class="empty-state">Planning the best official route…</p>`;

  try {
    const response = await fetchJson(
      `/api/v1/transit/route?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&network=${encodeURIComponent(network)}`
    );

    const stepsHtml = response.steps.map((step) => `
      <li class="route-step">
        <strong>${escapeHtml(step.route_label || step.step_type)}</strong>
        <p>${escapeHtml(step.instruction)}</p>
      </li>`).join("");

    const notesHtml = (response.notes || []).map((n) => `<li class="route-step"><p>${escapeHtml(n)}</p></li>`).join("");

    dom.routeResult.innerHTML = `
      <div class="route-summary">
        <strong>${escapeHtml(response.matched_origin)} &rarr; ${escapeHtml(response.matched_destination)}</strong>
        <p>Estimated: <strong>${Math.round(response.total_estimated_minutes)} min</strong> &nbsp;·&nbsp; ${escapeHtml(response.network)}</p>
        <ul class="route-steps">${stepsHtml}</ul>
        ${notesHtml ? `<ul class="route-steps">${notesHtml}</ul>` : ""}
      </div>`;
  } catch (error) {
    dom.routeResult.innerHTML = `<p class="empty-state">${escapeHtml(error.message || String(error))}</p>`;
  } finally {
    dom.routeSubmitButton.disabled = false;
  }
}

/* ════════════════════════════════════════
   Filter debounce
   ════════════════════════════════════════ */

function onFilterChanged() {
  renderLiveVehicles();
  if (state.filterDebounceTimer) clearTimeout(state.filterDebounceTimer);
  state.filterDebounceTimer = setTimeout(() => void loadNearby(), 240);
}

/* ════════════════════════════════════════
   Auto-refresh scheduler
   ════════════════════════════════════════ */

function scheduleRefresh() {
  if (state.refreshTimer)          clearInterval(state.refreshTimer);
  if (state.refreshCountdownTimer) clearInterval(state.refreshCountdownTimer);
  state.nextRefreshAt         = Date.now() + LIVE_REFRESH_MS;
  renderAutoRefreshStatus();
  state.refreshCountdownTimer = setInterval(() => renderAutoRefreshStatus(),  1_000);
  state.refreshTimer          = setInterval(() => void refreshAll(),          LIVE_REFRESH_MS);
}

function renderAutoRefreshStatus(overrideText = "") {
  if (!dom.autoRefreshStatus) return;
  if (overrideText) { dom.autoRefreshStatus.textContent = overrideText; return; }
  if (!state.nextRefreshAt)   { dom.autoRefreshStatus.textContent = "Auto refresh on"; return; }
  const sec = Math.ceil(Math.max(0, state.nextRefreshAt - Date.now()) / 1_000);
  dom.autoRefreshStatus.textContent = `Auto refresh in ${sec}s`;
}

/* ════════════════════════════════════════
   Marker animation
   ════════════════════════════════════════ */

function animateMarkerUpdate(marker, targetLatLng, meta) {
  const from    = marker.getLatLng();
  const [toLat, toLng] = targetLatLng;
  const changed = Math.abs(from.lat - toLat) > 0.00001 || Math.abs(from.lng - toLng) > 0.00001;

  marker.setIcon(buildVehicleIcon({ label: meta.label, mode: meta.mode, bearing: meta.bearing, moving: changed }));
  marker.setPopupContent(meta.popupHtml);

  if (!changed) { cancelMarkerAnimation(marker); return; }

  cancelMarkerAnimation(marker);
  const start    = performance.now();
  const startLat = from.lat;
  const startLng = from.lng;

  const step = (now) => {
    const t     = Math.min(1, (now - start) / MARKER_ANIMATION_MS);
    const eased = 1 - Math.pow(1 - t, 3);
    marker.setLatLng([startLat + (toLat - startLat) * eased, startLng + (toLng - startLng) * eased]);
    if (t < 1) {
      marker._fitclawAnimationFrame = requestAnimationFrame(step);
      return;
    }
    marker.setLatLng([toLat, toLng]);
    marker.setIcon(buildVehicleIcon({ label: meta.label, mode: meta.mode, bearing: meta.bearing, moving: false }));
    marker._fitclawAnimationFrame = null;
  };

  marker._fitclawAnimationFrame = requestAnimationFrame(step);
}

function cancelMarkerAnimation(marker) {
  if (marker._fitclawAnimationFrame) {
    cancelAnimationFrame(marker._fitclawAnimationFrame);
    marker._fitclawAnimationFrame = null;
  }
}

/* ════════════════════════════════════════
   Helpers
   ════════════════════════════════════════ */

function buildVehicleKey(item) {
  return [
    state.liveFeed?.provider_key || "provider",
    item.vehicle_id    || "",
    item.license_plate || "",
    item.trip_id       || "",
    item.route_id      || "",
  ].join("::");
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    let detail = "";
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed === "object" && parsed ? parsed.detail || parsed.message || "" : "";
    } catch {}
    if (Array.isArray(detail)) detail = detail.join(", ");
    throw new Error(detail || text || `Request failed with ${res.status}`);
  }
  return res.json();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g,  "&amp;")
    .replace(/</g,  "&lt;")
    .replace(/>/g,  "&gt;")
    .replace(/"/g,  "&quot;")
    .replace(/'/g,  "&#39;");
}

function formatDateTime(value) {
  try {
    return new Date(value).toLocaleString([], {
      month:  "short", day: "numeric",
      hour:   "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return String(value || "--"); }
}

function formatMeters(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "--";
  return n >= 1000 ? `${(n / 1000).toFixed(1)} km` : `${Math.round(n)} m`;
}

function shortenLabel(value, max) {
  const t = String(value || "").trim();
  return t.length <= max ? t : `${t.slice(0, max - 1)}\u2026`;
}
