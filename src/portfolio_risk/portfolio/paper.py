"""Paper trading: a virtual cash account with market fills at live prices.

The account is just a regular portfolio named ``paper`` plus derived cash:
``cash = starting balance − buys (incl. fees) + sells (net of fees)``. Fills
execute at the CURRENT yfinance quote (falling back to the last cached daily
close, which is also what mock mode uses), so no schema change and the whole
ledger/analytics stack works on it unchanged. Buys are rejected when they
exceed cash; sells when they exceed the position.
"""

from __future__ import annotations

from .. import config

PAPER_PORTFOLIO = "paper"


def _paper_portfolio(user_id: str = "anonymous") -> str:
    """Portfolio name scoped to a user. Falls back to the shared 'paper' name."""
    return PAPER_PORTFOLIO if user_id == "anonymous" else f"paper:{user_id}"


def _cash(txns: list[dict], start: float) -> float:
    cash = start
    for t in txns:
        gross = float(t["shares"]) * float(t["price"])
        fees = float(t.get("fees") or 0.0)
        if str(t["side"]).upper() == "BUY":
            cash -= gross + fees
        else:
            cash += gross - fees
    return cash


def _fill_price(ticker: str) -> float:
    """Market-fill price: live quote first, last daily close as fallback."""
    from ..data.market_data import get_prices, get_quote

    quote = get_quote(ticker)
    if quote and quote.get("price"):
        return float(quote["price"])
    # Same lookback analytics.position_values uses, so a mock-mode fill prices
    # identically to how the resulting position is valued.
    series = get_prices([ticker], lookback_days=260)[ticker].dropna()
    if series.empty:
        raise ValueError(f"No price data for {ticker}.")
    return float(series.iloc[-1])


def account_state(user_id: str = "anonymous") -> dict:
    from . import analytics

    pf = _paper_portfolio(user_id)
    start = config.paper_start_cash()
    pv = analytics.position_values(pf)
    cash = _cash(pv["txns"], start)
    equity = pv["total_value"]
    total = cash + equity
    return {
        "portfolio": pf,
        "start_cash": round(start, 2),
        "cash": round(cash, 2),
        "positions_value": round(equity, 2),
        "total_value": round(total, 2),
        "return_pct": round((total / start - 1.0) * 100.0, 2),
        "realized_pnl": round(pv["ledger"]["realized_pnl_total"], 2),
        "n_trades": len(pv["txns"]),
        "positions": pv["rows"],
        "transactions": pv["txns"][-50:],
        "note": (
            "Simulated account — fills use the current market quote; no real "
            "money is involved. Educational, not investment advice."
        ),
    }


def execute_trade(side: str, ticker: str, shares: float, user_id: str = "anonymous") -> dict:
    """Market order against the live quote. Returns the fill + fresh account."""
    from . import ledger, store

    pf = _paper_portfolio(user_id)
    side = (side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        return {"error": f"side must be BUY or SELL, got {side!r}"}
    try:
        shares = float(shares)
    except (TypeError, ValueError):
        return {"error": "shares must be a number"}
    if shares <= 0:
        return {"error": "shares must be > 0"}
    tk = (ticker or "").strip().upper()
    if not tk:
        return {"error": "ticker is required"}

    try:
        price = _fill_price(tk)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Couldn't price {tk}: {exc}"}

    txns = store.list_transactions(pf)
    if side == "BUY":
        cost = shares * price
        cash = _cash(txns, config.paper_start_cash())
        if cost > cash + 1e-6:
            return {
                "error": (
                    f"Not enough paper cash: {shares:g} {tk} ≈ ${cost:,.2f}, "
                    f"but you have ${cash:,.2f}."
                )
            }
    else:
        held = ledger.compute_holdings(txns)["positions"].get(tk, {}).get("shares", 0.0)
        if shares > held + 1e-9:
            return {"error": f"You hold {held:g} {tk} on paper; can't sell {shares:g}."}

    fill = store.add_transaction(pf, tk, side, shares, price, note="paper market fill")
    return {"fill": fill, "account": account_state(user_id)}


def reset_account(user_id: str = "anonymous") -> dict:
    """Wipe all paper trades and start over from the full cash balance."""
    from . import store

    pf = _paper_portfolio(user_id)
    txns = store.list_transactions(pf)
    for t in txns:
        store.delete_transaction(t["id"])
    return {"reset": True, "deleted": len(txns), "account": account_state(user_id)}
