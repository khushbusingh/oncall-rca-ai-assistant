"""
Search response cache for /api/search.

- **In-memory (default)**: zero dependencies, lowest latency; isolated per process (not shared
  across Uvicorn workers or multiple replicas).

- **Redis** (set ``REDIS_URL``): shared across workers and app instances; use when you run
  more than one process or need a single warm cache after deploys.

Invalidation: version bump on any Chroma write (see ``invalidate_search_cache``), so stale
results are never served after KB changes. Redis entries also get a TTL to cap memory from
orphaned version keys.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_generation = 0
_memory_cache: OrderedDict[Tuple[str, Optional[int], int], Tuple[int, Dict[str, Any]]] = OrderedDict()

REDIS_VER_KEY = "oncall:search:ver"
REDIS_ENTRY_PREFIX = "oncall:search:e:"


def _digest_key(query_norm: str, service_id: Optional[int], top_k: int) -> str:
    raw = f"{query_norm}\x00{service_id}\x00{top_k}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def invalidate_search_cache() -> None:
    """Call after any Chroma add/delete so cached results cannot be stale."""
    global _generation
    r = get_redis()
    if r is not None:
        try:
            r.incr(REDIS_VER_KEY)
        except Exception as e:
            logger.warning("Redis invalidate failed; bumping in-process cache only: %s", e)
    with _lock:
        _generation += 1
        _memory_cache.clear()


def get_search_cached(
    query_norm: str,
    service_id: Optional[int],
    top_k: int,
    *,
    max_entries: int,
) -> Optional[Dict[str, Any]]:
    """Return cached JSON-safe dict for SearchResponse.model_validate, or None."""
    if max_entries <= 0 or not query_norm:
        return None

    dkey = _digest_key(query_norm, service_id, top_k)
    r = get_redis()
    if r is not None:
        try:
            ver_raw = r.get(REDIS_VER_KEY)
            ver = int(ver_raw) if ver_raw is not None else 0
            blob = r.get(f"{REDIS_ENTRY_PREFIX}{ver}:{dkey}")
            if blob:
                return json.loads(blob)
        except Exception as e:
            logger.warning("Redis search cache read failed: %s", e)
        return None

    key = (query_norm, service_id, top_k)
    with _lock:
        if key not in _memory_cache:
            return None
        gen, payload = _memory_cache[key]
        if gen != _generation:
            del _memory_cache[key]
            return None
        _memory_cache.move_to_end(key)
        return payload


def set_search_cached(
    query_norm: str,
    service_id: Optional[int],
    top_k: int,
    payload: Dict[str, Any],
    *,
    max_entries: int,
) -> None:
    """Store JSON-safe dict (e.g. SearchResponse.model_dump(mode='json'))."""
    if max_entries <= 0 or not query_norm:
        return

    dkey = _digest_key(query_norm, service_id, top_k)
    r = get_redis()
    if r is not None:
        ttl = max(60, int(getattr(settings, "search_cache_ttl_seconds", 86400)))
        try:
            ver_raw = r.get(REDIS_VER_KEY)
            ver = int(ver_raw) if ver_raw is not None else 0
            r.setex(
                f"{REDIS_ENTRY_PREFIX}{ver}:{dkey}",
                ttl,
                json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("Redis search cache write failed: %s", e)
        return

    key = (query_norm, service_id, top_k)
    with _lock:
        while len(_memory_cache) >= max_entries:
            _memory_cache.popitem(last=False)
        _memory_cache[key] = (_generation, payload)
        _memory_cache.move_to_end(key)
