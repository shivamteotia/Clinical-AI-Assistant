const state = {
  patients: [],
  selectedPatientId: null,
  mode: "fast",
};

const els = {
  healthBadge: document.querySelector("#healthBadge"),
  vectorBadge: document.querySelector("#vectorBadge"),
  patientSearch: document.querySelector("#patientSearch"),
  patientList: document.querySelector("#patientList"),
  patientTitle: document.querySelector("#patientTitle"),
  patientMeta: document.querySelector("#patientMeta"),
  recordContent: document.querySelector("#recordContent"),
  rebuildIndexBtn: document.querySelector("#rebuildIndexBtn"),
  simpleModeBtn: document.querySelector("#simpleModeBtn"),
  llmModeBtn: document.querySelector("#llmModeBtn"),
  questionInput: document.querySelector("#questionInput"),
  askBtn: document.querySelector("#askBtn"),
  answerBox: document.querySelector("#answerBox"),
  sourceCount: document.querySelector("#sourceCount"),
  sourcesList: document.querySelector("#sourcesList"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setLoading(button, label, loading) {
  button.disabled = loading;
  button.dataset.originalLabel = button.dataset.originalLabel || button.textContent;
  button.textContent = loading ? label : button.dataset.originalLabel;
}

async function loadHealth() {
  try {
    await api("/health");
    els.healthBadge.textContent = "Online";
    els.healthBadge.classList.remove("offline");
  } catch {
    els.healthBadge.textContent = "Offline";
    els.healthBadge.classList.add("offline");
  }
}

async function loadVectorStatus() {
  try {
    const status = await api("/rag/status");
    const provider = status.provider === "qdrant" ? "Qdrant" : "SQLite";
    const stateText = status.connected ? status.status : "offline";
    els.vectorBadge.textContent = `${provider}: ${stateText}`;
    els.vectorBadge.title = status.collection
      ? `Collection: ${status.collection}`
      : status.persist_path || "";
    els.vectorBadge.classList.toggle("offline", !status.connected);
    els.vectorBadge.classList.toggle("ready", status.connected && status.status === "ready");
  } catch {
    els.vectorBadge.textContent = "Vector: offline";
    els.vectorBadge.classList.add("offline");
  }
}

async function loadPatients() {
  state.patients = await api("/patients");
  renderPatients();
  if (state.patients.length > 0) {
    selectPatient(state.patients[0].patient_id);
  }
}

function renderPatients() {
  const query = els.patientSearch.value.trim().toLowerCase();
  const patients = state.patients.filter((patient) => {
    const text = `${patient.patient_id} ${patient.name} ${patient.gender} ${patient.address}`.toLowerCase();
    return text.includes(query);
  });

  els.patientList.innerHTML = patients
    .map(
      (patient) => `
        <button class="patient-item ${patient.patient_id === state.selectedPatientId ? "active" : ""}" type="button" data-patient-id="${escapeHtml(patient.patient_id)}">
          <div class="patient-name">
            <span>${escapeHtml(patient.name)}</span>
            <span>${escapeHtml(patient.patient_id)}</span>
          </div>
          <div class="patient-detail">${escapeHtml(patient.age)} yrs - ${escapeHtml(patient.gender)} - ${escapeHtml(patient.address)}</div>
        </button>
      `,
    )
    .join("");
}

async function selectPatient(patientId) {
  state.selectedPatientId = patientId;
  renderPatients();
  els.recordContent.textContent = "Loading patient record...";
  els.recordContent.classList.add("empty-state");

  try {
    const record = await api(`/patients/${encodeURIComponent(patientId)}/record`);
    renderRecord(record);
  } catch (error) {
    els.recordContent.textContent = `Could not load patient record. ${error.message}`;
  }
}

function renderRecord(record) {
  const patient = record.patient;
  els.patientTitle.textContent = `${patient.name} (${patient.patient_id})`;
  els.patientMeta.textContent = `${patient.age} yrs - ${patient.gender}`;
  els.recordContent.classList.remove("empty-state");
  els.recordContent.innerHTML = `
    ${section("Encounters", record.encounters, (row) => `
      <strong>${escapeHtml(row.diagnosis)}</strong>
      <span>${escapeHtml(row.date)} - ${escapeHtml(row.visit_type)}</span>
      <span>${escapeHtml(row.chief_complaint)}</span>
    `)}
    ${section("Labs", record.labs, (row) => `
      <strong>${escapeHtml(row.test_name)}: ${escapeHtml(row.value)} ${escapeHtml(row.unit)}</strong>
      <span>${escapeHtml(row.date)} - Ref: ${escapeHtml(row.reference_range)}</span>
    `)}
    ${section("Medications", record.medications, (row) => `
      <strong>${escapeHtml(row.drug_name)}</strong>
      <span>${escapeHtml(row.dose)} - ${escapeHtml(row.frequency)} - Start: ${escapeHtml(row.start_date)}</span>
    `)}
    ${section("Clinical Notes", record.clinical_notes, (row) => `
      <strong>${escapeHtml(row.note_type)} - ${escapeHtml(row.date)}</strong>
      <span>${escapeHtml(row.note_text)}</span>
    `)}
  `;
}

function section(title, rows, renderRow) {
  const content = rows.length
    ? rows.map((row) => `<div class="data-row">${renderRow(row)}</div>`).join("")
    : `<div class="data-row empty-state">No records found.</div>`;
  return `
    <div class="section-block">
      <h3>${escapeHtml(title)}</h3>
      <div class="data-grid">${content}</div>
    </div>
  `;
}

async function rebuildIndex() {
  setLoading(els.rebuildIndexBtn, "Rebuilding...", true);
  try {
    const result = await api("/rag/index", { method: "POST" });
    await loadVectorStatus();
    els.answerBox.classList.remove("empty-state");
    els.answerBox.innerHTML = `<div class="answer-text">Index rebuilt. ${result.chunk_count} chunks indexed.</div>`;
  } catch (error) {
    els.answerBox.innerHTML = `<div class="answer-text">Index rebuild failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.rebuildIndexBtn, "Rebuild Index", false);
  }
}

async function askQuestion() {
  const query = els.questionInput.value.trim();
  if (!query) {
    els.questionInput.focus();
    return;
  }

  const endpoint = state.mode === "llm" ? "/rag/ask-llm" : "/rag/ask";
  setLoading(els.askBtn, state.mode === "llm" ? "Thinking..." : "Searching...", true);
  els.answerBox.classList.add("empty-state");
  els.answerBox.textContent = state.mode === "llm" ? "Ollama is generating an answer..." : "Searching retrieved evidence...";
  els.sourcesList.innerHTML = "";
  els.sourceCount.textContent = "0 chunks";

  try {
    const result = await api(endpoint, {
      method: "POST",
      body: JSON.stringify({ query, k: 3 }),
    });
    renderAnswer(result);
    renderSources(result.sources || []);
  } catch (error) {
    els.answerBox.textContent = `Question failed. ${error.message}`;
  } finally {
    setLoading(els.askBtn, "Ask", false);
  }
}

function renderAnswer(result) {
  const warnings = result.safety_warnings || [];
  els.answerBox.classList.remove("empty-state");
  els.answerBox.innerHTML = `
    <div class="source-meta">
      <span class="confidence-pill">Confidence: ${escapeHtml(result.confidence || "unknown")}</span>
      ${result.model ? `<span>Model: ${escapeHtml(result.model)}</span>` : `<span>Mode: Fast retrieval</span>`}
    </div>
    <div class="answer-text">${escapeHtml(result.answer)}</div>
    ${
      warnings.length
        ? `<ul class="warning-list">${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
        : ""
    }
  `;
}

function renderSources(sources) {
  els.sourceCount.textContent = `${sources.length} chunk${sources.length === 1 ? "" : "s"}`;
  els.sourcesList.innerHTML = sources
    .map((source, index) => {
      const metadata = source.metadata || {};
      return `
        <article class="source-card">
          <div class="source-meta">
            <span>#${index + 1}</span>
            <span>${escapeHtml(metadata.patient_id)} - ${escapeHtml(metadata.patient_name)}</span>
            <span>Score ${Number(source.score || 0).toFixed(3)}</span>
          </div>
          <div class="source-text">${escapeHtml(source.page_content)}</div>
        </article>
      `;
    })
    .join("");
}

function setMode(mode) {
  state.mode = mode;
  els.simpleModeBtn.classList.toggle("active", mode === "fast");
  els.llmModeBtn.classList.toggle("active", mode === "llm");
}

els.patientSearch.addEventListener("input", renderPatients);
els.patientList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-patient-id]");
  if (button) selectPatient(button.dataset.patientId);
});
els.rebuildIndexBtn.addEventListener("click", rebuildIndex);
els.askBtn.addEventListener("click", askQuestion);
els.questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    askQuestion();
  }
});
els.simpleModeBtn.addEventListener("click", () => setMode("fast"));
els.llmModeBtn.addEventListener("click", () => setMode("llm"));
document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    els.questionInput.value = button.dataset.query;
    askQuestion();
  });
});

loadHealth();
loadVectorStatus();
loadPatients().catch((error) => {
  els.patientList.innerHTML = `<div class="empty-state">Could not load patients. ${escapeHtml(error.message)}</div>`;
});
