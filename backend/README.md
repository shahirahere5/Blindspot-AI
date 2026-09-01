# Blind Spot AI — Phase 1: Input Pipeline

## Project

**Blind Spot AI** is an AI system that finds the risks, assumptions, biases,
and missing perspectives humans overlook before they make important
decisions. Rather than asking "Is this good?", it asks:

> **"What am I missing?"**

Future phases will run pitch decks, research papers, proposals, and other
decision-related documents through a pipeline of specialist AI agents
(Optimist, Skeptic, Financial, Security, Ethics, Legal), synthesized by a
moderator into a Blind Spot Report.

## Phase 1: What this implements

Phase 1 implements the **document ingestion pipeline** — the foundation
every later phase depends on. It:

1. Accepts file uploads (PDF, PPTX, DOCX, TXT, PNG, JPG/JPEG, WEBP)
2. Validates them (extension, MIME type, size, emptiness)
3. Assigns each file a unique document ID
4. Stores the original file locally
5. Extracts content in a format-specific way (pages, slides, paragraphs, text, image metadata)
6. Converts everything into a single **normalized document** representation
7. Persists the normalized document as JSON
8. Exposes it via a simple REST API

No LLM, RAG, agents, or paid services are used in Phase 1. The processing
layer is fully independent of any AI provider so Phase 2's AI layer (or a
different provider in the future) can be plugged in without touching this
code.

## Project Structure

```
backend/
├── main.py                       # FastAPI app entrypoint
├── config.py                     # Centralized config (paths, limits, AI settings)
├── requirements.txt
├── .env.example                  # Phase 2 environment variable template
├── .gitignore                     # Keeps .env and local data out of source control
├── README.md
│
├── api/
│   ├── __init__.py
│   ├── documents.py               # /api/documents upload + GET routes (Phase 1)
│   ├── validation.py               # Upload validation helpers (Phase 1)
│   └── analysis.py                 # /api/documents/{id}/analyze route (Phase 2)
│
├── processing/                    # Phase 1: format-specific extraction (unchanged)
│   ├── __init__.py
│   ├── base.py
│   ├── factory.py
│   ├── exceptions.py
│   ├── pdf.py
│   ├── pptx.py
│   ├── docx.py
│   ├── txt.py
│   └── image.py
│
├── services/                      # Phase 2: orchestration layer
│   ├── __init__.py
│   ├── document_service.py         # fetch/validate a document + build labeled content
│   └── analysis_service.py         # orchestrates the AI call + validates the result
│
├── ai/                             # Phase 2: AI provider abstraction
│   ├── __init__.py
│   ├── base.py                     # AIClient interface + error types
│   ├── client.py                   # GroqClient implementation + factory
│   ├── prompts.py                  # System prompt + user prompt builder
│   └── json_utils.py                # Safe JSON extraction from raw model output
│
├── schemas/
│   ├── __init__.py
│   ├── document.py                 # NormalizedDocument, ContentBlock, etc. (Phase 1)
│   └── analysis.py                  # AnalysisReport and sub-models (Phase 2)
│
├── storage/
│   ├── __init__.py
│   └── document_store.py           # Local filesystem persistence (unchanged)
│
├── data/
│   ├── uploads/                    # Original uploaded files (doc_<uuid>.<ext>)
│   └── documents/                  # Normalized JSON documents (doc_<uuid>.json)
│
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Shared fixtures (isolated test client, sample files)
    ├── fakes.py                      # Fake AIClient + canned responses for Phase 2 tests
    ├── test_upload_api.py            # Phase 1
    ├── test_validation.py            # Phase 1
    ├── test_get_document_api.py      # Phase 1
    ├── test_processing.py            # Phase 1
    ├── test_schema.py                # Phase 1
    ├── test_analysis_api.py          # Phase 2: /analyze endpoint (mocked AI client)
    ├── test_ai_client.py             # Phase 2: GroqClient (mocked transport)
    ├── test_json_utils.py            # Phase 2: JSON extraction utility
    └── test_analysis_schema.py       # Phase 2: AnalysisReport schema validation
```

## Setup

Copy the environment template (only needed for Phase 2's `/analyze`
endpoint; Phase 1 upload/retrieval and the automated test suite work
without it):

```bash
cp .env.example .env
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

**Windows:**

```bash
.venv\Scripts\activate
```

**macOS/Linux:**

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

From the `backend/` directory:

```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
Interactive API docs (Swagger UI) are available at `http://127.0.0.1:8000/docs`.

## Phase 2: Single AI Analyzer

Phase 2 adds the first AI intelligence layer on top of the Phase 1 pipeline.
It takes a document that has already been uploaded and processed, and runs
**one** analysis pass over its normalized content to answer: *"What might
the user be missing?"*

It identifies:

- **Risks** — things that could go wrong, with severity
- **Assumptions** — things taken for granted, with confidence level
- **Biases** — one-sided reasoning or selective evidence
- **Missing perspectives** — stakeholders or angles not addressed
- **Unanswered questions** — important gaps, with importance level
- **Recommendations** — concrete next steps, with priority

This is a **single unified analyzer**, not a multi-agent system — that's
Phase 3. The architecture is deliberately layered so Phase 3 can swap this
one call for several specialist agents without touching the document
pipeline, the AI transport layer, or the JSON-safety utilities:

```
NormalizedDocument (Phase 1)
        ↓
services/document_service.py   → validates + builds labeled, source-marked content
        ↓
ai/prompts.py                  → builds system + user prompts
        ↓
ai/client.py (GroqClient)      → calls Groq's hosted API, returns raw text
        ↓
ai/json_utils.py               → safely extracts a JSON object from the response
        ↓
schemas/analysis.py            → validates/normalizes into AnalysisReport
        ↓
services/analysis_service.py   → cross-checks source_locations against real content
        ↓
AnalysisReport (JSON)
```

No AI provider is hardcoded. The `AIClient` abstract interface (`ai/base.py`)
is implemented by `GroqClient` today, but another provider (Groq, a local
Ollama model, or anything else) could implement the same interface and be
selected via the `AI_PROVIDER` environment variable without changing
`services/analysis_service.py` or the API layer at all.

### Groq setup (required for real analysis, not required for tests)

Phase 2 uses [Groq](https://groq.com)'s hosted API to run a fast,
**open-weight** model without needing local GPU/CPU/RAM resources — no local
model server to run. The automated test suite mocks the AI client entirely
and never requires a real Groq account or API key.

1. Create a free account and API key at
   [console.groq.com/keys](https://console.groq.com/keys).
2. Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

3. Fill in your key and model in `.env`:

   ```env
   GROQ_API_KEY=your_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   GROQ_BASE_URL=https://api.groq.com/openai/v1
   ```

   `openai/gpt-oss-120b` is an open-weight model available on Groq with good
   structured-JSON support, and is a sensible default. See
   [console.groq.com/docs/models](https://console.groq.com/docs/models) for
   the current list of supported models if you'd like to use a different one.

4. **Never commit your real `.env` file.** It's already excluded via
   `.gitignore`; only `.env.example` (with blank placeholders) is tracked.

If `GROQ_API_KEY` is missing, `/analyze` returns a clear `500` configuration
error rather than crashing. If the key is invalid, the model name is wrong,
or Groq is unreachable, `/analyze` returns a clear `502`/`429`/`504` error
explaining what went wrong — it never leaks a stack trace.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `groq` | Which AI client implementation to use. |
| `GROQ_API_KEY` | *(none — required)* | Your Groq API key. Never hardcoded; missing key returns a controlled `500`. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model name. Must be a currently supported Groq model. |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq's OpenAI-compatible API base URL. |
| `GROQ_CONNECT_TIMEOUT_SECONDS` | `5` | Connection timeout. |
| `GROQ_TIMEOUT_SECONDS` | `60` | Full request timeout. |
| `GROQ_TEMPERATURE` | `0.2` | Sampling temperature (low, for more consistent structured JSON). |
| `MAX_ANALYSIS_CONTENT_CHARS` | `20000` | Max characters of document text sent to the model per analysis; larger documents get a `413` instead of being silently truncated. |

### `POST /api/documents/{document_id}/analyze`

Runs a single-pass analysis over an already-uploaded, already-processed
document. No file is uploaded again — just reference the existing
`document_id`.

**Request:**

```bash
curl -X POST http://127.0.0.1:8000/api/documents/doc_550e8400-e29b-41d4-a716-446655440000/analyze
```

**Successful response (`200`):**

```json
{
  "document_id": "doc_550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "summary": "The pitch proposes a subscription-based scheduling tool for small clinics.",
  "overall_assessment": "The idea is plausible but several important questions remain unanswered.",
  "risks": [
    {
      "title": "Scalability risk",
      "description": "The proposed architecture may not handle rapid growth.",
      "severity": "high",
      "evidence": "The startup expects to acquire one million users within six months.",
      "source_locations": [2],
      "recommendation": "Add a scaling strategy and capacity assumptions."
    }
  ],
  "assumptions": [ /* ... */ ],
  "biases": [ /* ... */ ],
  "missing_perspectives": [ /* ... */ ],
  "unanswered_questions": [ /* ... */ ],
  "recommendations": [ /* ... */ ],
  "metadata": {
    "model": "openai/gpt-oss-120b",
    "analyzed_content_items": 5
  }
}
```

**Error responses:**

| Status | Meaning |
|---|---|
| `404` | Document does not exist. |
| `400` | Document isn't ready to analyze (image pending multimodal analysis, scanned PDF requiring OCR, failed processing, or no extractable text). |
| `413` | Document's extracted text exceeds `MAX_ANALYSIS_CONTENT_CHARS`. |
| `422` | The AI model's output couldn't be parsed into valid JSON or didn't match the expected schema. |
| `429` | Groq's rate limit was reached for the configured API key. |
| `500` | `GROQ_API_KEY` is missing (server misconfiguration, not the caller's fault). |
| `502` | Groq rejected the API key, the model is unavailable/invalid, Groq is unreachable, or it returned an invalid response. |
| `504` | Groq didn't respond within the configured timeout. |

Every error returns a JSON body with a `detail` field explaining what went
wrong and, where relevant, how to fix it — no raw stack traces are ever
returned to the client.

### Evidence and source locations

The analyzer is given the document's content pre-labeled with source
markers matching its content block types, e.g.:

```
[PAGE 1]
The startup expects to acquire one million users within six months.

[PAGE 2]
The company currently has no defined customer acquisition budget.
```

(`[SLIDE N]` for PPTX, `[PARAGRAPH N]` for DOCX paragraphs, `[TABLE N]` for
DOCX tables, `[TEXT N]` for plain text.)

The model is instructed to cite `source_locations` (the numeric `N`) for
each finding, or return an empty list if it isn't confident. As an extra
safeguard, the server cross-checks every returned location against the
locations that actually exist in the document and silently drops any that
don't — a finding's location list can only shrink, never gain a fabricated
value.

### Large documents

Phase 2 does not implement chunking, embeddings, or RAG (that's a later
phase). Instead, it enforces a simple, configurable ceiling
(`MAX_ANALYSIS_CONTENT_CHARS`, default 20,000 characters) on how much
extracted text is sent to the model in one pass. Documents beyond that limit
get a clear `413` error rather than being silently truncated or crashing
the server.

## API

### `POST /api/documents/upload`

Accepts a multipart file upload (`file` field). Supported extensions:
`.pdf`, `.pptx`, `.docx`, `.txt`, `.png`, `.jpg`, `.jpeg`, `.webp`.
Max file size: 50 MB (configurable in `config.py`).

Successful response:

```json
{
  "success": true,
  "document_id": "doc_550e8400-e29b-41d4-a716-446655440000",
  "filename": "startup_pitch.pdf",
  "file_type": "pdf",
  "status": "processed",
  "metadata": { "page_count": 5 },
  "warnings": []
}
```

### `GET /api/documents/{document_id}`

Returns the full normalized document. Returns `404` if the document does
not exist.

## Tests

From the `backend/` directory:

```bash
pytest
```

Or with verbose output:

```bash
pytest -v
```

Tests use isolated temporary storage directories, so running them never
touches or pollutes `data/uploads/` or `data/documents/`.

## Manual API Testing (curl)

```bash
# TXT
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.txt"

# PDF
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.pdf"

# DOCX
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.docx"

# PPTX
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.pptx"

# Image
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.png"

# GET a document
curl http://127.0.0.1:8000/api/documents/doc_550e8400-e29b-41d4-a716-446655440000
```

## Real end-to-end test of the Groq integration

The steps above (and `pytest`) never call the real Groq API. To verify the
actual integration works end-to-end:

1. Create `.env` from the template and fill in your real key and model:

   ```bash
   cp .env.example .env
   ```

   ```env
   GROQ_API_KEY=gsk_your_real_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   ```

2. Start the backend:

   ```bash
   uvicorn main:app --reload
   ```

3. Open Swagger UI: http://127.0.0.1:8000/docs
4. Upload a test document via `POST /api/documents/upload` (or curl below)
   and copy the `document_id` from the response.
5. Call `POST /api/documents/{document_id}/analyze` with that ID.
6. Inspect the response — you should see real `risks`, `assumptions`,
   `biases`, etc. grounded in your document's content, with `metadata.model`
   showing the Groq model that produced it.

Example curl flow:

```bash
DOC_ID=$(curl -s -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.pdf" | python3 -c "import sys,json;print(json.load(sys.stdin)['document_id'])")

echo "Uploaded as $DOC_ID"

curl -X POST http://127.0.0.1:8000/api/documents/$DOC_ID/analyze
```

If you see a `500` with a message about `GROQ_API_KEY`, double check your
`.env` file is present and was picked up (restart `uvicorn` after editing
it). If you see a `502` mentioning an invalid API key, regenerate your key
at [console.groq.com/keys](https://console.groq.com/keys).

## Phase 3 Preview

Phase 3 will replace the single analyzer call in
`services/analysis_service.py` with multiple specialist agents (Optimist,
Skeptic, Financial, Security, Ethics, Legal) plus a moderator that
synthesizes their findings — without needing to change `ai/client.py`,
`ai/json_utils.py`, `services/document_service.py`, or anything in Phase 1.
Later phases will add RAG/embeddings for large-document handling in place
of today's simple character-limit safeguard.
