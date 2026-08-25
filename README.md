# AI Spend Intelligence Platform

[![CI](https://github.com/CrisLap/AI-Spend-Intelligence-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/CrisLap/AI-Spend-Intelligence-Platform/actions/workflows/ci.yml)

An enterprise AI platform that combines Retrieval-Augmented Generation and autonomous AI agents to analyze company spend, identify inefficiencies, and recommend cost-saving opportunities. Supports the entire lifecycle: document ingestion, UNSPSC classification, semantic search, RAG chat, a family of goal-driven multi-tool agents (Cost Saving, Forecast, Contract Risk) sharing one ReAct engine, anomaly and duplicate detection, analytics dashboard, and feedback-driven improvement loops.

## Architecture

```
                                   User
                                    |
                                    v
                       assistant_router.py (POST /assistant)
                       intent classifier: rule-based tiers -> LLM fallback
                                    |
                       +------------+------------+
                       |                          |
                       v                          v
              Chat (RAG assistant)        Cost Saving / Forecast / Contract Risk Agent
              chat_react.py               cost_saving_agent.py (agent_type param)
              (answered inline)           (handoff suggestion -> prefilled agent page)
                       |                          |
                       v                          v
              react_engine.py  <-- generic multi-tool ReAct loop -->
                       |                          |
                       |                 Tool registry (agents/tools.py)
                       |                 +-- spend_overview     (analytics.py)
                       |                 +-- supplier_variance  (analytics.py)
                       |                 +-- anomaly_scan       (anomalies.py)
                       |                 +-- contract_search    (contract_intelligence.py)
                       |                 +-- forecast_spend     (analytics.py)
                       v                          v
              Qdrant: spend_documents    Qdrant: spend_contracts
                                                   |
                                                   v
                                        Recommendation Engine
                                        (transparent heuristics
                                         over real DB data)
                                                   |
                                                   v
                                        AgentRun (persisted + audited)

Frontend (React) → FastAPI Backend → PostgreSQL (relational) + Qdrant (vector store) + Ollama (AI)
```

The Cost Saving Agent's recommendations are deliberately decoupled from its
ReAct trace: the trace is what the LLM actually reasoned through and is
shown to the user as-is, while the recommendations are computed directly by
a deterministic engine over the same underlying data functions - so every
number shown is grounded in a real, reproducible query, never invented by
the model. See `backend/app/services/cost_saving_agent.py` for the exact
heuristics (e.g. the supplier-variance threshold and the assumed
renegotiation recovery rate) and why they're named constants, not magic
numbers.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, ThreadPoolExecutor
- **AI:** Ollama (local LLM & embeddings), ReAct reasoning, Groq (free-tier cloud fallback when Ollama is unreachable, e.g. in production), fallback to deterministic hash embeddings offline
- **Database:** PostgreSQL, Qdrant vector store
- **Frontend:** React 19, TypeScript, Tailwind CSS v4, Recharts
- **DevOps:** Docker, Docker Compose, GitHub Actions (CI/CD), Render

## Modules

| # | Module | Description |
|---|--------|-------------|
| 1 | Document Intelligence | OCR (Tesseract), PDF/Excel/CSV/image parsing, LLM extraction → structured JSON |
| 2 | Spend Classification | 3-tier classification (rule-based → embedding similarity → LLM) against a UNSPSC-inspired custom taxonomy |
| 3 | Semantic Search | Natural-language vector search across all spend line items |
| 4 | AI Chat | Retrieval-Augmented Generation (RAG) chat with a real ReAct loop over two tools - semantic `search_spend` for open-ended lookups, and a deterministic `top_expenses` ranking for "highest/biggest" questions a similarity search can't reliably answer - source citations, conversation memory (trimming + summarization), guardrails, and a persistent chat history (`GET /chat/sessions`) the frontend lets a user browse, resume, and delete |
| 5 | Duplicate Detection | Exact (supplier+invoice+amount) + semantic (embedding similarity) matching |
| 6 | Anomaly Detection | Per-category z-score outlier detection on price, quantity, and new-supplier alerts |
| 7 | Dashboard | Real-time charts: spend by category/month, top suppliers, KPI cards |
| 8 | Feedback Loop | User corrections stored → real-time classifier retraining via `POST /classification/retrain` |
| 9 | REST API | Complete OpenAPI-documented endpoints for every module |
| 10 | User Management | JWT auth, RBAC (Admin/Buyer/Finance), audit logging. Spend data (documents, line items, dashboard, search, duplicates, anomalies, contracts) is shared per role — every Buyer sees every Buyer's data, every Finance user sees every Finance user's data, and Admin (a singleton role) sees everything; chat history and Cost Saving Agent run history stay private per user |
| 11 | Cost Saving Agent | Goal-driven multi-tool agent (spend overview, supplier variance, anomaly scan, contract clause search) built on a generic, reusable ReAct engine; a deterministic Recommendation Engine turns real query results into cited, estimated-saving opportunities; every run is persisted with a full audit trail; guardrails (input validation, output sanitization) apply the same as the Chat |
| 12 | Contract Intelligence | Contract full text is chunked and semantically indexed (separate Qdrant collection) so clauses - auto-renewal, penalties - are searchable, not just line items |
| 13 | Forecast Agent | Same agent framework, one tool: projects next month's total spend with a linear-trend fit over real monthly history (`agent_type=forecast`) |
| 14 | Contract Risk Agent | Same agent framework and contract-clause RAG as the Cost Saving Agent, searched for risk language instead - penalties, exclusivity, missing price caps (`agent_type=contract_risk`) |
| 15 | AI Assistant (intent router) | `POST /assistant` is a single entry point that classifies a message as a spend question or an agent goal (rule-based keyword tiers, LLM fallback) and routes it: a spend question is answered by the RAG chat inline, a cost-saving/forecast/contract-risk goal comes back as a handoff suggestion the Chat page uses to jump to the Cost Saving Agent page, prefilled and ready to run |

## Design Notes

A few implementation details that aren't obvious from the module table above:

- **Structured function-calling everywhere.** `chat_with_tools()` in `app/services/ai.py` asks Groq's OpenAI-compatible endpoint for structured `tool_calls` (via `tools=`) whenever Ollama is unreachable; the Chat RAG and the Cost Saving/Forecast/Contract Risk agents all run on this path (`ReactStep.mode == "structured"`). Chat used to deliberately keep the plain text-parsed ReAct format instead (a single tool "shouldn't need it"), but agentic Groq models like `openai/gpt-oss-20b` attempt a real structured tool call for a described tool regardless of how many tools are registered - without a matching `tools=` schema in the request, Groq rejects the reply outright with a 400 `tool_use_failed`, which made every Groq-served chat reply fail straight through to the offline fallback. Text-parsed mode (`mode == "text_parsed"`) remains the fallback for turns that don't return a structured call (e.g. Ollama, which is never asked for one) - both modes are visible in the step trace.
- **One ReAct loop, two consumers.** `GET /cost-saving/analyze/stream` emits each ReAct step live as it happens instead of the whole trace at once. `react_engine.py`'s loop is a generator (`iter_react_steps()`) consumed both by this streaming endpoint and by the batch `run_react()`, so there is a single implementation of the loop, not two. The frontend reads the stream via `fetch()` + `ReadableStream` rather than `EventSource`, specifically because `EventSource` can't send the custom `Authorization: Bearer` header this app's auth relies on everywhere else, and a query-string token would leak into browser history/server logs.
- **Shared agent framework, not three stacks.** The Cost Saving, Forecast, and Contract Risk agents reuse the same `react_engine.py` + tool-registry pattern - a new agent is a new tool registry, system prompt, and recommendation function, not new infrastructure. All three share one table (`AgentRun.agent_type`), one endpoint (`agent_type` param), and one frontend page (a type selector), instead of three separate REST/UI stacks.
- **Superlatives need a real ranking, not a similarity score.** `search_spend` only surfaces documents that are textually similar to the query, so "what was our highest expense" can silently miss a bigger item that just didn't match the query text - yet the model would still answer with full confidence. The Chat's system prompt now explicitly tells it to use the deterministic `top_expenses` tool (`agents/tools.py`, `ORDER BY total DESC`) for any highest/biggest/most-expensive question instead of inferring a superlative from `search_spend` hits alone.
- **Guardrails apply everywhere an LLM sees free-text user input**, not just the Chat: `validate_input`/`sanitize_output` (`guardrails.py`) now guard the Cost Saving/Forecast/Contract Risk agents' `goal` too - a blocked goal skips the LLM call entirely, though the deterministic Recommendation Engine still runs (it depends on `agent_type` and real data, never on the goal text).
- **Spend data visibility is scoped by role, not by individual user.** `get_visible_user_ids()` (`app/core/deps.py`) resolves, per request, the set of user ids the caller may see: everyone sharing their role, or no filter at all for Admin. Every read/write touching documents, line items, the dashboard, search, duplicates, anomalies, and contract clauses goes through this - both on the PostgreSQL side (`user_id IN (...)`) and on the Qdrant side (a `MatchAny` filter on the same ids), so vector search results never drift out of sync with what the relational queries return. Admin is enforced as a singleton: promoting a second user to Admin (`PATCH /users/{id}/role`) automatically demotes the current one to Buyer in the same transaction, rather than allowing two Admins to exist. The classifier's feedback exemplars (`classifier.py::_FEEDBACK_EXEMPLARS`) are similarly scoped by `(role, category)` instead of being one global pool, so a Buyer's corrections don't bias Finance's classifications. Chat sessions and Cost Saving Agent run history are the deliberate exception - they stay private per individual user even though the spend data they analyze is shared.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 (or Docker)
- Ollama (for local AI)
- Qdrant (for vector search)

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your database and Ollama settings
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker (backend services)

```bash
docker compose up -d
```

This starts: API (`:8000`), PostgreSQL, Qdrant (`:6333`), Ollama (`:11434`). It does **not** include the frontend — start that separately with `npm run dev` as shown above.

### Demo Data

The app starts empty. To populate it with realistic sample data (3 users
with different roles, invoices/orders across 6 months, one deliberate
example of each detection type - a duplicate line, a price anomaly, a
quantity anomaly, and a new-supplier anomaly - plus two suppliers with a
verified spend increase and two contracts with an indexed auto-renewal
clause, so the Cost Saving Agent has real opportunities to find):

```bash
cd backend
python scripts/seed_demo_data.py            # skips if already seeded
python scripts/seed_demo_data.py --reset    # wipes and reseeds
```

Login with any of `demo.admin@spendintel.io` / `demo.buyer@spendintel.io` /
`demo.finance@spendintel.io`, password `DemoPass123!` (printed by the script
too). Requires `DATABASE_URL` to be reachable; Ollama/Qdrant are optional -
the script falls back to the same offline methods the app itself uses if
they aren't running. Since spend data is shared per role (see Design Notes
above), the buyer and finance logins each see only their own seeded set
today - registering a second buyer/finance account would immediately see
the existing one's data too, without needing to reseed anything.

### Production Deploy (zero-cost stack)

The default `render.yaml` no longer self-hosts Qdrant/Ollama as Render
private services — those start billing immediately even on the smallest
plan. Instead it relies on external free tiers plus a Groq fallback for the
LLM, keeping the whole stack at $0/month.

**1. Postgres → [Neon](https://neon.tech) (free forever)**
Create a free project, copy the connection string. (Render's own free
Postgres expires after 90 days — fine for a demo, not for a portfolio piece
meant to stay up.)

**2. Vector store → [Qdrant Cloud](https://cloud.qdrant.io) (1GB free forever)**
Create a free cluster, copy its **URL** and **API key**.

**3. LLM fallback → [Groq](https://console.groq.com) (free tier, no card required)**
Generate an API key. Used automatically whenever Ollama isn't reachable
(i.e. always, in production) — see `app/services/ai.py::chat`, which tries
Ollama first, then Groq, then a deterministic offline reply as last resort.

**4. Embeddings fallback → [Jina AI](https://jina.ai) (free tier, no card required)**
Generate an API key (1M free tokens on signup). Used automatically whenever
Ollama isn't reachable — see `app/services/ai.py::embed_text`, which tries
Ollama first, then Jina (`jina-embeddings-v3`, requested at 768 dimensions to
match this project's Qdrant schema exactly), then a deterministic offline
hash embedding as last resort. Without `JINA_API_KEY` set, semantic
search/RAG retrieval quality is noticeably lower (the hash fallback only
catches literal keyword overlap, not real meaning) but still functional.

**5. Backend → Render**, driven by `render.yaml` (Blueprint):
```bash
# From the Render dashboard: New > Blueprint, point it at this repo.
```
- Plan **Free** — the service sleeps after ~15 min of inactivity and takes
  30-60s to wake up on the next request. Expected behavior on the free tier.
  Mitigated two ways: `.github/workflows/keepalive.yml` pings `/health`
  every 10 minutes to keep the service warm (set the repo variable
  `RENDER_HEALTH_URL` to your deployed URL, otherwise it defaults to
  `https://ai-spend-intelligence-api.onrender.com/health`), and the frontend
  shows an honest "waking up" banner if a request is slow instead of looking
  broken. Two things to know about the keep-alive workflow: GitHub disables
  scheduled workflows automatically after 60 days with no push to the repo
  (re-enable it manually from the Actions tab, or just push a commit), and
  keeping one free Render service alive ~24/7 uses close to the account's
  entire free instance-hour budget (~750h/month) — worth remembering before
  adding a second free service on the same Render account.
- Set these as Render secrets: `DATABASE_URL` (Neon), `QDRANT_URL` +
  `QDRANT_API_KEY` (Qdrant Cloud), `GROQ_API_KEY`, `JINA_API_KEY`.
  `SECRET_KEY` is auto-generated by the blueprint. Leave `OLLAMA_HOST` empty.
- Migrations run automatically on every container start (the Dockerfile's
  `CMD` runs `alembic upgrade head` before starting uvicorn), so no manual
  step is needed after deploys, including the first one. For demo data,
  run `python scripts/seed_demo_data.py` once, locally, with `DATABASE_URL`
  pointed at Neon (no Render shell needed — free plans don't include one).

**6. Frontend → Vercel**, driven by `frontend/vercel.json`:
1. Import the repo in Vercel, set **Root Directory** to `frontend`.
2. Set the environment variable `VITE_API_URL` to your deployed Render API URL (e.g. `https://ai-spend-intelligence-api.onrender.com`).
3. Update `CORS_ORIGINS` on the backend (Render env var) to include your Vercel domain, then redeploy the backend.

**Local development** is unaffected: `docker-compose up` still runs a local
Postgres, Qdrant, and (optionally) Ollama container, matching the defaults
in `.env.example`.

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register new user (self-service choice of "buyer" or "finance"; "admin" is never accepted here, only granted later via `PATCH /users/{id}/role`) |
| POST | `/auth/login` | Login, get JWT token |
| GET | `/auth/me` | Current user profile |
| GET | `/users` | List users (admin only) |
| PATCH | `/users/{id}/role` | Change a user's role (admin only); promoting a second user to "admin" auto-demotes the current one to "buyer" (admin is a singleton) |
| DELETE | `/users/{id}` | Delete a user (admin only) |
| GET | `/users/{id}/audit-log` | View a user's audit trail (admin only) |
| POST | `/documents/upload` | Upload a document (PDF/CSV/Excel/Image) |
| POST | `/documents/{id}/process` | Parse, classify, detect anomalies/duplicates |
| GET | `/documents` | List documents visible to the current user (shared with everyone sharing their role; all documents for admin) |
| GET | `/documents/{id}` | Get document with line items |
| DELETE | `/documents/{id}` | Delete a document |
| POST | `/classification` | Classify descriptions via API |
| POST | `/classification/single` | Classify a single description |
| GET | `/search?q=...` | Semantic search |
| PATCH | `/classification/line-items/{id}` | Correct a classification (auto-seeds feedback) |
| POST | `/classification/retrain` | Bulk-retrain classifier from user feedback (admin/finance only) |
| GET | `/anomalies` | List flagged anomalies |
| GET | `/duplicates` | List duplicate groups |
| GET | `/analytics/dashboard` | Dashboard aggregations |
| POST | `/feedback` | Submit user feedback |
| POST | `/chat` | Ask a question (ReAct RAG with guardrails & memory) |
| GET | `/chat/sessions` | List chat sessions |
| GET | `/chat/sessions/{id}/messages` | Get chat history |
| DELETE | `/chat/sessions/{id}` | Delete a session |
| POST | `/cost-saving/analyze` | Run an agent for a goal (`agent_type`: `cost_saving` \| `forecast` \| `contract_risk`), get back a ReAct trace + cited recommendations |
| GET | `/cost-saving/analyze/stream` | Same as above, streamed live as `text/event-stream` (`step` events, then a `done` event) |
| GET | `/cost-saving/history` | List past agent runs for the current user (optionally filtered by `agent_type`) |
| GET | `/cost-saving/history/{id}` | Get a single past agent run |
| POST | `/assistant` | Single intent-routed entry point: a spend question is answered inline (same shape as `/chat`); a cost-saving/forecast/contract-risk goal returns a `suggestion` (`agent_type` + `goal`) instead of running the agent inline |
| GET | `/assistant/stream` | Same intent routing as above, streamed live as `text/event-stream` |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Runtime environment |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — **the app refuses to start with this default when `ENVIRONMENT=production`** |
| `MAX_UPLOAD_MB` | `50` | Max upload size, enforced on `/documents/upload` (rejects with 413 above this, 415 for unsupported file types) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_CHAT_MODEL` | `llama3.2` | Model for chat completions |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Model for embeddings |
| `OLLAMA_TIMEOUT` | `30` | Seconds before falling back to Groq (or offline) when Ollama doesn't respond |
| `GROQ_API_KEY` | _(unset)_ | Enables the Groq cloud fallback when Ollama is unreachable |
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-20b` | Groq model used for the fallback |
| `GROQ_TIMEOUT` | `30` | Seconds before falling back to the offline deterministic reply |
| `JINA_API_KEY` | _(unset)_ | Enables the Jina AI cloud embeddings fallback when Ollama is unreachable |
| `JINA_EMBED_MODEL` | `jina-embeddings-v3` | Jina model used for the embeddings fallback |
| `JINA_TIMEOUT` | `30` | Seconds before falling back to the offline hash embedding |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector DB URL |
| `QDRANT_API_KEY` | _(unset)_ | Required for Qdrant Cloud, unused for a local/self-hosted instance |
| `QDRANT_COLLECTION` | `spend_documents` | Qdrant collection for invoice/order line items |
| `QDRANT_CONTRACT_COLLECTION` | `spend_contracts` | Separate Qdrant collection for contract-clause chunks (contract point ids reuse the DB's own ids, so this must not collide with `QDRANT_COLLECTION`) |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Allowed CORS origins |
| `ANOMALY_ZSCORE_THRESHOLD` | `2.5` | Z-score anomaly threshold |
| `DUPLICATE_SIMILARITY_THRESHOLD` | `0.88` | Similarity threshold for dupes |

## Testing

```bash
cd backend
python -m pytest tests/ -v

cd frontend
npm test
```

Backend: 162 pytest tests across 29 files (`backend/tests/`). Frontend:
Vitest + React Testing Library, covering `AgentStepTimeline` and
`RecommendationCard`; `npm test` runs in CI (`frontend-test` job).

## RAG Evaluation

```bash
cd backend
python scripts/evaluate_rag.py
```

Measures retrieval precision, answer relevance, and faithfulness against a curated test set.

## GitHub Actions

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | Push/PR to `main` | Backend lint (ruff), backend tests (pytest), frontend typecheck (tsc), frontend build (vite), frontend tests (vitest) |
| `cd.yml` | Push to `main` | Build Docker image → push to GHCR → deploy to Render |
| `keepalive.yml` | Schedule (every 10 min) + manual dispatch | Ping `/health` on the deployed Render API to keep the free-tier service warm |

## Project Structure

```
.github/workflows/     → CI/CD pipelines
backend/
  app/
    api/               → FastAPI route handlers
    core/              → Config, DB, auth, security
    models/            → SQLAlchemy ORM models
    schemas/           → Pydantic v2 request/response schemas
    services/          → Business logic
      ai.py                  → Ollama chat & embeddings (fixed-dim, hash fallback offline)
      analytics.py           → Spend overview, supplier variance, dashboard aggregations, forecasting
      chat_react.py          → thin wrapper: two-tool (search_spend, top_expenses) ReAct chat on top of agents/react_engine.py
      chat_service.py        → RAG pipeline with memory trimming
      classifier.py          → 3-tier classification (rule → embedding → LLM)
      document_intelligence.py → OCR/parsing/extraction pipeline for uploaded documents
      duplicates.py          → Exact + semantic duplicate detection
      feedback_service.py    → User feedback capture and retraining triggers
      i18n_strings.py        → User-facing string localization
      search.py              → Semantic search over indexed spend line items
      vector_store.py        → Qdrant integration (line-item + contract-chunk collections)
      contract_intelligence.py → contract text chunking, embedding, semantic clause search
      cost_saving_agent.py   → Cost Saving / Forecast / Contract Risk agents: runs the ReAct loop + the Recommendation Engine (agent_type param)
      assistant_router.py    → intent classifier for POST /assistant (rule-based tiers -> LLM fallback)
      agents/
        react_engine.py      → generic multi-tool ReAct loop (Thought/Action/Observation)
        tools.py              → shared tool registry (spend overview, variance, anomalies, contract search, top expenses) wrapping existing services, used by the Cost Saving Agent and by chat_react.py
      anomalies.py           → Price, quantity, supplier anomaly detection
      guardrails.py          → Input validation & output sanitization
      audit_service.py       → Audit trail (login, uploads, corrections, retrain, role changes, agent runs)
      executor.py            → Thread pool for CPU-bound tasks
  scripts/             → RAG evaluation (evaluate_rag.py), demo data seeding (seed_demo_data.py)
  tests/               → 162 pytest tests (29 files)
  Dockerfile
frontend/
  src/
    pages/             → Login, Dashboard, Documents, DocumentView, Classification,
                          SemanticSearch, ChatPage, CostSavingAgentPage, AnomaliesPage,
                          DuplicatesPage, AdminUsers (11 pages)
    components/        → Layout, Card, AgentStepTimeline, RecommendationCard, ForecastChart,
                          BackendWakingBanner, ConfirmDialog, ErrorBoundary, InlineError,
                          Markdown, Skeleton, TableScroll, ToastContainer
    hooks/             → useBackendWaking, useDocumentTitle
    api.ts             → API client
  vercel.json          → Vercel deploy config
```

## License

MIT
