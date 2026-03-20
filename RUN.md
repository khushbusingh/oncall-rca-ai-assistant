# How to run the app and see it live

## 1. Start the backend (Terminal 1)

From the project root:

```bash
cd /Users/khushbu.kumari/CRM/oncall-rag-assistant/backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Leave this running. First run downloads the embedding model (~80MB).

**Check:** Open http://localhost:8000/health — should return `{"status":"ok"}`.  
**API docs:** http://localhost:8000/docs

---

## 2. Start the frontend (Terminal 2)

Open a **new** terminal:

```bash
cd /Users/khushbu.kumari/CRM/oncall-rag-assistant/frontend
npm install
npm run dev
```

Leave this running.

---

## 3. Open the app in the browser

Go to: **http://localhost:3000**

You should see the CRM On-Call Assistant UI (Search, RCA / Runbook, Services, RCA by file).

---

## One-time setup only

- Backend: `venv` and `pip install` once; then you only need `uvicorn ...`.
- Frontend: `npm install` once; then you only need `npm run dev`.

## If the frontend can’t reach the backend

- Ensure the backend is running on port 8000.
- The frontend proxies `/api` and `/health` to `http://127.0.0.1:8000` (see `frontend/vite.config.js`).
