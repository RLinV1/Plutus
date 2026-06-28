"""Pure portfolio accounting: holdings, average cost, P&L, value history, TWR.

No I/O here — callers pass in transactions (as dicts) and price frames, which
keeps every function unit-testable and deterministic. Cost basis uses the
AVERAGE-COST method (what most brokerage apps display); tax-lot accounting is
deliberately out of scope.
"""

from __future__ import annotations

import pandas as pd


class LedgerError(ValueError):
    pass


def _txn_key(t: dict) -> tuple:
    """Chronological sort key: trade date, then insertion id (intra-day order)."""
    return (str(t.get("trade_date") or ""), t.get("id") or 0)


def compute_holdings(txns: list[dict]) -> dict:
    """Run the transaction list through average-cost accounting.

    Returns ``{"positions": {ticker: {shares, avg_cost, cost_basis,
    realized_pnl}}, "warnings": [...], "realized_pnl_total": float}``.
    Oversells (selling more than held) are clipped and reported as warnings
    rather than raising, so one bad row never hides the whole portfolio.
    """
    positions: dict[str, dict] = {}
    warnings: list[str] = []
    for t in sorted(txns, key=_txn_key):
        tk = str(t["ticker"]).upper()
        side = str(t["side"]).upper()
        s = float(t["shares"])
        price = float(t["price"])
        fees = float(t.get("fees") or 0.0)
        if s <= 0 or price <= 0:
            warnings.append(f"Skipped {side} {tk}: non-positive shares/price.")
            continue
        p = positions.setdefault(
            tk, {"shares": 0.0, "cost_basis": 0.0, "realized_pnl": 0.0}
        )
        if side == "BUY":
            p["cost_basis"] += s * price + fees
            p["shares"] += s
        elif side == "SELL":
            if s > p["shares"] + 1e-9:
                warnings.append(
                    f"{t.get('trade_date', '?')}: SELL {s:g} {tk} but only "
                    f"{p['shares']:g} held — clipped to what you own."
                )
                s = p["shares"]
            if s <= 0:
                continue
            avg = p["cost_basis"] / p["shares"]
            p["realized_pnl"] += s * (price - avg) - fees
            p["cost_basis"] -= s * avg
            p["shares"] -= s
        else:
            raise LedgerError(f"Unknown transaction side: {t['side']!r}")

    for p in positions.values():
        if p["shares"] < 1e-9:
            p["shares"] = 0.0
            p["cost_basis"] = 0.0
            p["avg_cost"] = None
        else:
            p["avg_cost"] = p["cost_basis"] / p["shares"]

    return {
        "positions": positions,
        "warnings": warnings,
        "realized_pnl_total": float(
            sum(p["realized_pnl"] for p in positions.values())
        ),
    }


def held_tickers(txns: list[dict]) -> list[str]:
    """Tickers with a nonzero position right now, sorted (canonical order
    matters: mock price generation consumes RNG per ticker in request order)."""
    pos = compute_holdings(txns)["positions"]
    return sorted(t for t, p in pos.items() if p["shares"] > 0)


def shares_matrix(txns: list[dict], date_index) -> pd.DataFrame:
    """Cumulative shares held per ticker as a step function over ``date_index``.

    Transactions dated before the index collapse into the initial position;
    transactions on non-trading dates snap forward to the next index date.
    """
    idx = pd.DatetimeIndex(date_index)
    tickers = sorted({str(t["ticker"]).upper() for t in txns})
    out = pd.DataFrame(0.0, index=idx, columns=tickers)
    if idx.empty or not txns:
        return out

    deltas: dict[str, dict[pd.Timestamp, float]] = {tk: {} for tk in tickers}
    for t in sorted(txns, key=_txn_key):
        tk = str(t["ticker"]).upper()
        d = pd.Timestamp(t["trade_date"])
        sign = 1.0 if str(t["side"]).upper() == "BUY" else -1.0
        deltas[tk][d] = deltas[tk].get(d, 0.0) + sign * float(t["shares"])

    for tk in tickers:
        if not deltas[tk]:
            continue
        cum = pd.Series(deltas[tk]).sort_index().cumsum()
        aligned = (
            cum.reindex(idx.union(cum.index)).ffill().reindex(idx).fillna(0.0)
        )
        # Oversells are clipped in compute_holdings; mirror that here so the
        # value series never goes negative from a bad row.
        out[tk] = aligned.clip(lower=0.0)
    return out


def portfolio_value_series(txns: list[dict], prices: pd.DataFrame) -> pd.Series:
    """Daily market value of the whole portfolio: shares step-function × prices."""
    shares = shares_matrix(txns, prices.index)
    cols = [c for c in shares.columns if c in prices.columns]
    if not cols:
        return pd.Series(0.0, index=prices.index)
    return (shares[cols] * prices[cols].ffill()).fillna(0.0).sum(axis=1)


def flows_series(txns: list[dict], date_index) -> pd.Series:
    """External cash flow per index date (cash isn't modeled, so each trade is a
    flow at its trade price): BUY = +shares*price+fees, SELL = -(shares*price-fees).
    Trades on non-trading dates snap forward, matching ``shares_matrix``."""
    idx = pd.DatetimeIndex(date_index)
    flows = pd.Series(0.0, index=idx)
    if idx.empty:
        return flows
    for t in txns:
        d = pd.Timestamp(t["trade_date"])
        s = float(t["shares"])
        price = float(t["price"])
        fees = float(t.get("fees") or 0.0)
        if str(t["side"]).upper() == "BUY":
            amt = s * price + fees
        else:
            amt = -(s * price - fees)
        pos = idx.searchsorted(d)
        if pos >= len(idx):
            continue  # after the window — irrelevant to this view
        flows.iloc[pos] += amt
    return flows


def time_weighted_returns(
    values: pd.Series, flows: pd.Series | None = None
) -> pd.Series:
    """Daily time-weighted returns: r_t = (V_t - F_t) / V_{t-1} - 1.

    Flows (deposits via buys, withdrawals via sells) are stripped out so new
    money never shows up as performance. Days with no prior value (account not
    started yet, or fully cashed out) are skipped.
    """
    v = values.astype(float)
    f = (
        flows.reindex(v.index).fillna(0.0)
        if flows is not None
        else pd.Series(0.0, index=v.index)
    )
    prev = v.shift(1)
    r = (v - f) / prev - 1.0
    return r[prev > 1e-9].dropna()
