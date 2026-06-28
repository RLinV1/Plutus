"""Postgres persistence for news + RAG documents (SQLAlchemy 2.x).

Everything here is a **no-op when ``DATABASE_URL`` is unset** — callers guard with
``db_enabled()`` so tests/offline runs never touch a database. When enabled it
backs three tables:
- ``news``       — deduped downloaded headlines (history + fewer yfinance calls).
- ``documents``  — ingestion metadata (which docs are in the RAG index).
- ``doc_chunks`` — chunk text + MiniLM embedding (384-d) + a generated tsvector,
  powering pgvector hybrid (vector + full-text) search.

This module is imported lazily by callers (only when ``db_enabled()``), so the
stdio MCP server and mock/test paths don't pay for it.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config

log = logging.getLogger("portfolio_risk.db")
if not log.handlers:
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

EMBED_DIM = 384  # all-MiniLM-L6-v2

_engine = None
_Session = None


def db_enabled() -> bool:
    return config.database_url() is not None


def _init_engine():
    global _engine, _Session
    if _engine is not None:
        return
    from sqlalchemy import create_engine

    _engine = create_engine(config.database_url(), pool_pre_ping=True, future=True)
    _Session = sessionmaker(bind=_engine, future=True)


def get_engine():
    _init_engine()
    return _engine


@contextlib.contextmanager
def session():
    _init_engine()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class Base(DeclarativeBase):
    pass


class News(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[str] = mapped_column(String(64), default="")
    relevant: Mapped[bool] = mapped_column(Boolean, default=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("ticker", "url", name="uq_news_ticker_url"),)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(128), unique=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True, default="GENERAL")
    source: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(16), default="seed")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocChunk(Base):
    __tablename__ = "doc_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(128), index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True, default="GENERAL")
    source: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(16), index=True, default="seed")
    chunk_idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    # embedding column added below (needs pgvector type, imported lazily-safe)
    __table_args__ = (UniqueConstraint("doc_id", "chunk_idx", name="uq_chunk_doc_idx"),)


# Attach the pgvector Vector column to DocChunk (kept separate so a missing
# pgvector import can't break the whole module at import time).
try:
    from pgvector.sqlalchemy import Vector

    DocChunk.embedding = mapped_column(Vector(EMBED_DIM))  # type: ignore[attr-defined]
except Exception as exc:  # pragma: no cover
    log.warning("pgvector not available: %s", exc)


# --------------------------------------------------------------------------- #
# Schema init + extra DDL (generated tsvector + hybrid-search indexes)
# --------------------------------------------------------------------------- #
def init_db() -> None:
    """Create tables + the full-text/vector indexes. No-op if DB disabled."""
    if not db_enabled():
        return
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(eng)
    ddl = [
        "ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text,''))) STORED",
        "CREATE INDEX IF NOT EXISTS doc_chunks_tsv_idx ON doc_chunks USING GIN (tsv)",
        "CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx "
        "ON doc_chunks USING hnsw (embedding vector_cosine_ops)",
    ]
    for stmt in ddl:
        try:
            with eng.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001
            log.warning("DDL skipped (%s): %s", exc, stmt[:60])
    log.info("db: schema ready")


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #
def upsert_news(ticker: str, articles: list[dict]) -> int:
    """Insert articles, skipping duplicates by (ticker, url). Returns rows tried."""
    if not db_enabled() or not articles:
        return 0
    rows = [
        {
            "ticker": ticker.upper(),
            "title": a.get("title", ""),
            "publisher": a.get("publisher", ""),
            "url": a.get("url", "") or f"_no_url_{i}",  # keep unique when url missing
            "summary": a.get("summary", ""),
            "published": str(a.get("published", "")),
            "relevant": bool(a.get("relevant", True)),
        }
        for i, a in enumerate(articles)
    ]
    try:
        with session() as s:
            stmt = pg_insert(News).values(rows).on_conflict_do_nothing(
                index_elements=["ticker", "url"]
            )
            s.execute(stmt)
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert_news failed for %s: %s", ticker, exc)
        return 0


def recent_news(ticker: str, limit: int = 12) -> list[dict]:
    """Most recent persisted articles for a ticker (fallback when yfinance fails)."""
    if not db_enabled():
        return []
    try:
        with session() as s:
            stmt = (
                select(News)
                .where(News.ticker == ticker.upper())
                .order_by(News.fetched_at.desc())
                .limit(limit)
            )
            return [
                {
                    "title": n.title,
                    "publisher": n.publisher,
                    "url": n.url if not n.url.startswith("_no_url_") else "",
                    "summary": n.summary,
                    "published": n.published,
                    "relevant": n.relevant,
                    "tickers": [n.ticker],
                }
                for n in s.scalars(stmt).all()
            ]
    except Exception as exc:  # noqa: BLE001
        log.warning("recent_news failed for %s: %s", ticker, exc)
        return []


def iter_news_for_ingest(limit: int = 500) -> list[dict]:
    """Recent relevant news rows to fold into the RAG corpus."""
    if not db_enabled():
        return []
    with session() as s:
        stmt = (
            select(News)
            .where(News.relevant.is_(True))
            .order_by(News.fetched_at.desc())
            .limit(limit)
        )
        return [
            {"id": n.id, "ticker": n.ticker, "title": n.title, "summary": n.summary}
            for n in s.scalars(stmt).all()
        ]


# --------------------------------------------------------------------------- #
# Documents / chunks (RAG store)
# --------------------------------------------------------------------------- #
def clear_documents(kind: str) -> None:
    """Delete a document kind (e.g. 'seed') so re-ingest doesn't leave stragglers."""
    if not db_enabled():
        return
    with session() as s:
        s.query(DocChunk).filter(DocChunk.kind == kind).delete()
        s.query(Document).filter(Document.kind == kind).delete()


def record_document(doc_id: str, ticker: str, source: str, kind: str, chunk_count: int) -> None:
    if not db_enabled():
        return
    with session() as s:
        stmt = (
            pg_insert(Document)
            .values(
                doc_id=doc_id, ticker=ticker, source=source, kind=kind,
                chunk_count=chunk_count,
            )
            .on_conflict_do_update(
                index_elements=["doc_id"],
                set_={"source": source, "kind": kind, "chunk_count": chunk_count},
            )
        )
        s.execute(stmt)


def upsert_chunks(records: list[dict]) -> int:
    """Upsert doc chunks (records have doc_id,ticker,source,kind,chunk_idx,text,embedding)."""
    if not db_enabled() or not records:
        return 0
    with session() as s:
        stmt = pg_insert(DocChunk).values(records).on_conflict_do_update(
            index_elements=["doc_id", "chunk_idx"],
            set_={
                "text": pg_insert(DocChunk).excluded.text,
                "embedding": pg_insert(DocChunk).excluded.embedding,
                "ticker": pg_insert(DocChunk).excluded.ticker,
                "source": pg_insert(DocChunk).excluded.source,
                "kind": pg_insert(DocChunk).excluded.kind,
            },
        )
        s.execute(stmt)
    return len(records)
