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

## Phase 3: Multi-Agent Debate Engine

Phase 3 replaces the single-pass analysis of Phase 2 with a genuine
**multi-agent debate**: six independent specialist agents each analyze the
*same* document from their own narrow perspective, without seeing each
other's output, and a seventh **Moderator** agent synthesizes their
findings into one unified report.

Phase 1 and Phase 2 are completely unchanged and untouched by Phase 3.
`POST /api/documents/upload`, `GET /api/documents/{id}`, and
`POST /api/documents/{id}/analyze` continue to work exactly as before.

### Multi-agent architecture

```
NormalizedDocument (Phase 1)
        ↓
services/document_service.py     → validates + builds labeled content (unchanged, reused)
        ↓
        ├── Optimist Agent   ─┐
        ├── Skeptic Agent    │
        ├── Security Agent   ├─  run independently & concurrently
        ├── Financial Agent  │   (each gets the same document content,
        ├── Ethics Agent     │    none sees another agent's output)
        └── Legal Agent     ─┘
        ↓
services/debate_service.py       → collects agent results (successes + failures)
        ↓
Moderator Agent                  → compares, deduplicates, ranks, synthesizes
        ↓
schemas/debate.py                → validates the final DebateResult
```

The **agents are independent AI perspectives, not separate trained
models** — all seven (six specialists + Moderator) call the exact same
underlying Groq model (`ai/client.py`'s `GroqClient`, unmodified), each
with its own system prompt and role defined in `ai/debate_prompts.py`.
Nothing about the AI transport layer, JSON-safety utilities
(`ai/json_utils.py`), or the document pipeline changed for Phase 3.

New/changed files for Phase 3:

```
backend/
├── ai/
│   └── debate_prompts.py         # NEW: per-agent + moderator system/user prompts
├── schemas/
│   └── debate.py                 # NEW: AgentFinding, AgentAnalysis, DebateResult, etc.
├── services/
│   └── debate_service.py         # NEW: orchestrates agents + moderator
├── api/
│   └── debate.py                 # NEW: POST /api/documents/{id}/debate
├── main.py                       # CHANGED: registers the new debate router
├── config.py                     # CHANGED: adds DEBATE_MAX_CONCURRENT_AGENTS
└── tests/
    ├── fakes.py                  # CHANGED: adds DebateFakeAIClient + canned JSON
    ├── test_debate_agents.py     # NEW: per-agent unit tests
    ├── test_debate_service.py    # NEW: orchestration/service tests
    └── test_debate_api.py        # NEW: endpoint tests
```

### Agent descriptions

| Agent | Perspective |
|---|---|
| **Optimist** | Strengths, opportunities, well-supported positive assumptions, feasible aspects — but still flags real weaknesses when they matter. |
| **Skeptic** | Weak assumptions, unsupported claims, contradictions, missing evidence, failure scenarios, technical feasibility, overconfidence, hidden dependencies. |
| **Security** | Data security, privacy, auth, data leakage, prompt injection, malicious inputs, system abuse, AI/infrastructure security. Explains when security is genuinely not applicable rather than inventing risks. |
| **Financial** | Cost assumptions, revenue model, pricing, ROI, market viability, operational/scalability costs, monetization assumptions. Never invents numbers; distinguishes stated vs. missing financial information. |
| **Ethics** | Fairness, bias, discrimination risk, human impact, misuse potential, transparency, accountability, overreliance on AI. Never makes unsupported accusations. |
| **Legal** | Legal/regulatory risk, privacy requirements, IP, liability, compliance, consent. Explicitly states it is not providing legal advice and that a qualified professional should review flagged issues. |
| **Moderator** | Compares all six perspectives, identifies agreements/disagreements, deduplicates, resolves contradictions where possible, ranks the most important risks, preserves a well-justified single-agent finding even if uncorroborated, and produces the final unified report. |

### `POST /api/documents/{document_id}/debate`

Runs the full multi-agent debate over a previously uploaded and processed
document.

```bash
curl -X POST http://127.0.0.1:8000/api/documents/doc_550e8400-e29b-41d4-a716-446655440000/debate
```

**Successful response (`200`):**

```json
{
  "document_id": "doc_550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "agent_analyses": [
    {
      "agent": "optimist",
      "role": "Optimist Agent",
      "status": "succeeded",
      "error": null,
      "summary": "The proposal has real strengths...",
      "findings": [ /* AgentFinding: title, description, severity, evidence, source_locations, recommendation */ ],
      "assumptions": [ /* Assumption */ ],
      "questions": [ /* UnansweredQuestion */ ],
      "confidence": "medium",
      "metadata": {}
    }
    /* ... skeptic, security, financial, ethics, legal ... */
  ],
  "agreements": ["Multiple agents noted the proposal lacks supporting detail."],
  "disagreements": ["The Optimist sees the growth plan as a strength while the Skeptic sees it as unsupported."],
  "final_blind_spots": ["No agent found evidence of a validated customer base."],
  "final_risks": [ /* Risk, same shape as Phase 2 */ ],
  "final_assumptions": [ /* Assumption */ ],
  "final_biases": [ /* Bias */ ],
  "missing_perspectives": [ /* MissingPerspective */ ],
  "unanswered_questions": [ /* UnansweredQuestion */ ],
  "recommendations": [ /* Recommendation */ ],
  "overall_assessment": "The proposal is promising but leaves several important questions unanswered.",
  "metadata": {
    "model": "openai/gpt-oss-120b",
    "agents_used": 6,
    "agents_succeeded": ["optimist", "skeptic", "security", "financial", "ethics", "legal"],
    "agents_failed": [],
    "analyzed_content_items": 5
  }
}
```

Note that `final_risks`, `final_assumptions`, `final_biases`,
`missing_perspectives`, `unanswered_questions`, and `recommendations` use
the **exact same shapes** as Phase 2's `AnalysisReport` (`schemas/analysis.py`
is reused directly), so a frontend that already renders a Phase 2 report can
render the Phase 3 `DebateResult`'s synthesized fields with no changes —
`agent_analyses` is the only genuinely new structure to render.

**Error responses:** the same status codes as `/analyze`, plus two new
Phase-3-specific cases:

| Status | Meaning |
|---|---|
| `404` | Document does not exist. |
| `400` | Document isn't ready to analyze (same conditions as `/analyze`). |
| `413` | Document's extracted text exceeds `MAX_ANALYSIS_CONTENT_CHARS`. |
| `422` | The Moderator's output couldn't be parsed into valid JSON or didn't match the expected schema. |
| `429` | Groq's rate limit was reached (from the Moderator call; individual agent rate limits are absorbed as agent failures, see below). |
| `500` | `GROQ_API_KEY` is missing (server misconfiguration). |
| `502` | Groq rejected the API key/model, is unreachable, or returned an invalid response for the **Moderator** call — **or** every one of the six specialist agents failed, leaving nothing to moderate. |
| `504` | Groq didn't respond within the configured timeout (Moderator call). |

Every error returns a JSON body with a `detail` field — no raw stack traces
are ever returned to the client, same as Phase 1/2.

### Agent failure handling

A single specialist agent failing (AI error, malformed JSON, schema
validation failure) does **not** fail the whole debate. Each agent's result
in `agent_analyses` carries its own `status` (`"succeeded"` / `"failed"`)
and, on failure, an `error` message. The response's top-level `metadata`
also lists `agents_succeeded` and `agents_failed` for convenience:

```json
{
  "agent": "financial",
  "role": "Financial Agent",
  "status": "failed",
  "error": "The Groq API rate limit was reached...",
  "summary": "",
  "findings": [],
  "assumptions": [],
  "questions": [],
  "confidence": "medium",
  "metadata": {}
}
```

The Moderator is explicitly told which agents failed and is instructed not
to pretend that perspective was covered. If **every** agent fails, there is
nothing meaningful to moderate, so the endpoint returns a `502` instead of
fabricating a report. If the **Moderator itself** fails (AI error,
unparseable output, schema mismatch), the endpoint returns a clear error
(`502`/`504`/`422` as appropriate) rather than returning a partial or
fabricated final result — a `200` response always means the Moderator
successfully produced a real synthesis.

### Independent analysis & concurrency

Each of the six agents receives the document's labeled content
independently, built once per debate and reused unchanged across all seven
AI calls (six agents + Moderator) — no agent ever sees another agent's
output, only the Moderator does. The six agents run **concurrently** via
`asyncio.gather`, bounded by a semaphore (`DEBATE_MAX_CONCURRENT_AGENTS`,
default 6 — i.e. unbounded in practice since there are only six agents, but
lowerable via the environment if a given Groq account's rate limit needs
tighter throttling). The Moderator always runs strictly after all six agent
calls have completed (successfully or not).

### Source locations

Preserved exactly as in Phase 2: every agent finding and the Moderator's
final findings cite `source_locations` referencing the same `[PAGE N]` /
`[SLIDE N]` / `[PARAGRAPH N]` / `[TABLE N]` / `[TEXT N]` markers. The server
cross-checks every returned location (from every agent, and from the
Moderator) against locations that actually exist in the document and
silently drops any that don't — the same safeguard Phase 2 uses, applied
per-agent and again on the Moderator's synthesized output.

### Environment variables

Phase 3 reuses every Phase 2 Groq environment variable unchanged (see the
table above) and adds one:

| Variable | Default | Description |
|---|---|---|
| `DEBATE_MAX_CONCURRENT_AGENTS` | `6` | Maximum number of the six specialist agents allowed to call Groq concurrently. Lower this if you hit rate limits on a free-tier Groq account. |

### How to run

Same as Phase 1/2 — from the `backend/` directory:

```bash
cp .env.example .env   # fill in GROQ_API_KEY for real debate runs
pip install -r requirements.txt
uvicorn main:app --reload
```

### Manually testing via Swagger

1. Start the server: `uvicorn main:app --reload`.
2. Open `http://127.0.0.1:8000/docs`.
3. Upload a document via `POST /api/documents/upload` and copy its
   `document_id`.
4. Call `POST /api/documents/{document_id}/debate` with that ID (leave the
   request body empty — the endpoint takes no payload, just the path
   parameter).
5. Inspect the response: `agent_analyses` should contain six entries
   (`optimist`, `skeptic`, `security`, `financial`, `ethics`, `legal`), each
   `status: "succeeded"` under normal conditions, followed by the
   Moderator-synthesized `final_risks`, `final_assumptions`,
   `agreements`/`disagreements`, and `overall_assessment`.

Example curl flow (same pattern as Phase 2's real end-to-end test):

```bash
DOC_ID=$(curl -s -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@sample.pdf" | python3 -c "import sys,json;print(json.load(sys.stdin)['document_id'])")

echo "Uploaded as $DOC_ID"

curl -X POST http://127.0.0.1:8000/api/documents/$DOC_ID/debate
```

### How to test

```bash
pytest
```

The full suite (Phase 1 + Phase 2 + Phase 3) never calls the real Groq API
— `tests/fakes.py`'s `DebateFakeAIClient` routes canned per-agent and
per-moderator JSON responses (or canned `AIClientError`s) by inspecting
which role's system prompt was used, since the six agents run concurrently
and call order can't be relied on. No test consumes Groq API credits.

New Phase 3 test files:

* `tests/test_debate_agents.py` — each agent's title/role/prompt is
  correct and distinct; valid responses parse; malformed JSON, schema
  validation failures, and AI client errors are all handled per-agent
  without raising.
* `tests/test_debate_service.py` — all six agents execute and the
  Moderator receives their results; one failed agent doesn't fail the
  debate; all agents failing raises a clear error before the Moderator is
  ever called; Moderator AI failures propagate untouched; Moderator
  JSON/schema failures raise a clear generation error; fabricated source
  locations (from an agent or the Moderator) are filtered; a missing
  document raises the same `DocumentNotFoundError` as Phase 2.
* `tests/test_debate_api.py` — `POST /api/documents/{id}/debate` end to
  end: `200` success, `404` missing document, `400` not-ready document,
  `413` oversized document, one-agent-failure still returns `200` with the
  failure recorded, all-agents-failing returns `502`, and the Moderator's
  own connection/timeout/config/auth/model/JSON/schema failures map to the
  same status codes Phase 2 uses for `/analyze`.

### Architectural decisions

* **Reuse over rebuild.** `services/document_service.py`, `ai/client.py`,
  and `ai/json_utils.py` are completely unmodified. Phase 3 only adds new
  modules (`ai/debate_prompts.py`, `schemas/debate.py`,
  `services/debate_service.py`, `api/debate.py`) plus two small additive
  changes (`main.py` router registration, one new `config.py` setting).
* **Schema reuse for the synthesized output.** `DebateResult`'s
  `final_risks`/`final_assumptions`/`final_biases`/`missing_perspectives`/
  `unanswered_questions`/`recommendations` reuse the exact Phase 2 Pydantic
  models (`Risk`, `Assumption`, `Bias`, ...) rather than parallel Phase-3
  versions, so validation/normalization logic (including
  `source_locations` coercion) isn't duplicated and a frontend already
  built for Phase 2 mostly works unchanged for these fields.
  `AgentFinding` (used only inside `agent_analyses`) is a distinct, simpler
  model since per-agent findings aren't quite the same concept as a
  finalized `Risk`.
  A separate `ModeratorOutput` model is used purely to validate the
  Moderator's raw JSON before it's merged with the already-validated agent
  analyses into the final `DebateResult` — it's not returned to clients.
* **Agents never raise.** `_run_single_agent` catches every failure mode
  (AI transport, JSON extraction, schema validation, and anything
  unexpected) and always returns an `AgentAnalysis`, with `status="failed"`
  and an `error` message on failure. This is what makes "one agent
  failing doesn't fail the debate" trivial at the orchestration level —
  `asyncio.gather` never sees an exception from an individual agent.
* **The Moderator is the one call allowed to fail loudly.** Unlike the
  agents, the Moderator's `ai_client.generate()` call is *not* wrapped in a
  blanket try/except in `debate_service.py` — `AIClientError` subclasses
  propagate untouched to the API layer, exactly like Phase 2's single
  analyzer call, so a real upstream failure produces a real `502`/`504`/etc
  instead of a silently degraded report.
* **Bounded concurrency via a semaphore**, not raw `asyncio.gather` with no
  limit, per the "respect Groq rate limits" requirement — even though the
  default lets all six run at once (there are only six), the mechanism is
  in place and configurable without any code changes.

### Known limitations

* No chunking/RAG yet — large documents still hit the same
  `MAX_ANALYSIS_CONTENT_CHARS` ceiling as Phase 2 (a `413`), just now
  checked once before fanning out to all seven AI calls instead of one.
* All seven roles (six agents + Moderator) call the same configured Groq
  model; Phase 3 does not support assigning different models per agent.
* The Moderator sees each successful agent's structured output rendered as
  plain text (not raw JSON) to keep its prompt compact and cheap on a
  free-tier Groq account; it does not receive the failed agents' partial/
  raw output, only their names.
* No persistence of `DebateResult`s — each call to `/debate` re-runs the
  full seven-call pipeline; a document's debate report isn't cached or
  stored alongside its normalized JSON the way Phase 1's upload output is.
* No frontend, auth, database, web search, voice input, image vision
  analysis, or deployment — explicitly out of scope for this phase. RAG is
  addressed in Phase 4 (see below).

## Phase 4: Retrieval-Augmented Generation (RAG)

Phase 4 adds an opt-in RAG pipeline: instead of sending an AI call the
entire document's text, the document is split into small chunks, embedded,
stored in a local vector index, and only the chunks most relevant to a
given question are retrieved and shown to the model. This grounds every
answer in the specific passages that back it up (rather than "the whole
30-page deck"), reduces unsupported/fabricated claims, and lets `/analyze`
and `/debate` scale to documents larger than `MAX_ANALYSIS_CONTENT_CHARS`
without every AI call needing the full text.

**RAG is off by default.** `RAG_ENABLED=false` (the default) means
`/analyze` and `/debate` behave exactly as in Phase 2/3 — full document
text, no chunking, no embeddings, no vector store touched at all. Every
Phase 1-3 test continues to pass unmodified because of this: RAG is
additive, never a replacement, unless explicitly turned on.

### Why RAG, and why this design

* **Chunking operates on Phase 1's own output.** `rag/chunking.py` splits
  each `ContentBlock` (`schemas/document.py`, unchanged) that Phase 1
  already extracted — a chunk's `source_location`/`source_type` are always
  copied from a real block, so chunking can never invent a page or slide
  number.
* **Embeddings are free and fully local.** Groq (the project's only AI
  provider) doesn't serve embeddings, and the brief explicitly rules out
  Ollama/a local LLM. Rather than requiring a paid embedding API or a
  multi-hundred-MB local model download (poor fit for "free resources" and
  "easy local development"), the default embedding provider
  (`ai/embeddings/hashing.py`) is a deterministic feature-hashing
  (bag-of-words-style) embedding: pure Python standard library, no network
  access, no model file, same vector for the same text on any machine. It's
  not a state-of-the-art semantic embedding, but it's a solid, well-known
  baseline for retrieval *within a single document's own chunks* — a much
  easier task than open-domain search. The interface
  (`ai/embeddings/base.py`) is provider-independent, so a real semantic
  embedding model can be added later as a second implementation without
  touching chunking, the vector store, or retrieval.
* **The vector store is a simple local JSON store, not Chroma/a production
  vector DB.** One JSON file per document under `RAG_VECTOR_STORE_PATH`
  (mirroring `storage/document_store.py`'s one-file-per-document pattern),
  brute-force cosine similarity in pure Python. A hackathon document rarely
  has more than a few hundred chunks, so this is fast enough, has zero
  extra runtime dependencies (no server process, no native build steps on
  a judge's machine), and persists across restarts by construction.

### Architecture

```
NormalizedDocument (Phase 1, unchanged)
        ↓
rag/chunking.py            → DocumentChunk per ContentBlock (word-aware split)
        ↓
ai/embeddings/*            → one vector per chunk (default: local hashing)
        ↓
storage/vector_store.py    → persisted, one JSON file per document_id
        ↓
services/retrieval_service.py   → index / similarity search, per document
        ↓
rag/context_builder.py     → renders retrieved chunks as "[Source: Page 2]\n..."
        ↓
services/rag_service.py    → ties it together: per-query RagContext(content, valid_locations, item_count)
        ↓                                  ↓
services/analysis_service.py    services/debate_service.py   (both: only when RAG_ENABLED)
```

New/changed files for Phase 4:

```
backend/
├── rag/
│   ├── chunking.py               # NEW: word-aware document chunker
│   └── context_builder.py        # NEW: renders retrieved chunks into grounded text
├── ai/
│   └── embeddings/
│       ├── base.py               # NEW: EmbeddingProvider interface + error types
│       ├── hashing.py            # NEW: free, local, deterministic default provider
│       └── factory.py            # NEW: get_embedding_provider()
├── storage/
│   └── vector_store.py           # NEW: SimpleVectorStore (local, JSON-persisted)
├── schemas/
│   └── rag.py                    # NEW: DocumentChunk, RetrievedChunk, index/retrieve API schemas
├── services/
│   ├── retrieval_service.py      # NEW: indexing + retrieval orchestration
│   ├── rag_service.py            # NEW: RagContext + per-agent/analysis retrieval queries
│   ├── analysis_service.py       # CHANGED: RAG branch added; non-RAG path untouched
│   └── debate_service.py         # CHANGED: RAG branch added; non-RAG path untouched
├── api/
│   ├── rag.py                    # NEW: POST /index, POST /retrieve
│   ├── analysis.py                # CHANGED: handles EmbeddingError/VectorStoreError
│   └── debate.py                  # CHANGED: handles EmbeddingError/VectorStoreError
├── main.py                       # CHANGED: registers the new rag router
├── config.py                     # CHANGED: adds RAG_* settings
└── tests/
    ├── conftest.py                # CHANGED: isolates the vector store dir per test
    ├── fakes.py                   # CHANGED: adds FakeEmbeddingProvider
    ├── test_chunking.py           # NEW
    ├── test_embeddings.py         # NEW
    ├── test_vector_store.py       # NEW
    ├── test_retrieval_service.py  # NEW
    ├── test_rag_context.py        # NEW
    ├── test_rag_api.py            # NEW
    ├── test_analysis_rag_integration.py   # NEW
    └── test_debate_rag_integration.py     # NEW
```

### Chunking

`rag.chunking.chunk_document(document, chunk_size, chunk_overlap)` splits
every non-empty `ContentBlock` independently, word-aware (never splits a
word in half), with `RAG_CHUNK_OVERLAP` characters of trailing context
repeated at the start of the next chunk. A block that already fits within
`RAG_CHUNK_SIZE` is left as a single chunk. Every `DocumentChunk` carries
`document_id`, `chunk_index` (sequential across the whole document),
`text`, `source_type`, and `source_location` — the last two always copied
from the real `ContentBlock`.

### Embeddings

`ai.embeddings.factory.get_embedding_provider()` reads
`RAG_EMBEDDING_PROVIDER` (default, and only provider implemented today:
`hashing`) and returns an `EmbeddingProvider`. **Local vs. external:** the
hashing provider is 100% local — no network call, no API key, no model
download. To add a real semantic embedding provider later (e.g. a hosted
embedding API, or a local `sentence-transformers` model), implement
`ai.embeddings.base.EmbeddingProvider` and register it in
`ai/embeddings/factory.py`'s `_PROVIDERS` dict; nothing else in the
pipeline needs to change.

### Vector store

`storage.vector_store.SimpleVectorStore` (singleton: `vector_store`)
persists one JSON file per document under `RAG_VECTOR_STORE_PATH`
(`backend/data/vector_store/` by default), containing every chunk's text,
metadata, and embedding vector for that document. Re-indexing a document
fully replaces its previous index (never partially updated), so a document
can never end up with vectors from two different embedding providers/
dimensions mixed together. Search is brute-force cosine similarity, scoped
to a single `document_id` — there is no code path that can return another
document's chunks. **Local vs. external:** entirely local filesystem
storage, no server process, no external service.

### Retrieval

`services.retrieval_service` exposes:

* `ensure_document_indexed(document, force=False)` — chunks + embeds +
  stores a document if it isn't indexed yet (or unconditionally if
  `force=True`, used for explicit re-indexing). Raises
  `DocumentHasNoAnalyzableContentError` (reused from Phase 2 — same
  meaning) if chunking produces zero chunks.
* `retrieve_relevant_chunks(document_id, query, top_k=None)` — embeds the
  query and returns the `top_k` (default `RAG_TOP_K`) most similar chunks
  for that document. Raises `DocumentNotIndexedError` if the document
  hasn't been indexed yet. Never retrieves chunks from any other document.

`services.rag_service.build_context_from_query(document_id, query, top_k)`
combines retrieval with `rag.context_builder.build_rag_context(...)` into
a ready-to-use `RagContext(content, valid_locations, item_count)`.

### RAG context format

Retrieved chunks are rendered as:

```
[Source: Page 2]
<chunk text>

[Source: Slide 5]
<chunk text>
```

`valid_locations` — used to cross-check the model's `source_locations`
citations — is built *only* from the locations of chunks actually
retrieved and shown to the model for that call, not every location in the
document. This is deliberately stricter than Phase 2/3's full-document
validation: if an agent was only shown pages 2 and 5, a citation to page 9
is dropped even if page 9 genuinely exists elsewhere in the document,
because the model was never shown it and could not have gotten that
citation from real evidence.

### Integration with `/analyze` and `/debate`

When `RAG_ENABLED=true`:

* **`/analyze`** auto-indexes the document (if not already indexed), then
  retrieves chunks for one broad query covering everything the analyzer
  reports on (risks, assumptions, biases, missing perspectives, questions,
  recommendations), and sends only that grounded context to the model —
  instead of the full document text.
* **`/debate`** auto-indexes the document once, then retrieves a
  *different* set of chunks for each of the six specialist agents, using
  that agent's own perspective as the retrieval query (e.g. the Security
  agent retrieves chunks about "data security, privacy, authentication,
  ..."). This means each agent gets a smaller, more targeted prompt
  grounded in the evidence most relevant to *its* angle, rather than every
  agent sharing one large full-document prompt. The Moderator retrieves
  separately using a broad, whole-document query (similar to `/analyze`'s),
  so it has a synthesis-level view rather than any one agent's narrow
  slice. The six-agent-plus-Moderator architecture itself is unchanged —
  RAG only changes *what content* each participant is shown, never how
  many agents run or how the debate is orchestrated.

Both endpoints' JSON response shapes are **completely unchanged** by RAG —
only where the prompt content came from differs internally. Both add one
metadata field, `"rag_enabled": true/false`, so a response is self-
describing about which mode produced it.

When `RAG_ENABLED=false` (the default), neither endpoint imports or calls
the embedding layer or vector store at all — verified directly by
`test_analysis_rag_integration.py::test_analysis_without_rag_never_touches_embeddings`
and the equivalent debate test, which monkeypatch the RAG entry point to
raise if it's ever called and confirm the endpoint still succeeds normally.

### API

**`POST /api/documents/{document_id}/index`** — chunk, embed, and store a
document (always re-indexes from scratch). Useful to pre-warm the index, or
to force re-indexing after changing `RAG_EMBEDDING_PROVIDER` or chunk
settings.

```bash
curl -X POST http://127.0.0.1:8000/api/documents/doc_.../index
```

```json
{
  "success": true,
  "document_id": "doc_...",
  "chunks_indexed": 12,
  "embedding_provider": "hashing",
  "embedding_dimension": 256
}
```

**`POST /api/documents/{document_id}/retrieve`** — inspect what a
RAG-enabled `/analyze` or `/debate` call would actually retrieve for a
given query; auto-indexes the document first if needed. Mainly a debugging
tool.

```bash
curl -X POST http://127.0.0.1:8000/api/documents/doc_.../retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the financial risks?", "top_k": 3}'
```

```json
{
  "document_id": "doc_...",
  "query": "what are the financial risks?",
  "top_k": 3,
  "results": [
    {
      "text": "...",
      "score": 0.42,
      "metadata": {"chunk_index": 4, "source_type": "page", "source_location": 2}
    }
  ]
}
```

Error responses use the same `{"success": false, "error": ..., "detail": ...}`
shape as every other endpoint: `404` (document not found), `400` (document
not ready / not indexed / no analyzable content), `500` (embedding or
vector-store failure, or an unsupported `RAG_EMBEDDING_PROVIDER`).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `false` | Turn on RAG for `/analyze` and `/debate`. |
| `RAG_CHUNK_SIZE` | `800` | Max characters per chunk (word-aware). |
| `RAG_CHUNK_OVERLAP` | `150` | Characters of trailing context repeated between adjacent chunks. |
| `RAG_TOP_K` | `5` | Default number of chunks retrieved per query. |
| `RAG_EMBEDDING_PROVIDER` | `hashing` | Embedding provider name (`hashing` is the only one implemented today). |
| `RAG_EMBEDDING_DIMENSION` | `256` | Vector size used by the hashing provider. |
| `RAG_VECTOR_STORE_PATH` | `backend/data/vector_store` | Where per-document index JSON files are persisted. |

### How to run it locally

```bash
cp .env.example .env   # set RAG_ENABLED=true to turn RAG on
pip install -r requirements.txt
uvicorn main:app --reload
```

No extra setup beyond the existing Phase 1-3 setup — the default embedding
provider needs no API key, no model download, and no extra service to run.

### How to test

```bash
pytest
```

All Phase 4 tests use `FakeEmbeddingProvider` (see `tests/fakes.py`) or the
real, local, dependency-free `HashingEmbeddingProvider` directly — nothing
in the suite calls a real embedding API, and (as in Phase 2/3) nothing
calls the real Groq API either. New test files: `test_chunking.py`,
`test_embeddings.py`, `test_vector_store.py`, `test_retrieval_service.py`,
`test_rag_context.py`, `test_rag_api.py`,
`test_analysis_rag_integration.py`, `test_debate_rag_integration.py`.

### Known limitations / future improvements

* The default hashing embedding is a free, local baseline, not a
  state-of-the-art semantic embedding — retrieval quality would improve
  with a real embedding model (the interface is ready for one; see
  "Why RAG, and why this design" above).
* Retrieval is currently one query per analyzer/agent/moderator per call —
  there's no multi-query or iterative retrieval.
* No incremental re-indexing — any re-index fully replaces a document's
  previous chunks/vectors rather than diffing.
* No cross-document retrieval by design (each document's index is fully
  isolated) — there's no "search across all my documents" capability, nor
  is one planned, since Blind Spot AI analyzes one decision document at a
  time.
* The vector store's brute-force search is `O(chunks)` per query, which is
  fine at hackathon/document scale but would need a real ANN index (or a
  production vector database) at a much larger scale.
