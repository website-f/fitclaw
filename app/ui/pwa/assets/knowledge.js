/* Knowledge base mini-app — upload + list + delete + ask */
"use strict";

const USER_KEY = "fitclaw.userId";

const state = {
  userId: localStorage.getItem(USER_KEY) || "fitclaw",
  documents: [],
  selectedFile: null,
  loading: false,
};

const dom = {};

window.addEventListener("DOMContentLoaded", () => {
  cacheDom();
  bindEvents();
  void refreshDocuments();
});

function cacheDom() {
  dom.uploadForm = document.getElementById("kbUploadForm");
  dom.title = document.getElementById("kbTitle");
  dom.department = document.getElementById("kbDepartment");
  dom.tags = document.getElementById("kbTags");
  dom.fileInput = document.getElementById("kbFile");
  dom.dropzone = document.getElementById("kbDropzone");
  dom.dropzoneHint = document.getElementById("kbDropzoneHint");
  dom.uploadButton = document.getElementById("kbUploadButton");
  dom.uploadStatus = document.getElementById("kbUploadStatus");
  dom.askForm = document.getElementById("kbAskForm");
  dom.question = document.getElementById("kbQuestion");
  dom.askDepartment = document.getElementById("kbAskDepartment");
  dom.askButton = document.getElementById("kbAskButton");
  dom.answer = document.getElementById("kbAnswer");
  dom.docList = document.getElementById("kbDocList");
  dom.refreshButton = document.getElementById("kbRefresh");
}

function bindEvents() {
  dom.uploadForm.addEventListener("submit", onUploadSubmit);
  dom.fileInput.addEventListener("change", onFileSelected);
  dom.dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dom.dropzone.classList.add("is-dragging");
  });
  dom.dropzone.addEventListener("dragleave", () => dom.dropzone.classList.remove("is-dragging"));
  dom.dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dom.dropzone.classList.remove("is-dragging");
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      dom.fileInput.files = event.dataTransfer.files;
      onFileSelected();
    }
  });
  dom.askForm.addEventListener("submit", onAskSubmit);
  dom.refreshButton.addEventListener("click", () => void refreshDocuments());
}

function onFileSelected() {
  const file = dom.fileInput.files?.[0] || null;
  state.selectedFile = file;
  dom.dropzoneHint.textContent = file ? `${file.name} — ${(file.size / 1024).toFixed(1)} KB` : "Nothing selected yet.";
}

async function onUploadSubmit(event) {
  event.preventDefault();
  if (!state.selectedFile) {
    setUploadStatus("Pick a file first.", "error");
    return;
  }
  const form = new FormData();
  form.append("user_id", state.userId);
  form.append("file", state.selectedFile, state.selectedFile.name);
  if (dom.title.value.trim()) form.append("title", dom.title.value.trim());
  if (dom.department.value) form.append("department", dom.department.value);
  if (dom.tags.value.trim()) form.append("tags", dom.tags.value.trim());

  setUploadStatus("Indexing…", "pending");
  dom.uploadButton.disabled = true;
  try {
    const response = await fetch("/api/v1/knowledge/documents", { method: "POST", body: form });
    if (!response.ok) {
      const detail = await safeError(response);
      throw new Error(detail || `Upload failed (${response.status})`);
    }
    const payload = await response.json();
    setUploadStatus(`Indexed ${payload.chunks_indexed} chunks from ${payload.document.title}.`, "ok");
    dom.uploadForm.reset();
    state.selectedFile = null;
    dom.dropzoneHint.textContent = "Nothing selected yet.";
    await refreshDocuments();
  } catch (error) {
    setUploadStatus(error.message || String(error), "error");
  } finally {
    dom.uploadButton.disabled = false;
  }
}

async function onAskSubmit(event) {
  event.preventDefault();
  const question = dom.question.value.trim();
  if (!question) return;
  dom.askButton.disabled = true;
  dom.answer.hidden = false;
  dom.answer.innerHTML = `<p class="kb-thinking">Searching the knowledge base…</p>`;
  try {
    const payload = {
      user_id: state.userId,
      question,
      department: dom.askDepartment.value || null,
      limit: 4,
    };
    const response = await fetch("/api/v1/knowledge/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await safeError(response);
      throw new Error(detail || `Ask failed (${response.status})`);
    }
    renderAnswer(await response.json());
  } catch (error) {
    dom.answer.innerHTML = `<p class="kb-error">${escapeHtml(error.message || String(error))}</p>`;
  } finally {
    dom.askButton.disabled = false;
  }
}

function renderAnswer(payload) {
  const citations = payload.citations || [];
  const context = payload.used_context || [];
  const provider = payload.provider ? `<small class="kb-answer-meta">via ${escapeHtml(payload.provider)}</small>` : "";
  const citationList = citations
    .map((cite) => `<li><code>[KB:${escapeHtml(cite.doc_id)}#${cite.chunk_index}]</code> ${escapeHtml(cite.title)}${cite.source ? ` <small>· ${escapeHtml(cite.source)}</small>` : ""}</li>`)
    .join("");
  const contextBlocks = context
    .map(
      (hit) =>
        `<details class="kb-context-block"><summary>${escapeHtml(hit.title)} <small>#${hit.chunk_index} · score ${hit.score.toFixed(3)}</small></summary><p>${escapeHtml(hit.text)}</p></details>`
    )
    .join("");
  dom.answer.innerHTML = `
    <header class="kb-answer-head">
      <h3>Answer</h3>
      ${provider}
    </header>
    <p class="kb-answer-body">${formatAnswer(payload.answer)}</p>
    ${citations.length ? `<h4>Citations</h4><ul class="kb-citations">${citationList}</ul>` : ""}
    ${context.length ? `<h4>Context retrieved</h4><div class="kb-context-list">${contextBlocks}</div>` : ""}
  `;
}

function formatAnswer(text) {
  return escapeHtml(text || "").replace(/\[KB:([a-z0-9_]+)#(\d+)\]/gi, '<code class="kb-cite">[KB:$1#$2]</code>').replace(/\n/g, "<br>");
}

async function refreshDocuments() {
  if (state.loading) return;
  state.loading = true;
  dom.docList.innerHTML = `<p class="kb-empty">Loading…</p>`;
  try {
    const response = await fetch(`/api/v1/knowledge/documents?user_id=${encodeURIComponent(state.userId)}`);
    if (!response.ok) {
      const detail = await safeError(response);
      throw new Error(detail || `List failed (${response.status})`);
    }
    state.documents = await response.json();
    renderDocuments();
  } catch (error) {
    dom.docList.innerHTML = `<p class="kb-error">${escapeHtml(error.message || String(error))}</p>`;
  } finally {
    state.loading = false;
  }
}

function renderDocuments() {
  if (!state.documents.length) {
    dom.docList.innerHTML = `<p class="kb-empty">No documents indexed yet. Upload one above.</p>`;
    return;
  }
  const rows = state.documents
    .map((doc) => {
      const dept = doc.department ? `<span class="kb-pill kb-pill-dept">${escapeHtml(doc.department)}</span>` : "";
      const tags = (doc.tags || []).map((tag) => `<span class="kb-pill">${escapeHtml(tag)}</span>`).join("");
      const error = doc.error ? `<p class="kb-error-row">${escapeHtml(doc.error)}</p>` : "";
      return `
        <article class="kb-doc" data-doc-id="${escapeHtml(doc.doc_id)}">
          <header>
            <strong>${escapeHtml(doc.title)}</strong>
            <span class="kb-doc-kind">${escapeHtml(doc.kind.toUpperCase())}</span>
          </header>
          <p class="kb-doc-source">${escapeHtml(doc.source || "")}</p>
          <p class="kb-doc-meta">
            ${doc.chunk_count} chunks · ${doc.char_count.toLocaleString()} chars · uploaded ${formatDate(doc.uploaded_at)}
          </p>
          <div class="kb-doc-tags">${dept}${tags}</div>
          ${error}
          <div class="kb-doc-actions">
            <button type="button" class="text-button" data-action="copy" data-doc-id="${escapeHtml(doc.doc_id)}">Copy ID</button>
            <button type="button" class="text-button danger" data-action="delete" data-doc-id="${escapeHtml(doc.doc_id)}">Delete</button>
          </div>
        </article>
      `;
    })
    .join("");
  dom.docList.innerHTML = rows;
  dom.docList.querySelectorAll("button[data-action=delete]").forEach((button) => {
    button.addEventListener("click", () => deleteDocument(button.dataset.docId));
  });
  dom.docList.querySelectorAll("button[data-action=copy]").forEach((button) => {
    button.addEventListener("click", () => navigator.clipboard?.writeText(button.dataset.docId));
  });
}

async function deleteDocument(docId) {
  if (!docId || !confirm(`Delete document ${docId}? This removes its chunks too.`)) return;
  try {
    const response = await fetch(
      `/api/v1/knowledge/documents/${encodeURIComponent(docId)}?user_id=${encodeURIComponent(state.userId)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      const detail = await safeError(response);
      throw new Error(detail || `Delete failed (${response.status})`);
    }
    await refreshDocuments();
  } catch (error) {
    alert(error.message || String(error));
  }
}

function setUploadStatus(text, kind) {
  dom.uploadStatus.textContent = text || "";
  dom.uploadStatus.dataset.kind = kind || "";
}

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
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

async function safeError(response) {
  try {
    const data = await response.json();
    return data.detail || data.error || null;
  } catch {
    return null;
  }
}
