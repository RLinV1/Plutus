"""Scenario & strategy lab: crisis stress tests, what-if trades, rebalancing.

Crisis tests use a BETA-SCALED APPROXIMATION (each holding moves beta × the
market's crisis drop) because the offline price cache doesn't reach 2008.
Every result is labeled with its method — these are honest estimates for
education, never predictions.
"""

from __future__ import annotations

import numpy as np

from .. import config
from ..data.loader import load_returns
from ..data.market_data import get_prices
from ..risk import metrics
from ..risk.portfolio import Portfolio, compute_portfolio_report
from . import analytics

_DISCLAIMER = "Educational estimate, not personalized investment advice."

SCENARIOS: dict[str, dict] = {
    "gfc_2008": {
        "label": "2008 Global Financial Crisis",
        "market_drop": -0.55,
        "window": "Oct 2007 – Mar 2009",
    },
    "covid_2020": {
        "label": "COVID-19 crash",
        "market_drop": -0.34,
        "window": "Feb – Mar 2020",
    },
    "rates_2022": {
        "label": "2022 rate shock",
        "market_drop": -0.25,
        "window": "Jan – Oct 2022",
    },
    "black_monday": {
        "label": "Black Monday 1987 (single day)",
        "market_drop": -0.20,
        "window": "Oct 19, 1987",
    },
    "correction_10": {
        "label": "Generic 10% market correction",
        "market_drop": -0.10,
        "window": "hypothetical",
    },
}

_ALIASES = {
    "2008": "gfc_2008",
    "gfc": "gfc_2008",
    "financial crisis": "gfc_2008",
    "covid": "covid_2020",
    "2020": "covid_2020",
    "pandemic": "covid_2020",
    "2022": "rates_2022",
    "rate": "rates_2022",
    "inflation": "rates_2022",
    "1987": "black_monday",
    "monday": "black_monday",
    "correction": "correction_10",
    "10%": "correction_10",
}


def list_scenarios() -> list[dict]:
    return [
        {"id": k, **v, "market_drop_pct": round(v["market_drop"] * 100.0, 1)}
        for k, v in SCENARIOS.items()
    ]


def resolve_scenario(name: str) -> str | None:
    s = (name or "").strip().lower().replace("-", "_")
    if s in SCENARIOS:
        return s
    for key, target in _ALIASES.items():
        if key in s:
            return target
    return None


def stress_test(portfolio: str = "default", scenario: str = "covid_2020") -> dict:
    """Stress a SAVED portfolio: current position values -> beta-scaled shock."""
    pv = analytics.position_values(portfolio)
    if not pv["rows"]:
        return {"error": "No current holdings — nothing to stress test."}
    values = {r["ticker"]: (r["market_value"] or 0.0) for r in pv["rows"]}
    out = stress_test_values(values, scenario)
    if "error" not in out:
        out["portfolio"] = (portfolio or "default").strip() or "default"
    return out


def stress_test_values(values: dict[str, float], scenario: str = "covid_2020") -> dict:
    """Stress an ARBITRARY basket of {ticker: dollar value} — powers both saved
    portfolios and the scenario lab's custom basket builder."""
    sid = resolve_scenario(scenario)
    if sid is None:
        return {
            "error": f"Unknown scenario {scenario!r}.",
            "available": list_scenarios(),
        }
    spec = SCENARIOS[sid]
    values = {
        str(t).upper(): float(v) for t, v in values.items() if float(v) > 0
    }
    if not values:
        return {"error": "Add at least one position to stress test."}

    held = sorted(values)
    returns_df, bench = load_returns(held, "SPY", config.DEFAULT_LOOKBACK_DAYS)

    drop = spec["market_drop"]
    positions: list[dict] = []
    total_loss = 0.0
    total = sum(values.values())
    for t in held:
        b = metrics.beta(returns_df[t], bench)
        b = 1.0 if b != b else float(b)  # NaN beta -> assume market-like
        shock = float(np.clip(b * drop, -0.95, 0.5))
        loss = values[t] * shock
        total_loss += loss
        positions.append(
            {
                "ticker": t,
                "market_value": round(values[t], 2),
                "beta": round(b, 2),
                "estimated_move_pct": round(shock * 100.0, 2),
                "estimated_change": round(loss, 2),
            }
        )
    positions.sort(key=lambda p: -p["market_value"])

    loss_pct = total_loss / total if total > 0 else 0.0

    # Scale the shock against the basket's own typical bad day (95% VaR).
    w = np.array([values[t] / total for t in held])
    port_ret = metrics.portfolio_returns(returns_df[held], w)
    var95 = metrics.value_at_risk_historical(port_ret, 0.95)
    vs_var = abs(loss_pct) / var95 if var95 and var95 == var95 and var95 > 0 else None

    return {
        "portfolio": "custom_basket",
        "scenario": sid,
        "label": spec["label"],
        "window": spec["window"],
        "market_drop_pct": round(drop * 100.0, 1),
        "method": "beta_approximation",
        "positions": positions,
        "total_value": round(total, 2),
        "estimated_loss": round(total_loss, 2),
        "estimated_loss_pct": round(loss_pct * 100.0, 2),
        "estimated_value_after": round(total + total_loss, 2),
        "vs_daily_var": round(vs_var, 1) if vs_var is not None else None,
        "note": (
            "Beta-scaled estimate: each holding is assumed to move beta × the "
            "market's drop in that crisis. It is a first-order approximation, "
            f"not a replay of actual prices. {_DISCLAIMER}"
        ),
    }


def _report_for(weights: dict[str, float], returns_df, bench) -> dict:
    order = sorted(weights)
    rep = compute_portfolio_report(Portfolio(weights), returns_df[order], bench)
    hhi = float(sum((w / sum(weights.values())) ** 2 for w in weights.values()))
    top_w = max(weights.values()) / sum(weights.values())
    return {
        "volatility_annual_pct": round(rep["volatility"] * 100.0, 2),
        "beta": round(rep["beta"], 2),
        "sharpe": round(rep["sharpe"], 2),
        "var_hist_95_pct": round(rep["var_hist_95"] * 100.0, 2),
        "max_drawdown_pct": round(rep["max_drawdown"] * 100.0, 2),
        "hhi": round(hhi, 4),
        "top_weight_pct": round(top_w * 100.0, 2),
    }


def what_if_trade(
    portfolio: str, side: str, ticker: str, shares: float
) -> dict:
    """Portfolio risk before vs after a HYPOTHETICAL trade. Read-only —
    nothing is ever written to the transaction log."""
    side = (side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        return {"error": f"side must be BUY or SELL, got {side!r}"}
    shares = float(shares)
    if shares <= 0:
        return {"error": "shares must be > 0"}
    tk = (ticker or "").strip().upper()
    if not tk:
        return {"error": "ticker is required"}

    pv = analytics.position_values(portfolio)
    values = {r["ticker"]: (r["market_value"] or 0.0) for r in pv["rows"]}
    held_shares = {r["ticker"]: (r["shares"] or 0.0) for r in pv["rows"]}

    # Price the trade: current position price if held, else last cached close.
    if tk in {r["ticker"]: r for r in pv["rows"]}:
        price = next(r["price"] for r in pv["rows"] if r["ticker"] == tk)
    else:
        series = get_prices([tk], lookback_days=30)[tk].dropna()
        if series.empty:
            return {"error": f"No price data for {tk}."}
        price = float(series.iloc[-1])

    if side == "SELL":
        if tk not in held_shares:
            return {"error": f"You don't hold {tk}, so you can't sell it."}
        if shares > held_shares[tk] + 1e-9:
            return {
                "error": f"You hold {held_shares[tk]:g} {tk}; can't sell {shares:g}."
            }

    after_values = dict(values)
    delta_value = shares * price * (1.0 if side == "BUY" else -1.0)
    after_values[tk] = after_values.get(tk, 0.0) + delta_value
    after_values = {t: v for t, v in after_values.items() if v > 1e-9}

    if not after_values:
        return {"error": "That trade would empty the portfolio — nothing to compare."}

    union = sorted(set(values) | set(after_values))
    returns_df, bench = load_returns(union, "SPY", config.DEFAULT_LOOKBACK_DAYS)

    before = (
        _report_for(values, returns_df, bench) if values else None
    )
    after = _report_for(after_values, returns_df, bench)
    deltas = (
        {k: round(after[k] - before[k], 4) for k in after}
        if before is not None
        else None
    )

    return {
        "portfolio": (portfolio or "default").strip() or "default",
        "trade": {
            "side": side,
            "ticker": tk,
            "shares": shares,
            "est_price": round(price, 2),
            "est_value": round(shares * price, 2),
        },
        "before": before,
        "after": after,
        "deltas": deltas,
        "note": (
            "Hypothetical only — this tool never records a transaction. "
            f"{_DISCLAIMER}"
        ),
    }


def rebalance_plan(portfolio: str = "default", target=None) -> dict:
    """Suggested trades to move from current weights to a target allocation.

    ``target``: None/'equal_weight' (even split across current holdings) or a
    {ticker: weight} dict (weights normalized; tickers absent from the dict are
    sold; new tickers are bought). Trades under 0.5% of the portfolio are
    dropped as not worth the friction. No tax or fee modeling.
    """
    pv = analytics.position_values(portfolio)
    if not pv["rows"]:
        return {"error": "No current holdings — nothing to rebalance."}
    total = pv["total_value"]
    current = {r["ticker"]: (r["weight"] or 0.0) for r in pv["rows"]}
    prices = {r["ticker"]: (r["price"] or 0.0) for r in pv["rows"]}

    if target is None or (isinstance(target, str) and target.strip() in ("", "equal_weight")):
        tw = {t: 1.0 / len(current) for t in current}
        target_label = "equal weight"
    elif isinstance(target, dict):
        cleaned = {
            str(t).upper(): float(w) for t, w in target.items() if float(w) >= 0
        }
        ssum = sum(cleaned.values())
        if ssum <= 0:
            return {"error": "Target weights must sum to a positive number."}
        tw = {t: w / ssum for t, w in cleaned.items()}
        target_label = "custom target"
    else:
        return {"error": f"Unrecognized target {target!r}; use 'equal_weight' or a ticker->weight mapping."}

    # Prices for target tickers we don't currently hold.
    new_tickers = sorted(t for t in tw if t not in prices)
    if new_tickers:
        px = get_prices(new_tickers, lookback_days=30)
        for t in new_tickers:
            s = px[t].dropna() if t in px.columns else None
            if s is None or s.empty:
                return {"error": f"No price data for target ticker {t}."}
            prices[t] = float(s.iloc[-1])

    min_trade_value = 0.005 * total
    trades: list[dict] = []
    drift: dict[str, float] = {}
    for t in sorted(set(current) | set(tw)):
        cur_w = current.get(t, 0.0)
        tgt_w = tw.get(t, 0.0)
        drift[t] = round((tgt_w - cur_w) * 100.0, 2)
        dv = (tgt_w - cur_w) * total
        if abs(dv) < min_trade_value or prices.get(t, 0.0) <= 0:
            continue
        trades.append(
            {
                "ticker": t,
                "action": "BUY" if dv > 0 else "SELL",
                "shares": round(abs(dv) / prices[t], 4),
                "est_value": round(abs(dv), 2),
            }
        )
    trades.sort(key=lambda x: -x["est_value"])

    return {
        "portfolio": (portfolio or "default").strip() or "default",
        "target": target_label,
        "total_value": round(total, 2),
        "current_weights": {t: round(w, 4) for t, w in current.items()},
        "target_weights": {t: round(w, 4) for t, w in tw.items()},
        "drift_pct": drift,
        "suggested_trades": trades,
        "min_trade_threshold_pct": 0.5,
        "note": (
            "A teaching aid for thinking about allocation drift — ignores taxes, "
            f"fees, and lot selection. {_DISCLAIMER}"
        ),
    }
