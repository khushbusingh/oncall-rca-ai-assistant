"""RAG: embeddings, ChromaDB, and retrieval. Uses OpenAI when API key is set, else sentence-transformers."""
import logging
import os
import uuid
from typing import List, Optional

import chromadb

logger = logging.getLogger(__name__)
from chromadb.config import Settings as ChromaSettings

from app.config import settings

# Lazy-loaded embedding model (only when not using OpenAI)
_embedding_model = None


def _use_openai_embeddings() -> bool:
    return bool(settings.openai_api_key)


# def _embed_openai(texts: List[str]) -> List[List[float]]:
#     import httpx
#     from openai import OpenAI
#     # SSL verify: default False for corporate proxy. Set OPENAI_SSL_VERIFY=true to verify.
#     verify_env = os.environ.get("OPENAI_SSL_VERIFY", "false").strip().lower()
#     verify = verify_env in ("1", "true", "yes", "on")
#     http_client = httpx.Client(verify=verify)
#     client = OpenAI(api_key=settings.openai_api_key, http_client=http_client)
#     out = []
#     # OpenAI limit 300k tokens/request; batch by token estimate (~4 chars/token) to stay under
#     max_tokens_per_request = 200_000
#     i = 0
#     while i < len(texts):
#         batch = []
#         batch_tokens = 0
#         while i < len(texts) and (batch_tokens + len(texts[i]) // 4) <= max_tokens_per_request:
#             batch.append(texts[i])
#             batch_tokens += len(texts[i]) // 4
#             i += 1
#         if not batch:
#             # single chunk exceeds limit; send it anyway (will error if truly over 300k)
#             batch = [texts[i]]
#             i += 1
#         resp = client.embeddings.create(model=settings.openai_embedding_model, input=batch)
#         for e in resp.data:
#             out.append(e.embedding)
#     return out

def _embed_openai(texts: List[str]) -> List[List[float]]:
    import httpx
    from openai import OpenAI
    
    verify_env = os.environ.get("OPENAI_SSL_VERIFY", "false").strip().lower()
    verify = verify_env in ("1", "true", "yes", "on")
    http_client = httpx.Client(verify=verify)
    client = OpenAI(api_key=settings.openai_api_key, http_client=http_client)
    
    out = []
    # Embedding model context limit is 8192 tokens. Keep total per request under that.
    MAX_TOKENS_PER_BATCH = 7500
    MAX_CHARS_PER_CHUNK = 7500 * 4  # ~4 chars/token; truncate any chunk longer than this

    i = 0
    while i < len(texts):
        batch = []
        current_batch_tokens = 0

        while i < len(texts):
            raw = texts[i]
            # Truncate oversized chunks so we never send > 8192 tokens per item
            if len(raw) > MAX_CHARS_PER_CHUNK:
                raw = raw[:MAX_CHARS_PER_CHUNK]
            estimated_tokens = len(raw) // 4

            if current_batch_tokens + estimated_tokens > MAX_TOKENS_PER_BATCH and batch:
                break

            batch.append(raw)
            current_batch_tokens += estimated_tokens
            i += 1

        if batch:
            try:
                resp = client.embeddings.create(
                    model=settings.openai_embedding_model, 
                    input=batch
                )
                for e in resp.data:
                    out.append(e.embedding)
            except Exception as e:
                logger.error(f"OpenAI Embedding Error: {str(e)}")
                raise e
                
    return out

def _get_sentence_transformer():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        if settings.hf_token:
            os.environ["HF_TOKEN"] = settings.hf_token
            os.environ["HUGGING_FACE_HUB_TOKEN"] = settings.hf_token
        _embedding_model = SentenceTransformer(settings.embedding_model)
    return _embedding_model


def get_chroma_client():
    """Chroma client with persistence."""
    return chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_or_create_collection(name: str = "oncall_knowledge"):
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"description": "On-call knowledge base chunks"},
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    if _use_openai_embeddings():
        return _embed_openai(texts)
    model = _get_sentence_transformer()
    return model.encode(texts, show_progress_bar=False).tolist()


def add_chunks_to_collection(
    chunks: List[str],
    metadatas: Optional[List[dict]] = None,
    ids: Optional[List[str]] = None,
    collection_name: str = "oncall_knowledge",
):
    """Add text chunks to ChromaDB with embeddings."""
    if not chunks:
        return
    coll = get_or_create_collection(collection_name)
    embeddings = embed_texts(chunks)
    if ids is None:
        ids = [str(uuid.uuid4()) for _ in chunks]
    if metadatas is None:
        metadatas = [{}] * len(chunks)
    # Chroma expects list of dicts with same keys
    meta_clean = []
    for m in metadatas:
        m2 = {k: (str(v) if not isinstance(v, (str, int, float, bool)) else v) for k, v in m.items()}
        meta_clean.append(m2)
    coll.add(documents=chunks, embeddings=embeddings, metadatas=meta_clean, ids=ids)


def query_collection(
    query: str,
    top_k: int = 5,
    filter_metadata: Optional[dict] = None,
    collection_name: str = "oncall_knowledge",
) -> List[dict]:
    """Search for relevant chunks. Returns list of {document, metadata, distance}."""
    coll = get_or_create_collection(collection_name)
    try:
        coll_count = coll.count()
    except Exception:
        coll_count = None
    logger.info("query_collection: collection=%s count=%s filter=%s top_k=%s", collection_name, coll_count, filter_metadata, top_k)
    if _use_openai_embeddings():
        q_embedding = _embed_openai([query])
    else:
        model = _get_sentence_transformer()
        q_embedding = model.encode([query], show_progress_bar=False).tolist()
    kwargs = {"query_embeddings": q_embedding, "n_results": top_k, "include": ["documents", "metadatas", "distances"]}
    if filter_metadata:
        kwargs["where"] = filter_metadata
    results = coll.query(**kwargs)
    out = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            out.append({
                "document": doc,
                "metadata": (results["metadatas"][0][i] if results["metadatas"] else {}) or {},
                "distance": (results["distances"][0][i] if results.get("distances") else None),
            })
    logger.info("query_collection: returned %s chunks", len(out))
    return out


def delete_chunks_by_ids(ids: List[str], collection_name: str = "oncall_knowledge"):
    """Remove chunks by their ChromaDB ids."""
    if not ids:
        return
    coll = get_or_create_collection(collection_name)
    coll.delete(ids=ids)


def delete_chunks_by_metadata(
    where: dict,
    collection_name: str = "oncall_knowledge",
):
    """Remove all chunks matching the given metadata filter (e.g. service_id + filename for uploads)."""
    if not where:
        return
    coll = get_or_create_collection(collection_name)
    coll.delete(where=where)
