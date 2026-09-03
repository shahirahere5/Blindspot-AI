# Blind Spot AI

Blind Spot AI reviews decision documents from multiple perspectives. A React and TypeScript dashboard uploads documents to a FastAPI backend, where content is validated, normalized, optionally retrieved through RAG, and sent to Groq for either a structured analysis or a six-specialist debate with moderator synthesis.

## Current features

- TXT, PDF, DOCX, PPTX, and image upload with size, extension, and practical MIME validation
- Structured risks, assumptions, biases, missing perspectives, questions, and recommendations
- Optimist, Skeptic, Security, Financial, Ethics, and Legal agents plus a moderator
- Optional document-scoped RAG with source-location validation
- React dashboard with loading, empty, retry, error, analysis, debate, and source states
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
normalized documents      validated structured results
  |
optional chunking -> hashing embeddings -> per-document JSON vector index
```

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
|   |-- ai/                     Groq client, prompts, JSON safety, embeddings
|   |-- api/                    document, analysis, debate, and RAG routes
|   |-- processing/             format-specific processors
|   |-- rag/                    chunking and context construction
|   |-- schemas/                Pydantic contracts
|   |-- services/               orchestration and retrieval services
|   |-- storage/                document, path-safety, and vector persistence
|   |-- data/
|   |   |-- documents/
|   |   `-- uploads/
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
| `RAG_EMBEDDING_PROVIDER` | `hashing` | Local embedding provider |
| `RAG_EMBEDDING_DIMENSION` | `256` | Hashing vector size |
| `RAG_VECTOR_STORE_PATH` | `backend/data/vector_store` | Persistent index directory |
| `FRONTEND_ORIGINS` | local Vite origins | Explicit comma-separated CORS allowlist |

Frontend variables are public browser configuration:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI base URL |
| `VITE_API_TIMEOUT_MS` | `180000` | Browser request timeout in milliseconds |

Never place `GROQ_API_KEY` or any secret in a `VITE_*` variable; Vite exposes those values to browser code. Real `.env` files are ignored by Git.

## Analysis, debate, and RAG

Analysis validates extracted AI JSON against `AnalysisReport`. Debate runs the six fixed specialist roles independently and sends successful results to the moderator; one specialist failure is recorded safely, while all-agent or moderator failure returns an error. Raw provider diagnostics are logged server-side but are not returned to clients.

RAG is opt-in with `RAG_ENABLED=true`. It retains source metadata, auto-indexes when needed, and stores one validated index per document. Index payloads and chunks must match the requested document ID. Any model-proposed source location not present in the document or retrieved context is removed, including when the valid source set is empty.

## Security and reliability notes

- Upload reads are bounded by the configured 50 MB limit before processing.
- Generated document IDs, validated suffixes, and resolved-path checks prevent storage traversal.
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
| `POST` | `/api/documents/{document_id}/analyze` | Generate structured analysis |
| `POST` | `/api/documents/{document_id}/debate` | Run specialists and moderator |
| `POST` | `/api/documents/{document_id}/index` | Force a RAG re-index |
| `POST` | `/api/documents/{document_id}/retrieve` | Retrieve document-scoped chunks |

Retrieval accepts `{"query": "financial risks", "top_k": 3}`.

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
- The hashing embedder is a lexical baseline, not a semantic transformer model.
- JSON-vector search is brute-force and intended for local, document-scale workloads.
- Image uploads retain metadata but require a future OCR or multimodal stage for analysis.
