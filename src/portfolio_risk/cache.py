"""Shared JSON cache: Redis when ``REDIS_URL`` is set, else an in-process dict.

This is what lets the API scale to multiple stateless replicas — they share cache
hits through Redis instead of each holding its own dict. It NEVER raises: on any
Redis error it logs to stderr and falls back to the in-process dict, so the app
keeps working offline and tests stay deterministic with no ``REDIS_URL`` set.

Values must be JSON-serializable. Only the MCP-safe stderr logger is used.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from . import config

log = logging.getLogger("portfolio_risk.cache")
if not log.handlers:  # stderr only — never corrupt the MCP stdout stream
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

# In-process fallback store: key -> (expiry_monotonic_or_0, value)
_local: dict[str, tuple[float, Any]] = {}

_redis = None
_redis_tried = False


def _client():
    """Lazy Redis singleton; returns None (use dict) if unset/unreachable."""
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    url = config.redis_url()
    if not url:
        return None
    try:
        import redis  # imported lazily so it's optional when REDIS_URL is unset

        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        _redis = client
        log.info("cache: using Redis")
    except Exception as exc:  # noqa: BLE001
        log.warning("cache: Redis unavailable (%s); using in-process dict", exc)
        _redis = None
    return _redis


def cache_get_json(key: str) -> Any | None:
    """Return the cached value for ``key`` or None on miss."""
    client = _client()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:  # noqa: BLE001
            log.warning("cache get failed (%s); falling back to dict", exc)
    hit = _local.get(key)
    if hit is not None:
        expiry, value = hit
        if expiry == 0 or expiry > time.monotonic():
            return value
        _local.pop(key, None)
    return None


def cache_set_json(key: str, value: Any, ttl_seconds: float) -> None:
    """Store ``value`` (JSON-serializable) under ``key`` with a TTL."""
    client = _client()
    if client is not None:
        try:
            client.setex(key, int(max(ttl_seconds, 1)), json.dumps(value))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("cache set failed (%s); falling back to dict", exc)
    expiry = time.monotonic() + ttl_seconds if ttl_seconds else 0
    _local[key] = (expiry, value)
