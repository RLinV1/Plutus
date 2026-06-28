"""Alert rules: pure evaluation + the one I/O function that snapshots the market.

``evaluate_rules`` is deliberately PURE (rules + market_state + now -> hits) so
every trigger/cooldown path is unit-testable without a network or a clock.
``build_market_state`` is the only function that touches market data, and
``run_alert_cycle`` is the orchestration step the API's background loop calls.

Rule types (threshold semantics):
- price_above / price_below: current price crosses a dollar level.
- pct_move: |today's change| >= threshold (in PERCENT, e.g. 3 = 3%).
- rsi_above / rsi_below: 14-day RSI crosses a level (0-100).
- drawdown: trailing-peak decline >= threshold percent (e.g. 10 = down 10%
  from its recent high over the cached window).
- news_volume: at least ``threshold`` relevant articles in the latest fetch.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta

from .. import config

log = logging.getLogger("portfolio_risk.portfolio.alerts")
if not log.handlers:  # stderr only — tools.py imports this package
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


def _fmt_pct(x: float) -> str:
    return f"{x * 100.0:+.2f}%"


def evaluate_rules(
    rules: list[dict], market_state: dict[str, dict], now: datetime
) -> list[dict]:
    """Pure: which enabled rules fire right now?

    ``market_state``: {ticker: {price, change_pct, rsi, drawdown_pct,
    relevant_news_24h}} — any field may be None/missing, in which case rules
    needing it simply don't fire. Cooldown: a rule stays quiet for
    ``cooldown_minutes`` after ``last_triggered_at``.
    """
    hits: list[dict] = []
    for r in rules:
        if not r.get("enabled", True):
            continue
        state = market_state.get((r.get("ticker") or "").upper())
        if not state:
            continue
        last = r.get("last_triggered_at")
        if last:
            try:
                last_dt = datetime.fromisoformat(str(last))
                if last_dt + timedelta(minutes=r.get("cooldown_minutes") or 0) > now:
                    continue  # cooling down
            except ValueError:
                pass

        kind = r["rule_type"]
        th = float(r["threshold"])
        t = r["ticker"].upper()
        price = state.get("price")
        title = body = None

        if kind == "price_above" and price is not None and price >= th:
            title = f"{t} above ${th:,.2f}"
            body = f"{t} is trading at ${price:,.2f}, at/above your ${th:,.2f} level."
        elif kind == "price_below" and price is not None and price <= th:
            title = f"{t} below ${th:,.2f}"
            body = f"{t} is trading at ${price:,.2f}, at/below your ${th:,.2f} level."
        elif kind == "pct_move":
            chg = state.get("change_pct")
            if chg is not None and abs(chg) * 100.0 >= th:
                title = f"{t} moved {_fmt_pct(chg)} today"
                body = f"{t} changed {_fmt_pct(chg)} today — beyond your {th:g}% trigger."
        elif kind in ("rsi_above", "rsi_below"):
            rsi = state.get("rsi")
            if rsi is not None and (
                (kind == "rsi_above" and rsi >= th)
                or (kind == "rsi_below" and rsi <= th)
            ):
                hot = "overbought" if kind == "rsi_above" else "oversold"
                title = f"{t} RSI at {rsi:.0f} ({hot})"
                body = f"{t}'s 14-day RSI is {rsi:.1f}, crossing your {th:g} level."
        elif kind == "drawdown":
            dd = state.get("drawdown_pct")
            if dd is not None and dd >= th:
                title = f"{t} down {dd:.1f}% from its recent high"
                body = (
                    f"{t} has fallen {dd:.1f}% from its trailing peak — beyond "
                    f"your {th:g}% drawdown trigger."
                )
        elif kind == "news_volume":
            n = state.get("relevant_news_24h")
            if n is not None and n >= th:
                title = f"Unusual news volume on {t} ({n} articles)"
                body = f"{n} relevant articles for {t} in the latest fetch (trigger: {th:g})."

        if title:
            hits.append(
                {
                    "rule_id": r["id"],
                    "portfolio_id": r.get("portfolio_id"),
                    "ticker": t,
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "payload": {
                        "rule_type": kind,
                        "threshold": th,
                        "price": price,
                        "change_pct": state.get("change_pct"),
                        "rsi": state.get("rsi"),
                        "drawdown_pct": state.get("drawdown_pct"),
                    },
                }
            )
    return hits


def build_market_state(
    tickers: list[str], need_indicators: set[str] | None = None
) -> dict[str, dict]:
    """The one I/O function: a per-ticker snapshot for rule evaluation.

    Quote (price + day change) for everyone — fetched CONCURRENTLY, since each
    live quote is a network round-trip and the tape now carries ~30 tickers;
    RSI/drawdown only for tickers a rule actually needs them for. In mock mode
    there are no live quotes — the last cached close stands in and the day
    change comes from the last two closes.
    """
    from concurrent.futures import ThreadPoolExecutor

    from ..data.market_data import get_news, get_prices, get_quote
    from ..risk import indicators

    need_indicators = need_indicators or set()
    out: dict[str, dict] = {}
    syms = sorted({(t or "").upper() for t in tickers if t})
    if not syms:
        return out

    try:
        prices = get_prices(syms, lookback_days=300)
    except Exception as exc:  # noqa: BLE001
        log.warning("alerts price load failed: %s", exc)
        prices = None

    def _quote_or_none(t: str):
        try:
            return get_quote(t)
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        quotes = dict(zip(syms, pool.map(_quote_or_none, syms)))

    for t in syms:
        state: dict = {
            "price": None,
            "change_pct": None,
            "rsi": None,
            "drawdown_pct": None,
            "relevant_news_24h": None,
        }
        series = None
        if prices is not None and t in prices.columns:
            series = prices[t].dropna()
        quote = quotes.get(t)
        if quote and quote.get("price"):
            state["price"] = float(quote["price"])
            state["change_pct"] = float(quote.get("change_pct") or 0.0)
        elif series is not None and len(series) >= 2:
            state["price"] = float(series.iloc[-1])
            state["change_pct"] = float(series.iloc[-1] / series.iloc[-2] - 1.0)

        if t in need_indicators and series is not None and len(series) >= 15:
            rsi = indicators.rsi(series, 14)
            state["rsi"] = None if rsi != rsi else float(rsi)
            peak = float(series.max())
            if peak > 0 and state["price"] is not None:
                state["drawdown_pct"] = max(
                    0.0, (1.0 - state["price"] / peak) * 100.0
                )
        if t in need_indicators:
            try:
                articles = get_news(t, limit=12)
                state["relevant_news_24h"] = sum(
                    1 for a in articles if a.get("relevant")
                )
            except Exception:  # noqa: BLE001
                pass
        out[t] = state
    return out


_INDICATOR_RULES = {"rsi_above", "rsi_below", "drawdown", "news_volume"}

# Always-on tape tickers: the names people expect scrolling on a terminal,
# merged with whatever the user actually holds or has alerts on.
_TAPE_DEFAULTS = [
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META",
    "TSLA", "AMD", "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "KO", "DIS",
]


def run_alert_cycle(now: datetime | None = None) -> dict:
    """One full pass: load rules + held tickers, snapshot the market, evaluate,
    persist notifications, stamp cooldowns. Returns what the caller should
    broadcast: {"quotes": {...}, "notifications": [...]}.
    """
    from . import analytics, store

    now = now or datetime.now()
    rules = store.list_alert_rules(enabled_only=True)

    held: set[str] = set()
    try:
        for pf in store.list_portfolios():
            pv_txns = store.list_transactions(pf["name"])
            from . import ledger

            held.update(ledger.held_tickers(pv_txns))
    except Exception as exc:  # noqa: BLE001
        log.warning("alerts: holdings lookup failed: %s", exc)

    rule_tickers = {r["ticker"] for r in rules}
    # Defaults + holdings + alert tickers, capped so a huge watchlist can't
    # hammer yfinance each cycle (quotes are fetched concurrently + cached).
    tickers = sorted(set(_TAPE_DEFAULTS) | held | rule_tickers)[:32]

    need_ind = {r["ticker"] for r in rules if r["rule_type"] in _INDICATOR_RULES}
    state = build_market_state(tickers, need_ind)
    hits = evaluate_rules(rules, state, now)

    saved: list[dict] = []
    for h in hits:
        try:
            n = store.add_notification(
                title=h["title"],
                body=h["body"],
                ticker=h["ticker"],
                kind=h["kind"],
                rule_id=h["rule_id"],
                portfolio_id=h.get("portfolio_id"),
                payload=h["payload"],
            )
            store.mark_rule_triggered(h["rule_id"], now)
            saved.append(n)
        except Exception as exc:  # noqa: BLE001
            log.warning("alerts: failed to persist notification: %s", exc)

    quotes = {
        t: {"price": s.get("price"), "change_pct": s.get("change_pct")}
        for t, s in state.items()
        if s.get("price") is not None
    }
    return {"quotes": quotes, "notifications": saved}
