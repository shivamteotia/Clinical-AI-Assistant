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
    <div id="journeyContent" class="journey-block empty-state">Loading pre-generated holistic patient view...</div>
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
        <p class="eyebrow">Holistic Patient View</p>
        <h3>${escapeHtml(journey.current_focus || "Clinical journey")}</h3>
      </div>
      <div class="journey-status-stack">
        <span class="status-pill ${journey.is_stale ? "offline" : "ready"}">${journey.is_stale ? "Stale" : "Current"}</span>
        <span class="status-pill muted-pill">${escapeHtml(journey.generated_by || "stored")}</span>
      </div>
    </div>
    <div class="journey-meta-line">
      <span>Generated: ${escapeHtml(journey.generated_at || "unknown")}</span>
      <span>Record: ${escapeHtml(journey.source_record_version || "unknown")}</span>
    </div>
    <p>${escapeHtml(journey.summary)}</p>
    ${renderJourneyFeedbackControls(journey)}
    ${renderGroundedClaims(journey.claims)}
    ${renderJourneyList("Timeline", journey.timeline, (item) => `
      <strong>${escapeHtml(item.date)} - ${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.type)} - ${escapeHtml(item.detail)}</span>
    `)}
    ${renderSimpleList("Key labs", journey.key_labs)}
    ${renderSimpleList("Active medications", journey.active_medications)}
    <div class="journey-notice">${escapeHtml(journey.safety_notice)}</div>
  `;
}


function renderJourneyFeedbackControls(journey) {
  return `
    <div class="journey-feedback" aria-live="polite">
      <div class="mini-heading">Clinician feedback</div>
      <div class="feedback-actions">
        <button class="secondary-button feedback-button" type="button" data-feedback-type="useful">Useful</button>
        <button class="secondary-button feedback-button" type="button" data-feedback-type="missing_info">Missing info</button>
        <button class="secondary-button feedback-button" type="button" data-feedback-type="incorrect">Incorrect</button>
      </div>
      <label class="feedback-comment">
        <span>Optional note</span>
        <textarea id="journeyFeedbackComment" maxlength="500" placeholder="Short feedback for the AI/admin team"></textarea>
      </label>
      <div id="journeyFeedbackStatus" class="inspect-note"></div>
    </div>
  `;
}

async function submitJourneyFeedback(feedbackType, button) {
  if (!state.selectedPatientId) return;
  const commentInput = document.querySelector("#journeyFeedbackComment");
  const status = document.querySelector("#journeyFeedbackStatus");
  if (button) setLoading(button, "Saving...", true);
  if (status) status.textContent = "Saving feedback...";
  try {
    await api(`/patients/${encodeURIComponent(state.selectedPatientId)}/journey/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback_type: feedbackType, comment: commentInput?.value || null }),
    });
    if (commentInput) commentInput.value = "";
    if (status) status.textContent = "Feedback recorded.";
  } catch (error) {
    if (status) status.textContent = `Feedback failed. ${error.message}`;
  } finally {
    if (button) setLoading(button, "", false);
  }
}
function renderLatestRunMeta(run) {
  if (!run) return "";
  return `
      <span>Run: ${escapeHtml(run.status)} / ${escapeHtml(run.trigger || "generation")}</span>
      <span>Tokens est: ${escapeHtml(run.estimated_input_tokens || "unknown")}</span>
      <span>Duration: ${escapeHtml(run.duration_ms ?? "unknown")} ms</span>`;
}
function renderGroundedClaims(claims) {
  if (!claims || claims.length === 0) return "";
  return `
    <div class="journey-mini-section">
      <div class="mini-heading">Source-grounded claims</div>
      <div class="claim-list">
        ${claims.map((claim) => `
          <div class="claim-row">
            <span>${escapeHtml(claim.sentence)}</span>
            <div class="source-chip-row">
              ${(claim.sources || []).map((source) => `<span class="source-chip">${escapeHtml(source)}</span>`).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    </div>
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


async function refreshSelectedJourney() {
  if (!state.selectedPatientId) return;
  const button = document.querySelector("#refreshJourneyBtn");
  if (button) setLoading(button, "Refreshing...", true);
  try {
    const result = await api(`/patients/${encodeURIComponent(state.selectedPatientId)}/journey/refresh`, {
      method: "POST",
      body: JSON.stringify({ use_llm: true, require_llm: false, background: false }),
    });
    if (result.journey) {
      renderJourney(result.journey);
    }
  } catch (error) {
    const container = document.querySelector("#journeyContent");
    if (container) {
      container.insertAdjacentHTML("afterbegin", `<div class="journey-error">Refresh failed. ${escapeHtml(error.message)}</div>`);
    }
  } finally {
    const currentButton = document.querySelector("#refreshJourneyBtn");
    if (currentButton) setLoading(currentButton, "Refresh", false);
  }
}
async function rebuildIndex() {
  setLoading(els.rebuildIndexBtn, "Rebuilding...", true);
  try {
    await api("/rag/index", { method: "POST" });
    await loadVectorStatus();
  } catch (error) {
    els.recordContent.innerHTML = `<div class="empty-state">Index rebuild failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.rebuildIndexBtn, "Rebuild Index", false);
  }
}

els.patientSelect.addEventListener("change", (event) => selectPatient(event.target.value));
els.rebuildIndexBtn.addEventListener("click", rebuildIndex);
els.recordContent.addEventListener("click", (event) => {
  if (event.target?.id === "refreshJourneyBtn") refreshSelectedJourney();
});

loadHealth();
loadVectorStatus();
loadPatients().catch((error) => {
  els.selectedPatientCard.innerHTML = `<div class="empty-state">Could not load patients. ${escapeHtml(error.message)}</div>`;
});
