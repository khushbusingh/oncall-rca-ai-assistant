"""Shared optional Redis client for search cache and embedding cache."""
from __future__ import annotations

import logging
import threading

from app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_redis_client = None
_redis_gave_up = False
_redis_warned = False


def get_redis():
    """Return a redis client if ``REDIS_URL`` is set and reachable; else None."""
    global _redis_client, _redis_gave_up, _redis_warned
    url = (getattr(settings, "redis_url", None) or "").strip()
    if not url:
        return None
    if _redis_gave_up:
        return None
    if _redis_client is not None:
        return _redis_client
    with _lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis as redis_lib

            r = redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=2.0)
            r.ping()
            _redis_client = r
            logger.info("Redis connected for caches (%s)", url.split("@")[-1] if "@" in url else "configured")
            return _redis_client
        except Exception as e:
            _redis_gave_up = True
            if not _redis_warned:
                _redis_warned = True
                logger.warning(
                    "Redis unavailable (%s); using in-memory caches for this process.",
                    e,
                )
            return None
