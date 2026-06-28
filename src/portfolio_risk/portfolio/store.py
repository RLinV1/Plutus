"""Thin CRUD over the portfolio database. Every function returns plain
JSON-serializable dicts (or bools/ints), mirroring the tools.py convention."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from .db import (
    AlertRuleModel,
    NotificationModel,
    PortfolioModel,
    TransactionModel,
    session,
)

_SIDES = ("BUY", "SELL")
RULE_TYPES = (
    "price_above",
    "price_below",
    "pct_move",
    "rsi_above",
    "rsi_below",
    "drawdown",
    "news_volume",
)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _parse_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d).strip()[:10])


def _txn_dict(t: TransactionModel) -> dict:
    return {
        "id": t.id,
        "portfolio_id": t.portfolio_id,
        "ticker": t.ticker,
        "side": t.side,
        "shares": float(t.shares),
        "price": float(t.price),
        "fees": float(t.fees or 0.0),
        "trade_date": _iso(t.trade_date),
        "note": t.note or "",
    }


def _rule_dict(r: AlertRuleModel) -> dict:
    return {
        "id": r.id,
        "portfolio_id": r.portfolio_id,
        "ticker": r.ticker,
        "rule_type": r.rule_type,
        "threshold": float(r.threshold),
        "enabled": bool(r.enabled),
        "cooldown_minutes": int(r.cooldown_minutes or 0),
        "last_triggered_at": _iso(r.last_triggered_at),
        "created_at": _iso(r.created_at),
    }


def _notif_dict(n: NotificationModel) -> dict:
    return {
        "id": n.id,
        "rule_id": n.rule_id,
        "portfolio_id": n.portfolio_id,
        "ticker": n.ticker or "",
        "kind": n.kind or "alert",
        "title": n.title,
        "body": n.body or "",
        "payload": n.payload,
        "read": bool(n.read),
        "created_at": _iso(n.created_at),
    }


# --------------------------------------------------------------------------- #
# Portfolios
# --------------------------------------------------------------------------- #
def get_or_create_portfolio(name: str = "default") -> dict:
    name = (name or "default").strip() or "default"
    with session() as s:
        row = s.scalar(select(PortfolioModel).where(PortfolioModel.name == name))
        if row is None:
            row = PortfolioModel(name=name)
            s.add(row)
            s.flush()
        return {"id": row.id, "name": row.name, "base_currency": row.base_currency}


def list_portfolios() -> list[dict]:
    with session() as s:
        rows = s.scalars(select(PortfolioModel).order_by(PortfolioModel.name)).all()
        return [
            {"id": r.id, "name": r.name, "base_currency": r.base_currency} for r in rows
        ]


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
def add_transaction(
    portfolio: str,
    ticker: str,
    side: str,
    shares: float,
    price: float,
    fees: float = 0.0,
    trade_date=None,
    note: str = "",
) -> dict:
    side = (side or "").strip().upper()
    if side not in _SIDES:
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    shares = float(shares)
    price = float(price)
    fees = float(fees or 0.0)
    if shares <= 0:
        raise ValueError("shares must be > 0")
    if price <= 0:
        raise ValueError("price must be > 0")
    if fees < 0:
        raise ValueError("fees must be >= 0")
    tk = (ticker or "").strip().upper()
    if not tk:
        raise ValueError("ticker is required")
    when = _parse_date(trade_date) if trade_date else date.today()

    pf = get_or_create_portfolio(portfolio)
    with session() as s:
        row = TransactionModel(
            portfolio_id=pf["id"],
            ticker=tk,
            side=side,
            shares=shares,
            price=price,
            fees=fees,
            trade_date=when,
            note=(note or "")[:500],
        )
        s.add(row)
        s.flush()
        return _txn_dict(row)


def add_transactions(portfolio: str, rows: list[dict]) -> list[dict]:
    """Bulk insert (CSV import). Each row: ticker, side, shares, price,
    optional fees/trade_date/note. Validates every row before writing any."""
    out: list[dict] = []
    for r in rows:
        out.append(
            add_transaction(
                portfolio,
                r["ticker"],
                r["side"],
                r["shares"],
                r["price"],
                r.get("fees", 0.0),
                r.get("trade_date"),
                r.get("note", ""),
            )
        )
    return out


def list_transactions(portfolio: str = "default") -> list[dict]:
    pf = get_or_create_portfolio(portfolio)
    with session() as s:
        rows = s.scalars(
            select(TransactionModel)
            .where(TransactionModel.portfolio_id == pf["id"])
            .order_by(TransactionModel.trade_date, TransactionModel.id)
        ).all()
        return [_txn_dict(t) for t in rows]


def delete_transaction(txn_id: int) -> bool:
    with session() as s:
        row = s.get(TransactionModel, int(txn_id))
        if row is None:
            return False
        s.delete(row)
        return True


def delete_all_transactions(portfolio: str) -> int:
    """Wipe every transaction in a portfolio (the portfolio row stays).
    Destructive — the API layer requires typed confirmation before calling."""
    pf = get_or_create_portfolio(portfolio)
    with session() as s:
        rows = s.scalars(
            select(TransactionModel).where(TransactionModel.portfolio_id == pf["id"])
        ).all()
        for r in rows:
            s.delete(r)
        return len(rows)


# --------------------------------------------------------------------------- #
# Alert rules
# --------------------------------------------------------------------------- #
def add_alert_rule(
    ticker: str,
    rule_type: str,
    threshold: float,
    portfolio: str | None = None,
    cooldown_minutes: int = 240,
) -> dict:
    rule_type = (rule_type or "").strip().lower()
    if rule_type not in RULE_TYPES:
        raise ValueError(f"rule_type must be one of {RULE_TYPES}, got {rule_type!r}")
    tk = (ticker or "").strip().upper()
    if not tk:
        raise ValueError("ticker is required")
    pf_id = get_or_create_portfolio(portfolio)["id"] if portfolio else None
    with session() as s:
        row = AlertRuleModel(
            portfolio_id=pf_id,
            ticker=tk,
            rule_type=rule_type,
            threshold=float(threshold),
            cooldown_minutes=max(0, int(cooldown_minutes)),
        )
        s.add(row)
        s.flush()
        return _rule_dict(row)


def list_alert_rules(enabled_only: bool = False) -> list[dict]:
    with session() as s:
        q = select(AlertRuleModel).order_by(AlertRuleModel.id)
        if enabled_only:
            q = q.where(AlertRuleModel.enabled.is_(True))
        return [_rule_dict(r) for r in s.scalars(q).all()]


def update_alert_rule(rule_id: int, **fields) -> dict | None:
    allowed = {"enabled", "threshold", "cooldown_minutes"}
    with session() as s:
        row = s.get(AlertRuleModel, int(rule_id))
        if row is None:
            return None
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(row, k, v)
        s.flush()
        return _rule_dict(row)


def delete_alert_rule(rule_id: int) -> bool:
    with session() as s:
        row = s.get(AlertRuleModel, int(rule_id))
        if row is None:
            return False
        # Notifications the rule produced keep their history — just detach
        # them so the FK doesn't block the delete.
        for n in s.scalars(
            select(NotificationModel).where(NotificationModel.rule_id == row.id)
        ).all():
            n.rule_id = None
        s.delete(row)
        return True


def mark_rule_triggered(rule_id: int, when: datetime) -> None:
    with session() as s:
        row = s.get(AlertRuleModel, int(rule_id))
        if row is not None:
            row.last_triggered_at = when


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
def add_notification(
    title: str,
    body: str = "",
    ticker: str = "",
    kind: str = "alert",
    rule_id: int | None = None,
    portfolio_id: int | None = None,
    payload: dict | None = None,
) -> dict:
    with session() as s:
        row = NotificationModel(
            rule_id=rule_id,
            portfolio_id=portfolio_id,
            ticker=(ticker or "").upper(),
            kind=kind,
            title=title[:255],
            body=body,
            payload=payload,
        )
        s.add(row)
        s.flush()
        return _notif_dict(row)


def list_notifications(unread_only: bool = False, limit: int = 50) -> list[dict]:
    with session() as s:
        q = (
            select(NotificationModel)
            .order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc())
            .limit(max(1, int(limit)))
        )
        if unread_only:
            q = q.where(NotificationModel.read.is_(False))
        return [_notif_dict(n) for n in s.scalars(q).all()]


def mark_notifications_read(ids: list[int] | None = None) -> int:
    """Mark the given notifications read (or ALL unread when ids is None)."""
    with session() as s:
        q = select(NotificationModel).where(NotificationModel.read.is_(False))
        if ids:
            q = q.where(NotificationModel.id.in_([int(i) for i in ids]))
        rows = s.scalars(q).all()
        for r in rows:
            r.read = True
        return len(rows)
