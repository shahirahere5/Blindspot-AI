# Blind Spot AI

Blind Spot AI reviews decision documents from multiple perspectives, tracks how blind spots change across explicit revisions, connects validated findings in a persistent knowledge graph, and answers grounded follow-up questions about them.

Upload a document (proposal, memo, plan, pitch deck, etc.) and Blind Spot AI will:

- Break it down into **structured risks, assumptions, biases, missing perspectives, questions, and recommendations**
- Run a **multi-agent debate** — Optimist, Skeptic, Security, Financial, Ethics, and Legal agents plus a moderator — to argue out the blind spots from different angles
- Let you upload a **revised version** and get a semantic old-vs-new comparison instead of a plain text diff
- Build a **persistent knowledge graph** of findings, evidence, and relationships across a document's versions, with "What am I missing?" diagnostics
- Answer **grounded follow-up questions** in a chat interface (with optional voice input/output), citing only evidence that actually exists in the document
- Optionally understand **images, scanned PDFs, and embedded slide visuals**, not just text

It is built as a React + TypeScript frontend talking to a FastAPI + Pydantic backend, with Groq used for the underlying language and vision models.

## Why this exists

Most document review only catches what the reader already knows to look for. Blind Spot AI is built around the opposite idea: use multiple structured, adversarial perspectives (plus retrieval-grounded evidence) to surface the risks, assumptions, and missing viewpoints a single read-through misses — and to keep that understanding consistent as a document evolves through revisions.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, Vitest + Testing Library |
| Backend | FastAPI, Pydantic, Uvicorn, HTTPX |
| Document processing | PyMuPDF (PDF), python-docx, python-pptx, Pillow |
| AI / LLM | Groq (OpenAI-compatible API) for text analysis, debate, comparison, conversation, and optional vision |
| Retrieval | Local deterministic hashing embeddings + a persistent JSON vector store (no external vector DB required) |
| Persistence | Local atomic JSON storage (documents, versions, comparisons, knowledge graph, conversations) |
| Testing | Pytest (backend), Vitest (frontend) |

## Project structure

```text
Blindspot-AI/
├── backend/     FastAPI application, AI orchestration, storage, tests
│   └── README.md   Full backend documentation (setup, architecture, API, phases)
├── frontend/    React + TypeScript dashboard
│   └── README.md   Frontend documentation (setup, structure, scripts)
└── README.md    This file
```

For full setup instructions, environment variables, the complete API reference, and a phase-by-phase breakdown of how the backend was built, see **[`backend/README.md`](backend/README.md)**.
For frontend-specific details, see **[`frontend/README.md`](frontend/README.md)**.

## Quick start

You'll need Python 3.11+, Node 18+, and (optionally) a free [Groq API key](https://console.groq.com/keys) for live AI features.

**1. Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cp .env.example .env             # add GROQ_API_KEY to enable AI features
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**2. Frontend** (in a second terminal)

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

**3. Open the app**

- Frontend: `http://localhost:5173`
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

Upload, document retrieval, local indexing, health checks, and the automated test suite all work without a Groq key. Analysis, debate, comparison, and conversational synthesis need `GROQ_API_KEY` set in `backend/.env`.

## Core features at a glance

- Multi-format upload: TXT, PDF, DOCX, PPTX, and images, with size/extension/MIME validation
- Structured AI analysis: risks, assumptions, biases, missing perspectives, questions, recommendations
- Six-agent debate system with a moderator synthesizing the final view
- Optional Retrieval-Augmented Generation (RAG) for large documents, using a local, dependency-free embedding index
- Explicit version families with semantic (not just textual) old-vs-new comparison
- Persistent, document-scoped knowledge graph with typed relationships and blind-spot diagnostics
- Grounded conversational chat, scoped to a document or an entire version series, with citation validation
- Optional browser-native voice input/output for the chat interface
- Optional multimodal understanding of images, scanned PDF pages, and embedded PPTX visuals
- Backend and frontend automated test suites

## Running tests

```bash
# Backend
cd backend && python -m pytest

# Frontend
cd frontend && npm test && npm run typecheck && npm run build
```

## Known limitations

This is a hackathon-scale local application: there is no authentication/multi-tenant support, storage uses local JSON with in-process locking (not a transactional database), and it is not intended to be exposed as a public multi-user service without additional hardening. See [`backend/README.md`](backend/README.md#known-limitations) for the complete list.

## License

No license has been added yet. Add a `LICENSE` file if you intend to open-source this project.