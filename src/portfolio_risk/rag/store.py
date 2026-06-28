"""Chroma persistent vector store with local sentence-transformer embeddings.

Embeddings run locally via ``all-MiniLM-L6-v2`` (downloaded once, ~80MB) so no
embedding API key is needed. Telemetry is disabled to keep stdout clean for the
MCP server.
"""

from __future__ import annotations

import os

from .. import config

# Disable Chroma telemetry/progress before importing chromadb.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "False")


def get_client():
    import chromadb
    from chromadb.config import Settings

    config.ensure_dirs()
    return chromadb.PersistentClient(
        path=str(config.CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def _embedding_function():
    from chromadb.utils import embedding_functions

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


def collection_exists() -> bool:
    """Cheap check that avoids constructing the embedding model."""
    try:
        client = get_client()
        return any(c.name == config.COLLECTION_NAME for c in client.list_collections())
    except Exception:
        return False


def get_collection(create: bool = False):
    """Return the filings collection, creating it if requested.

    Building the embedding function loads the sentence-transformer model
    (downloaded once, ~80MB), so callers on the read path should check
    ``collection_exists()`` first to avoid loading it for a missing collection.
    """
    client = get_client()
    ef = _embedding_function()
    if create:
        return client.get_or_create_collection(
            name=config.COLLECTION_NAME, embedding_function=ef
        )
    return client.get_collection(name=config.COLLECTION_NAME, embedding_function=ef)
