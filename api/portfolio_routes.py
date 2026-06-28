"""REST surface for portfolios, transactions, CSV import, alerts, notifications.

Analysis endpoints delegate to ``portfolio_risk.tools`` (the single source of
truth the agent also uses); mutations go straight to the store — by design the
AGENT has no write tools, only this HTTP layer mutates.
"""

from __future__ import annotations

from fastapi import APIRouter

from portfolio_risk import tools
from portfolio_risk.portfolio import csv_import, store
from portfolio_risk.portfolio import analytics

router = APIRouter(prefix="/api")


def _safe(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _ensure_demo(name: str) -> None:
    """The DEMO portfolio is self-healing: whenever it's requested empty (fresh
    install, or right after a reset) the standard sample transactions are
    re-seeded. Pure deterministic data — no AI involved."""
    if (name or "").strip().lower() != "demo":
        return
    try:
        from evals.seed_portfolio import ensure_seeded

        ensure_seeded("demo")
    except Exception:  # noqa: BLE001 - demo healing must never break a request
        pass


# --- Portfolios & transactions ---------------------------------------------- #
@router.get("/portfolios")
def portfolios() -> dict:
    return _safe(lambda: {"portfolios": store.list_portfolios()})


@router.get("/portfolio/{name}")
def portfolio_overview(name: str) -> dict:
    _ensure_demo(name)
    return tools.get_portfolio_overview(name)


@router.get("/portfolio/{name}/risk")
def portfolio_risk(name: str, benchmark: str = "SPY") -> dict:
    _ensure_demo(name)
    return tools.get_portfolio_risk_report(name, benchmark)


@router.get("/portfolio/{name}/equity_curve")
def portfolio_equity_curve(name: str, days: int = 504) -> dict:
    _ensure_demo(name)
    return _safe(analytics.equity_curve, name, min(max(days, 30), 3024))


@router.get("/portfolio/{name}/transactions")
def transactions(name: str) -> dict:
    _ensure_demo(name)
    return _safe(lambda: {"transactions": store.list_transactions(name)})


@router.post("/portfolio/{name}/transactions")
def add_transaction(name: str, payload: dict) -> dict:
    p = payload or {}
    return _safe(
        store.add_transaction,
        name,
        p.get("ticker", ""),
        p.get("side", ""),
        p.get("shares", 0),
        p.get("price", 0),
        p.get("fees", 0.0),
        p.get("trade_date"),
        p.get("note", ""),
    )


@router.delete("/portfolio/transactions/{txn_id}")
def delete_transaction(txn_id: int) -> dict:
    return _safe(lambda: {"deleted": store.delete_transaction(txn_id)})


@router.post("/portfolio/{name}/reset")
def reset_portfolio(name: str, payload: dict) -> dict:
    """Delete ALL transactions in a portfolio. Requires the caller to echo the
    portfolio name as typed confirmation — no accidental wipes."""
    confirm = ((payload or {}).get("confirm") or "").strip()
    if confirm.upper() != name.strip().upper():
        return {
            "error": (
                f"Confirmation text didn't match — type the portfolio name "
                f"({name.upper()}) exactly to reset it."
            )
        }
    return _safe(lambda: {"reset": True, "deleted": store.delete_all_transactions(name)})


@router.post("/portfolio/{name}/import_csv")
def import_csv(name: str, payload: dict) -> dict:
    """Dry-run by default: returns parsed rows + per-line errors. Pass
    {"commit": true} with the same csv text to actually write."""
    p = payload or {}
    text = p.get("csv", "")
    if not text.strip():
        return {"error": "Empty CSV."}
    parsed = csv_import.parse_csv(text)
    if not p.get("commit"):
        return {**parsed, "committed": False}
    if not parsed["rows"]:
        return {**parsed, "committed": False, "error": "No importable rows."}
    written = _safe(csv_import.commit_rows, name, parsed["rows"])
    if isinstance(written, dict) and "error" in written:
        return {**parsed, "committed": False, **written}
    return {**parsed, "committed": True, "imported": len(written)}


# --- Analysis / advisor views ----------------------------------------------- #
@router.get("/portfolio/{name}/news")
def portfolio_news(name: str, limit_per_ticker: int = 3) -> dict:
    return tools.get_portfolio_news(name, limit_per_ticker)


@router.get("/portfolio/{name}/briefing")
def portfolio_briefing(name: str, period: str = "1d") -> dict:
    return tools.get_portfolio_briefing(name, period)


@router.get("/portfolio/{name}/scenario")
def portfolio_scenario(name: str, scenario: str = "covid_2020") -> dict:
    _ensure_demo(name)
    return tools.run_portfolio_scenario(scenario, name)


@router.get("/scenarios")
def scenarios() -> dict:
    return tools.run_portfolio_scenario("list")


@router.post("/scenario/basket")
def scenario_basket(payload: dict) -> dict:
    """Stress-test an ad-hoc basket (scenario lab's basket builder): positions
    are [{ticker, value?}] with value defaulting to $10,000 each."""
    from portfolio_risk.portfolio import scenarios as scen

    p = payload or {}
    values: dict[str, float] = {}
    for row in p.get("positions") or []:
        t = str(row.get("ticker", "")).strip().upper()
        if not t:
            continue
        try:
            v = float(row.get("value") or 10_000)
        except (TypeError, ValueError):
            v = 10_000.0
        if v > 0:
            values[t] = values.get(t, 0.0) + v
    return _safe(scen.stress_test_values, values, p.get("scenario", "covid_2020"))


@router.post("/portfolio/{name}/simulate")
def simulate(name: str, payload: dict) -> dict:
    p = payload or {}
    return tools.simulate_trade(
        p.get("side", ""), p.get("ticker", ""), p.get("shares", 0), name
    )


@router.get("/portfolio/{name}/rebalance")
def rebalance(name: str, target: str = "equal_weight") -> dict:
    _ensure_demo(name)
    return tools.get_rebalance_plan(name, target)


# --- Paper trading ------------------------------------------------------------ #
@router.get("/paper/account")
def paper_account() -> dict:
    from portfolio_risk.portfolio import paper

    return _safe(paper.account_state)


@router.post("/paper/trade")
def paper_trade(payload: dict) -> dict:
    from portfolio_risk.portfolio import paper

    p = payload or {}
    return _safe(paper.execute_trade, p.get("side", ""), p.get("ticker", ""), p.get("shares", 0))


@router.post("/paper/reset")
def paper_reset() -> dict:
    from portfolio_risk.portfolio import paper

    return _safe(paper.reset_account)


# --- Alerts & notifications -------------------------------------------------- #
@router.get("/alerts")
def alerts() -> dict:
    return _safe(lambda: {"rules": store.list_alert_rules()})


@router.post("/alerts")
def add_alert(payload: dict) -> dict:
    import re

    p = payload or {}
    t = str(p.get("ticker", "")).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", t):
        return {"error": f"{t or '(empty)'} doesn't look like a ticker symbol."}
    # Only arm rules for tickers that actually price — a rule on a typo would
    # sit silent forever, which reads as "alerts are broken".
    try:
        from portfolio_risk.data.market_data import get_prices

        get_prices([t], lookback_days=30)
    except Exception:  # noqa: BLE001
        return {"error": f"Unknown ticker {t} — no price data found for it."}
    return _safe(
        store.add_alert_rule,
        t,
        p.get("rule_type", ""),
        p.get("threshold", 0),
        p.get("portfolio"),
        p.get("cooldown_minutes", 240),
    )


@router.patch("/alerts/{rule_id}")
def update_alert(rule_id: int, payload: dict) -> dict:
    p = payload or {}
    out = _safe(
        store.update_alert_rule,
        rule_id,
        enabled=p.get("enabled"),
        threshold=p.get("threshold"),
        cooldown_minutes=p.get("cooldown_minutes"),
    )
    return out if out else {"error": f"No alert rule {rule_id}."}


@router.delete("/alerts/{rule_id}")
def delete_alert(rule_id: int) -> dict:
    return _safe(lambda: {"deleted": store.delete_alert_rule(rule_id)})


@router.get("/notifications")
def notifications(unread: int = 0, limit: int = 50) -> dict:
    return _safe(
        lambda: {"notifications": store.list_notifications(bool(unread), limit)}
    )


@router.post("/notifications/read")
def mark_read(payload: dict | None = None) -> dict:
    ids = (payload or {}).get("ids")
    return _safe(lambda: {"marked": store.mark_notifications_read(ids)})
