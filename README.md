# Clinical AI System - V1 Local HIS
<img width="1868" height="873" alt="image" src="https://github.com/user-attachments/assets/7ab172f1-11d8-467e-a60d-543ce200f541" />

This is the first local prototype for the Clinical AI pipeline.

The V1 goal is simple:

1. Store dummy patient data locally.
2. Load the data into SQLite.
3. Expose patient records through a simple API.
4. Use this API later as the data source for the RAG pipeline.

## Setup

Create a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Seed the local HIS database:

```powershell
python scripts\seed_data.py
```

Generate a larger deterministic longitudinal dummy dataset. It keeps the same 20 patients and creates 3 encounters, 3 clinical notes, and repeated labs where relevant for each patient journey:

```powershell
python scripts\generate_dummy_data.py
python scripts\seed_data.py
```

Run the API:

```powershell
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/
```

Admin console:

```text
http://127.0.0.1:8000/admin
```

API docs:

```text
http://127.0.0.1:8000/docs
```


## Run With Docker

Create a local `.env` file first. Keep real credentials out of Git:

```powershell
Copy-Item .env.example .env
```

Default Docker run uses the FastAPI app container and your configured Qdrant Cloud credentials:

```powershell
docker compose up --build app
```

Open:

```text
http://127.0.0.1:8000/
```

The compose setup mounts local runtime state into the container:

- `./data:/app/data` for stored journeys, audit logs, refresh queue logs, and run logs
- the dummy HIS SQLite database is seeded inside the image during build

To try a local Qdrant container instead of Qdrant Cloud, set this in `.env`:

```text
VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=clinical_patient_chunks
```

Then run:

```powershell
docker compose --profile local-qdrant up --build app qdrant
```

The application image does not include `.env`, local databases, virtual environments, or runtime JSONL logs.


## API Authentication

The app supports simple API-key role separation through request headers:

```text
X-API-Key: your_key
X-User-Id: doctor_or_admin_id
```

Set these in `.env` to enable auth:

```text
CLINICAL_AI_DOCTOR_API_KEY=replace_with_doctor_api_key
CLINICAL_AI_ADMIN_API_KEY=replace_with_admin_api_key
```

If both keys are unset, local development remains open. When keys are configured:

- doctor/admin keys can view patient lists, records, journeys, and ask RAG questions
- only the admin key can view audit events, journey run logs, refresh/regenerate journeys, inspect the journey pipeline, and rebuild the vector index
- `/health`, `/`, `/inspect`, and static assets remain public

## Current Endpoints

- `GET /`
- `GET /inspect`
- `GET /admin`
- `GET /admin/status`
- `GET /his/sync/status`
- `POST /his/sync`
- `GET /health`
- `GET /patients`
- `GET /patients/{patient_id}`
- `GET /patients/{patient_id}/record`
- `GET /patients/{patient_id}/journey`
- `POST /patients/{patient_id}/journey/feedback`
- `POST /patients/{patient_id}/journey/generate`
- `POST /patients/{patient_id}/journey/refresh`
- `POST /patients/{patient_id}/ask`
- `POST /patients/{patient_id}/ask-llm`
- `GET /rag/documents`
- `GET /rag/chunks`
- `GET /rag/status`
- `POST /rag/index`
- `POST /rag/search`
- `POST /rag/ask`
- `POST /rag/ask-llm`
- `GET /audit/events`
- `GET /journeys/stale`
- `GET /journeys/queue`
- `POST /journeys/process-queue`
- `GET /journeys/runs`
- `GET /journey-feedback`
- `GET /patients/{patient_id}/journey/runs`
- `POST /journeys/refresh-stale`



## Admin Console

Open the operator dashboard at:

```text
http://127.0.0.1:8000/admin
```

The admin console shows API health, vector store status, stale journeys, recent journey generation runs, and audit events. It also provides controls to rebuild the vector index, refresh stale journeys, and refresh a selected patient's precomputed holistic journey. If API-key auth is enabled, paste the admin key into the console's `Admin API key` field; it is stored only in browser session storage.

The safe admin status endpoint is `GET /admin/status`. It returns operational flags such as auth enabled/configured, vector provider/status, LLM provider/model, stale journey count, recent run count, and recent audit count. It does not return API key values, prompts, patient notes, summaries, or generated answers.




## Incremental HIS Sync

The app should not regenerate all LLM patient journeys whenever the HIS changes. Instead, it scans canonical HIS records and compares each current record hash against the stored journey source hash.

Use the Admin Console or these admin endpoints:

```text
GET /his/sync/status
POST /his/sync
```

`GET /his/sync/status` detects patients that need work:

- `new_patient`: patient exists in HIS but has no stored journey
- `record_changed`: patient journey exists, but the source record hash no longer matches the current canonical HIS record

`POST /his/sync` queues only those actionable patients by default. It does not regenerate unchanged patients. Set `process: true` to generate/refresh actionable journeys immediately; otherwise the refresh queue records the notification for a worker or operator.

Run the same workflow from the CLI:

```powershell
python scripts\sync_his_journeys.py
python scripts\sync_his_journeys.py --queue
python scripts\sync_his_journeys.py --process --provider groq --model llama-3.3-70b-versatile
```

## Clinician Journey Feedback

Doctors can submit lightweight feedback on a precomputed holistic patient journey:

```text
POST /patients/{patient_id}/journey/feedback
```

Allowed `feedback_type` values are `useful`, `missing_info`, `incorrect`, and `other`. Feedback is stored in an append-only local JSONL log and visible to admins through `GET /journey-feedback` and the Admin Console. Audit events record feedback metadata such as type and comment length, not the free-text comment itself.

## Runtime State Paths

The app writes operational state under `data/` by default. For tests, containers, or alternate deployments, these paths can be overridden without changing code:

```text
CLINICAL_AI_AUDIT_LOG_PATH=data/audit_logs.jsonl
CLINICAL_AI_JOURNEY_PATH=data/patient_journeys.json
CLINICAL_AI_JOURNEY_RUN_LOG_PATH=data/journey_runs.jsonl
CLINICAL_AI_JOURNEY_REFRESH_QUEUE_PATH=data/journey_refresh_queue.jsonl
```

Automated tests use temporary journey and queue paths so local precomputed patient journeys are not rewritten by test runs.

## Audit Logging

The API writes append-only audit events to `data\audit_logs.jsonl` for the main clinical and AI workflow actions:

- patient record viewed
- patient journey viewed or regenerated
- journey inspection opened
- vector index rebuilt
- RAG search or answer requested

Audit events include actor, timestamp, patient ID when relevant, and safe metadata such as model name, stale/current status, record version, result counts, and section counts. They intentionally do not store raw clinical notes, prompts, API keys, summaries, or generated answers. For local testing, override the log path with `CLINICAL_AI_AUDIT_LOG_PATH`.

Inspect recent audit events:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/audit/events?limit=50"
```

## Load Patient Data For RAG

This script loads all local HIS patient records into LangChain `Document` objects:

```powershell
python scripts\load_langchain_documents.py
```

Each document contains the combined structured and unstructured patient record in `page_content`, with patient identifiers stored in `metadata`.

## Chunk Patient Documents

This script splits the LangChain patient documents into smaller chunks for vector search:

```powershell
python scripts\chunk_langchain_documents.py
```

Each chunk keeps patient metadata plus a `chunk_index`, making it ready for embeddings and vector storage.

## Build And Search The Vector Store

This script embeds the patient chunks and stores them in a local SQLite vector store:

```powershell
python scripts\build_vector_store.py
```

Search the local vector store:

```powershell
python scripts\search_vector_store.py "Which patient has diabetes and high HbA1c?"
```

The API also exposes:

```text
POST /rag/index
POST /rag/search
POST /rag/ask
POST /rag/ask-llm
```

The current V1 embedding model is `sentence-transformers/all-MiniLM-L6-v2`, running locally through Hugging Face Sentence Transformers. The code also keeps a deterministic hash embedding fallback for simple no-download testing. Later, replace the embedding model with a clinical-grade embedding model if needed.

ChromaDB was considered for V1, but on Windows it can require Microsoft C++ Build Tools for `chroma-hnswlib`. The current SQLite vector store keeps the pipeline local and easy to run, while preserving a clean place to swap in Chroma later.

## Use Qdrant For V2 Vector Search

SQLite remains the default local vector store. To switch the same RAG API and scripts to Qdrant, create a local `.env` file from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Set:

```text
VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=https://your-cluster-url.qdrant.tech
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_COLLECTION=clinical_patient_chunks
```

Then build the Qdrant collection:

```powershell
python scripts\build_qdrant_vector_store.py
```

Search Qdrant directly:

```powershell
python scripts\search_qdrant_vector_store.py "Which patient has diabetes and high HbA1c?"
```

The Qdrant backend uses hybrid retrieval:

- exact patient ID filters when a query names a patient such as `P001`
- structured metadata payloads for diagnoses, lab tests, medications, and source sections
- semantic vector similarity plus keyword, phrase, patient ID, and metadata score boosts

When `VECTOR_STORE_PROVIDER=qdrant`, the API endpoints below use Qdrant automatically:

```text
GET /rag/status
POST /rag/index
POST /rag/search
POST /rag/ask
POST /rag/ask-llm
```

Keep `.env` local. It is ignored by Git and should not be committed.

## Ask A RAG Question

## Precompute Holistic Patient Views

Precompute LLM patient summaries for the doctor-facing patient view:

```powershell
python scripts\generate_patient_journeys.py
```

To generate LLM-written journeys with a hosted Groq model:

```powershell
python scripts\generate_patient_journeys.py --provider groq --model llama-3.3-70b-versatile --require-llm
```

Required `.env` values:

```text
PATIENT_JOURNEY_LLM_PROVIDER=groq
PATIENT_JOURNEY_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=your_groq_api_key
```

To generate with local Ollama instead:

```powershell
python scripts\generate_patient_journeys.py --ollama --model phi3
```

Patient records are exposed through a canonical dummy HIS adapter. `GET /patients/{patient_id}/record` includes `record_metadata` with `source_system`, `source_record_id`, `record_hash`, `record_version`, and `last_updated`. Journey responses store the source record hash and return `is_stale` by comparing the stored hash with the current canonical record hash.

Journey generation uses an episode-aware context packer before calling the LLM. The episode builder groups each patient record into chronological episodes from encounter dates, then attaches same-date labs, medication starts, and clinical notes. The packed context uses `episodic_patient_context.v1` plus `encounter_date_episodes.v1`, and emits included/total/omitted counts, input character count, estimated input tokens, and reserved output tokens so context-window usage is visible in `/inspect` and stored journey metadata.

The app reads `data\patient_journeys.json` when a doctor selects a patient from the dropdown. This keeps the doctor-facing page fast: patient selection renders the stored holistic view immediately instead of waiting for an LLM call. Journey responses include source-grounded `claims`, so each summary sentence can show the HIS row, episode, encounter, lab, medication, or note IDs that support it. `POST /patients/{patient_id}/journey/generate` remains available for admin generation workflows. `POST /patients/{patient_id}/journey/refresh` and `POST /journeys/refresh-stale` are the operational refresh paths for stale summaries. Use `--require-llm` for production-style generation so local fallback summaries are not saved by accident.

Journey artifacts now use the versioned `patient_journey.v1` Pydantic contract. The LLM response must contain exactly `summary` and `claims`, with no unknown fields. Each claim must contain a sentence copied from the summary and at least one source ID that exists in the canonical patient record. The completed artifact is validated again before storage, including context count reconciliation, patient/run consistency, and canonical source record identity. Existing pre-versioned journey files are upgraded to `patient_journey.v1` when read, while malformed new artifacts are rejected rather than silently persisted.


Refresh stale journeys after canonical HIS records change:

```powershell
python scripts\refresh_stale_journeys.py --dry-run
python scripts\refresh_stale_journeys.py --provider groq --model llama-3.3-70b-versatile --require-llm
```

The refresh workflow writes safe queue events to `data\journey_refresh_queue.jsonl` and audit events for refresh requested, completed, and failed states. The queue log is local and ignored by Git.

Journey generation also writes local observability events to `data\journey_runs.jsonl`. Each run records patient ID, provider, model, trigger, status, context strategy, source record version, estimated input tokens, duration, generated_by, and error metadata when applicable. The run log is local and ignored by Git. Inspect it through `GET /journeys/runs` or `GET /patients/{patient_id}/journey/runs`.
Inspect the internal journey pipeline for one patient without calling the LLM:

```powershell
python scripts\inspect_patient_journey_pipeline.py P006
```

This prints each step's source function or endpoint, input, output type, output shape, and data, including the episode-builder output before the LLM context is packed. To also inspect the live provider response without saving anything:

```powershell
python scripts\inspect_patient_journey_pipeline.py P006 --call-llm
```

Open the same dry-run inspection chain in the browser:

```text
http://127.0.0.1:8000/inspect
```

This script retrieves patient chunks and builds a simple grounded answer:

```powershell
python scripts\ask_rag.py "Which patient has diabetes and high HbA1c?"
```

The answer builder is intentionally simple in V1. It returns source chunks so the retrieved evidence can be inspected before an LLM is added.

Responses include:

- `confidence`
- `intent`
- `safety_level`
- `evidence`
- `safety_warnings`
- `limitations`
- `sources`

V2 safety behavior classifies clinical intent before answering. Diagnosis,
treatment, dosage, medication-change, and urgent-symptom questions are treated
as restricted or urgent. The system summarizes retrieved dummy-record evidence
only and does not provide clinical instructions.

## Evaluate Retrieval And Answers

Run the basic evaluation set:

```powershell
python scripts\evaluate_rag.py --rebuild
```

The evaluation checks whether expected patient IDs and key terms appear for known dummy-data questions.


## Continuous Integration

GitHub Actions runs the CI workflow on pushes and pull requests to `master`. The workflow installs Python 3.12 dependencies, seeds the dummy HIS database, runs the unittest suite, and scans tracked files for common Groq/Qdrant secret-like patterns.

## Run Tests

Run the automated API, RAG, and safety tests:

```powershell
python -m unittest discover
```

## Ask With Local Ollama LLM

After installing Ollama and pulling `phi3`, ask a question with the local model:

```powershell
python scripts\ask_ollama.py "Which patient has diabetes and high HbA1c?"
```

The API endpoint is:

```text
POST /rag/ask-llm
```

This endpoint retrieves patient chunks first, then asks the local Ollama model to answer only from that retrieved context.
