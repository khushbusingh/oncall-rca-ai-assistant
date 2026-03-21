# CRM On-Call RAG Assistant

A RAG (Retrieval Augmented Generation) app to smooth on-call: search runbooks by natural language, maintain knowledge per service, and ingest PDF/DOCX docs. Data is stored persistently (SQLite + ChromaDB).

## Features

- **Search**: Natural-language search over all knowledge (manual entries + uploaded docs). Optional filter by CRM service. Optional AI-generated answer (if OpenAI key is set).
- **Knowledge base (CRUD)**: Add, edit, delete runbook entries per service. Stored in SQLite and indexed for search.
- **Services (CRUD)**: Manage CRM services (e.g. sa-myntra, spectrum-server). Each service has its own entries and uploads.
- **Upload PDF/DOCX**: Ingest existing runbooks; content is chunked, embedded, and stored in ChromaDB for search.

## Quick start

### Backend (Python)

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Data is stored under `backend/data/` (SQLite DB + ChromaDB + uploads). First run will download the embedding model (~80MB).

### Ingest existing documents (one-time)

To load all PDF/DOC/DOCX files from the `documents/` folder into the knowledge base (creates **CRM** and **SA** services if missing, infers service from filename):

```bash
cd backend
source venv/bin/activate
python -m app.ingest_documents
```

After this, use the app (Search, RCA / Runbook, RCA by file) to add or update any new cases.

### Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The dev server proxies `/api` and `/health` to the backend (port 8000).

## Configuration (backend)

Create `backend/.env` (optional):

```env
# Database (default: sqlite in ./data/oncall.db)
DATABASE_URL=sqlite+aiosqlite:///./data/oncall.db

# ChromaDB persistence
CHROMA_PERSIST_DIR=./data/chroma_db

# OpenAI (ChatGPT) – when set, used for both embeddings and search answers (no Hugging Face)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
# SSL verify: default False (for corporate proxy). Set true for normal networks.
# OPENAI_SSL_VERIFY=true

# RAG tuning
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K_RETRIEVE=5
```

With `OPENAI_API_KEY`: embeddings and answers use OpenAI (no Hugging Face). Without it: local sentence-transformers; search returns only chunks (no AI answer). 
## Usage

1. **Services**: Add your CRM services (e.g. sa-myntra, spectrum-server).
2. **Knowledge base**: Add runbook entries (title, description, solution) per service. These are searchable immediately.
3. **Upload**: Upload existing PDF/DOCX runbooks; assign to a service. Content is chunked and indexed.
4. **Search**: On call, type a question (e.g. “Payment failure in sa-myntra”) and optionally pick a service. You get relevant chunks and, if configured, an AI-generated answer.

## Tech stack

- **Backend**: FastAPI, SQLAlchemy (async), ChromaDB, sentence-transformers, PyPDF, python-docx.
- **Frontend**: React 18, Vite. No extra UI library.
- **Storage**: SQLite (services, entries, upload metadata), ChromaDB (vector index for search).

## API (for reference)

- `GET/POST /api/services`, `GET/PATCH/DELETE /api/services/{id}`
- `GET/POST /api/entries`, `GET/PATCH/DELETE /api/entries/{id}` (query param: `service_id`)
- `POST /api/upload` (form: `file`, `service_id`)
- `POST /api/search` (JSON: `query`, optional `service_id`, `top_k`)

Open http://localhost:8000/docs for Swagger UI.

## Deploy on Render

`ModuleNotFoundError: No module named 'app'` happens if Uvicorn runs from the **repository root** instead of **`backend/`**.

**Option A — Dashboard:** set **Root Directory** to `backend`, then:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**Option B — Stay at repo root:** use:

- **Build command:** `cd backend && pip install -r requirements.txt`
- **Start command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`

This repo includes [`render.yaml`](render.yaml) (Blueprint) with `rootDir: backend` so imports match local `cd backend` usage. Mount a **persistent disk** on `backend/data` if you need SQLite/Chroma to survive redeploys.

## Deploy frontend on Vercel (API on Render)

The browser must call your Render API by **full URL**; the Vite dev proxy only applies locally.

1. In **Vercel** → your project → **Settings → Environment Variables**, add (all deployment targets you use, e.g. Production):

   | Name | Value |
   |------|--------|
   | `VITE_API_URL` | `https://oncall-rca-api.onrender.com` |

   No trailing slash. Redeploy after saving (Vite bakes this in at build time).

2. **Root Directory:** if the repo is this monorepo, set **Root Directory** to `frontend` so **Build Command** is `npm run build` and **Output Directory** is `dist`.

3. Local dev stays unchanged: do **not** set `VITE_API_URL` (or use `frontend/.env.example` as a reference only); `npm run dev` keeps using relative `/api` → Vite proxy.

Backend CORS is already permissive (`allow_origins=["*"]`); no backend change required for a Vercel origin.

### Vercel build: `ERR_MODULE_NOT_FOUND` during `vite build`

Usually one of:

1. **Wrong root** — In Vercel → **Settings → General → Root Directory**, set **`frontend`** (for this monorepo). If the build runs from the repo root, `vite` is never installed.
2. **Node too old** — Vite 5 needs **Node ≥ 18**. This repo includes **`frontend/.nvmrc`** (`20`); Vercel will pick that up. You can also set **Settings → Node.js Version** to **20.x**.
3. **Missing install** — `vite` and `@vitejs/plugin-react` are listed under **`dependencies`** so they are always installed even when install runs with production-like flags.
