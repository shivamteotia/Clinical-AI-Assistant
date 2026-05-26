# Clinical AI System - V1 Local HIS

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

Generate a larger deterministic dummy dataset:

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

API docs:

```text
http://127.0.0.1:8000/docs
```

## Current Endpoints

- `GET /health`
- `GET /patients`
- `GET /patients/{patient_id}`
- `GET /patients/{patient_id}/record`
- `GET /patients/{patient_id}/journey`
- `POST /patients/{patient_id}/journey/generate`
- `POST /patients/{patient_id}/ask`
- `POST /patients/{patient_id}/ask-llm`
- `GET /rag/documents`
- `GET /rag/chunks`
- `GET /rag/status`
- `POST /rag/index`
- `POST /rag/search`
- `POST /rag/ask`
- `POST /rag/ask-llm`

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

The app reads `data\patient_journeys.json` when a doctor selects a patient from the dropdown. This keeps the doctor-facing page fast: patient selection renders the stored holistic view immediately instead of waiting for an LLM call. `POST /patients/{patient_id}/journey/generate` remains available for admin/background refresh workflows, not as a normal doctor interaction. Use `--require-llm` for production-style generation so local fallback summaries are not saved by accident.

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
