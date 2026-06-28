"""pgvector-backed RAG: hybrid (vector + full-text) search with optional rerank.

Used when ``RAG_BACKEND=pgvector`` and ``DATABASE_URL`` is set. Embeds with the
same local MiniLM model as the Chroma path, stores chunks in Postgres
(`doc_chunks`), and retrieves with **Reciprocal Rank Fusion** over a dense
(cosine) ranking and a lexical (`tsvector`) ranking — so exact-keyword hits that
pure vector search misses still surface. An optional cross-encoder reranker
(`RAG_RERANK=1`) re-scores the top candidates for precision.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import text

from .. import config, db

log = logging.getLogger("portfolio_risk.pg_store")
if not log.handlers:
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

_model = None
_reranker = None


def _embedder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    vecs = _embedder().encode(list(texts), normalize_embeddings=False)
    return [[float(x) for x in v] for v in vecs]


def add_chunks(doc_id: str, ticker: str, source: str, kind: str, chunks: list[str]) -> int:
    """Embed + upsert chunks for a document. Returns chunk count."""
    if not chunks:
        return 0
    embs = embed(chunks)
    records = [
        {
            "doc_id": doc_id,
            "ticker": ticker,
            "source": source,
            "kind": kind,
            "chunk_idx": i,
            "text": c,
            "embedding": embs[i],
        }
        for i, c in enumerate(chunks)
    ]
    return db.upsert_chunks(records)


_HYBRID_SQL = text(
    """
    WITH dense AS (
        SELECT id, doc_id, ticker, source, text,
               row_number() OVER (ORDER BY embedding <=> (:qvec)::vector) AS rnk
        FROM doc_chunks
        WHERE (CAST(:ticker AS text) IS NULL OR ticker = :ticker)
        ORDER BY embedding <=> (:qvec)::vector
        LIMIT :cand
    ),
    lex AS (
        SELECT id, doc_id, ticker, source, text,
               row_number() OVER (
                   ORDER BY ts_rank(tsv, plainto_tsquery('english', :q)) DESC
               ) AS rnk
        FROM doc_chunks
        WHERE tsv @@ plainto_tsquery('english', :q)
          AND (CAST(:ticker AS text) IS NULL OR ticker = :ticker)
        LIMIT :cand
    )
    SELECT COALESCE(d.text, l.text)     AS text,
           COALESCE(d.ticker, l.ticker) AS ticker,
           COALESCE(d.source, l.source) AS source,
           COALESCE(1.0 / (60 + d.rnk), 0) + COALESCE(1.0 / (60 + l.rnk), 0) AS score
    FROM dense d
    FULL OUTER JOIN lex l ON d.id = l.id
    ORDER BY score DESC
    LIMIT :fetch
    """
)


def _rerank(query: str, rows: list[dict], k: int) -> list[dict]:
    """Re-score candidates with a cross-encoder, then take top k."""
    global _reranker
    try:
        if _reranker is None:
            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        scores = _reranker.predict([(query, r["text"]) for r in rows])
        for r, s in zip(rows, scores):
            r["score"] = round(float(s), 4)
        rows.sort(key=lambda r: r["score"], reverse=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("rerank failed (%s); using fusion order", exc)
    return rows[:k]


def hybrid_search(query: str, ticker: str | None = None, k: int = 4) -> list[dict]:
    """Hybrid RRF search. Returns [{text, ticker, source, score}] (same shape as Chroma)."""
    if not db.db_enabled():
        return []
    rerank = config.rag_rerank()
    qvec = "[" + ",".join(f"{x:.6f}" for x in embed([query])[0]) + "]"
    cand = max(k * 5, 20)
    fetch = max(k * 4, 20) if rerank else k
    params = {
        "qvec": qvec,
        "q": query,
        "ticker": ticker.upper() if ticker else None,
        "cand": cand,
        "fetch": fetch,
    }
    try:
        with db.get_engine().connect() as conn:
            res = conn.execute(_HYBRID_SQL, params)
            rows = [
                {
                    "text": r.text,
                    "ticker": r.ticker or "",
                    "source": r.source or "",
                    "score": round(float(r.score), 4),
                }
                for r in res
            ]
    except Exception as exc:  # noqa: BLE001
        log.warning("hybrid_search failed: %s", exc)
        return []
    if rerank and rows:
        return _rerank(query, rows, k)
    return rows[:k]
