"""Ingest documents into the RAG store (Chroma by default, or pgvector).

- ``ingest_seed`` loads the bundled plain-English corpus. Idempotent.
- ``ingest_edgar`` pulls a ticker's latest 10-K "Item 1A Risk Factors" from SEC
  EDGAR (free, keyless, needs a descriptive User-Agent).
- ``ingest_news`` (pgvector only) folds persisted news rows into the corpus so the
  agent can ground "what's happening" answers in real recent articles.

Backend is chosen by ``RAG_BACKEND`` (chroma | pgvector) + ``DATABASE_URL``.

Run:  python -m portfolio_risk.rag.ingest                 # seed only
      python -m portfolio_risk.rag.ingest --edgar AAPL    # seed + that 10-K
      python -m portfolio_risk.rag.ingest --news          # seed + news → corpus
      python -m portfolio_risk.rag.ingest --all           # seed + default EDGAR + news
"""

from __future__ import annotations

import argparse
import re
import sys

from .. import config
from .store import get_client, get_collection

_DEFAULT_EDGAR = ["AAPL", "MSFT", "NVDA"]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split into overlapping word-windows. Cheap, deterministic, good enough."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(words), step):
        window = words[start : start + chunk_size]
        if window:
            chunks.append(" ".join(window))
        if start + chunk_size >= len(words):
            break
    return chunks


def _ticker_from_filename(name: str) -> str:
    m = re.match(r"([A-Z]+)_", name)
    return m.group(1) if m else "GENERAL"


def _use_pgvector() -> bool:
    from .. import db

    return config.rag_backend() == "pgvector" and db.db_enabled()


def _index(doc_id: str, ticker: str, source: str, kind: str, text: str, collection) -> int:
    """Chunk + store a document into the active backend. Returns chunk count."""
    chunks = chunk_text(text)
    if not chunks:
        return 0
    if collection is not None:  # Chroma
        ids = [f"{doc_id}::chunk{i}" for i in range(len(chunks))]
        metadatas = [
            {"ticker": ticker, "source": source, "chunk_idx": i} for i in range(len(chunks))
        ]
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
    else:  # pgvector
        from .. import db
        from . import pg_store

        pg_store.add_chunks(doc_id, ticker, source, kind, chunks)
        db.record_document(doc_id, ticker, source, kind, len(chunks))
    return len(chunks)


def _open_backend(reset_kind: str | None = None):
    """Return a Chroma collection, or None for pgvector. Optionally reset a kind."""
    if _use_pgvector():
        from .. import db

        db.init_db()
        if reset_kind:
            db.clear_documents(reset_kind)
        return None
    if reset_kind == "seed":
        try:
            get_client().delete_collection(config.COLLECTION_NAME)
            print("  reset existing collection", file=sys.stderr)
        except Exception:  # collection may not exist yet
            pass
    return get_collection(create=True)


def ingest_seed() -> int:
    """Load every file in the seed corpus. Resets prior seed docs first."""
    collection = _open_backend(reset_kind="seed")
    total = 0
    files = sorted(config.SEED_DIR.glob("*.md")) + sorted(config.SEED_DIR.glob("*.txt"))
    for path in files:
        ticker = _ticker_from_filename(path.name)
        text = path.read_text(encoding="utf-8")
        added = _index(path.stem, ticker, path.name, "seed", text, collection)
        total += added
        print(f"  ingested {added:>3} chunks from {path.name}", file=sys.stderr)
    return total


def ingest_edgar(ticker: str, user_agent: str | None = None) -> int:
    """Pull the latest 10-K 'Item 1A Risk Factors' for ``ticker`` from SEC EDGAR."""
    import requests

    ua = user_agent or config.edgar_user_agent()
    headers = {"User-Agent": ua}

    tk = requests.get(
        "https://www.sec.gov/files/company_tickers.json", headers=headers, timeout=30
    ).json()
    cik = None
    for row in tk.values():
        if row["ticker"].upper() == ticker.upper():
            cik = str(row["cik_str"]).zfill(10)
            break
    if cik is None:
        raise ValueError(f"Ticker {ticker} not found in EDGAR company list.")

    subs = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json", headers=headers, timeout=30
    ).json()
    recent = subs["filings"]["recent"]
    doc_url = None
    for form, acc, doc in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"]
    ):
        if form == "10-K":
            acc_nodash = acc.replace("-", "")
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
            break
    if doc_url is None:
        raise ValueError(f"No 10-K found for {ticker}.")

    html = requests.get(doc_url, headers=headers, timeout=60).text
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"(Item\s*1A.*?)(Item\s*1B|Item\s*2\b)", text, re.IGNORECASE)
    section = m.group(1) if m else text[:20000]

    collection = None if _use_pgvector() else get_collection(create=True)
    added = _index(
        f"{ticker}_edgar_10k", ticker.upper(), f"SEC EDGAR 10-K ({ticker})", "edgar",
        section, collection,
    )
    print(f"  ingested {added} chunks from EDGAR 10-K for {ticker}", file=sys.stderr)
    return added


def ingest_news() -> int:
    """Fold persisted news rows into the RAG corpus (pgvector backend only)."""
    if not _use_pgvector():
        print(
            "  news→RAG ingest requires RAG_BACKEND=pgvector + DATABASE_URL; skipping",
            file=sys.stderr,
        )
        return 0
    from .. import db

    db.init_db()
    db.clear_documents("news")
    rows = db.iter_news_for_ingest()
    total = 0
    for r in rows:
        body = f"{r['title']}. {r.get('summary', '')}".strip()
        if not body:
            continue
        total += _index(f"news:{r['id']}", r["ticker"], "news", "news", body, None)
    print(f"  ingested {total} chunks from {len(rows)} news rows", file=sys.stderr)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into the RAG store.")
    parser.add_argument("--edgar", nargs="*", metavar="TICKER", help="Also pull 10-Ks from SEC EDGAR.")
    parser.add_argument("--news", action="store_true", help="Fold persisted news into the corpus.")
    parser.add_argument("--all", action="store_true", help="Seed + default EDGAR + news.")
    args = parser.parse_args()

    print("Ingesting seed corpus...", file=sys.stderr)
    total = ingest_seed()

    edgar_tickers: list[str] = []
    if args.all:
        edgar_tickers = _DEFAULT_EDGAR
    elif args.edgar is not None:
        edgar_tickers = args.edgar or _DEFAULT_EDGAR
    for t in edgar_tickers:
        try:
            total += ingest_edgar(t)
        except Exception as exc:  # noqa: BLE001
            print(f"  EDGAR ingest failed for {t}: {exc}", file=sys.stderr)

    if args.all or args.news:
        total += ingest_news()

    print(f"Done. {total} chunks ingested (backend={config.rag_backend()}).", file=sys.stderr)


if __name__ == "__main__":
    main()
