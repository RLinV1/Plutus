"""Portfolio-level analytics: overview, risk report, equity curve.

This is a GLUE layer: accounting math lives in ``ledger.py``, risk math in
``risk/metrics.py`` + ``risk/portfolio.py`` (reused, never duplicated), and
market data comes through the same cached ``market_data`` functions every
other tool uses. Everything returns JSON-clean dicts; numbers go through
``_mf`` (NaN -> None) so the MCP layer never sees a numpy scalar.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from ..data.loader import load_returns
from ..data.market_data import get_company_info, get_prices, get_quote
from ..risk import metrics
from ..risk.portfolio import Portfolio, compute_portfolio_report
from . import ledger, store

_DISCLAIMER = "Educational information, not personalized investment advice."


def _mf(x, nd: int = 4):
    """float-or-None (NaN -> None), rounded — mirrors tools._maybe_float."""
    if x is None:
        return None
    f = float(x)
    return None if f != f else round(f, nd)


def _vol_bucket(vol: float) -> str:
    """Same thresholds as tools._movement_bucket, applied to the whole portfolio."""
    if vol != vol:
        return "unknown"
    if vol < 0.15:
        return "calm — steadier than most single stocks"
    if vol < 0.30:
        return "average — typical stock-market ups and downs"
    return "bumpy — expect big swings"


def _concentration_reading(hhi: float, top_weight: float, n: int) -> tuple[str, str]:
    if n == 0:
        return "empty", "No holdings yet."
    if n == 1:
        return (
            "all in one position",
            "Everything rides on a single stock — any company-specific problem "
            "hits the entire portfolio at once.",
        )
    if hhi >= 0.40 or top_weight >= 0.50:
        return (
            "highly concentrated",
            "A large share of the portfolio sits in one or two names, so "
            "company-specific news will move the whole account.",
        )
    if hhi >= 0.25 or top_weight >= 0.35:
        return (
            "concentrated",
            "A few positions dominate; consider whether that's intentional.",
        )
    if hhi >= 0.15:
        return (
            "moderately diversified",
            "Reasonably spread out, with some tilt toward the largest positions.",
        )
    return (
        "well diversified",
        "Value is spread across many positions, which dampens single-stock shocks.",
    )


def position_values(portfolio: str = "default") -> dict:
    """Shared building block: transactions -> ledger -> per-position current
    price, market value, and weight. Used by overview, risk, and scenarios."""
    txns = store.list_transactions(portfolio)
    led = ledger.compute_holdings(txns)
    held = sorted(t for t, p in led["positions"].items() if p["shares"] > 0)
    base = {"txns": txns, "ledger": led, "held": held, "rows": [], "total_value": 0.0}
    if not held:
        return base

    prices = get_prices(held, lookback_days=260)
    rows: list[dict] = []
    for t in held:
        p = led["positions"][t]
        series = prices[t].dropna() if t in prices.columns else pd.Series(dtype=float)
        if series.empty:
            # No price data — fall back to cost so the position isn't invisible.
            price, change = p["avg_cost"] or 0.0, None
        else:
            quote = get_quote(t)
            if quote and quote.get("price"):
                price = float(quote["price"])
                change = float(quote.get("change_pct", 0.0))
            else:
                price = float(series.iloc[-1])
                change = (
                    float(series.iloc[-1] / series.iloc[-2] - 1.0)
                    if len(series) >= 2
                    else None
                )
        mv = p["shares"] * price
        rows.append(
            {
                "ticker": t,
                "shares": _mf(p["shares"]),
                "avg_cost": _mf(p["avg_cost"], 2),
                "cost_basis": _mf(p["cost_basis"], 2),
                "price": _mf(price, 2),
                "day_change_pct": _mf(change),
                "market_value": _mf(mv, 2),
                "unrealized_pnl": _mf(mv - p["cost_basis"], 2),
                "unrealized_pnl_pct": _mf(
                    (mv / p["cost_basis"] - 1.0) if p["cost_basis"] > 0 else None
                ),
                "realized_pnl": _mf(p["realized_pnl"], 2),
            }
        )
    total = float(sum(r["market_value"] or 0.0 for r in rows))
    for r in rows:
        r["weight"] = _mf((r["market_value"] or 0.0) / total if total > 0 else None)
    rows.sort(key=lambda r: -(r["market_value"] or 0.0))
    base["rows"] = rows
    base["total_value"] = total
    return base


def overview(portfolio: str = "default") -> dict:
    pv = position_values(portfolio)
    name = (portfolio or "default").strip() or "default"
    if not pv["rows"]:
        return {
            "portfolio": name,
            "holdings": [],
            "totals": {
                "market_value": 0.0,
                "cost_basis": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": None,
                "realized_pnl": _mf(pv["ledger"]["realized_pnl_total"], 2) or 0.0,
                "day_change_pct": None,
            },
            "warnings": pv["ledger"]["warnings"],
            "note": (
                "No current holdings. Record a BUY transaction first (Portfolio "
                "tab in the app, or POST /api/portfolio/{name}/transactions)."
            ),
        }

    info = get_company_info(pv["held"])
    sector_weights: dict[str, float] = {}
    for r in pv["rows"]:
        meta = info.get(r["ticker"], {})
        r["name"] = meta.get("name", r["ticker"])
        r["sector"] = meta.get("sector", "Unknown")
        sector_weights[r["sector"]] = sector_weights.get(r["sector"], 0.0) + (
            r["weight"] or 0.0
        )

    total = pv["total_value"]
    cost = float(sum(r["cost_basis"] or 0.0 for r in pv["rows"]))
    weights = [r["weight"] or 0.0 for r in pv["rows"]]
    hhi = float(sum(w * w for w in weights))
    top = pv["rows"][0]
    day = sum(
        (r["weight"] or 0.0) * r["day_change_pct"]
        for r in pv["rows"]
        if r["day_change_pct"] is not None
    )
    label, detail = _concentration_reading(hhi, top["weight"] or 0.0, len(pv["rows"]))

    return {
        "portfolio": name,
        "holdings": pv["rows"],
        "totals": {
            "market_value": _mf(total, 2),
            "cost_basis": _mf(cost, 2),
            "unrealized_pnl": _mf(total - cost, 2),
            "unrealized_pnl_pct": _mf((total / cost - 1.0) if cost > 0 else None),
            "realized_pnl": _mf(pv["ledger"]["realized_pnl_total"], 2),
            "day_change_pct": _mf(day),
        },
        "allocation_by_sector": {k: _mf(v) for k, v in sorted(sector_weights.items())},
        "top_position": {"ticker": top["ticker"], "weight": top["weight"]},
        "hhi": _mf(hhi),
        "concentration": label,
        "concentration_detail": detail,
        "warnings": pv["ledger"]["warnings"],
        "note": _DISCLAIMER,
    }


def risk_report(
    portfolio: str = "default", benchmark: str = config.DEFAULT_BENCHMARK
) -> dict:
    """Every headline risk number for the portfolio AS CURRENTLY CONSTITUTED
    (current market-value weights against historical returns)."""
    pv = position_values(portfolio)
    name = (portfolio or "default").strip() or "default"
    if not pv["rows"]:
        return {"portfolio": name, "error": "No current holdings — nothing to assess."}

    weights = {
        r["ticker"]: (r["weight"] or 0.0) for r in pv["rows"] if (r["weight"] or 0) > 0
    }
    returns_df, bench = load_returns(
        sorted(weights), benchmark, config.DEFAULT_LOOKBACK_DAYS
    )
    report = compute_portfolio_report(Portfolio(weights), returns_df[sorted(weights)], bench)

    corr = metrics.correlation_matrix(returns_df[sorted(weights)])
    tickers = list(corr.columns)
    pair = None
    if len(tickers) >= 2:
        best = (-2.0, None, None)
        for i, a in enumerate(tickers):
            for b in tickers[i + 1 :]:
                c = float(corr.loc[a, b])
                if c == c and c > best[0]:
                    best = (c, a, b)
        if best[1]:
            pair = {"tickers": [best[1], best[2]], "correlation": _mf(best[0])}

    hhi = float(sum(w * w for w in weights.values()))
    top = pv["rows"][0]
    total = pv["total_value"]
    vol = report["volatility"]
    var95 = report["var_hist_95"]
    conc_label, conc_detail = _concentration_reading(
        hhi, top["weight"] or 0.0, len(pv["rows"])
    )

    sens = (
        "less sensitive than the market"
        if report["beta"] < 0.8
        else "about as sensitive as the market"
        if report["beta"] <= 1.2
        else "more sensitive than the market"
    )
    summary = (
        f"Your portfolio's volatility is about {vol * 100.0:.2f}% a year — "
        f"{_vol_bucket(vol)}. On a bad day (worse than 95% of days) it loses about "
        f"{var95 * 100.0:.2f}% (~${var95 * total:,.0f}). Versus the overall market it is "
        f"{sens} (beta {report['beta']:.2f}). It is {conc_label}: {conc_detail} "
        f"{_DISCLAIMER}"
    )

    return {
        "portfolio": name,
        "benchmark": benchmark.upper(),
        "market_value": _mf(total, 2),
        "n_positions": len(pv["rows"]),
        "weights": {t: _mf(w) for t, w in weights.items()},
        "volatility": _mf(report["volatility"]),
        "volatility_annual_pct": _mf(report["volatility"] * 100.0, 2),
        "beta": _mf(report["beta"], 2),
        "sharpe": _mf(report["sharpe"], 2),
        "expected_return": _mf(report["expected_return"]),
        "max_drawdown": _mf(report["max_drawdown"]),
        "var_hist_95": _mf(report["var_hist_95"]),
        "var_param_95": _mf(report["var_param_95"]),
        "var_mc_95": _mf(report["var_mc_95"]),
        "cvar_95": _mf(report["cvar_95"]),
        "var_hist_95_dollars": _mf(report["var_hist_95"] * total, 2),
        "cvar_95_dollars": _mf(report["cvar_95"] * total, 2),
        "hhi": _mf(hhi),
        "concentration": conc_label,
        "diversification_detail": conc_detail,
        "correlation": {
            "tickers": tickers,
            "matrix": [[_mf(corr.loc[a, b]) for b in tickers] for a in tickers],
        },
        "highest_correlated_pair": pair,
        "plain_summary": summary,
    }


def equity_curve(
    portfolio: str = "default", lookback_days: int = config.DEFAULT_LOOKBACK_DAYS
) -> dict:
    """The account's value history reconstructed from transactions × daily
    prices, plus a time-weighted return index (new money excluded)."""
    name = (portfolio or "default").strip() or "default"
    txns = store.list_transactions(portfolio)
    if not txns:
        return {"portfolio": name, "points": [], "twr_points": [], "note": "No transactions yet."}

    tickers = sorted({t["ticker"] for t in txns})
    prices = get_prices(tickers, lookback_days=lookback_days)
    values = ledger.portfolio_value_series(txns, prices)
    # Trim the leading flat-zero stretch before the first position existed.
    started = values.gt(0).cummax()
    values = values[started]
    if values.empty:
        return {"portfolio": name, "points": [], "twr_points": [], "note": "No holdings in the price window."}

    flows = ledger.flows_series(txns, values.index)
    r = ledger.time_weighted_returns(values, flows)
    twr_index = 100.0 * (1.0 + r).cumprod()

    def _pts(series: pd.Series) -> list[dict]:
        return [
            {"t": pd.Timestamp(i).strftime("%Y-%m-%d"), "v": round(float(v), 2)}
            for i, v in series.items()
        ]

    twr_total = float(twr_index.iloc[-1] / 100.0 - 1.0) if len(twr_index) else None
    return {
        "portfolio": name,
        "points": _pts(values),
        "twr_points": _pts(twr_index),
        "summary": {
            "start": str(values.index[0].date()),
            "end": str(values.index[-1].date()),
            "market_value_end": _mf(values.iloc[-1], 2),
            "twr_return_pct": _mf(twr_total * 100.0 if twr_total is not None else None, 2),
            "max_drawdown_pct": _mf(metrics.max_drawdown(r) * 100.0, 2) if len(r) else None,
        },
        "note": "Value history includes deposits; the TWR index strips new money out.",
    }
