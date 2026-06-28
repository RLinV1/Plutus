"""RAG ingest+search roundtrip on a throwaway Chroma collection.

Skipped if chromadb / sentence-transformers are unavailable, or if the embedding
model can't be loaded (e.g. fully offline first run with no cached model).
"""

from __future__ import annotations

import pytest

chromadb = pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    from portfolio_risk import config

    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "COLLECTION_NAME", "test_filings")
    # store.py reads config attributes at call time, so monkeypatch is enough.
    yield


def test_ingest_and_search(isolated_store):
    from portfolio_risk.rag import search, store

    try:
        col = store.get_collection(create=True)
    except Exception as exc:  # model download/load failure -> skip, don't fail
        pytest.skip(f"embedding model unavailable: {exc}")

    col.upsert(
        ids=["doc1::c0", "doc2::c0"],
        documents=[
            "Apple depends heavily on iPhone sales and supply chain concentration.",
            "Microsoft cloud business faces cybersecurity and data protection risk.",
        ],
        metadatas=[
            {"ticker": "AAPL", "source": "AAPL_10k.md", "chunk_idx": 0},
            {"ticker": "MSFT", "source": "MSFT_10k.md", "chunk_idx": 0},
        ],
    )

    results = search.search_knowledge("supply chain risk for the iPhone maker", k=2)
    assert results, "expected at least one retrieval"
    assert results[0]["ticker"] in {"AAPL", "MSFT"}
    # The AAPL doc should be the closest match for an iPhone/supply-chain query.
    assert results[0]["ticker"] == "AAPL"


def test_chunk_text():
    from portfolio_risk.rag.ingest import chunk_text

    words = " ".join(str(i) for i in range(2000))
    chunks = chunk_text(words, chunk_size=800, overlap=100)
    assert len(chunks) >= 2
    assert all(chunks)
