"""Query the knowledge library — pgvector hybrid or Chroma dense, by RAG_BACKEND."""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("portfolio_risk.rag.search")
if not log.handlers:
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


def search_knowledge(query: str, ticker: str | None = None, k: int = 4) -> list[dict]:
    """Return up to ``k`` retrieved chunks for ``query``.

    Each result: {text, ticker, source, score} (higher score = more relevant).
    Uses pgvector hybrid search when ``RAG_BACKEND=pgvector`` and a database is
    configured; otherwise the embedded Chroma dense path (the default). Returns
    [] gracefully if the store isn't ready.
    """
    from .. import config

    if config.rag_backend() == "pgvector":
        try:
            from .. import db

            if db.db_enabled():
                from . import pg_store

                return pg_store.hybrid_search(query, ticker, k)
        except Exception as exc:  # noqa: BLE001
            log.warning("pgvector search failed (%s); falling back to Chroma", exc)

    # --- Chroma dense path (default / fallback) ---
    from .store import collection_exists, get_collection

    if not collection_exists():  # avoid loading the embedding model for nothing
        return []
    try:
        collection = get_collection(create=False)
    except Exception:
        return []

    where = {"ticker": ticker.upper()} if ticker else None
    res = collection.query(query_texts=[query], n_results=k, where=where)

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: list[dict] = []
    for doc, meta, dist in zip(docs, metas, dists):
        meta = meta or {}
        out.append(
            {
                "text": doc,
                "ticker": meta.get("ticker", ""),
                "source": meta.get("source", ""),
                "score": round(1.0 - float(dist), 4),
            }
        )
    return out
