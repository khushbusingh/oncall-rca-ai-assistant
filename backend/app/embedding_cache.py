"""
Cache for **query** embedding vectors (OpenAI or local sentence-transformers).

Same text always maps to the same embedding regardless of knowledge-base updates, so this
does not use the search-cache version bump. Keys include the active embedding model name so
switching models never serves a mismatched vector.

Use **Redis** when ``REDIS_URL`` is set (shared across workers); otherwise in-memory LRU.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections import OrderedDict
from typing import List, Optional, Tuple

from app.config import settings
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_memory: OrderedDict[str, List[float]] = OrderedDict()

REDIS_PREFIX = "oncall:emb:v1:"


def _normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip()).lower()[:4000]


def _fingerprint(backend: str, model: str, query_norm: str) -> str:
    raw = f"{backend}\x00{model}\x00{query_norm}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_key_parts(use_openai: bool) -> Tuple[str, str]:
    if use_openai:
        return "openai", (settings.openai_embedding_model or "").strip() or "default"
    return "local", (settings.embedding_model or "").strip() or "default"


def get_cached_query_embedding(query: str, *, use_openai: bool) -> Optional[List[float]]:
    """Return a single embedding vector if cached, else None."""
    if not getattr(settings, "enable_embedding_cache", True):
        return None
    query_norm = _normalize_query(query)
    if not query_norm:
        return None

    backend, model = _cache_key_parts(use_openai)
    fp = _fingerprint(backend, model, query_norm)
    max_entries = max(0, int(getattr(settings, "embedding_cache_max_entries", 512)))

    r = get_redis()
    if r is not None:
        ttl = max(300, int(getattr(settings, "embedding_cache_ttl_seconds", 86400)))
        try:
            blob = r.get(f"{REDIS_PREFIX}{fp}")
            if blob:
                vec = json.loads(blob)
                if isinstance(vec, list) and vec and isinstance(vec[0], (int, float)):
                    logger.debug("embedding cache hit (Redis)")
                    return [float(x) for x in vec]
        except Exception as e:
            logger.warning("Redis embedding cache read failed: %s", e)
        return None

    if max_entries <= 0:
        return None
    with _lock:
        if fp not in _memory:
            return None
        vec = _memory[fp]
        _memory.move_to_end(fp)
        logger.debug("embedding cache hit (memory)")
        return list(vec)


def set_cached_query_embedding(query: str, vector: List[float], *, use_openai: bool) -> None:
    """Store one embedding vector for the query text."""
    if not getattr(settings, "enable_embedding_cache", True):
        return
    query_norm = _normalize_query(query)
    if not query_norm or not vector:
        return

    backend, model = _cache_key_parts(use_openai)
    fp = _fingerprint(backend, model, query_norm)
    max_entries = max(0, int(getattr(settings, "embedding_cache_max_entries", 512)))

    r = get_redis()
    if r is not None:
        ttl = max(300, int(getattr(settings, "embedding_cache_ttl_seconds", 86400)))
        try:
            r.setex(
                f"{REDIS_PREFIX}{fp}",
                ttl,
                json.dumps(vector, separators=(",", ":")),
            )
        except Exception as e:
            logger.warning("Redis embedding cache write failed: %s", e)
        return

    if max_entries <= 0:
        return
    with _lock:
        if fp in _memory:
            _memory.pop(fp)
        while len(_memory) >= max_entries:
            _memory.popitem(last=False)
        _memory[fp] = list(vector)
