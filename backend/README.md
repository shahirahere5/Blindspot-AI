# Blind Spot AI

Blind Spot AI reviews decision documents from multiple perspectives and tracks how their blind spots change across explicit revisions. A React and TypeScript dashboard uploads documents to a FastAPI backend, where content is validated, normalized, optionally retrieved through RAG, and sent to Groq for structured analysis, comparison, or a six-specialist debate with moderator synthesis.

## Current features

- TXT, PDF, DOCX, PPTX, and image upload with size, extension, and practical MIME validation
- Optional visual understanding for standalone images, scanned/image-heavy PDF pages, and embedded PPTX pictures
- Structured risks, assumptions, biases, missing perspectives, questions, and recommendations
- Optimist, Skeptic, Security, Financial, Ethics, and Legal agents plus a moderator
- Optional document-scoped RAG with source-location validation
- Explicit, persistent version families with semantic old/new comparison and separate evidence citations
- React dashboard with loading, empty, retry, error, analysis, debate, version, and source states
- Backend and frontend automated tests

## Architecture and technology

```text
React 19 + TypeScript + Vite
             |
          HTTP API
             |
FastAPI + Pydantic
  |          |                 |
processors   Groq analysis     six agents + moderator
  |          |                 |
text + optional vision evidence -> validated structured results
  |
optional chunking -> hashing embeddings -> per-document JSON vector index
explicit version links -> deterministic diff -> isolated old/new semantic comparison
```

The optional vision layer uses an OpenAI-compatible provider to turn selected visuals into validated textual evidence. The server assigns image/page/slide provenance, then persists that evidence in the existing normalized document. RAG, analysis, debate, and source validation therefore use the same pipeline for textual and visual evidence. The text model is unchanged.

The repository's current RAG implementation uses deterministic local feature-hashing embeddings and a persistent JSON vector store. It does not require a model download or a separate vector database. The backend owns document processing, AI credentials, retrieval, schemas, and source validation. Frontend types mirror the Pydantic API contracts.

Backend dependencies include FastAPI, Uvicorn, Pydantic, HTTPX, PyMuPDF, python-docx, python-pptx, Pillow, and Pytest. Frontend dependencies include React, Vite, TypeScript, Vitest, Testing Library, and jsdom.

## Project structure

Generated uploads, indexes, dependencies, builds, and caches are omitted.

```text
Blindspot-AI/
|-- .gitignore
|-- backend/
|   |-- .env.example
|   |-- main.py                 FastAPI app, CORS, and exception handlers
|   |-- config.py               upload, AI, RAG, and origin configuration
|   |-- requirements.txt
|   |-- pytest.ini
|   |-- README.md
|   |-- ai/                     text/vision clients, prompts, JSON safety, embeddings
|   |-- api/                    document, analysis, debate, version comparison, and RAG routes
|   |-- processing/             format-specific processors
|   |-- rag/                    chunking and context construction
|   |-- schemas/                Pydantic contracts
|   |-- services/               orchestration and retrieval services
|   |-- storage/                document, version, comparison-cache, path, and vector persistence
|   |-- data/
|   |   |-- documents/
|   |   |-- uploads/
|   |   |-- version_groups/
|   |   `-- comparison_cache/
|   `-- tests/
`-- frontend/
    |-- .env.example
    |-- package.json
    |-- package-lock.json
    |-- vite.config.ts
    |-- tsconfig.json
    `-- src/
        |-- App.tsx
        |-- App.test.tsx
        |-- components/
        |-- services/           centralized API client and tests
        |-- test/               test setup and fixtures
        `-- types/              backend contract mirrors
```

## Backend setup and startup

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy with `cp .env.example .env`. Set `GROQ_API_KEY` in `backend/.env` for real analysis and debate calls. Upload, document retrieval, default RAG, health checks, and automated tests do not require that key.

## Frontend setup and startup

In another terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open `http://localhost:5173`. API documentation is at `http://127.0.0.1:8000/docs`; health is at `http://127.0.0.1:8000/health`.

## Environment variables

Backend variables are documented in `backend/.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | empty | Private server-side Groq credential |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Analysis and debate model |
| `GROQ_BASE_URL` | Groq API URL | OpenAI-compatible provider endpoint |
| `GROQ_CONNECT_TIMEOUT_SECONDS` | `5` | Provider connection timeout |
| `GROQ_TIMEOUT_SECONDS` | `60` | Provider request timeout |
| `MAX_ANALYSIS_CONTENT_CHARS` | `20000` | Non-RAG prompt-size safeguard |
| `DEBATE_MAX_CONCURRENT_AGENTS` | `6` | Specialist concurrency limit |
| `RAG_ENABLED` | `false` | Enables retrieval for analysis and debate |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `800` / `150` | Chunking controls |
| `RAG_TOP_K` | `5` | Default retrieval count |
| `COMPARISON_RAG_TOP_K` | `8` | Per-version retrieval count for large comparisons |
| `MAX_COMPARISON_CONTENT_CHARS` | `30000` | Combined old/new size before comparison switches to RAG |
| `RAG_EMBEDDING_PROVIDER` | `hashing` | Local embedding provider |
| `RAG_EMBEDDING_DIMENSION` | `256` | Hashing vector size |
| `RAG_VECTOR_STORE_PATH` | `backend/data/vector_store` | Persistent index directory |
| `FRONTEND_ORIGINS` | local Vite origins | Explicit comma-separated CORS allowlist |
| `MULTIMODAL_ENABLED` | `false` | Enables optional visual evidence extraction |
| `VISION_PROVIDER` | `groq` | `groq` or a generic `openai_compatible` endpoint |
| `VISION_API_KEY` | empty | Optional private vision credential; Groq can reuse `GROQ_API_KEY` |
| `VISION_MODEL` | empty | Required vision-capable model when multimodal is enabled |
| `VISION_BASE_URL` | empty | Optional endpoint override; required for a generic provider |
| `VISION_TIMEOUT_SECONDS` | `60` | Per-provider-call timeout |
| `VISION_DOCUMENT_TIMEOUT_SECONDS` | `150` | Overall visual processing timeout per upload |
| `VISION_MAX_ITEMS_PER_DOCUMENT` | `10` | Maximum selected visuals per upload |
| `VISION_MAX_IMAGE_PIXELS` | `20000000` | Image/decompression safety limit |

Frontend variables are public browser configuration:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI base URL |
| `VITE_API_TIMEOUT_MS` | `180000` | Browser request timeout in milliseconds |

Never place `GROQ_API_KEY`, `VISION_API_KEY`, or any secret in a `VITE_*` variable; Vite exposes those values to browser code. Real `.env` files are ignored by Git.

## Multimodal processing

Multimodal processing is disabled by default and is never required for the existing text workflow. To enable it, set `MULTIMODAL_ENABLED=true`, select a provider, and configure a vision-capable `VISION_MODEL`. `VISION_PROVIDER=groq` reuses the existing Groq key and URL unless vision-specific overrides are supplied. `VISION_PROVIDER=openai_compatible` requires `VISION_API_KEY`, `VISION_BASE_URL`, and `VISION_MODEL`.

Standalone PNG, JPG/JPEG, and WEBP files are analyzed once at image location 1. PDF pages are selected conservatively when extracted text is sparse or meaningful images cover a configured portion of the page; normal text-only pages do not invoke vision. Existing PDF text is retained and supplemented. PPTX text and notes are retained while sufficiently large embedded pictures are analyzed at their slide number. DOCX paragraphs and tables remain supported, but embedded DOCX images are not processed in this implementation.

Visual provider output is schema-validated and normalized into visible text, a summary, evidence, relationships, and concerns. Repeated identical image bytes within one upload reuse a document-local result. Provider/configuration errors produce safe warnings; usable extracted text and successful visual items remain available.

## Analysis, debate, and RAG

Analysis validates extracted AI JSON against `AnalysisReport`. Debate runs the six fixed specialist roles independently and sends successful results to the moderator; one specialist failure is recorded safely, while all-agent or moderator failure returns an error. Raw provider diagnostics are logged server-side but are not returned to clients.

RAG is opt-in with `RAG_ENABLED=true`. It retains source metadata, auto-indexes when needed, and stores one validated index per document. Index payloads and chunks must match the requested document ID. Any model-proposed source location not present in the document or retrieved context is removed, including when the valid source set is empty.

## Version memory and comparison

Normal uploads remain standalone and are never grouped by filename or content. A family is created only when the user calls the new-version endpoint for a selected document. Each revision keeps its own immutable document ID, chronological version number, predecessor, timestamp, and optional label/notes. Family metadata is stored as atomic local JSON; a process lock prevents duplicate numbering, and only the latest revision can receive a successor.

Comparison first computes a deterministic block-level structural diff. Small pairs use their full separately labeled normalized content. Large pairs automatically index and retrieve from the old and new document IDs independently, even when global `RAG_ENABLED` is false; no third document is queried. Model-proposed old and new source locations are validated against their respective evidence sets, never a merged set. Normalized multimodal evidence participates without a separate comparison path.

Validated comparison reports are cached by immutable old ID, new ID, and model to avoid repeat provider calls. Analysis and debate outputs are not used as persistent "memory": they remain on-demand results whose model and settings may change, so carrying them forward would risk stale conclusions. Version relationships and comparisons provide the persistent memory layer without contaminating normal single-document analysis.

## Security and reliability notes

- Upload reads are bounded by the configured 50 MB limit before processing.
- Image pixel counts, visual item counts, per-call timeouts, and per-document visual processing time are bounded.
- Generated document IDs, validated suffixes, and resolved-path checks prevent storage traversal.
- Version relationships are explicit; cross-family, self, reversed, and stale-parent operations are rejected.
- Failed processing removes orphaned raw uploads.
- CORS uses explicit origins, methods, and headers and does not allow credentials.
- React renders document and AI text as text, not raw HTML.
- Backend 5xx/provider details are sanitized; the frontend also rejects unapproved 5xx details.
- The frontend aborts requests that exceed its configured timeout.
- This local application has no authentication or per-user authorization; do not expose it as a multi-tenant public service without adding those controls.

## API overview

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/documents/upload` | Validate, store, and normalize a multipart file |
| `GET` | `/api/documents/{document_id}` | Retrieve a normalized document |
| `POST` | `/api/documents/{document_id}/versions` | Upload an explicit successor with optional label and notes |
| `GET` | `/api/documents/{document_id}/versions` | List chronological family history (or standalone V1) |
| `POST` | `/api/documents/compare` | Compare an older/newer pair from the same family |
| `POST` | `/api/documents/{document_id}/analyze` | Generate structured analysis |
| `POST` | `/api/documents/{document_id}/debate` | Run specialists and moderator |
| `POST` | `/api/documents/{document_id}/index` | Force a RAG re-index |
| `POST` | `/api/documents/{document_id}/retrieve` | Retrieve document-scoped chunks |

Retrieval accepts `{"query": "financial risks", "top_k": 3}`. Comparison accepts `{"old_document_id": "doc_...", "new_document_id": "doc_..."}`. The version upload is multipart with `file` plus optional `version_label` and `notes` fields.

## Tests

```powershell
cd backend
python -m pytest
```

```powershell
cd frontend
npm test
npm run typecheck
npm run build
```

Tests use isolated storage and fake AI/embedding providers; they do not make external Groq calls.

## Known limitations

- There is no authentication or multi-user document ownership model.
- Analysis and debate reports are generated on demand and are not persisted.
- Local JSON locking protects concurrent requests within one backend process; multi-process deployment would require a transactional database or cross-process lock.
- The hashing embedder is a lexical baseline, not a semantic transformer model.
- JSON-vector search is brute-force and intended for local, document-scale workloads.
- Embedded DOCX images, native PowerPoint charts/SmartArt, and raw image-vector retrieval are not processed visually.
- Multimodal accuracy and supported encodings depend on the configured vision-capable provider/model.
