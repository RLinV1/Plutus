"""Persistence for portfolios, transactions, alert rules, and notifications.

SQLite by default (zero setup, ``data/portfolio.db``); the exact same models
run on Postgres when ``DATABASE_URL`` / ``PORTFOLIO_DB_URL`` is set. This is a
deliberately SEPARATE module from ``portfolio_risk.db`` (the optional
news/pgvector Postgres store) so that module keeps its "no-op when
DATABASE_URL is unset" contract and its Postgres-only SQL untouched.

IMPORTANT: never print to stdout — this module is imported (via tools.py) by
the stdio MCP server. Logs go to stderr.
"""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .. import config

log = logging.getLogger("portfolio_risk.portfolio.db")
if not log.handlers:  # stderr only
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PortfolioBase(DeclarativeBase):
    pass


class PortfolioModel(PortfolioBase):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TransactionModel(PortfolioBase):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"), index=True, nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY | SELL
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_txn_portfolio_ticker_date", "portfolio_id", "ticker", "trade_date"),
    )


class AlertRuleModel(PortfolioBase):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolios.id"), nullable=True
    )
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    # price_above | price_below | pct_move | rsi_above | rsi_below | drawdown | news_volume
    rule_type: Mapped[str] = mapped_column(String(24), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=240)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class NotificationModel(PortfolioBase):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("alert_rules.id"), nullable=True
    )
    portfolio_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolios.id"), nullable=True
    )
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), default="")
    kind: Mapped[str] = mapped_column(String(24), default="alert")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class UserPlanModel(PortfolioBase):
    """A Clerk user's subscription tier + Stripe linkage. Absence => free plan."""

    __tablename__ = "user_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    plan: Mapped[str] = mapped_column(String(16), default="free")  # free | pro | pro_max
    status: Mapped[str] = mapped_column(String(24), default="active")  # Stripe sub status
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class PromptUsageModel(PortfolioBase):
    """Per-user, per-UTC-day prompt counter for daily rate limiting."""

    __tablename__ = "prompt_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_usage_user_day", "clerk_user_id", "day", unique=True),
    )


# --------------------------------------------------------------------------- #
# Engine management. Lazy + keyed on the URL so tests can repoint
# PORTFOLIO_DB_URL at a temp file and transparently get a fresh engine.
# --------------------------------------------------------------------------- #
_engine = None
_engine_url: str | None = None
_session_factory = None


def _make_engine(url: str):
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        # The API's background loop and request handlers share this engine
        # across threads; WAL + busy_timeout keeps concurrent writers safe.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def get_engine():
    """The shared engine for the current ``portfolio_db_url()`` (created lazily,
    schema ensured on first use so the MCP-server path works without the API)."""
    global _engine, _engine_url, _session_factory
    url = config.portfolio_db_url()
    if _engine is None or url != _engine_url:
        if _engine is not None:
            _engine.dispose()
        if url.startswith("sqlite"):
            config.ensure_dirs()
        _engine = _make_engine(url)
        _engine_url = url
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        PortfolioBase.metadata.create_all(_engine)
    return _engine


def reset_engine() -> None:
    """Dispose the cached engine (used by tests when switching DB files)."""
    global _engine, _engine_url, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
    _session_factory = None


def init_portfolio_db() -> None:
    """Idempotent: ensure the engine exists and the schema is created."""
    get_engine()
    migrate_schema()


def migrate_schema() -> None:
    """Add new columns to existing tables (idempotent — safe to call on every boot)."""
    from sqlalchemy import text

    engine = get_engine()
    cols = [
        ("alert_rules", "clerk_user_id", "VARCHAR(64)"),
        ("notifications", "clerk_user_id", "VARCHAR(64)"),
    ]
    with engine.begin() as conn:
        for table, col, typ in cols:
            if engine.dialect.name == "postgresql":
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
                )
            else:  # SQLite
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
                except Exception:  # noqa: BLE001
                    pass  # column already exists


@contextmanager
def session():
    """Short-lived session: commit on success, rollback on error, always close.

    Keep the scope tight — never hold one of these across an ``await``.
    """
    get_engine()
    s = _session_factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
