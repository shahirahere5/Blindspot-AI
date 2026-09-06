# Blind Spot AI — Frontend

> Part of the [Blind Spot AI](../README.md) project. This document covers the React dashboard specifically. See the [backend README](../backend/README.md) for the FastAPI API, architecture, and full environment variable reference.

A React + TypeScript dashboard for uploading decision documents, running AI analysis and multi-agent debate on them, tracking versions, exploring the resulting knowledge graph, and chatting with a grounded assistant about the document — including optional voice input/output.

## Tech stack

- **React 19** + **TypeScript**
- **Vite** for dev server and build
- **Vitest** + **Testing Library** + **jsdom** for tests
- No UI/CSS framework — plain CSS in `src/styles.css`
- No routing library — a single-page tabbed layout managed with local component state

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # Windows: Copy-Item .env.example .env
npm run dev
```

The app runs at `http://localhost:5173` and expects the backend (see [`backend/README.md`](../backend/README.md)) to be running at the URL configured below.

## Environment variables

Set in `frontend/.env` (copied from `.env.example`). These are public, browser-visible values — never put secrets or the Groq API key here.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the FastAPI backend |
| `VITE_API_TIMEOUT_MS` | `180000` | Client-side request timeout, in milliseconds |

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Vite dev server on port 5173 |
| `npm run build` | Type-check (`tsc -b`) and produce a production build |
| `npm run typecheck` | Type-check only, no build output |
| `npm test` | Run the Vitest suite once |
| `npm run test:watch` | Run Vitest in watch mode |

## Project structure

```text
frontend/
├── .env.example
├── index.html
├── vite.config.ts
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── package.json
└── src/
    ├── main.tsx              React entry point
    ├── App.tsx               Top-level state, tab routing, and API orchestration
    ├── App.test.tsx
    ├── styles.css
    ├── components/
    │   ├── UploadPanel.tsx       Upload / open-existing-document flow
    │   ├── DocumentView.tsx      Normalized document view
    │   ├── AnalysisView.tsx      Structured analysis (risks, assumptions, biases, etc.)
    │   ├── DebateView.tsx        Six-agent debate + moderator view
    │   ├── VersionView.tsx       Version history and old/new comparison
    │   ├── GraphView.tsx         Knowledge graph explorer and diagnostics
    │   ├── ChatView.tsx          Grounded conversational chat + voice
    │   ├── ChatView.test.tsx
    │   ├── SourceReferences.tsx  Shared citation/source rendering
    │   └── States.tsx            Shared loading / empty / error / retry states
    ├── services/
    │   ├── api.ts             Centralized typed API client (fetch wrapper, error handling)
    │   ├── api.test.ts
    │   ├── voice.ts           Browser SpeechRecognition / speechSynthesis wrapper
    │   └── voice.test.ts
    ├── types/
    │   └── api.ts             TypeScript mirrors of the backend's Pydantic contracts
    └── test/
        ├── setup.ts           Vitest/jsdom setup
        └── fixtures.ts        Shared test fixtures
```

## How the UI is organized

`App.tsx` owns the top-level state (the currently loaded document, analysis, and debate results) and renders a tabbed layout:

- **Document** — upload a new file or open an existing document by ID, and view its normalized content
- **Analysis** — run and display structured analysis (risks, assumptions, biases, missing perspectives, questions, recommendations)
- **Debate** — run the six-agent debate and view each specialist's findings plus the moderator's synthesis
- **Versions** — view version history for a document family and request an old-vs-new semantic comparison
- **Graph** — explore the persistent knowledge graph for the current document or its whole version series, with node-type filters and blind-spot diagnostics
- **Chat** — ask grounded follow-up questions about the document or version series, with optional voice input/output

Each view follows a consistent loading / empty / error-with-retry state pattern (`components/States.tsx`), and all citations/source references are rendered through the shared `SourceReferences` component so evidence is displayed consistently across tabs.

All backend communication goes through `services/api.ts`, a single typed client that mirrors the backend's API contracts (`types/api.ts`) and normalizes errors into a consistent `ApiError`. Voice input/output is isolated in `services/voice.ts`, which wraps the browser's native `SpeechRecognition`/`speechSynthesis` APIs and degrades gracefully (falling back to text-only chat) in unsupported browsers.

## Tests

```bash
npm test
npm run typecheck
npm run build
```

Tests cover the API client, voice service (including unsupported-browser and permission-denied paths), and the chat view's UI states, using Vitest, Testing Library, and jsdom. They run against fakes/mocks and do not require a live backend.

## Notes

- Document and AI-generated text is always rendered as text, never as raw HTML, to avoid injecting untrusted content into the DOM.
- The frontend enforces its own request timeout (`VITE_API_TIMEOUT_MS`) independent of any backend timeout.
- For the full list of backend behaviors this UI depends on (RAG, knowledge graph, citation validation, rate-limit handling, etc.), see [`backend/README.md`](../backend/README.md).