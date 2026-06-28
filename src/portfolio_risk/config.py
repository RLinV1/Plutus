"""Central configuration: paths, constants, and mode switches.

This module performs no I/O at import time beyond resolving paths and reading
environment variables, so it is safe to import from the stdio MCP server.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Optional .env loading (never fatal if python-dotenv is missing) ---
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

# --- Paths ---
PKG_ROOT = Path(__file__).resolve().parent              # .../src/portfolio_risk
PROJECT_ROOT = PKG_ROOT.parents[1]                      # repo root
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
PRICE_CACHE_DIR = CACHE_DIR / "prices"
CHROMA_DIR = DATA_DIR / "chroma"
SEED_DIR = PKG_ROOT / "rag" / "seed"

# --- Finance constants ---
TRADING_DAYS = 252
DEFAULT_BENCHMARK = "SPY"
DEFAULT_RF_ANNUAL = 0.02
DEFAULT_LOOKBACK_DAYS = 504  # ~2 years of trading days
COLLECTION_NAME = "filings"

# --- Claude ---
# Sonnet 4.6 is much cheaper than Opus 4.8 — preferred for the agent's API calls.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000
# Reasoning effort: low | medium | high. Lower = faster + cheaper (fewer, more
# consolidated tool calls, less preamble). "low" keeps the advisor snappy.
EFFORT = "low"

# --- Mode switches ---
def _flag(name: str, default: str) -> str:
    return os.environ.get(name, default).strip().lower()


def use_mock_data() -> bool:
    """Default OFF: pull real live data from yfinance.

    The app ships with live data on by default. Set ``USE_MOCK_DATA=1`` for
    deterministic synthetic prices and zero network calls — which tests and the
    eval harness do, to stay reproducible and offline.
    """
    return _flag("USE_MOCK_DATA", "0") not in ("0", "false", "no")


def use_mock_llm() -> bool:
    """Default 'auto': mock agent unless ANTHROPIC_API_KEY is present."""
    mode = _flag("USE_MOCK_LLM", "auto")
    if mode in ("1", "true", "yes"):
        return True
    if mode in ("0", "false", "no"):
        return False
    # auto
    return not bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def edgar_user_agent() -> str:
    return os.environ.get("EDGAR_USER_AGENT", "PortfolioRisk research@example.com")


# --- Infrastructure switches (all optional; unset => in-process / offline) ---
def redis_url() -> str | None:
    """Redis connection string for the shared cache; None => in-process dict."""
    return os.environ.get("REDIS_URL", "").strip() or None


def database_url() -> str | None:
    """SQLAlchemy URL for Postgres (news + RAG store); None => DB disabled."""
    return os.environ.get("DATABASE_URL", "").strip() or None


def portfolio_db_url() -> str:
    """SQLAlchemy URL for the portfolio store (always on, unlike database_url).

    Priority: ``PORTFOLIO_DB_URL`` (tests point this at a temp file) >
    ``DATABASE_URL`` (share the configured Postgres) > a zero-setup local
    SQLite file. The portfolio models are dialect-neutral, so the same code
    runs on both engines.
    """
    return (
        os.environ.get("PORTFOLIO_DB_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
        or f"sqlite:///{(DATA_DIR / 'portfolio.db').as_posix()}"
    )


def alert_poll_seconds() -> float:
    """How often the API's background loop re-checks alert rules and quotes."""
    try:
        return max(5.0, float(os.environ.get("ALERT_POLL_SEC", "20")))
    except ValueError:
        return 20.0


def paper_start_cash() -> float:
    """Virtual starting balance for the paper-trading account."""
    try:
        return max(100.0, float(os.environ.get("PAPER_START_CASH", "100000")))
    except ValueError:
        return 100000.0


def run_alerts_loop() -> bool:
    """Whether THIS api process runs the background alerts/quotes loop.

    Default on. When scaling the API horizontally (docker compose
    --scale api=N), set RUN_ALERTS_LOOP=0 on all but one replica so rules
    aren't evaluated N times per cycle.
    """
    return _flag("RUN_ALERTS_LOOP", "1") not in ("0", "false", "no")


def rag_backend() -> str:
    """RAG backend: 'chroma' (default, embedded) or 'pgvector' (hybrid in Postgres)."""
    return _flag("RAG_BACKEND", "chroma")


def rag_rerank() -> bool:
    """Whether to apply a cross-encoder reranker after hybrid retrieval."""
    return _flag("RAG_RERANK", "0") in ("1", "true", "yes")


def ensure_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, PRICE_CACHE_DIR, CHROMA_DIR):
        d.mkdir(parents=True, exist_ok=True)
