const state = {
  patients: [],
  selectedPatientId: null,
  mode: "fast",
};

const els = {
  healthBadge: document.querySelector("#healthBadge"),
  vectorBadge: document.querySelector("#vectorBadge"),
  patientSelect: document.querySelector("#patientSelect"),
  selectedPatientCard: document.querySelector("#selectedPatientCard"),
  patientTitle: document.querySelector("#patientTitle"),
  patientMeta: document.querySelector("#patientMeta"),
  recordContent: document.querySelector("#recordContent"),
  rebuildIndexBtn: document.querySelector("#rebuildIndexBtn"),
  generateJourneyBtn: document.querySelector("#generateJourneyBtn"),
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
  els.patientSelect.innerHTML = state.patients
    .map(
      (patient) => `<option value="${escapeHtml(patient.patient_id)}">${escapeHtml(patient.patient_id)} - ${escapeHtml(patient.name)}</option>`,
    )
    .join("");
  if (state.selectedPatientId) {
    els.patientSelect.value = state.selectedPatientId;
  }
}

async function selectPatient(patientId) {
  state.selectedPatientId = patientId;
  renderPatients();
  renderSelectedPatientCard(patientId);
  els.recordContent.textContent = "Loading patient record...";
  els.recordContent.classList.add("empty-state");
  els.answerBox.classList.add("empty-state");
  els.answerBox.textContent = "Ask a question to query this selected patient's journey and retrieved record evidence.";
  els.sourcesList.innerHTML = "";
  els.sourceCount.textContent = "0 chunks";

  try {
    const [record, journey] = await Promise.all([
      api(`/patients/${encodeURIComponent(patientId)}/record`),
      api(`/patients/${encodeURIComponent(patientId)}/journey`),
    ]);
    renderRecord(record);
    renderJourney(journey);
  } catch (error) {
    els.recordContent.textContent = `Could not load patient record. ${error.message}`;
  }
}

function renderSelectedPatientCard(patientId) {
  const patient = state.patients.find((item) => item.patient_id === patientId);
  if (!patient) return;

  els.selectedPatientCard.classList.remove("empty-state");
  els.selectedPatientCard.innerHTML = `
    <div class="patient-name">
      <span>${escapeHtml(patient.name)}</span>
      <span>${escapeHtml(patient.patient_id)}</span>
    </div>
    <div class="patient-detail">${escapeHtml(patient.age)} yrs - ${escapeHtml(patient.gender)} - ${escapeHtml(patient.address)}</div>
  `;
}

function renderRecord(record) {
  const patient = record.patient;
  els.patientTitle.textContent = `${patient.name} (${patient.patient_id})`;
  els.patientMeta.textContent = `${patient.age} yrs - ${patient.gender}`;
  els.recordContent.classList.remove("empty-state");
  els.recordContent.innerHTML = `
    <div id="journeyContent" class="journey-block empty-state">Loading generated patient journey...</div>
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

function renderJourney(journey) {
  const container = document.querySelector("#journeyContent");
  if (!container) return;

  container.classList.remove("empty-state");
  container.innerHTML = `
    <div class="journey-header">
      <div>
        <p class="eyebrow">Generated Patient Journey</p>
        <h3>${escapeHtml(journey.current_focus || "Clinical journey")}</h3>
      </div>
      <span class="status-pill muted-pill">${escapeHtml(journey.generated_by || "stored")}</span>
    </div>
    <p>${escapeHtml(journey.summary)}</p>
    ${renderJourneyList("Timeline", journey.timeline, (item) => `
      <strong>${escapeHtml(item.date)} - ${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.type)} - ${escapeHtml(item.detail)}</span>
    `)}
    ${renderSimpleList("Key labs", journey.key_labs)}
    ${renderSimpleList("Active medications", journey.active_medications)}
    <div class="journey-notice">${escapeHtml(journey.safety_notice)}</div>
  `;
}

function renderJourneyList(title, rows, renderRow) {
  if (!rows || rows.length === 0) return "";
  return `
    <div class="journey-mini-section">
      <div class="mini-heading">${escapeHtml(title)}</div>
      <div class="data-grid">${rows.map((row) => `<div class="data-row">${renderRow(row)}</div>`).join("")}</div>
    </div>
  `;
}

function renderSimpleList(title, rows) {
  if (!rows || rows.length === 0) return "";
  return `
    <div class="journey-mini-section">
      <div class="mini-heading">${escapeHtml(title)}</div>
      <ul class="compact-list">${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>
    </div>
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

async function generateJourney() {
  if (!state.selectedPatientId) return;

  setLoading(els.generateJourneyBtn, "Generating...", true);
  try {
    const journey = await api(`/patients/${encodeURIComponent(state.selectedPatientId)}/journey/generate`, {
      method: "POST",
      body: JSON.stringify({ use_llm: true, model: "phi3" }),
    });
    renderJourney(journey);
    els.answerBox.classList.remove("empty-state");
    els.answerBox.innerHTML = `<div class="answer-text">Patient journey generated and stored using ${escapeHtml(journey.generated_by)}.</div>`;
  } catch (error) {
    els.answerBox.classList.remove("empty-state");
    els.answerBox.innerHTML = `<div class="answer-text">Journey generation failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.generateJourneyBtn, "Generate LLM Journey", false);
  }
}

async function askQuestion() {
  const query = els.questionInput.value.trim();
  if (!query) {
    els.questionInput.focus();
    return;
  }

  const endpoint = state.selectedPatientId
    ? `/patients/${encodeURIComponent(state.selectedPatientId)}/${state.mode === "llm" ? "ask-llm" : "ask"}`
    : state.mode === "llm" ? "/rag/ask-llm" : "/rag/ask";
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
  const limitations = result.limitations || [];
  const evidence = result.evidence || [];
  els.answerBox.classList.remove("empty-state");
  els.answerBox.innerHTML = `
    <div class="source-meta">
      <span class="confidence-pill">Confidence: ${escapeHtml(result.confidence || "unknown")}</span>
      <span>Intent: ${escapeHtml(formatLabel(result.intent || "unknown"))}</span>
      <span>Safety: ${escapeHtml(formatLabel(result.safety_level || "unknown"))}</span>
      ${result.model ? `<span>Model: ${escapeHtml(result.model)}</span>` : `<span>Mode: Fast retrieval</span>`}
    </div>
    <div class="answer-text">${escapeHtml(result.answer)}</div>
    ${
      evidence.length
        ? `<div class="evidence-list">
            <div class="mini-heading">Evidence</div>
            ${evidence.map(renderEvidenceItem).join("")}
          </div>`
        : ""
    }
    ${
      warnings.length
        ? `<ul class="warning-list">${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
        : ""
    }
    ${
      limitations.length
        ? `<ul class="limitation-list">${limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : ""
    }
  `;
}

function renderEvidenceItem(item) {
  return `
    <div class="evidence-item">
      <div class="source-meta">
        <span>${escapeHtml(item.patient_id)} - ${escapeHtml(item.patient_name)}</span>
        <span>Chunk ${escapeHtml(item.chunk_index ?? "n/a")}</span>
        <span>Score ${Number(item.score || 0).toFixed(3)}</span>
      </div>
      <div>${escapeHtml(item.text)}</div>
    </div>
  `;
}

function formatLabel(value) {
  return String(value).replaceAll("_", " ");
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

els.patientSelect.addEventListener("change", (event) => selectPatient(event.target.value));
els.rebuildIndexBtn.addEventListener("click", rebuildIndex);
els.generateJourneyBtn.addEventListener("click", generateJourney);
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
  els.selectedPatientCard.innerHTML = `<div class="empty-state">Could not load patients. ${escapeHtml(error.message)}</div>`;
});
