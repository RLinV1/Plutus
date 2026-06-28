"""Core tool implementations — the single source of truth for the toolset.

The MCP server registers thin ``@mcp.tool()`` wrappers around these, the mock
agent dispatches to them directly, and tests call them straight. Every function
returns a plain JSON-serializable dict and converts errors into {"error": ...}.

These are the *beginner-friendly* stock-research tools: they compute real numbers
(volatility, beta, moving averages) under the hood but return them with
plain-English readings. Nothing here is investment advice.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import config
from .data import mock_data
from .data.loader import load_returns
from .data.market_data import (
    get_company_info,
    get_dividends,
    get_intel,
    get_movers,
    get_news,
    get_prices,
    get_quote,
)
from .data.market_data import get_fundamentals as _md_fundamentals
from .data.market_data import get_market_overview as _md_market_overview
from .risk import indicators, metrics

# Period name -> approximate number of trading days. "max" = all available.
_PERIODS: dict[str, int] = {
    "1d": 1, "1w": 5, "2w": 10, "1mo": 21, "3mo": 63, "6mo": 126,
    "1y": 252, "2y": 504, "5y": 1260, "max": 9000,
}


def _err(exc: Exception) -> dict:
    return {"error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# Small plain-English translators (deterministic thresholds — evals rely on them)
# --------------------------------------------------------------------------- #
def _movement_bucket(vol_annual: float) -> tuple[str, str]:
    """Translate annualized volatility (a fraction) into a friendly label."""
    if vol_annual != vol_annual:  # NaN
        return ("unknown", "Not enough price history to judge how much it moves.")
    if vol_annual < 0.15:
        return ("calm", "This stock is relatively steady — smaller day-to-day swings than most.")
    if vol_annual < 0.30:
        return ("average", "This stock has fairly typical ups and downs.")
    return ("bumpy", "This stock's price swings more than most — expect big ups and downs.")


def _sensitivity_bucket(beta: float) -> str:
    """Translate beta into how a stock tends to move relative to the market."""
    if beta != beta:  # NaN
        return "of unclear sensitivity to the market"
    if beta < 0.8:
        return "less sensitive than the market"
    if beta <= 1.2:
        return "about as sensitive as the market"
    if beta <= 1.5:
        return "more sensitive than the market"
    return "much more sensitive than the market"


def _human_money(n) -> str:
    if n is None:
        return "N/A"
    n = float(n)
    for label, div in (("trillion", 1e12), ("billion", 1e9), ("million", 1e6)):
        if abs(n) >= div:
            return f"${n / div:.1f} {label}"
    return f"${n:,.0f}"


def _maybe_float(x):
    """Cast to float, mapping NaN -> None so the result is clean JSON."""
    if x is None:
        return None
    f = float(x)
    return None if f != f else round(f, 4)


def _price_series(ticker: str, lookback_days: int) -> pd.Series:
    df = get_prices([ticker], lookback_days=lookback_days)
    col = ticker.upper()
    if col not in df.columns:
        raise ValueError(f"No price data available for {col}.")
    s = df[col].dropna()
    if s.empty:
        raise ValueError(f"No price data available for {col}.")
    return s


def _current(ticker: str, series: pd.Series) -> tuple[float, float]:
    """(current price, today's change as a fraction).

    Prefers a live yfinance quote (real-time-ish price + change vs the previous
    close); falls back to the last two daily closes from ``series`` (mock mode or
    if the live quote is unavailable).
    """
    quote = get_quote(ticker)
    if quote and quote.get("price"):
        return float(quote["price"]), float(quote.get("change_pct", 0.0))
    last = float(series.iloc[-1])
    change = float(series.iloc[-1] / series.iloc[-2] - 1.0) if len(series) >= 2 else 0.0
    return last, change


def _snapshot_row(ticker: str, lookback_days: int = 260) -> dict:
    """The shared building block for snapshot + compare: one stock's basics."""
    t = ticker.upper()
    info = get_company_info([t])[t]
    series = _price_series(t, lookback_days)
    price, change_pct = _current(t, series)
    vol = metrics.annualized_volatility(series.pct_change().dropna())
    movement, _ = _movement_bucket(vol)
    return {
        "ticker": t,
        "name": info.get("name", t),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry"),
        "description": info.get("description", ""),
        "website": info.get("website"),
        "country": info.get("country"),
        "employees": info.get("employees"),
        "current_price": round(price, 2),
        "change_pct": round(change_pct, 4),
        "market_cap": _maybe_float(info.get("market_cap")),
        "market_cap_human": _human_money(info.get("market_cap")),
        "pe_ratio": _maybe_float(info.get("pe_ratio")),
        "forward_pe": _maybe_float(info.get("forward_pe")),
        "dividend_yield": _maybe_float(info.get("dividend_yield")),
        "profit_margin": _maybe_float(info.get("profit_margin")),
        "revenue_growth": _maybe_float(info.get("revenue_growth")),
        "recommendation": info.get("recommendation"),
        "analyst_target": _maybe_float(info.get("analyst_target")),
        "analyst_count": info.get("analyst_count"),
        "movement": movement,
    }


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
def get_stock_snapshot(ticker: str) -> dict:
    """Plain-English overview of one stock: what the company does, its current
    price and latest move, market cap, and P/E ratio."""
    try:
        return _snapshot_row(ticker)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_price_performance(ticker: str, period: str = "1y") -> dict:
    """How a stock has performed over a period, with a plain-English movement label."""
    try:
        period = period.lower()
        days = _PERIODS.get(period, 252)
        series = _price_series(ticker, lookback_days=max(days + 5, 30))
        if len(series) < days + 1:
            days = len(series) - 1
        total_return = float(series.iloc[-1] / series.iloc[-(days + 1)] - 1.0)
        vol = metrics.annualized_volatility(series.pct_change().dropna())
        movement, detail = _movement_bucket(vol)
        return {
            "ticker": ticker.upper(),
            "period": period,
            "total_return": round(total_return, 4),
            "return_pct": round(total_return * 100.0, 2),
            "movement": movement,
            "movement_detail": detail,
            "volatility_annual_pct": round(vol * 100.0, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def _move_label(move_pct: float) -> str:
    """Plain-English size of a move (magnitude, direction-agnostic)."""
    m = abs(move_pct)
    if m < 1.0:
        return "barely moved"
    if m < 3.0:
        return "moved modestly"
    if m < 7.0:
        return "moved sharply"
    return "moved dramatically"


def _articles_in_window(articles: list[dict], start_dt) -> list[dict]:
    """Keep articles published on/after ``start_dt``. If none of the articles are
    dated (e.g. offline mock news), fall back to returning them all so the answer
    isn't empty; if some are dated but none fall in the window, return []."""
    dated_in_window: list[dict] = []
    undated: list[dict] = []
    any_dated = False
    for a in articles:
        p = a.get("published")
        if p:
            any_dated = True
            try:
                dt = pd.to_datetime(p, utc=True).tz_localize(None)
                if dt.date() >= start_dt.date():
                    dated_in_window.append(a)
            except Exception:  # noqa: BLE001
                undated.append(a)
        else:
            undated.append(a)
    if any_dated:
        return dated_in_window
    return undated


def explain_price_move(ticker: str, period: str = "1d") -> dict:
    """Why a stock moved: the size of the move over ``period`` plus the news from
    that same window, so the move can be explained by recent events.

    ``period`` is one of 1d, 1w, 1mo, 3mo, 6mo, 1y. Returns the move %, a plain
    movement label, the time window, and the candidate-driver headlines. The
    interpretation ("the drop tracks the earnings miss") is left to the caller.
    """
    try:
        t = ticker.upper()
        period = period.lower()
        if period in ("1d", "today", ""):
            series = _price_series(t, lookback_days=10)
            price, change = _current(t, series)
            move_pct = round(change * 100.0, 2)
            period = "1d"
            start_dt = series.index[-2] if len(series) >= 2 else series.index[-1]
        else:
            days = _PERIODS.get(period, 1)
            series = _price_series(t, lookback_days=max(days + 5, 30))
            if len(series) < days + 1:
                days = len(series) - 1
            start_dt = series.index[-(days + 1)]
            price = round(float(series.iloc[-1]), 2)
            move_pct = round((float(series.iloc[-1]) / float(series.iloc[-(days + 1)]) - 1.0) * 100.0, 2)
        end_dt = series.index[-1]

        articles = get_news(t, limit=12)
        window_articles = _articles_in_window(articles, start_dt)

        return {
            "ticker": t,
            "period": period,
            "move_pct": move_pct,
            "move_frac": round(move_pct / 100.0, 4),
            "direction": "up" if move_pct >= 0 else "down",
            "movement_label": _move_label(move_pct),
            "current_price": price,
            "window_start": str(start_dt.date()),
            "window_end": str(end_dt.date()),
            "articles": window_articles,
            "note": (
                "Headlines are from the same window as the move; they are candidate "
                "explanations, not confirmed causes."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def compare_stocks(tickers: list[str]) -> dict:
    """Side-by-side basics for a few stocks (name, sector, price, recent move,
    market cap, P/E, and how much each tends to move)."""
    try:
        tickers = [t.upper() for t in tickers]
        if len(tickers) < 2:
            return {"error": "Give me at least two tickers to compare."}
        # Each row is several yfinance round-trips; fetch tickers concurrently
        # (network-bound, so threads cut latency roughly linearly).
        with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as pool:
            rows = list(pool.map(_snapshot_row, tickers))
        return {"tickers": tickers, "rows": rows}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def explain_stock_risk(ticker: str, benchmark: str = config.DEFAULT_BENCHMARK) -> dict:
    """Explain in plain words how risky/volatile a stock tends to be, using its
    volatility and its beta versus the overall market."""
    try:
        returns_df, bench = load_returns([ticker], benchmark, config.DEFAULT_LOOKBACK_DAYS)
        col = ticker.upper()
        b = metrics.beta(returns_df[col], bench)
        vol = metrics.annualized_volatility(returns_df[col])
        sensitivity = _sensitivity_bucket(b)
        movement, movement_detail = _movement_bucket(vol)
        summary = (
            f"{col} tends to be {movement} and is {sensitivity}. {movement_detail} "
            f"This is educational information, not investment advice."
        )
        return {
            "ticker": col,
            "compared_to": f"the overall market ({benchmark.upper()})",
            "beta": round(float(b), 2),
            "sensitivity": sensitivity,
            "movement": movement,
            "volatility_annual_pct": round(vol * 100.0, 2),
            "plain_summary": summary,
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_technical_indicators(ticker: str) -> dict:
    """Common chart metrics for a stock: the 50- and 200-day moving averages
    (with a trend read), the 14-day RSI, and where it sits in its 52-week range."""
    try:
        series = _price_series(ticker, lookback_days=300)
        price, _ = _current(ticker, series)
        sma_50 = indicators.sma(series, 50)
        sma_200 = indicators.sma(series, 200)
        rsi = indicators.rsi(series, 14)
        low_52w, high_52w, position = indicators.fifty_two_week_range(series)

        if sma_200 == sma_200:  # not NaN
            trend = (
                "above its 200-day average (often read as a long-term uptrend)"
                if price > sma_200
                else "below its 200-day average (often read as a long-term downtrend)"
            )
        else:
            trend = "not enough history for a 200-day average yet"

        if rsi != rsi:
            rsi_reading = "unknown"
        elif rsi > 70:
            rsi_reading = "overbought (has risen quickly lately)"
        elif rsi < 30:
            rsi_reading = "oversold (has fallen quickly lately)"
        else:
            rsi_reading = "neutral"

        if position != position:
            range_reading = "unknown"
        elif position > 0.8:
            range_reading = "near its 52-week high"
        elif position < 0.2:
            range_reading = "near its 52-week low"
        else:
            range_reading = "in the middle of its 52-week range"

        return {
            "ticker": ticker.upper(),
            "price": round(price, 2),
            "sma_50": _maybe_float(sma_50),
            "sma_200": _maybe_float(sma_200),
            "trend": trend,
            "rsi": _maybe_float(rsi),
            "rsi_reading": rsi_reading,
            "low_52w": _maybe_float(low_52w),
            "high_52w": _maybe_float(high_52w),
            "range_position": _maybe_float(position),
            "range_reading": range_reading,
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_ticker_news(ticker: str, limit: int = 6) -> dict:
    """Recent news headlines for a stock (free, via Yahoo Finance).

    Returns {"ticker", "articles": [{title, publisher, url, published, summary}]}.
    Use this for "what's the latest news on X" and to ground commentary in recent
    events. Articles may be empty if no news is available.
    """
    try:
        articles = get_news(ticker, limit)
        return {"ticker": ticker.upper(), "articles": articles}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_watchlist_digest(tickers: list[str], period: str = "1d") -> dict:
    """A plain-English brief for a watchlist: each stock's recent move plus the
    headlines from that same window. Powers the daily digest (web + scheduled).

    Returns {"period", "items": [{ticker, move_pct, direction, movement_label,
    current_price, headlines:[{title, publisher, url}]}]}. Reuses
    ``explain_price_move`` so the move and its candidate-driver news stay in sync.
    """
    try:
        syms = [t.strip().upper() for t in tickers if t and t.strip()][:10]
        if not syms:
            return {"error": "Give me at least one ticker for the digest."}
        items: list[dict] = []
        for t in syms:
            mv = explain_price_move(t, period)
            if "error" in mv:
                items.append({"ticker": t, "error": mv["error"]})
                continue
            items.append(
                {
                    "ticker": t,
                    "period": mv["period"],
                    "move_pct": mv["move_pct"],
                    "direction": mv["direction"],
                    "movement_label": mv["movement_label"],
                    "current_price": mv["current_price"],
                    "headlines": [
                        {
                            "title": a.get("title", ""),
                            "publisher": a.get("publisher", ""),
                            "url": a.get("url", ""),
                        }
                        for a in mv.get("articles", [])[:3]
                    ],
                }
            )
        return {"period": period, "items": items}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_fundamentals(ticker: str) -> dict:
    """How the business is doing financially: revenue (with growth), margins,
    net income, free cash flow, and the debt load — with plain-English readings.
    """
    try:
        t = ticker.upper()
        out = _md_fundamentals(t)
        if "error" in out:
            return out

        growth = out.get("revenue_growth")
        if growth is None:
            growth_reading = "unknown"
        elif growth < 0:
            growth_reading = "shrinking"
        elif growth < 0.05:
            growth_reading = "roughly flat"
        elif growth < 0.15:
            growth_reading = "growing steadily"
        else:
            growth_reading = "growing quickly"

        margin = out.get("profit_margin")
        if margin is None:
            margin_reading = "unknown"
        elif margin < 0:
            margin_reading = "losing money"
        elif margin < 0.05:
            margin_reading = "thin profit margins"
        elif margin < 0.15:
            margin_reading = "moderate profit margins"
        else:
            margin_reading = "strongly profitable"

        dte = out.get("debt_to_equity")
        if dte is None:
            debt_reading = "unknown"
        elif dte < 0.5:
            debt_reading = "a light debt load"
        elif dte < 1.5:
            debt_reading = "a manageable debt load"
        else:
            debt_reading = "a heavy debt load"

        rev_txt = _human_money(out.get("revenue")) if out.get("revenue") else "unknown revenue"
        summary = (
            f"{t}'s revenue is {growth_reading}"
            + (f" ({growth * 100:+.1f}% year over year)" if growth is not None else "")
            + f" at {rev_txt} a year; the business is {margin_reading}"
            + (f" ({margin * 100:.1f}% net margin)" if margin is not None else "")
            + f" and carries {debt_reading}."
        )
        return {
            **out,
            "revenue_human": _human_money(out.get("revenue")) if out.get("revenue") else None,
            "net_income_human": _human_money(out.get("net_income")) if out.get("net_income") is not None else None,
            "free_cash_flow_human": _human_money(out.get("free_cash_flow")) if out.get("free_cash_flow") is not None else None,
            "growth_reading": growth_reading,
            "margin_reading": margin_reading,
            "debt_reading": debt_reading,
            "plain_summary": summary,
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_dividend_info(ticker: str) -> dict:
    """Whether a stock pays a dividend and what it yields: recent payments,
    trailing-12-month total, yield, and the next ex-dividend date."""
    try:
        t = ticker.upper()
        out = get_dividends(t)
        if "error" in out:
            return out
        y = out.get("dividend_yield")
        if not out.get("pays_dividend") or not y:
            reading = "doesn't currently pay a dividend"
        elif y < 0.015:
            reading = "pays a modest dividend"
        elif y < 0.035:
            reading = "pays a moderate dividend"
        elif y < 0.06:
            reading = "pays a high dividend"
        else:
            reading = (
                "pays a very high dividend — sometimes a warning sign, since a "
                "falling share price pushes the yield up"
            )
        summary = f"{t} {reading}"
        if y:
            summary += f", yielding about {y * 100:.2f}% a year (${out['ttm_dividend']:.2f} per share over the last 12 months)"
        summary += "."
        return {
            **out,
            "dividend_yield_pct": round(y * 100.0, 2) if y else 0.0,
            "reading": reading,
            "plain_summary": summary,
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_stock_intel(ticker: str) -> dict:
    """Street activity around a stock: the next earnings date, recent analyst
    upgrades/downgrades, insider buying/selling, and top institutional holders."""
    try:
        t = ticker.upper()
        out = get_intel(t)
        if "error" in out:
            return out
        insiders = out.get("insiders") or []
        buys = sum(1 for i in insiders if "purchase" in (i.get("transaction") or "").lower()
                   or "buy" in (i.get("transaction") or "").lower())
        sells = sum(1 for i in insiders if "sale" in (i.get("transaction") or "").lower()
                    or "sell" in (i.get("transaction") or "").lower())
        bits = []
        if out.get("next_earnings"):
            bits.append(f"{t}'s next earnings report is expected around {out['next_earnings']}")
        upgrades = out.get("upgrades") or []
        if upgrades:
            u = upgrades[0]
            bits.append(
                f"the most recent analyst action is {u.get('firm', 'a firm')} "
                f"moving to '{u.get('to_grade') or u.get('action')}'"
            )
        if insiders:
            bits.append(f"recent insider filings show {buys} buy(s) and {sells} sale(s)")
        summary = ("; ".join(bits) + "." if bits else f"No recent street activity found for {t}.")
        return {
            **out,
            "insider_buys": buys,
            "insider_sells": sells,
            "plain_summary": summary,
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_market_overview() -> dict:
    """How the overall market is doing today: S&P 500 / Nasdaq / Dow levels and
    day moves, the VIX 'fear gauge' with a mood reading, and the 10-year yield.
    """
    try:
        out = _md_market_overview()
        if "error" in out:
            return out
        vix = (out.get("vix") or {}).get("level")
        if vix is None:
            mood = "unknown"
        elif vix < 15:
            mood = "calm"
        elif vix < 22:
            mood = "normal"
        elif vix < 30:
            mood = "nervous"
        else:
            mood = "fearful"
        spx = next((i for i in out.get("indices", []) if i["symbol"] == "^GSPC"), None)
        bits = []
        if spx:
            direction = "up" if spx["change_pct"] >= 0 else "down"
            bits.append(f"The S&P 500 is {direction} {abs(spx['change_pct']) * 100:.2f}% today")
        if vix is not None:
            bits.append(
                f"the VIX — Wall Street's 'fear gauge' — sits at {vix:.1f}, "
                f"which reads as {mood}"
            )
        if out.get("ten_year_yield_pct") is not None:
            bits.append(f"the 10-year Treasury yields about {out['ten_year_yield_pct']:.2f}%")
        summary = (". ".join(s[0].upper() + s[1:] for s in bits) + "." if bits
                   else "Market data is unavailable right now.")
        return {**out, "mood": mood, "plain_summary": summary}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_market_movers(category: str = "gainers") -> dict:
    """Today's biggest movers across the market: 'gainers', 'losers', or the
    most 'active' (highest-volume) stocks."""
    try:
        cat = (category or "gainers").lower()
        if "los" in cat:
            cat = "losers"
        elif "activ" in cat:
            cat = "active"
        else:
            cat = "gainers"
        rows = get_movers(cat)
        out = {"category": cat, "rows": rows}
        if not rows:
            out["note"] = "Mover data is unavailable right now — try again shortly."
        return out
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def _is_filing_source(src: str) -> bool:
    s = (src or "").lower()
    return "edgar" in s or "sec" in s or "10-k" in s


def get_filing_risks(ticker: str, k: int = 6) -> dict:
    """The 'Risk Factors' a company discloses in its SEC 10-K filing, as cited
    excerpts ready to summarize in plain English.

    Offline (mock) mode returns deterministic synthetic risk factors. Live mode
    pulls the ticker's EDGAR-sourced chunks from the RAG store (ingest them with
    ``python -m portfolio_risk.rag.ingest --edgar <TICKER>``). Returns
    {"ticker", "source", "results": [{text, source, url, ...}], "note"}.
    """
    try:
        t = ticker.upper()
        if config.use_mock_data():
            results = mock_data.generate_filing_risks(t, k)
            return {
                "ticker": t,
                "source": f"MOCK 10-K Risk Factors ({t})",
                "results": results,
                "note": "Offline mock risk factors for demo/testing — not a real SEC filing.",
            }
        from .rag.search import search_knowledge as _search

        hits = _search(
            query="risk factors what could go wrong with the business",
            ticker=t,
            k=max(k * 2, 10),
        )
        filing = [h for h in hits if _is_filing_source(h.get("source", ""))]
        if not filing:
            return {
                "ticker": t,
                "results": [],
                "note": (
                    f"No SEC 10-K is ingested for {t} yet. Ingest it with: "
                    f"python -m portfolio_risk.rag.ingest --edgar {t}"
                ),
            }
        link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={t}&type=10-K"
        for h in filing:
            h["ticker"] = t
            if not h.get("url"):
                h["url"] = link
        return {
            "ticker": t,
            "source": f"SEC EDGAR 10-K ({t})",
            "results": filing[:k],
            "note": "Summarize these 10-K risk-factor excerpts in plain English, with citations.",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def search_knowledge(query: str, ticker: str = "", k: int = 4) -> dict:
    """Search the plain-English knowledge library: company profiles, "what to
    watch out for" notes, and investing-basics explainers (e.g. what a P/E ratio
    or 200-day moving average means). Returns cited snippets."""
    try:
        from .rag.search import search_knowledge as _search

        results = _search(query=query, ticker=ticker or None, k=k)
        if not results and ticker:
            results = _search(query=query, ticker=None, k=k)
        return {"results": results}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# --------------------------------------------------------------------------- #
# Portfolio tools (read-only: the agent can analyze the user's portfolio but
# can never modify it — transactions are written only through the REST API).
# The heavy lifting lives in portfolio/{analytics,scenarios}.py; imports are
# lazy so the stdio MCP server stays light to start.
# --------------------------------------------------------------------------- #
def get_portfolio_overview(portfolio: str = "default") -> dict:
    """The user's actual portfolio: holdings with cost basis and P&L, totals,
    sector allocation, and a plain-English concentration reading."""
    try:
        from .portfolio import analytics

        return analytics.overview(portfolio)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_portfolio_risk_report(
    portfolio: str = "default", benchmark: str = config.DEFAULT_BENCHMARK
) -> dict:
    """Portfolio-level risk: volatility, beta, Sharpe, max drawdown, VaR/CVaR
    (historical, parametric, Monte Carlo), correlations, and concentration —
    all for the portfolio as currently constituted."""
    try:
        from .portfolio import analytics

        return analytics.risk_report(portfolio, benchmark)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_portfolio_news(portfolio: str = "default", limit_per_ticker: int = 3) -> dict:
    """Recent headlines mapped to the user's holdings, largest positions first."""
    try:
        from .portfolio import analytics

        pv = analytics.position_values(portfolio)
        if not pv["rows"]:
            return {"portfolio": portfolio, "items": [], "note": "No current holdings."}
        items = []
        for r in pv["rows"]:
            arts = get_news(r["ticker"], max(1, int(limit_per_ticker)))
            items.append(
                {
                    "ticker": r["ticker"],
                    "weight": r["weight"],
                    "articles": arts,
                }
            )
        return {
            "portfolio": (portfolio or "default").strip() or "default",
            "items": items,
            "note": "Headlines are ordered by position size, biggest first.",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_portfolio_briefing(portfolio: str = "default", period: str = "1d") -> dict:
    """The proactive-advisor payload: every holding's move over ``period`` with
    same-window headlines, the portfolio's day P&L, the biggest mover,
    concentration warnings, and unread alert notifications."""
    try:
        from .portfolio import analytics
        from .portfolio import store as pstore

        ov = analytics.overview(portfolio)
        if "error" in ov:
            return ov
        if not ov["holdings"]:
            return {
                "portfolio": ov["portfolio"],
                "movers": [],
                "note": ov.get("note", "No current holdings."),
            }

        movers: list[dict] = []
        for row in ov["holdings"]:
            mv = explain_price_move(row["ticker"], period)
            if "error" in mv:
                movers.append({"ticker": row["ticker"], "error": mv["error"]})
                continue
            movers.append(
                {
                    "ticker": row["ticker"],
                    "weight": row["weight"],
                    "move_pct": mv["move_pct"],
                    "direction": mv["direction"],
                    "movement_label": mv["movement_label"],
                    "current_price": mv["current_price"],
                    "headlines": [
                        {
                            "title": a.get("title", ""),
                            "publisher": a.get("publisher", ""),
                            "url": a.get("url", ""),
                        }
                        for a in mv.get("articles", [])[:2]
                    ],
                }
            )
        ranked = [m for m in movers if "move_pct" in m]
        ranked.sort(key=lambda m: -abs(m["move_pct"]))

        warnings = list(ov.get("warnings", []))
        top = ov.get("top_position") or {}
        if (top.get("weight") or 0) > 0.25:
            warnings.append(
                f"{top['ticker']} is {top['weight'] * 100:.0f}% of the portfolio — "
                "a single position dominates."
            )
        if (ov.get("hhi") or 0) > 0.30:
            warnings.append(
                "Overall concentration is high (HHI "
                f"{ov['hhi']:.2f}); the portfolio behaves like very few bets."
            )

        try:
            notifications = pstore.list_notifications(unread_only=True, limit=5)
        except Exception:  # noqa: BLE001
            notifications = []

        return {
            "portfolio": ov["portfolio"],
            "period": period,
            "totals": ov["totals"],
            "movers": movers,
            "biggest_mover": ranked[0] if ranked else None,
            "concentration": ov.get("concentration"),
            "warnings": warnings,
            "unread_notifications": notifications,
            "note": (
                "Headlines come from the same window as each move; they are "
                "candidate explanations, not confirmed causes. Educational, not "
                "personalized advice."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def run_portfolio_scenario(
    scenario: str = "covid_2020", portfolio: str = "default"
) -> dict:
    """Stress-test the portfolio against a named historical crisis using a
    beta-scaled approximation. ``scenario`` of 'list' returns the catalog."""
    try:
        from .portfolio import scenarios as scen

        if (scenario or "").strip().lower() in ("list", "?", ""):
            return {"scenarios": scen.list_scenarios()}
        return scen.stress_test(portfolio, scenario)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def simulate_trade(
    side: str, ticker: str, shares: float, portfolio: str = "default"
) -> dict:
    """Hypothetical trade: portfolio risk metrics before vs after. READ-ONLY —
    never records a transaction."""
    try:
        from .portfolio import scenarios as scen

        return scen.what_if_trade(portfolio, side, ticker, shares)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def get_rebalance_plan(portfolio: str = "default", target: str = "equal_weight") -> dict:
    """Suggested trades toward a target allocation. ``target`` is
    'equal_weight' or a JSON object string like '{"AAPL": 0.4, "SPY": 0.6}'."""
    try:
        import json as _json

        from .portfolio import scenarios as scen

        parsed = target
        if isinstance(target, str) and target.strip().startswith("{"):
            parsed = _json.loads(target)
        return scen.rebalance_plan(portfolio, parsed)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
