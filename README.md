# AI Spend Intelligence Platform

[![CI](https://github.com/YOUR_USER/ai-spend-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USER/ai-spend-intelligence-platform/actions/workflows/ci.yml)

A fully modular AI-powered platform for intelligent corporate spend management. Supports the entire lifecycle: document ingestion, UNSPSC classification, semantic search, RAG chat, anomaly and duplicate detection, analytics dashboard, and feedback-driven improvement loops.

## Architecture

```
Frontend (React) → FastAPI Backend → PostgreSQL (relational) + Qdrant (vector store) + Ollama (AI)
```

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
| 4 | AI Chat | Retrieval-Augmented Generation (RAG) chat with a real ReAct loop (the model can issue further `search_spend` searches before answering), source citations, conversation memory (trimming + summarization), guardrails |
| 5 | Duplicate Detection | Exact (supplier+invoice+amount) + semantic (embedding similarity) matching |
| 6 | Anomaly Detection | Per-category z-score outlier detection on price, quantity, and new-supplier alerts |
| 7 | Dashboard | Real-time charts: spend by category/month, top suppliers, KPI cards |
| 8 | Feedback Loop | User corrections stored → real-time classifier retraining via `POST /classification/retrain` |
| 9 | REST API | Complete OpenAPI-documented endpoints for every module |
| 10 | User Management | JWT auth, RBAC (Admin/Buyer/Finance), audit logging |

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
with different roles, 9 invoices/orders across 6 months, and one deliberate
example of each detection type - a duplicate line, a price anomaly, a
quantity anomaly, and a new-supplier anomaly):

```bash
cd backend
python scripts/seed_demo_data.py            # skips if already seeded
python scripts/seed_demo_data.py --reset    # wipes and reseeds
```

Login with any of `demo.admin@spendintel.io` / `demo.buyer@spendintel.io` /
`demo.finance@spendintel.io`, password `DemoPass123!` (printed by the script
too). Requires `DATABASE_URL` to be reachable; Ollama/Qdrant are optional -
the script falls back to the same offline methods the app itself uses if
they aren't running.

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
Embeddings still fall back to the offline hash method in production, since
Groq has no embeddings endpoint; retrieval quality is lower than with a real
embedding model but fully functional.

**4. Backend → Render**, driven by `render.yaml` (Blueprint):
```bash
# From the Render dashboard: New > Blueprint, point it at this repo.
```
- Plan **Free** — the service sleeps after ~15 min of inactivity and takes
  30-60s to wake up on the next request. Expected behavior on the free tier.
- Set these as Render secrets: `DATABASE_URL` (Neon), `QDRANT_URL` +
  `QDRANT_API_KEY` (Qdrant Cloud), `GROQ_API_KEY`. `SECRET_KEY` is
  auto-generated by the blueprint. Leave `OLLAMA_HOST` empty.
- After the first deploy, run `alembic upgrade head` against the Neon URL
  (Render shell or locally with `DATABASE_URL` pointed at Neon), then
  optionally `python scripts/seed_demo_data.py` for demo data.

**5. Frontend → Vercel**, driven by `frontend/vercel.json`:
1. Import the repo in Vercel, set **Root Directory** to `frontend`.
2. Set the environment variable `VITE_API_URL` to your deployed Render API URL (e.g. `https://ai-spend-intelligence-api.onrender.com`).
3. Update `CORS_ORIGINS` on the backend (Render env var) to include your Vercel domain, then redeploy the backend.

**Local development** is unaffected: `docker-compose up` still runs a local
Postgres, Qdrant, and (optionally) Ollama container, matching the defaults
in `.env.example`.

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register new user (always created as "buyer") |
| POST | `/auth/login` | Login, get JWT token |
| GET | `/auth/me` | Current user profile |
| GET | `/users` | List users (admin only) |
| PATCH | `/users/{id}/role` | Change a user's role (admin only) |
| GET | `/users/{id}/audit-log` | View a user's audit trail (admin only) |
| POST | `/documents/upload` | Upload a document (PDF/CSV/Excel/Image) |
| POST | `/documents/{id}/process` | Parse, classify, detect anomalies/duplicates |
| GET | `/documents` | List user documents |
| GET | `/documents/{id}` | Get document with line items |
| DELETE | `/documents/{id}` | Delete a document |
| POST | `/classification` | Classify descriptions via API |
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
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector DB URL |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Allowed CORS origins |
| `ANOMALY_ZSCORE_THRESHOLD` | `2.5` | Z-score anomaly threshold |
| `DUPLICATE_SIMILARITY_THRESHOLD` | `0.88` | Similarity threshold for dupes |

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

## RAG Evaluation

```bash
cd backend
python scripts/evaluate_rag.py
```

Measures retrieval precision, answer relevance, and faithfulness against a curated test set.

## GitHub Actions

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | Push/PR to `main` | Backend lint (ruff), backend tests (pytest), frontend typecheck (tsc), frontend build (vite) |
| `cd.yml` | Push to `main` | Build Docker image → push to GHCR → deploy to Render |

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
      ai.py            → Ollama chat & embeddings (fixed-dim, hash fallback offline)
      chat_react.py    → ReAct loop (Thought/Action/Observation) with a real search_spend tool
      chat_service.py  → RAG pipeline with memory trimming
      classifier.py    → 3-tier classification (rule → embedding → LLM)
      vector_store.py  → Qdrant integration (semantic search + RAG retrieval)
      anomalies.py     → Price, quantity, supplier anomaly detection
      guardrails.py    → Input validation & output sanitization
      audit_service.py → Audit trail (login, uploads, corrections, retrain, role changes)
      executor.py      → Thread pool for CPU-bound tasks
  scripts/             → RAG evaluation (evaluate_rag.py)
  tests/               → 72 pytest tests
  Dockerfile
frontend/
  src/
    pages/             → 10 pages (Dashboard, Documents, Chat, Admin, etc.)
    components/        → Layout shell
    api.ts             → API client
  vercel.json          → Vercel deploy config
```

## License

MIT
