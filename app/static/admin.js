const state = {
  patients: [],
  selectedPatientId: null,
  apiKey: sessionStorage.getItem("clinical_admin_api_key") || "",
  userId: sessionStorage.getItem("clinical_admin_user_id") || "admin",
};

const els = {
  healthBadge: document.querySelector("#healthBadge"),
  vectorBadge: document.querySelector("#vectorBadge"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  userIdInput: document.querySelector("#userIdInput"),
  patientSelect: document.querySelector("#patientSelect"),
  selectedPatientCard: document.querySelector("#selectedPatientCard"),
  refreshDashboardBtn: document.querySelector("#refreshDashboardBtn"),
  rebuildIndexBtn: document.querySelector("#rebuildIndexBtn"),
  refreshStaleBtn: document.querySelector("#refreshStaleBtn"),
  scanHisBtn: document.querySelector("#scanHisBtn"),
  queueHisBtn: document.querySelector("#queueHisBtn"),
  processQueueBtn: document.querySelector("#processQueueBtn"),
  refreshJourneyBtn: document.querySelector("#refreshJourneyBtn"),
  inspectPatientBtn: document.querySelector("#inspectPatientBtn"),
  dashboardMeta: document.querySelector("#dashboardMeta"),
  apiMetric: document.querySelector("#apiMetric"),
  vectorMetric: document.querySelector("#vectorMetric"),
  staleMetric: document.querySelector("#staleMetric"),
  runMetric: document.querySelector("#runMetric"),
  systemSnapshot: document.querySelector("#systemSnapshot"),
  patientOpsMeta: document.querySelector("#patientOpsMeta"),
  patientOpsContent: document.querySelector("#patientOpsContent"),
  hisSyncMeta: document.querySelector("#hisSyncMeta"),
  hisSyncList: document.querySelector("#hisSyncList"),
  queueMeta: document.querySelector("#queueMeta"),
  queueList: document.querySelector("#queueList"),
  staleMeta: document.querySelector("#staleMeta"),
  staleList: document.querySelector("#staleList"),
  runsMeta: document.querySelector("#runsMeta"),
  runsList: document.querySelector("#runsList"),
  feedbackMeta: document.querySelector("#feedbackMeta"),
  feedbackList: document.querySelector("#feedbackList"),
  auditMeta: document.querySelector("#auditMeta"),
  auditList: document.querySelector("#auditList"),
};

els.apiKeyInput.value = state.apiKey;
els.userIdInput.value = state.userId;

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  if (state.userId) headers["X-User-Id"] = state.userId;

  const response = await fetch(path, { ...options, headers });
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

function compactDate(value) {
  if (!value) return "unknown";
  return String(value).replace("T", " ").replace("Z", "").slice(0, 19);
}

function setLoading(button, label, loading) {
  button.disabled = loading;
  button.dataset.originalLabel = button.dataset.originalLabel || button.textContent;
  button.textContent = loading ? label : button.dataset.originalLabel;
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
    els.apiMetric.textContent = "Online";
  } catch {
    els.healthBadge.textContent = "Offline";
    els.healthBadge.classList.add("offline");
    els.healthBadge.classList.remove("ready");
    els.apiMetric.textContent = "Offline";
  }
}

async function loadAdminStatus() {
  try {
    const status = await api("/admin/status");
    const authMode = status.auth?.enabled ? "enabled" : "open local dev";
    const vector = status.vector_store || {};
    const journeyLlm = status.journey_llm || {};
    const journeys = status.journeys || {};
    const audit = status.audit || {};
    els.staleMetric.textContent = String(journeys.stale_count ?? 0);
    els.runMetric.textContent = journeys.latest_run_status
      ? `${journeys.latest_run_status} / ${journeys.latest_run_patient_id || "patient?"}`
      : "No runs";
    els.systemSnapshot.classList.remove("empty-state");
    els.systemSnapshot.innerHTML = `
      <div class="data-row">
        <strong>Auth</strong>
        <span>Mode: ${escapeHtml(authMode)}</span>
        <span>Doctor key configured: ${status.auth?.doctor_key_configured ? "yes" : "no"}</span>
        <span>Admin key configured: ${status.auth?.admin_key_configured ? "yes" : "no"}</span>
      </div>
      <div class="data-row">
        <strong>Vector store</strong>
        <span>Configured: ${escapeHtml(vector.configured_provider || "unknown")}</span>
        <span>Active: ${escapeHtml(vector.active_provider || "unknown")} / ${escapeHtml(vector.status || "unknown")}</span>
        <span>Collection: ${escapeHtml(vector.collection || "none")}</span>
        <span>Qdrant URL configured: ${vector.qdrant_url_configured ? "yes" : "no"}</span>
        <span>Qdrant key configured: ${vector.qdrant_api_key_configured ? "yes" : "no"}</span>
      </div>
      <div class="data-row">
        <strong>Journey LLM</strong>
        <span>Provider: ${escapeHtml(journeyLlm.provider || "unknown")}</span>
        <span>Model: ${escapeHtml(journeyLlm.model || "unknown")}</span>
        <span>Groq key configured: ${journeyLlm.groq_api_key_configured ? "yes" : "no"}</span>
      </div>
      <div class="data-row">
        <strong>Recent activity</strong>
        <span>Stale journeys: ${escapeHtml(journeys.stale_count ?? 0)}</span>
        <span>Recent runs sampled: ${escapeHtml(journeys.recent_run_count ?? 0)}</span>
        <span>Recent audit events sampled: ${escapeHtml(audit.recent_event_count ?? 0)}</span>
        <span>Latest audit event: ${escapeHtml(audit.latest_event_type || "none")}</span>
      </div>
    `;
  } catch (error) {
    els.systemSnapshot.innerHTML = `<div class="data-row empty-state">Could not load system status. ${escapeHtml(error.message)}</div>`;
  }
}
async function loadVectorStatus() {
  try {
    const status = await api("/rag/status");
    const provider = status.provider === "qdrant" ? "Qdrant" : "SQLite";
    const stateText = status.connected ? status.status : "offline";
    const chunks = Number.isFinite(status.chunk_count) ? `${status.chunk_count} chunks` : "chunks unknown";
    els.vectorBadge.textContent = `${provider}: ${stateText}`;
    els.vectorBadge.title = status.collection ? `Collection: ${status.collection}` : status.persist_path || "";
    els.vectorBadge.classList.toggle("offline", !status.connected);
    els.vectorBadge.classList.toggle("ready", status.connected && status.status === "ready");
    els.vectorMetric.textContent = `${provider} / ${stateText} / ${chunks}`;
  } catch (error) {
    els.vectorBadge.textContent = "Vector: offline";
    els.vectorBadge.classList.add("offline");
    els.vectorMetric.textContent = `Failed: ${error.message}`;
  }
}

async function loadPatients() {
  state.patients = await api("/patients");
  els.patientSelect.innerHTML = state.patients
    .map((patient) => `<option value="${escapeHtml(patient.patient_id)}">${escapeHtml(patient.patient_id)} - ${escapeHtml(patient.name)}</option>`)
    .join("");

  if (!state.selectedPatientId && state.patients.length > 0) {
    state.selectedPatientId = state.patients[0].patient_id;
  }
  if (state.selectedPatientId) {
    els.patientSelect.value = state.selectedPatientId;
    await selectPatient(state.selectedPatientId);
  }
}

async function selectPatient(patientId) {
  state.selectedPatientId = patientId;
  const patient = state.patients.find((item) => item.patient_id === patientId);
  if (patient) {
    els.selectedPatientCard.classList.remove("empty-state");
    els.selectedPatientCard.innerHTML = `
      <div class="patient-name">
        <span>${escapeHtml(patient.name)}</span>
        <span>${escapeHtml(patient.patient_id)}</span>
      </div>
      <div class="patient-detail">${escapeHtml(patient.age)} yrs - ${escapeHtml(patient.gender)} - ${escapeHtml(patient.address)}</div>
    `;
  }
  await loadSelectedPatientOps();
}

async function loadSelectedPatientOps() {
  if (!state.selectedPatientId) return;
  els.patientOpsContent.textContent = "Loading patient operations...";
  els.patientOpsContent.classList.add("empty-state");
  try {
    const [record, journey, runs] = await Promise.all([
      api(`/patients/${encodeURIComponent(state.selectedPatientId)}/record`),
      api(`/patients/${encodeURIComponent(state.selectedPatientId)}/journey`),
      api(`/patients/${encodeURIComponent(state.selectedPatientId)}/journey/runs?limit=5`),
    ]);
    const metadata = record.record_metadata || {};
    const latestRun = runs[0];
    els.patientOpsMeta.textContent = `${record.patient.name} (${record.patient.patient_id})`;
    els.patientOpsContent.classList.remove("empty-state");
    els.patientOpsContent.innerHTML = `
      <div class="data-row">
        <strong>Canonical record</strong>
        <span>Version: ${escapeHtml(metadata.record_version || "unknown")}</span>
        <span>Updated: ${escapeHtml(metadata.last_updated || "unknown")}</span>
      </div>
      <div class="data-row">
        <strong>Stored journey</strong>
        <span>Status: ${journey.is_stale ? "stale" : "current"}</span>
        <span>Generated by: ${escapeHtml(journey.generated_by || "unknown")}</span>
        <span>Model: ${escapeHtml(journey.journey_model || "unknown")}</span>
      </div>
      <div class="data-row">
        <strong>Latest run</strong>
        <span>${latestRun ? `${escapeHtml(latestRun.status)} / ${escapeHtml(latestRun.trigger || "generation")}` : "No run logs found"}</span>
        <span>${latestRun ? `Duration: ${escapeHtml(latestRun.duration_ms ?? "unknown")} ms` : ""}</span>
      </div>
    `;
  } catch (error) {
    els.patientOpsContent.innerHTML = `<div class="data-row empty-state">Could not load patient operations. ${escapeHtml(error.message)}</div>`;
  }
}

async function loadHisSyncStatus() {
  try {
    const result = await api("/his/sync/status");
    els.hisSyncMeta.textContent = `${result.action_required_count || 0} action needed`;
    const rows = result.items || [];
    if (rows.length === 0) {
      els.hisSyncList.classList.add("empty-state");
      els.hisSyncList.textContent = "No new or changed HIS patient records found.";
      return;
    }
    els.hisSyncList.classList.remove("empty-state");
    els.hisSyncList.innerHTML = rows.map((item) => `
      <div class="admin-table-row">
        <strong>${escapeHtml(item.patient_id)}</strong>
        <span>${escapeHtml(item.patient_name || "patient")}</span>
        <span>${escapeHtml(item.change_type || "change")}</span>
        <span>Record: ${escapeHtml(item.record_version || "unknown")}</span>
        <span>Updated: ${escapeHtml(item.last_updated || "unknown")}</span>
      </div>
    `).join("");
  } catch (error) {
    els.hisSyncList.innerHTML = `<div class="admin-table-row empty-state">Could not scan HIS changes. ${escapeHtml(error.message)}</div>`;
  }
}

async function queueHisUpdates() {
  setLoading(els.queueHisBtn, "Queuing...", true);
  try {
    await api("/his/sync", {
      method: "POST",
      body: JSON.stringify({ use_llm: true, require_llm: false, process: false }),
    });
    await Promise.all([loadHisSyncStatus(), loadJourneyQueue(), loadAuditEvents()]);
  } catch (error) {
    els.hisSyncList.innerHTML = `<div class="admin-table-row empty-state">Queue HIS updates failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.queueHisBtn, "Queue HIS Updates", false);
  }
}
async function loadJourneyQueue() {
  if (!els.queueList || !els.queueMeta) return;
  try {
    const result = await api("/journeys/queue?limit=20");
    els.queueMeta.textContent = `${result.pending_count || 0} pending`;
    const rows = result.pending || [];
    if (rows.length === 0) {
      els.queueList.classList.add("empty-state");
      els.queueList.textContent = "No pending journey refresh jobs.";
      return;
    }
    els.queueList.classList.remove("empty-state");
    els.queueList.innerHTML = rows.map((item) => `
      <div class="admin-table-row">
        <strong>${escapeHtml(item.patient_id || "unknown")}</strong>
        <span>${escapeHtml(item.reason || "queued")}</span>
        <span>${escapeHtml(item.actor || "system")}</span>
        <span>${escapeHtml(compactDate(item.created_at))}</span>
        <span>${escapeHtml(item.refresh_id || "no refresh id")}</span>
      </div>
    `).join("");
  } catch (error) {
    els.queueList.innerHTML = `<div class="admin-table-row empty-state">Could not load journey queue. ${escapeHtml(error.message)}</div>`;
  }
}

async function processJourneyQueue() {
  if (!els.processQueueBtn || !els.queueList) return;
  setLoading(els.processQueueBtn, "Processing...", true);
  try {
    await api("/journeys/process-queue", {
      method: "POST",
      body: JSON.stringify({ use_llm: true, require_llm: false, limit: 10 }),
    });
    await Promise.all([loadJourneyQueue(), loadJourneyRuns(), loadAuditEvents(), loadSelectedPatientOps()]);
  } catch (error) {
    els.queueList.innerHTML = `<div class="admin-table-row empty-state">Process queue failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.processQueueBtn, "Process Queue", false);
  }
}
async function loadStaleJourneys() {
  try {
    const result = await api("/journeys/stale");
    els.staleMetric.textContent = String(result.stale_count ?? 0);
    els.staleMeta.textContent = `${result.stale_count ?? 0} stale`;
    const rows = result.stale || [];
    if (rows.length === 0) {
      els.staleList.classList.add("empty-state");
      els.staleList.textContent = "No stale patient journeys found.";
      return;
    }
    els.staleList.classList.remove("empty-state");
    els.staleList.innerHTML = rows.map((row) => `
      <div class="admin-table-row">
        <strong>${escapeHtml(row.patient_id)}</strong>
        <span>${escapeHtml(row.patient_name || "patient")}</span>
        <span>Stored: ${escapeHtml(row.source_record_version || "unknown")}</span>
        <span>Current: ${escapeHtml(row.current_source_record_version || "unknown")}</span>
      </div>
    `).join("");
  } catch (error) {
    els.staleMetric.textContent = "Failed";
    els.staleList.innerHTML = `<div class="admin-table-row empty-state">Could not load stale journeys. ${escapeHtml(error.message)}</div>`;
  }
}

async function loadJourneyRuns() {
  try {
    const runs = await api("/journeys/runs?limit=10");
    els.runsMeta.textContent = `${runs.length} shown`;
    els.runMetric.textContent = runs[0] ? `${runs[0].status} / ${runs[0].patient_id}` : "No runs";
    if (runs.length === 0) {
      els.runsList.classList.add("empty-state");
      els.runsList.textContent = "No journey generation runs found.";
      return;
    }
    els.runsList.classList.remove("empty-state");
    els.runsList.innerHTML = runs.map((run) => `
      <div class="admin-table-row">
        <strong>${escapeHtml(run.patient_id || "unknown")}</strong>
        <span>${escapeHtml(run.status || "unknown")} / ${escapeHtml(run.trigger || "generation")}</span>
        <span>${escapeHtml(run.provider || "provider?")} / ${escapeHtml(run.model || "model?")}</span>
        <span>${escapeHtml(run.estimated_input_tokens ?? "?")} tokens</span>
        <span>${escapeHtml(run.duration_ms ?? "?")} ms</span>
        <span>${escapeHtml(compactDate(run.created_at || run.started_at))}</span>
      </div>
    `).join("");
  } catch (error) {
    els.runMetric.textContent = "Failed";
    els.runsList.innerHTML = `<div class="admin-table-row empty-state">Could not load journey runs. ${escapeHtml(error.message)}</div>`;
  }
}

async function loadJourneyFeedback() {
  try {
    const feedback = await api("/journey-feedback?limit=10");
    els.feedbackMeta.textContent = `${feedback.length} shown`;
    if (feedback.length === 0) {
      els.feedbackList.classList.add("empty-state");
      els.feedbackList.textContent = "No journey feedback found.";
      return;
    }
    els.feedbackList.classList.remove("empty-state");
    els.feedbackList.innerHTML = feedback.map((event) => `
      <div class="admin-table-row">
        <strong>${escapeHtml(event.patient_id || "unknown")}</strong>
        <span>${escapeHtml(event.feedback_type || "feedback")}</span>
        <span>${escapeHtml(event.actor || "unknown actor")}</span>
        <span>${escapeHtml(compactDate(event.created_at))}</span>
        <span>${escapeHtml(event.comment || "no note")}</span>
      </div>
    `).join("");
  } catch (error) {
    els.feedbackList.innerHTML = `<div class="admin-table-row empty-state">Could not load journey feedback. ${escapeHtml(error.message)}</div>`;
  }
}
async function loadAuditEvents() {
  try {
    const events = await api("/audit/events?limit=10");
    els.auditMeta.textContent = `${events.length} shown`;
    if (events.length === 0) {
      els.auditList.classList.add("empty-state");
      els.auditList.textContent = "No audit events found.";
      return;
    }
    els.auditList.classList.remove("empty-state");
    els.auditList.innerHTML = events.map((event) => `
      <div class="admin-table-row">
        <strong>${escapeHtml(event.event_type || "event")}</strong>
        <span>${escapeHtml(event.patient_id || "no patient")}</span>
        <span>${escapeHtml(event.actor || "unknown actor")}</span>
        <span>${escapeHtml(compactDate(event.timestamp))}</span>
      </div>
    `).join("");
  } catch (error) {
    els.auditList.innerHTML = `<div class="admin-table-row empty-state">Could not load audit events. ${escapeHtml(error.message)}</div>`;
  }
}

async function refreshDashboard() {
  authChanged();
  els.dashboardMeta.textContent = "Refreshing...";
  await loadHealth();
  await Promise.all([loadVectorStatus(), loadAdminStatus(), loadHisSyncStatus(), loadJourneyQueue(), loadStaleJourneys(), loadJourneyRuns(), loadJourneyFeedback(), loadAuditEvents()]);
  if (state.selectedPatientId) await loadSelectedPatientOps();
  els.dashboardMeta.textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

async function rebuildIndex() {
  setLoading(els.rebuildIndexBtn, "Rebuilding...", true);
  try {
    await api("/rag/index", { method: "POST" });
    await Promise.all([loadVectorStatus(), loadAuditEvents()]);
  } catch (error) {
    els.vectorMetric.textContent = `Rebuild failed: ${error.message}`;
  } finally {
    setLoading(els.rebuildIndexBtn, "Rebuild Vector Index", false);
  }
}

async function refreshStaleJourneys() {
  setLoading(els.refreshStaleBtn, "Refreshing...", true);
  try {
    await api("/journeys/refresh-stale", {
      method: "POST",
      body: JSON.stringify({ use_llm: true, require_llm: false, background: false }),
    });
    await refreshDashboard();
  } catch (error) {
    els.staleList.innerHTML = `<div class="admin-table-row empty-state">Refresh stale failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.refreshStaleBtn, "Refresh Stale Journeys", false);
  }
}

async function refreshSelectedJourney() {
  if (!state.selectedPatientId) return;
  setLoading(els.refreshJourneyBtn, "Refreshing...", true);
  try {
    await api(`/patients/${encodeURIComponent(state.selectedPatientId)}/journey/refresh`, {
      method: "POST",
      body: JSON.stringify({ use_llm: true, require_llm: false, background: false }),
    });
    await Promise.all([loadSelectedPatientOps(), loadJourneyRuns(), loadJourneyFeedback(), loadAuditEvents(), loadStaleJourneys()]);
  } catch (error) {
    els.patientOpsContent.innerHTML = `<div class="data-row empty-state">Journey refresh failed. ${escapeHtml(error.message)}</div>`;
  } finally {
    setLoading(els.refreshJourneyBtn, "Refresh Journey", false);
  }
}

els.apiKeyInput.addEventListener("change", refreshDashboard);
els.userIdInput.addEventListener("change", refreshDashboard);
els.patientSelect.addEventListener("change", (event) => selectPatient(event.target.value));
els.refreshDashboardBtn.addEventListener("click", refreshDashboard);
els.rebuildIndexBtn.addEventListener("click", rebuildIndex);
els.refreshStaleBtn.addEventListener("click", refreshStaleJourneys);
if (els.scanHisBtn) els.scanHisBtn.addEventListener("click", loadHisSyncStatus);
if (els.queueHisBtn) els.queueHisBtn.addEventListener("click", queueHisUpdates);
if (els.processQueueBtn) els.processQueueBtn.addEventListener("click", processJourneyQueue);
els.refreshJourneyBtn.addEventListener("click", refreshSelectedJourney);
els.inspectPatientBtn.addEventListener("click", () => {
  const target = state.selectedPatientId ? `/inspect?patient=${encodeURIComponent(state.selectedPatientId)}` : "/inspect";
  window.location.href = target;
});

loadHealth();
loadPatients()
  .then(refreshDashboard)
  .catch((error) => {
    els.selectedPatientCard.innerHTML = `<div class="empty-state">Could not load admin data. ${escapeHtml(error.message)}</div>`;
    refreshDashboard().catch(() => undefined);
  });
