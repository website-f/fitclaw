const storageKeys = {
  userId: "fitclaw_aiops_user_id",
  displayName: "fitclaw_aiops_display_name",
  sessionId: "fitclaw_aiops_session_id",
  memoryCoreWakeName: "fitclaw_memorycore_wake_name",
  memoryCorePlatform: "fitclaw_memorycore_platform",
};

const state = {
  userId: "",
  displayName: "",
  appVersion: "",
  loading: false,
  loadingProject: false,
  error: "",
  profile: null,
  projects: [],
  templates: [],
  selectedProjectKey: "",
  selectedProject: null,
  selectedMarkdown: "",
  wakeName: "jarvis",
  platform: "windows-x64",
  filter: "all",
};

const dom = {
  pageConnectionLabel: document.getElementById("pageConnectionLabel"),
  memoryCoreCount: document.getElementById("memoryCoreCount"),
  activeProjectCount: document.getElementById("activeProjectCount"),
  archivedProjectCount: document.getElementById("archivedProjectCount"),
  templateCount: document.getElementById("templateCount"),
  refreshMemoryCoreButton: document.getElementById("refreshMemoryCoreButton"),
  clearAllMemoryCoreButton: document.getElementById("clearAllMemoryCoreButton"),
  memoryCoreWakeNameInput: document.getElementById("memoryCoreWakeNameInput"),
  memoryCorePlatformSelect: document.getElementById("memoryCorePlatformSelect"),
  memoryCoreLauncherCopy: document.getElementById("memoryCoreLauncherCopy"),
  downloadMemoryCoreBundleButton: document.getElementById("downloadMemoryCoreBundleButton"),
  downloadMemoryCoreMarkdownButton: document.getElementById("downloadMemoryCoreMarkdownButton"),
  downloadMasterMemoryButton: document.getElementById("downloadMasterMemoryButton"),
  importMasterMemoryButton: document.getElementById("importMasterMemoryButton"),
  memoryCoreImportFile: document.getElementById("memoryCoreImportFile"),
  memoryCoreProfile: document.getElementById("memoryCoreProfile"),
  templateStatusLabel: document.getElementById("templateStatusLabel"),
  templateList: document.getElementById("templateList"),
  memoryCoreStatus: document.getElementById("memoryCoreStatus"),
  memoryCoreFilterAllButton: document.getElementById("memoryCoreFilterAllButton"),
  memoryCoreFilterActiveButton: document.getElementById("memoryCoreFilterActiveButton"),
  memoryCoreFilterArchivedButton: document.getElementById("memoryCoreFilterArchivedButton"),
  memoryCoreProjectList: document.getElementById("memoryCoreProjectList"),
  memoryCoreProjectTitle: document.getElementById("memoryCoreProjectTitle"),
  memoryCoreProjectMeta: document.getElementById("memoryCoreProjectMeta"),
  memoryCoreViewerBody: document.getElementById("memoryCoreViewerBody"),
  startMemoryCoreBriefingButton: document.getElementById("startMemoryCoreBriefingButton"),
  archiveMemoryCoreProjectButton: document.getElementById("archiveMemoryCoreProjectButton"),
  copyMemoryCoreButton: document.getElementById("copyMemoryCoreButton"),
  deleteMemoryCoreProjectButton: document.getElementById("deleteMemoryCoreProjectButton"),
};

window.addEventListener("load", () => {
  initializeProfile();
  bindEvents();
  registerPWA();
  void boot();
});

async function boot() {
  renderAll();
  await Promise.all([loadAppMeta(), loadTemplates(), loadMemoryCoreSummary(true)]);
  renderAll();
}

function bindEvents() {
  dom.refreshMemoryCoreButton.addEventListener("click", () => void loadMemoryCoreSummary(true));
  dom.clearAllMemoryCoreButton.addEventListener("click", () => void clearAllMemoryCore());
  dom.memoryCoreWakeNameInput.addEventListener("input", onWakeNameChanged);
  dom.memoryCorePlatformSelect.addEventListener("change", onPlatformChanged);
  dom.downloadMemoryCoreBundleButton.addEventListener("click", () => void downloadMemoryCoreBundle());
  dom.downloadMemoryCoreMarkdownButton.addEventListener("click", downloadSelectedMemoryCoreMarkdown);
  dom.downloadMasterMemoryButton.addEventListener("click", () => void downloadSelectedMasterMemory());
  dom.importMasterMemoryButton.addEventListener("click", () => dom.memoryCoreImportFile.click());
  dom.memoryCoreImportFile.addEventListener("change", onMemoryCoreImportFileSelected);
  dom.memoryCoreFilterAllButton.addEventListener("click", () => setMemoryCoreFilter("all"));
  dom.memoryCoreFilterActiveButton.addEventListener("click", () => setMemoryCoreFilter("active"));
  dom.memoryCoreFilterArchivedButton.addEventListener("click", () => setMemoryCoreFilter("archived"));
  dom.startMemoryCoreBriefingButton.addEventListener("click", () => void startMemoryCoreBriefingChat());
  dom.archiveMemoryCoreProjectButton.addEventListener("click", () => void toggleArchiveSelectedMemoryCoreProject());
  dom.copyMemoryCoreButton.addEventListener("click", () => void copyMemoryCoreMarkdown());
  dom.deleteMemoryCoreProjectButton.addEventListener("click", () => void deleteSelectedMemoryCoreProject());
  window.addEventListener("online", renderHeader);
  window.addEventListener("offline", renderHeader);
}

function initializeProfile() {
  state.userId = localStorage.getItem(storageKeys.userId) || `web-${createId()}`;
  state.displayName = localStorage.getItem(storageKeys.displayName) || "FitClaw Operator";
  state.wakeName = normalizeWakeName(localStorage.getItem(storageKeys.memoryCoreWakeName) || "jarvis");
  state.platform = normalizeMemoryCorePlatform(localStorage.getItem(storageKeys.memoryCorePlatform) || detectMemoryCorePlatform());

  localStorage.setItem(storageKeys.userId, state.userId);
  localStorage.setItem(storageKeys.displayName, state.displayName);
  localStorage.setItem(storageKeys.memoryCoreWakeName, state.wakeName);
  localStorage.setItem(storageKeys.memoryCorePlatform, state.platform);
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

async function loadTemplates() {
  try {
    state.templates = await fetchJson("/api/v1/memorycore/templates");
  } catch (error) {
    console.error("Failed to load Memory Core templates", error);
    state.templates = [];
    state.error = state.error || error.message || String(error);
  }
}

async function loadMemoryCoreSummary(loadSelectedProject = true) {
  state.loading = true;
  state.error = "";
  renderAll();

  try {
    const [profile, projects] = await Promise.all([
      fetchOptionalJson(`/api/v1/memorycore/profile?user_id=${encodeURIComponent(state.userId)}`),
      fetchJson(`/api/v1/memorycore/projects?user_id=${encodeURIComponent(state.userId)}`),
    ]);

    state.profile = profile;
    state.projects = Array.isArray(projects) ? projects : [];
    syncSelectedProject();

    if (loadSelectedProject && state.selectedProjectKey) {
      await loadMemoryCoreProject(state.selectedProjectKey);
    }
  } catch (error) {
    console.error("Failed to load Memory Core summary", error);
    state.error = error.message || String(error);
  } finally {
    state.loading = false;
    renderAll();
  }
}

async function loadMemoryCoreProject(projectKey) {
  if (!projectKey) {
    state.selectedProject = null;
    state.selectedProjectKey = "";
    state.selectedMarkdown = "";
    renderAll();
    return;
  }

  state.selectedProjectKey = projectKey;
  state.loadingProject = true;
  renderAll();

  try {
    const [project, markdown, touched] = await Promise.all([
      fetchJson(`/api/v1/memorycore/projects/${encodeURIComponent(projectKey)}?user_id=${encodeURIComponent(state.userId)}`),
      fetchText(`/api/v1/memorycore/projects/${encodeURIComponent(projectKey)}/markdown?user_id=${encodeURIComponent(state.userId)}`),
      fetchOptionalJson(`/api/v1/memorycore/projects/${encodeURIComponent(projectKey)}/touch?user_id=${encodeURIComponent(state.userId)}`, { method: "POST" }),
    ]);

    const normalizedProject = touched || project;
    state.selectedProject = normalizedProject;
    state.selectedMarkdown = markdown;
    state.projects = state.projects.map((item) =>
      item.project_key === normalizedProject.project_key ? normalizedProject : item
    );
  } catch (error) {
    console.error("Failed to load Memory Core project", error);
    state.error = error.message || String(error);
    state.selectedProject = null;
    state.selectedMarkdown = "";
  } finally {
    state.loadingProject = false;
    renderAll();
  }
}

function setMemoryCoreFilter(nextFilter) {
  state.filter = nextFilter;
  syncSelectedProject();
  renderAll();
}

function getVisibleProjects() {
  if (state.filter === "active") {
    return state.projects.filter((item) => item.status !== "archived");
  }
  if (state.filter === "archived") {
    return state.projects.filter((item) => item.status === "archived");
  }
  return state.projects;
}

function syncSelectedProject() {
  const visibleProjects = getVisibleProjects();
  const hasSelected = visibleProjects.some((item) => item.project_key === state.selectedProjectKey);
  if (!hasSelected) {
    state.selectedProjectKey = visibleProjects[0]?.project_key || "";
    state.selectedProject = visibleProjects[0] || null;
    state.selectedMarkdown = "";
  } else {
    state.selectedProject = state.projects.find((item) => item.project_key === state.selectedProjectKey) || null;
  }
}

function renderAll() {
  renderHeader();
  renderProfile();
  renderLauncher();
  renderTemplates();
  renderProjects();
  renderViewer();
}

function renderHeader() {
  const activeCount = state.projects.filter((item) => item.status !== "archived").length;
  const archivedCount = state.projects.filter((item) => item.status === "archived").length;
  const networkLabel = navigator.onLine ? "Connected" : "Offline shell";
  const versionLabel = state.appVersion ? ` | v${state.appVersion}` : "";

  dom.pageConnectionLabel.textContent = `${networkLabel}${versionLabel}`;
  dom.memoryCoreCount.textContent = String(state.projects.length || 0);
  dom.activeProjectCount.textContent = String(activeCount);
  dom.archivedProjectCount.textContent = String(archivedCount);
  dom.templateCount.textContent = String(state.templates.length || 0);

  if (state.loading) {
    dom.memoryCoreStatus.textContent = "Loading project memories...";
  } else if (state.error) {
    dom.memoryCoreStatus.textContent = `Needs attention: ${state.error}`;
  } else {
    dom.memoryCoreStatus.textContent = `${activeCount} active · ${archivedCount} archived · ${state.projects.length} total`;
  }

  dom.memoryCoreFilterAllButton.classList.toggle("is-active", state.filter === "all");
  dom.memoryCoreFilterActiveButton.classList.toggle("is-active", state.filter === "active");
  dom.memoryCoreFilterArchivedButton.classList.toggle("is-active", state.filter === "archived");
}

function renderProfile() {
  dom.memoryCoreProfile.innerHTML = "";
  const profile = state.profile;

  if (!profile) {
    dom.memoryCoreProfile.innerHTML = `
      <div class="memorycore-page-profile-empty">
        No profile memory saved yet. Save preferences from chat or the terminal launcher and they will appear here.
      </div>
    `;
    return;
  }

  const wrap = document.createElement("div");
  wrap.className = "memorycore-page-profile-copy";

  const title = document.createElement("strong");
  title.textContent = profile.display_name || state.displayName || state.userId;
  wrap.appendChild(title);

  if (profile.about) {
    const about = document.createElement("p");
    about.textContent = profile.about;
    wrap.appendChild(about);
  }

  wrap.appendChild(renderMemoryCoreTagRow("Identity", profile.identity_notes || []));
  wrap.appendChild(renderMemoryCoreTagRow("Relationship", profile.relationship_notes || []));
  wrap.appendChild(renderMemoryCoreTagRow("Standing", profile.standing_instructions || []));
  wrap.appendChild(
    renderMemoryCoreTagRow("Preferences", [
      ...(profile.preferences || []),
      ...(profile.coding_preferences || []).map((item) => `Code: ${item}`),
      ...(profile.workflow_preferences || []).map((item) => `Flow: ${item}`),
    ])
  );

  dom.memoryCoreProfile.appendChild(wrap);
}

function renderLauncher() {
  dom.memoryCoreWakeNameInput.value = state.wakeName;
  dom.memoryCorePlatformSelect.value = state.platform;
  const platformLabel = getMemoryCorePlatformLabel(state.platform);
  dom.memoryCoreLauncherCopy.innerHTML = `
    <div><strong>${escapeHtml(platformLabel)}</strong></div>
    <div><code class="inline-code">${escapeHtml(state.wakeName)} remember this whole thing</code></div>
    <div><code class="inline-code">hey ${escapeHtml(state.wakeName)} remember this whole thing</code></div>
    <div>Memory Core will save to cloud and also write a local <code class="inline-code">MEMORYCORE.md</code> in the current project folder by default.</div>
  `;

  const hasSelectedProject = Boolean(state.selectedProjectKey && state.selectedMarkdown);
  dom.downloadMemoryCoreMarkdownButton.disabled = !hasSelectedProject;
  dom.downloadMasterMemoryButton.disabled = !state.selectedProjectKey;
}

function renderTemplates() {
  dom.templateStatusLabel.textContent = state.templates.length ? `${state.templates.length} ready` : "No templates";
  dom.templateList.innerHTML = "";

  if (!state.templates.length) {
    dom.templateList.innerHTML = `<div class="memorycore-page-empty">Template packs will appear here after the server loads them.</div>`;
    return;
  }

  const selectedProjectTitle = state.selectedProject?.title || "selected project";

  state.templates.forEach((template) => {
    const card = document.createElement("article");
    card.className = "memorycore-page-template-card";

    const head = document.createElement("div");
    head.className = "memorycore-page-template-head";
    head.innerHTML = `
      <div>
        <strong>${escapeHtml(template.title)}</strong>
      </div>
      <span class="memorycore-page-template-category">${escapeHtml(template.category)}</span>
    `;
    card.appendChild(head);

    const summary = document.createElement("p");
    summary.textContent = template.summary || "Reusable Memory Core template.";
    card.appendChild(summary);

    const preview = document.createElement("div");
    preview.className = "memorycore-page-template-preview";
    [
      `${(template.library_items || []).length} library item${(template.library_items || []).length === 1 ? "" : "s"}`,
      `${(template.next_steps || []).length} next step${(template.next_steps || []).length === 1 ? "" : "s"}`,
      `${(template.open_questions || []).length} open question${(template.open_questions || []).length === 1 ? "" : "s"}`,
    ].forEach((label) => {
      const chip = document.createElement("span");
      chip.className = "memorycore-page-template-chip";
      chip.textContent = label;
      preview.appendChild(chip);
    });
    card.appendChild(preview);

    const actions = document.createElement("div");
    actions.className = "memorycore-page-template-actions";

    const applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.className = "ghost-button small-button";
    applyButton.textContent = state.selectedProject ? `Apply to ${selectedProjectTitle}` : "Select a project to apply";
    applyButton.disabled = !state.selectedProject;
    applyButton.addEventListener("click", () => void applyMemoryCoreTemplate(template.template_key));
    actions.appendChild(applyButton);
    card.appendChild(actions);

    dom.templateList.appendChild(card);
  });
}

function renderProjects() {
  dom.memoryCoreProjectList.innerHTML = "";

  const visibleProjects = getVisibleProjects();
  if (!visibleProjects.length) {
    dom.memoryCoreProjectList.innerHTML = `<div class="memorycore-page-empty">No saved project memories match the current filter yet.</div>`;
    return;
  }

  const groups = [];
  if (state.filter === "all") {
    groups.push({ label: "Active", items: visibleProjects.filter((item) => item.status !== "archived") });
    groups.push({ label: "Archived", items: visibleProjects.filter((item) => item.status === "archived") });
  } else {
    groups.push({
      label: state.filter === "archived" ? "Archived" : "Active",
      items: visibleProjects,
    });
  }

  groups
    .filter((group) => group.items.length)
    .forEach((group) => {
      const block = document.createElement("section");
      block.className = "memorycore-page-project-group";

      const label = document.createElement("div");
      label.className = "memorycore-page-group-label";
      label.textContent = group.label;
      block.appendChild(label);

      group.items.forEach((project) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `memorycore-project-item${project.project_key === state.selectedProjectKey ? " active" : ""}`;
        button.addEventListener("click", () => void loadMemoryCoreProject(project.project_key));

        const focusLine = project.current_focus || project.session_brief || project.summary || "No summary saved yet.";
        button.innerHTML = `
          <div class="memorycore-project-title-row">
            <div class="memorycore-project-heading">
              <strong>${escapeHtml(project.title)}</strong>
            </div>
            <span class="memorycore-project-status ${project.status === "archived" ? "is-archived" : "is-active"}">${escapeHtml(project.status || "active")}</span>
          </div>
          <div class="memorycore-project-summary">${escapeHtml(focusLine)}</div>
          <small>Updated ${escapeHtml(formatDateTime(project.updated_at))}${project.open_count ? ` · opened ${escapeHtml(String(project.open_count))}x` : ""}</small>
        `;
        block.appendChild(button);
      });

      dom.memoryCoreProjectList.appendChild(block);
    });
}

function renderViewer() {
  const viewerProject = state.selectedProject || state.projects.find((item) => item.project_key === state.selectedProjectKey) || null;
  const hasProject = Boolean(viewerProject);

  dom.startMemoryCoreBriefingButton.disabled = !hasProject;
  dom.archiveMemoryCoreProjectButton.disabled = !hasProject;
  dom.copyMemoryCoreButton.disabled = !state.selectedMarkdown;
  dom.deleteMemoryCoreProjectButton.disabled = !hasProject;
  dom.archiveMemoryCoreProjectButton.textContent = viewerProject?.status === "archived" ? "Restore" : "Archive";

  if (state.loadingProject) {
    dom.memoryCoreProjectTitle.textContent = viewerProject?.title || "Loading project memory";
    dom.memoryCoreProjectMeta.textContent = "Fetching the latest project memory snapshot from the server...";
    dom.memoryCoreViewerBody.innerHTML = `<div class="memorycore-page-empty">Loading project memory...</div>`;
    return;
  }

  if (state.error && !hasProject) {
    dom.memoryCoreProjectTitle.textContent = "Memory Core needs attention";
    dom.memoryCoreProjectMeta.textContent = "The latest request did not finish cleanly.";
    dom.memoryCoreViewerBody.innerHTML = `<div class="memorycore-page-alert">${escapeHtml(state.error)}</div>`;
    return;
  }

  if (!hasProject) {
    dom.memoryCoreProjectTitle.textContent = "Select a project";
    dom.memoryCoreProjectMeta.textContent = "Open one of your saved project memories to inspect the full snapshot, timeline, and reusable library items.";
    dom.memoryCoreViewerBody.innerHTML = `<div class="memorycore-page-empty">Choose a project memory from the left to see its briefing, timeline, library items, and full markdown snapshot.</div>`;
    return;
  }

  dom.memoryCoreProjectTitle.textContent = viewerProject.title;
  dom.memoryCoreProjectMeta.textContent = [
    viewerProject.status === "archived" ? "Archived memory" : "Active memory",
    viewerProject.last_opened_at ? `Opened ${formatDateTime(viewerProject.last_opened_at)}` : null,
    viewerProject.updated_at ? `Updated ${formatDateTime(viewerProject.updated_at)}` : null,
  ].filter(Boolean).join(" · ");

  dom.memoryCoreViewerBody.innerHTML = "";

  if (state.error) {
    const alert = document.createElement("div");
    alert.className = "memorycore-page-alert";
    alert.textContent = state.error;
    dom.memoryCoreViewerBody.appendChild(alert);
  }

  const detailGrid = document.createElement("div");
  detailGrid.className = "memorycore-detail-grid";
  detailGrid.appendChild(renderMemoryCoreMetricCard("Session briefing", viewerProject.session_brief || "No briefing saved yet."));
  detailGrid.appendChild(renderMemoryCoreMetricCard("Current focus", viewerProject.current_focus || "No focus saved yet."));
  detailGrid.appendChild(renderMemoryCoreMetricCard("Open count", viewerProject.open_count ? `${viewerProject.open_count} total opens` : "Not opened from Memory Core yet."));
  detailGrid.appendChild(renderMemoryCoreMetricCard("Project status", viewerProject.status || "active"));
  dom.memoryCoreViewerBody.appendChild(detailGrid);

  if (viewerProject.summary) {
    dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Project summary", [viewerProject.summary]));
  }
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Next steps", viewerProject.next_steps));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Reminders", viewerProject.reminders));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Decision log", viewerProject.decisions));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Open questions", viewerProject.open_questions));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Observations", viewerProject.observations));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Library items", viewerProject.library_items));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Skills & behaviors", viewerProject.skills));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Recent changes", viewerProject.recent_changes));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Important files", viewerProject.important_files, true));
  dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Useful commands", viewerProject.commands, true));
  dom.memoryCoreViewerBody.appendChild(
    renderMemoryCoreSection(
      "Activity timeline",
      (viewerProject.activity_log || []).map((item) =>
        item?.at ? `[${item.at}] ${item.detail}` : item?.detail || ""
      )
    )
  );

  if (state.selectedMarkdown) {
    const markdown = document.createElement("section");
    markdown.className = "memorycore-page-markdown";
    const heading = document.createElement("div");
    heading.className = "memorycore-detail-heading";
    heading.innerHTML = `<strong>Full markdown snapshot</strong><span>Portable context</span>`;
    markdown.appendChild(heading);

    const rich = document.createElement("div");
    rich.className = "message-rich memorycore-markdown";
    appendFormattedBlocks(rich, state.selectedMarkdown);
    markdown.appendChild(rich);
    dom.memoryCoreViewerBody.appendChild(markdown);
  } else {
    dom.memoryCoreViewerBody.appendChild(renderMemoryCoreSection("Markdown snapshot", ["No markdown loaded for this project yet."]));
  }
}

function renderMemoryCoreMetricCard(label, value) {
  const card = document.createElement("article");
  card.className = "memorycore-metric-card";
  card.innerHTML = `
    <span class="memorycore-metric-label">${escapeHtml(label)}</span>
    <div class="memorycore-metric-value">${linkifyText(String(value || "None"))}</div>
  `;
  return card;
}

function renderMemoryCoreSection(title, items, code = false) {
  const section = document.createElement("section");
  section.className = "memorycore-detail-section";
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  section.innerHTML = `
    <div class="memorycore-detail-heading">
      <strong>${escapeHtml(title)}</strong>
      <span>${values.length ? `${values.length} item${values.length === 1 ? "" : "s"}` : "No entries"}</span>
    </div>
  `;

  if (!values.length) {
    const empty = document.createElement("div");
    empty.className = "memorycore-page-empty";
    empty.textContent = `No ${title.toLowerCase()} saved yet.`;
    section.appendChild(empty);
    return section;
  }

  const list = document.createElement("ul");
  list.className = "memorycore-detail-list";
  values.forEach((item) => {
    const li = document.createElement("li");
    if (code) {
      const codeNode = document.createElement("code");
      codeNode.className = "inline-code";
      codeNode.textContent = item;
      li.appendChild(codeNode);
    } else {
      appendInlineNodes(li, item);
    }
    list.appendChild(li);
  });
  section.appendChild(list);
  return section;
}

function renderMemoryCoreTagRow(label, items) {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  const wrap = document.createElement("div");
  wrap.className = "memorycore-tag-cluster";

  const heading = document.createElement("small");
  heading.textContent = label;
  wrap.appendChild(heading);

  if (!values.length) {
    const empty = document.createElement("div");
    empty.className = "memorycore-page-empty";
    empty.textContent = "Nothing saved yet.";
    wrap.appendChild(empty);
    return wrap;
  }

  const row = document.createElement("div");
  row.className = "memorycore-tag-row";
  values.forEach((item) => {
    const tag = document.createElement("span");
    tag.className = "memorycore-tag";
    tag.textContent = item;
    row.appendChild(tag);
  });
  wrap.appendChild(row);
  return wrap;
}

async function applyMemoryCoreTemplate(templateKey) {
  const project = state.selectedProject || state.projects.find((item) => item.project_key === state.selectedProjectKey);
  if (!project) return;

  try {
    await fetchJson(
      `/api/v1/memorycore/projects/${encodeURIComponent(project.project_key)}/templates/${encodeURIComponent(templateKey)}?user_id=${encodeURIComponent(state.userId)}`,
      { method: "POST" }
    );
    await loadMemoryCoreProject(project.project_key);
    renderAll();
  } catch (error) {
    console.error("Failed to apply template", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

async function toggleArchiveSelectedMemoryCoreProject() {
  const project = state.selectedProject || state.projects.find((item) => item.project_key === state.selectedProjectKey);
  if (!project) return;

  try {
    const nextStatus = project.status === "archived" ? "active" : "archived";
    const updated = await fetchJson(
      `/api/v1/memorycore/projects/${encodeURIComponent(project.project_key)}/status?user_id=${encodeURIComponent(state.userId)}`,
      {
        method: "POST",
        body: JSON.stringify({ status: nextStatus }),
      }
    );
    state.projects = state.projects.map((item) => (item.project_key === updated.project_key ? updated : item));
    state.selectedProject = updated;
    state.selectedProjectKey = updated.project_key;
    await loadMemoryCoreProject(updated.project_key);
  } catch (error) {
    console.error("Failed to update Memory Core status", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

async function deleteSelectedMemoryCoreProject() {
  const project = state.selectedProject || state.projects.find((item) => item.project_key === state.selectedProjectKey);
  if (!project) return;

  const confirmed = window.confirm(`Delete the Memory Core for "${project.title}"? This removes the saved cloud copy for this project.`);
  if (!confirmed) return;

  try {
    await fetchJson(
      `/api/v1/memorycore/projects/${encodeURIComponent(project.project_key)}?user_id=${encodeURIComponent(state.userId)}`,
      { method: "DELETE" }
    );
    state.selectedProject = null;
    state.selectedProjectKey = "";
    state.selectedMarkdown = "";
    await loadMemoryCoreSummary(Boolean(state.projects.length > 1));
  } catch (error) {
    console.error("Failed to delete Memory Core project", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

async function clearAllMemoryCore() {
  const confirmed = window.confirm("Clear the entire Memory Core profile and all project memories? This cannot be undone.");
  if (!confirmed) return;

  try {
    await fetchJson(`/api/v1/memorycore/?user_id=${encodeURIComponent(state.userId)}`, { method: "DELETE" });
    state.profile = null;
    state.projects = [];
    state.selectedProject = null;
    state.selectedProjectKey = "";
    state.selectedMarkdown = "";
    state.error = "";
    renderAll();
  } catch (error) {
    console.error("Failed to clear Memory Core", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

async function copyMemoryCoreMarkdown() {
  if (!state.selectedMarkdown) return;
  try {
    await navigator.clipboard.writeText(state.selectedMarkdown);
  } catch (error) {
    console.error("Failed to copy Memory Core markdown", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

function onWakeNameChanged() {
  state.wakeName = normalizeWakeName(dom.memoryCoreWakeNameInput.value || "jarvis");
  localStorage.setItem(storageKeys.memoryCoreWakeName, state.wakeName);
  renderLauncher();
  renderTemplates();
}

function onPlatformChanged() {
  state.platform = normalizeMemoryCorePlatform(dom.memoryCorePlatformSelect.value);
  localStorage.setItem(storageKeys.memoryCorePlatform, state.platform);
  renderLauncher();
}

async function downloadMemoryCoreBundle() {
  const wakeName = normalizeWakeName(state.wakeName || "jarvis");
  const platform = normalizeMemoryCorePlatform(state.platform);
  const serverUrl = window.location.origin;
  const url =
    `/api/v1/memorycore/download/launcher?user_id=${encodeURIComponent(state.userId)}` +
    `&server_url=${encodeURIComponent(serverUrl)}` +
    `&wake_name=${encodeURIComponent(wakeName)}` +
    `&platform=${encodeURIComponent(platform)}`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Request failed with ${response.status}`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const matched = disposition.match(/filename="([^"]+)"/i);
    const filename = matched?.[1] || `memorycore-${platform}-${wakeName}.zip`;
    downloadBlob(blob, filename);
  } catch (error) {
    console.error("Failed to download Memory Core launcher bundle", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

function downloadSelectedMemoryCoreMarkdown() {
  if (!state.selectedMarkdown) return;
  const filename = state.selectedProjectKey ? `${state.selectedProjectKey}-MEMORYCORE.md` : "MEMORYCORE.md";
  downloadBlob(new Blob([state.selectedMarkdown], { type: "text/markdown;charset=utf-8" }), filename);
}

async function downloadSelectedMasterMemory() {
  const project = state.selectedProject || state.projects.find((item) => item.project_key === state.selectedProjectKey);
  if (!project) return;

  try {
    const markdown = await fetchText(
      `/api/v1/memorycore/projects/${encodeURIComponent(project.project_key)}/master-memory?user_id=${encodeURIComponent(state.userId)}`
    );
    downloadBlob(
      new Blob([markdown], { type: "text/markdown;charset=utf-8" }),
      `${project.project_key}-master-memory.md`
    );
  } catch (error) {
    console.error("Failed to download master memory", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

async function onMemoryCoreImportFileSelected(event) {
  const file = event.target.files?.[0];
  dom.memoryCoreImportFile.value = "";
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file, file.name);
  if (state.selectedProjectKey) {
    formData.append("project_key", state.selectedProjectKey);
  }

  try {
    const response = await fetch(`/api/v1/memorycore/import/master-memory?user_id=${encodeURIComponent(state.userId)}`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `Request failed with ${response.status}`);
    }
    const imported = await response.json();
    state.selectedProjectKey = imported.project_key;
    await loadMemoryCoreSummary(true);
  } catch (error) {
    console.error("Failed to import master memory", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

async function startMemoryCoreBriefingChat() {
  const project = state.selectedProject || state.projects.find((item) => item.project_key === state.selectedProjectKey);
  if (!project) return;

  const sessionId = `web:${state.userId}:${createId()}`;
  try {
    const response = await fetchJson(
      `/api/v1/memorycore/projects/${encodeURIComponent(project.project_key)}/brief-to-session?user_id=${encodeURIComponent(state.userId)}&session_id=${encodeURIComponent(sessionId)}`,
      { method: "POST" }
    );
    localStorage.setItem(storageKeys.sessionId, response.session_id || sessionId);
    window.location.href = "/app";
  } catch (error) {
    console.error("Failed to start briefed chat", error);
    state.error = error.message || String(error);
    renderAll();
  }
}

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

function createId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeWakeName(value) {
  const normalized = String(value || "jarvis")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return normalized || "jarvis";
}

function detectMemoryCorePlatform() {
  const platform = navigator.platform || navigator.userAgent || "";
  const ua = navigator.userAgent || "";
  if (/Win/i.test(platform) || /Windows/i.test(ua)) {
    return "windows-x64";
  }
  if (/Mac/i.test(platform) || /Mac OS X/i.test(ua)) {
    return /arm|Apple/i.test(ua) ? "macos-arm64" : "macos-arm64";
  }
  return "windows-x64";
}

function normalizeMemoryCorePlatform(value) {
  const allowed = new Set(["windows-x64", "macos-arm64", "macos-x64"]);
  return allowed.has(value) ? value : "windows-x64";
}

function getMemoryCorePlatformLabel(value) {
  switch (value) {
    case "macos-arm64":
      return "macOS Apple Silicon";
    case "macos-x64":
      return "macOS Intel";
    default:
      return "Windows x64";
  }
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

function linkifyText(value) {
  const escaped = escapeHtml(value).replace(/\n/g, "<br>");
  return escaped
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>')
    .replace(/(^|[\s>])(\/memorycore(?:[^\s<]*)?)/g, '$1<a href="$2">$2</a>')
    .replace(/(^|[\s>])(\/app(?:[^\s<]*)?)/g, '$1<a href="$2">$2</a>');
}

function formatDateTime(value) {
  if (!value) return "recently";
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
  const tokenPattern = /(\*\*[^*]+?\*\*|`[^`]+`|https?:\/\/[^\s<]+|\/[a-z0-9-]+[^\s<]*)/gi;
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

function registerPWA() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/app-sw.js", { scope: "/" }).catch((error) => {
      console.error("Service worker registration failed", error);
    });
  }
}
