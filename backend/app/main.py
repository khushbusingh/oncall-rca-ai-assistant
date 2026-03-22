"""FastAPI app: CRUD for services & knowledge, document upload, RAG search."""
import re
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db, init_db, Service, KnowledgeEntry, DocumentUpload, AsyncSessionLocal
from app.document_loader import load_and_chunk_file
from app.rag import add_chunks_to_collection, query_collection, delete_chunks_by_ids
from app.config import settings
from app.search_cache import get_search_cached, set_search_cached

app = FastAPI(title="CRM On-Call RAG Assistant", version="1.0.0")


@app.get("/")
async def root():
    """Backend API only. Use the frontend for the app UI."""
    return {
        "message": "CRM On-Call RAG Assistant API",
        "docs": "/docs",
        "health": "/health",
        "app_ui": "Open http://localhost:3000 for the React app",
    }


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic schemas ---
class ServiceCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ServiceOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True


class KnowledgeEntryCreate(BaseModel):
    service_id: int
    title: str
    description: Optional[str] = None
    solution: Optional[str] = None


class KnowledgeEntryUpdate(BaseModel):
    service_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    solution: Optional[str] = None


class KnowledgeEntryOut(BaseModel):
    id: int
    service_id: int
    title: str
    description: Optional[str]
    solution: Optional[str]
    source: str
    source_file: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class SearchQuery(BaseModel):
    query: str
    service_id: Optional[int] = None
    top_k: Optional[int] = None


class SearchResultChunk(BaseModel):
    document: str
    metadata: dict
    distance: Optional[float]


class SearchResponse(BaseModel):
    chunks: List[SearchResultChunk]
    answer: Optional[str] = None


# --- Helpers ---
# Stopwords and min length so we only boost on meaningful query terms
_QUERY_STOP = frozenset({"a", "an", "the", "of", "or", "and", "to", "for", "in", "on", "is", "it", "how", "what", "why", "when", "can", "do", "does", "i", "me", "my", "we", "be", "are", "was", "have", "has", "if", "at", "by", "with", "as", "from", "that", "this", "so", "but", "not", "no"})


def _query_terms(query: str) -> List[str]:
    """Extract meaningful search terms (lowercase, no stopwords, min length 2)."""
    words = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return [w for w in words if len(w) >= 2 and w not in _QUERY_STOP]


def _rerank_by_term_match(chunks: List[dict], query: str, top_k: int) -> List[dict]:
    """Prefer chunks that contain query terms to reduce irrelevant results. Keeps top_k chunks."""
    terms = _query_terms(query)
    if not terms:
        return chunks[:top_k]
    scored = []
    for c in chunks:
        doc = (c.get("document") or "").lower()
        match_count = sum(1 for t in terms if t in doc)
        distance = c.get("distance") is not None and c.get("distance") or 0.0
        scored.append((match_count, distance, c))
    # Sort: more term matches first, then lower distance (more similar), then original order
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [c for _, _, c in scored[:top_k]]


def _serialize_service(s: Service) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _serialize_entry(e: KnowledgeEntry) -> dict:
    return {
        "id": e.id,
        "service_id": e.service_id,
        "title": e.title,
        "description": e.description,
        "solution": e.solution,
        "source": e.source,
        "source_file": e.source_file,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _entry_to_search_text(entry: KnowledgeEntry) -> str:
    """Build a single searchable text for this entry (for vector store)."""
    parts = [f"Title: {entry.title}"]
    if entry.description:
        parts.append(f"Description: {entry.description}")
    if entry.solution:
        parts.append(f"Solution: {entry.solution}")
    return "\n\n".join(parts)


# Model context limit 8192 tokens. Reserve for system msg + "Context:\n" + "\n\nQuestion: " + query + response.
# ~2.5 chars/token => 8192 * 2.5 ≈ 20k chars total; cap context at 7500 chars (~3000 tokens) to be safe.
MAX_CONTEXT_CHARS = 7500


def _truncate_context_for_model(chunks: List[str], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Join chunks until total length <= max_chars. Character-based so we never exceed model limit."""
    parts = []
    total = 0
    sep_len = len("\n\n---\n\n")
    for c in chunks:
        need = len(c) + (sep_len if parts else 0)
        if total + need > max_chars and parts:
            break
        parts.append(c)
        total += need
    return "\n\n---\n\n".join(parts)


async def _generate_answer(query: str, context_chunks: List[str]) -> Optional[str]:
    """Use OpenAI to generate an answer from retrieved context (if API key set). On any error, return None so search still returns chunks."""
    if not settings.openai_api_key or not context_chunks:
        return None
    try:
        import httpx
        from openai import AsyncOpenAI
        verify_env = os.environ.get("OPENAI_SSL_VERIFY", "false").strip().lower()
        verify = verify_env in ("1", "true", "yes", "on")
        http_client = httpx.AsyncClient(verify=verify)
        client = AsyncOpenAI(api_key=settings.openai_api_key, http_client=http_client)
        context = _truncate_context_for_model(context_chunks)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are an on-call assistant. Answer based only on the provided context. When the context includes [Service: <name>], mention that service name in your answer (e.g. 'For CRM, ...' or 'According to the SA runbook, ...'). If the context does not contain the answer, say so and suggest checking the knowledge base."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning("RAG answer generation failed (chunks still returned): %s", e)
        return None


# --- Startup ---
@app.on_event("startup")
async def startup():
    await init_db()


# --- Services CRUD ---
@app.get("/api/services", response_model=List[ServiceOut])
async def list_services(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Service).order_by(Service.name))
    services = r.scalars().all()
    return [_serialize_service(s) for s in services]


@app.post("/api/services", response_model=ServiceOut)
async def create_service(body: ServiceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Service).where(Service.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Service with this name already exists")
    s = Service(name=body.name, description=body.description)
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return _serialize_service(s)


@app.get("/api/services/{service_id}", response_model=ServiceOut)
async def get_service(service_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Service).where(Service.id == service_id))
    s = r.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Service not found")
    return _serialize_service(s)


@app.patch("/api/services/{service_id}", response_model=ServiceOut)
async def update_service(service_id: int, body: ServiceUpdate, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Service).where(Service.id == service_id))
    s = r.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Service not found")
    if body.name is not None:
        s.name = body.name
    if body.description is not None:
        s.description = body.description
    await db.flush()
    await db.refresh(s)
    return _serialize_service(s)


@app.delete("/api/services/{service_id}")
async def delete_service(service_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Service).where(Service.id == service_id))
    s = r.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Service not found")
    await db.delete(s)
    return {"ok": True}


# --- Knowledge entries CRUD ---
@app.get("/api/entries", response_model=List[KnowledgeEntryOut])
async def list_entries(service_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    q = select(KnowledgeEntry).order_by(KnowledgeEntry.updated_at.desc())
    if service_id is not None:
        q = q.where(KnowledgeEntry.service_id == service_id)
    r = await db.execute(q)
    entries = r.scalars().all()
    return [_serialize_entry(e) for e in entries]


@app.post("/api/entries", response_model=KnowledgeEntryOut)
async def create_entry(body: KnowledgeEntryCreate, db: AsyncSession = Depends(get_db)):
    # Verify service exists
    r = await db.execute(select(Service).where(Service.id == body.service_id))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Service not found")
    e = KnowledgeEntry(
        service_id=body.service_id,
        title=body.title,
        description=body.description,
        solution=body.solution,
        source="manual",
    )
    db.add(e)
    await db.flush()
    await db.refresh(e)
    # Add to vector store for search (store id in metadata so we can update/delete later)
    text = _entry_to_search_text(e)
    chunk_id = f"entry_{e.id}"
    add_chunks_to_collection(
        [text],
        metadatas=[{"type": "entry", "entry_id": str(e.id), "service_id": str(body.service_id), "title": e.title}],
        ids=[chunk_id],
    )
    return _serialize_entry(e)


@app.get("/api/entries/{entry_id}", response_model=KnowledgeEntryOut)
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    e = r.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    return _serialize_entry(e)


@app.patch("/api/entries/{entry_id}", response_model=KnowledgeEntryOut)
async def update_entry(entry_id: int, body: KnowledgeEntryUpdate, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    e = r.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    if body.service_id is not None:
        e.service_id = body.service_id
    if body.title is not None:
        e.title = body.title
    if body.description is not None:
        e.description = body.description
    if body.solution is not None:
        e.solution = body.solution
    await db.flush()
    await db.refresh(e)
    # Update vector store: delete old chunk, add new
    delete_chunks_by_ids([f"entry_{entry_id}"])
    text = _entry_to_search_text(e)
    add_chunks_to_collection(
        [text],
        metadatas=[{"type": "entry", "entry_id": str(e.id), "service_id": str(e.service_id), "title": e.title}],
        ids=[f"entry_{e.id}"],
    )
    return _serialize_entry(e)


@app.delete("/api/entries/{entry_id}")
async def delete_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    e = r.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(e)
    delete_chunks_by_ids([f"entry_{entry_id}"])
    return {"ok": True}


# --- Document upload (PDF/DOCX) ---
UPLOAD_DIR = Path("./data/uploads")  # type: ignore
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    service_id: int = Form(...),
    update_existing: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """Add a new document or a new version of an existing one. Existing data is never deleted."""
    r = await db.execute(select(Service).where(Service.id == service_id))
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Service not found")
    filename = file.filename or "unknown"
    suffix = os.path.splitext(filename)[1].lower()
    upload_id = str(uuid.uuid4())
    path = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    try:
        chunks = load_and_chunk_file(
            str(path),
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse document: {e}")
    if not chunks:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="No text could be extracted from the document")
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {"type": "upload", "service_id": str(service_id), "filename": filename, "upload_id": upload_id, "chunk_id": i}
        for i in ids
    ]
    add_chunks_to_collection(chunks, metadatas=metadatas, ids=ids)
    doc_record = DocumentUpload(service_id=service_id, filename=filename, upload_id=upload_id, chunk_count=len(chunks))
    db.add(doc_record)
    await db.flush()
    return {"ok": True, "chunks": len(chunks), "filename": filename, "upload_id": upload_id, "is_new_version": update_existing}


def _get_latest_upload_ids(db_uploads: list) -> List[str]:
    """From DocumentUpload rows (ordered by created_at desc), return upload_ids for latest version of each (service_id, filename)."""
    seen = set()
    out = []
    for row in db_uploads:
        key = (row.service_id, row.filename)
        if key in seen or not row.upload_id:
            continue
        seen.add(key)
        out.append(row.upload_id)
    return out


# --- RAG Search ---
def _normalize_search_query(q: str) -> str:
    """Stable key for caching: collapse whitespace, lowercase."""
    return re.sub(r"\s+", " ", (q or "").strip()).lower()[:4000]


@app.post("/api/search", response_model=SearchResponse)
async def search(body: SearchQuery, db: AsyncSession = Depends(get_db)):
    logger.info("search request: query=%r service_id=%s top_k=%s", body.query, body.service_id, body.top_k)
    top_k = body.top_k or settings.top_k_retrieve
    query_norm = _normalize_search_query(body.query)
    if settings.enable_search_cache and query_norm:
        cached = get_search_cached(
            query_norm,
            body.service_id,
            top_k,
            max_entries=settings.search_cache_max_entries,
        )
        if cached is not None:
            logger.info("search cache hit (query_norm len=%s)", len(query_norm))
            return SearchResponse.model_validate(cached)
    q = select(DocumentUpload).order_by(desc(DocumentUpload.created_at))
    if body.service_id is not None:
        q = q.where(DocumentUpload.service_id == body.service_id)
    r = await db.execute(q)
    uploads = r.scalars().all()
    latest_upload_ids = _get_latest_upload_ids(uploads)
    logger.info("search: DocumentUpload rows=%s latest_upload_ids count=%s ids=%s", len(uploads), len(latest_upload_ids), latest_upload_ids[:5] if latest_upload_ids else [])
    filter_meta = None
    if latest_upload_ids:
        filter_meta = {
            "$or": [
                {"type": "entry"},
                {"$and": [{"type": "upload"}, {"upload_id": {"$in": latest_upload_ids}}]},
            ]
        }
        if body.service_id is not None:
            filter_meta = {
                "$and": [
                    {"service_id": str(body.service_id)},
                    filter_meta,
                ]
            }
    elif body.service_id is not None:
        filter_meta = {"service_id": str(body.service_id)}
    logger.info("search: filter_meta=%s", filter_meta)
    # Fetch more candidates so we can re-rank by query-term match and drop irrelevant chunks
    candidate_k = top_k * max(1, settings.search_candidates_multiplier)
    chunks_result = query_collection(body.query, top_k=candidate_k, filter_metadata=filter_meta)
    logger.info("search: Chroma returned chunks=%s", len(chunks_result))
    # Deduplicate by document text (overlap + repeated headers often produce same or near-duplicate chunks)
    seen_texts: set = set()
    unique_chunks = []
    for c in chunks_result:
        doc = c["document"] or ""
        doc_stripped = doc.strip()
        if doc_stripped and doc_stripped not in seen_texts:
            seen_texts.add(doc_stripped)
            unique_chunks.append(c)
    # Re-rank: prefer chunks that contain the user's search terms (e.g. "screenshot", "loading", "spinner")
    unique_chunks = _rerank_by_term_match(unique_chunks, body.query, top_k)
    # Resolve service_id -> service name for chunks and for answer
    service_ids = set()
    for c in unique_chunks:
        meta = c.get("metadata") or {}
        sid = meta.get("service_id")
        if sid is not None:
            service_ids.add(int(sid) if isinstance(sid, str) else sid)
    service_id_to_name: dict = {}
    if service_ids:
        r_svc = await db.execute(select(Service.id, Service.name).where(Service.id.in_(service_ids)))
        for row in r_svc.all():
            service_id_to_name[row.id] = row.name
    # Build context with service names so the LLM can mention them in the answer
    preview_len = settings.chunk_preview_chars
    context_texts = []
    chunk_responses = []
    for c in unique_chunks:
        meta = dict(c.get("metadata") or {})
        sid = meta.get("service_id")
        if sid is not None:
            sid_int = int(sid) if isinstance(sid, str) else sid
            name = service_id_to_name.get(sid_int, f"Service {sid}")
            meta["service_name"] = name
            context_texts.append(f"[Service: {name}]\n{c['document']}")
        else:
            meta["service_name"] = None
            context_texts.append(c["document"])
        # Return short preview in response to reduce payload and UI clutter
        doc = c["document"] or ""
        if len(doc) > preview_len:
            doc = doc[:preview_len].rstrip() + "…"
        chunk_responses.append(SearchResultChunk(document=doc, metadata=meta, distance=c.get("distance")))
    answer = await _generate_answer(body.query, context_texts)
    response = SearchResponse(chunks=chunk_responses, answer=answer)
    if settings.enable_search_cache and query_norm:
        set_search_cached(
            query_norm,
            body.service_id,
            top_k,
            response.model_dump(mode="json"),
            max_entries=settings.search_cache_max_entries,
        )
    return response


# --- Health ---
@app.get("/health")
async def health():
    return {"status": "ok"}


