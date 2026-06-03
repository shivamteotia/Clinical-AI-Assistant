const state = {
  patients: [],
  selectedPatientId: null,
  apiKey: sessionStorage.getItem("clinical_admin_api_key") || "",
  userId: sessionStorage.getItem("clinical_admin_user_id") || "admin",
};

const els = {
  healthBadge: document.querySelector("#healthBadge"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  userIdInput: document.querySelector("#userIdInput"),
  patientSelect: document.querySelector("#patientSelect"),
  selectedPatientCard: document.querySelector("#selectedPatientCard"),
  inspectTitle: document.querySelector("#inspectTitle"),
  inspectMeta: document.querySelector("#inspectMeta"),
  inspectContent: document.querySelector("#inspectContent"),
};

els.apiKeyInput.value = state.apiKey;
els.userIdInput.value = state.userId;

async function api(path) {
  const headers = { "Content-Type": "application/json" };
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  if (state.userId) headers["X-User-Id"] = state.userId;

  const response = await fetch(path, { headers });
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

function formatData(value) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function authChanged() {
  state.apiKey = els.apiKeyInput.value.trim();
  state.userId = els.userIdInput.value.trim() || "admin";
  sessionStorage.setItem("clinical_admin_api_key", state.apiKey);
  sessionStorage.setItem("clinical_admin_user_id", state.userId);
}

async function loadHealth() {
  try {
    await api("/health");
    els.healthBadge.textContent = "Online";
    els.healthBadge.classList.remove("offline");
    els.healthBadge.classList.add("ready");
  } catch {
    els.healthBadge.textContent = "Offline";
    els.healthBadge.classList.add("offline");
    els.healthBadge.classList.remove("ready");
  }
}

async function loadPatients() {
  state.patients = await api("/patients");
  renderPatients();
  const requestedPatientId = new URLSearchParams(window.location.search).get("patient");
  const requestedPatient = state.patients.find((patient) => patient.patient_id === requestedPatientId);
  const initialPatientId = requestedPatient?.patient_id || state.patients[0]?.patient_id;
  if (initialPatientId) {
    selectPatient(initialPatientId);
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
  els.inspectTitle.textContent = `Inspecting ${patientId}`;
  els.inspectMeta.textContent = "Loading";
  els.inspectContent.textContent = "Loading pipeline stages...";
  els.inspectContent.classList.add("empty-state");

  try {
    const inspection = await api(`/patients/${encodeURIComponent(patientId)}/journey/inspect`);
    renderInspection(inspection);
  } catch (error) {
    els.inspectContent.innerHTML = `<div class="empty-state">Could not load inspection data. ${escapeHtml(error.message)}</div>`;
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

function renderInspection(inspection) {
  const patient = state.patients.find((item) => item.patient_id === inspection.patient_id);
  els.inspectTitle.textContent = patient
    ? `${patient.name} (${patient.patient_id})`
    : inspection.patient_id;
  els.inspectMeta.textContent = `${inspection.provider} - ${inspection.model}`;
  els.inspectContent.classList.remove("empty-state");
  els.inspectContent.innerHTML = inspection.stages
    .map((stage, index) => renderStage(stage, index + 1))
    .join("");
}

function renderStage(stage, index) {
  return `
    <article class="inspect-stage">
      <div class="inspect-stage-header">
        <div>
          <p class="eyebrow">Step ${index}</p>
          <h3>${escapeHtml(stage.title)}</h3>
        </div>
        <span class="status-pill muted-pill">${escapeHtml(stage.output_type)}</span>
      </div>
      <div class="inspect-meta-grid">
        ${metaItem("Source", stage.source)}
        ${metaItem("Shape", stage.output_shape)}
        ${metaBlock("Input", stage.input)}
      </div>
      <p class="inspect-note">${escapeHtml(stage.note)}</p>
      <pre class="inspect-data"><code>${escapeHtml(formatData(stage.data))}</code></pre>
    </article>
  `;
}

function metaItem(label, value) {
  return `
    <div class="inspect-meta-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function metaBlock(label, value) {
  return `
    <div class="inspect-meta-item inspect-meta-wide">
      <span>${escapeHtml(label)}</span>
      <pre><code>${escapeHtml(formatData(value))}</code></pre>
    </div>
  `;
}

els.apiKeyInput.addEventListener("change", () => {
  authChanged();
  if (state.selectedPatientId) selectPatient(state.selectedPatientId);
});
els.userIdInput.addEventListener("change", () => {
  authChanged();
  if (state.selectedPatientId) selectPatient(state.selectedPatientId);
});
els.patientSelect.addEventListener("change", (event) => selectPatient(event.target.value));

loadHealth();
loadPatients().catch((error) => {
  els.selectedPatientCard.innerHTML = `<div class="empty-state">Could not load patients. ${escapeHtml(error.message)}</div>`;
});
