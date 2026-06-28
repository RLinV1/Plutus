"""Market data access: deterministic mock by default, live yfinance opt-in.

The default (``USE_MOCK_DATA=1``) returns synthetic prices and never touches the
network — ideal for offline runs, tests, and reproducible evals. Set
``USE_MOCK_DATA=0`` to pull real adjusted-close data from yfinance, cached to
parquet so repeat calls are offline.

IMPORTANT: this module must never write to stdout — the MCP server speaks
JSON-RPC over stdout and any stray print corrupts the stream. We log to stderr.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time

import pandas as pd

from .. import cache, config
from . import mock_data

log = logging.getLogger("portfolio_risk.market_data")
if not log.handlers:  # stderr only
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


class DataUnavailableError(RuntimeError):
    pass


# How stale cached data may be before we refetch. Prices must stay current, so a
# few calendar days (covers weekends/holidays); company info changes slowly.
_MAX_PRICE_AGE_DAYS = 4
_MAX_INFO_AGE_DAYS = 2


def _days_old(when) -> float:
    """Calendar days between ``when`` and today (local)."""
    try:
        last = pd.Timestamp(when).normalize()
        return (pd.Timestamp.now().normalize() - last).days
    except Exception:  # pragma: no cover - defensive
        return float("inf")


def _cache_path(ticker: str):
    return config.PRICE_CACHE_DIR / f"{ticker.upper()}.parquet"


def _read_cache(ticker: str) -> pd.Series | None:
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df["adj_close"]
    except Exception as exc:  # pragma: no cover - corrupt cache is rare
        log.warning("Failed to read cache for %s: %s", ticker, exc)
        return None


def _write_cache(ticker: str, series: pd.Series) -> None:
    config.ensure_dirs()
    pd.DataFrame({"adj_close": series}).to_parquet(_cache_path(ticker))


def _download_yf(tickers: list[str], period_days: int) -> pd.DataFrame:
    """Fetch adjusted close from yfinance with retry/backoff. stderr-only logs."""
    import yfinance as yf  # imported lazily so mock mode needs no yfinance

    # Very large lookbacks mean "all available history" — yfinance only accepts
    # the literal "max" for that, not an arbitrary day count.
    period = "max" if period_days >= 3000 else f"{max(period_days + 10, 30)}d"
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = yf.download(
                tickers,
                period=period,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if raw is None or raw.empty:
                raise DataUnavailableError("yfinance returned an empty frame")
            # Normalize single- vs multi-ticker column shapes to a flat frame.
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw["Close"]
            else:
                close = raw[["Close"]].rename(columns={"Close": tickers[0]})
            return close.dropna(how="all")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("yfinance attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
    raise DataUnavailableError(f"yfinance failed after retries: {last_exc}")


def get_prices(
    tickers: list[str],
    lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Adjusted-close matrix (index=dates, cols=tickers).

    Mock mode returns synthetic prices. Live mode reads the parquet cache and
    hits yfinance only for tickers missing from cache (or when force_refresh).
    """
    tickers = [t.upper() for t in tickers]
    if not tickers:
        raise DataUnavailableError("No tickers requested.")

    if config.use_mock_data():
        # Cap synthetic history so an "all time" request doesn't generate decades.
        return mock_data.generate_prices(tickers, days=min(lookback_days, 3024))

    # Live path with caching.
    cached: dict[str, pd.Series] = {}
    missing: list[str] = []
    for t in tickers:
        series = None if force_refresh else _read_cache(t)
        fresh = (
            series is not None
            and len(series) >= lookback_days * 0.5
            and _days_old(series.index.max()) <= _MAX_PRICE_AGE_DAYS
        )
        if fresh:
            cached[t] = series
        else:
            missing.append(t)

    if missing:
        fetched = _download_yf(missing, lookback_days)
        for t in missing:
            if t in fetched.columns:
                s = fetched[t].dropna()
                cached[t] = s
                _write_cache(t, s)
            else:
                log.warning("No data returned for %s; dropping.", t)

    usable = {t: cached[t] for t in tickers if t in cached}
    if not usable:
        raise DataUnavailableError(f"No usable price data for {tickers}.")
    df = pd.DataFrame(usable).sort_index()
    return df.tail(lookback_days)


def _ohlc_cache_path(ticker: str):
    return config.PRICE_CACHE_DIR / f"{ticker.upper()}.ohlc.parquet"


def get_ohlc(
    ticker: str,
    lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Daily OHLCV frame (open/high/low/close/volume) for candlestick charts.

    Mock mode derives deterministic OHLCV from the synthetic closes. Live mode
    downloads with ``auto_adjust=True`` (so OHLC are consistently adjusted, like
    ``get_prices``) into a SEPARATE ``.ohlc.parquet`` cache so the existing
    close-only cache and its consumers are untouched.
    """
    t = ticker.upper()
    if config.use_mock_data():
        return mock_data.generate_ohlc(t, days=min(lookback_days, 3024))

    path = _ohlc_cache_path(t)
    if not force_refresh and path.exists():
        try:
            df = pd.read_parquet(path)
            if (
                len(df) >= lookback_days * 0.5
                and _days_old(df.index.max()) <= _MAX_PRICE_AGE_DAYS
            ):
                return df.tail(lookback_days)
        except Exception as exc:  # pragma: no cover - corrupt cache is rare
            log.warning("Failed to read OHLC cache for %s: %s", t, exc)

    import yfinance as yf  # lazy: mock mode needs no yfinance

    period = "max" if lookback_days >= 3000 else f"{max(lookback_days + 10, 30)}d"
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = yf.download(
                t, period=period, auto_adjust=True, progress=False, threads=False
            )
            if raw is None or raw.empty:
                raise DataUnavailableError("yfinance returned an empty frame")
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[["Open", "High", "Low", "Close", "Volume"]].rename(
                columns=str.lower
            )
            df["volume"] = df["volume"].fillna(0.0)
            df = df.dropna(subset=["close"])
            config.ensure_dirs()
            df.to_parquet(path)
            return df.tail(lookback_days)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("yfinance OHLC attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
    raise DataUnavailableError(f"yfinance OHLC failed after retries: {last_exc}")


# Intraday candles. yfinance has no 10m interval, so 10m is resampled from 5m.
# Cached briefly (the data changes all session) in the shared JSON cache, not
# parquet — these frames are small and stale within a minute anyway.
_INTRADAY_TTL_SEC = 60.0
_YF_INTRADAY = {"1m": "1m", "10m": "5m", "1h": "1h"}
_OHLC_COLS = ["open", "high", "low", "close", "volume"]


def get_intraday_ohlc(
    ticker: str, period: str = "1d", interval: str = "1h"
) -> pd.DataFrame:
    """Intraday OHLCV bars for the chart.

    ``period`` is '1d' (last session) or '1w' (last 5 sessions); ``interval``
    is '1m', '10m', or '1h'. Mock mode returns a deterministic synthetic
    session.
    """
    t = ticker.upper()
    period = "1w" if period in ("1w", "5d", "1wk") else "1d"
    if interval not in _YF_INTRADAY:
        interval = "1h"

    if config.use_mock_data():
        return mock_data.generate_intraday_ohlc(t, period, interval)

    key = f"iohlc:v1:{t}:{period}:{interval}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return pd.DataFrame(
            cached["rows"], columns=_OHLC_COLS, index=pd.to_datetime(cached["index"])
        )

    import yfinance as yf

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = yf.download(
                t,
                period="5d" if period == "1w" else "1d",
                interval=_YF_INTRADAY[interval],
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if raw is None or raw.empty:
                raise DataUnavailableError("yfinance returned an empty frame")
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[["Open", "High", "Low", "Close", "Volume"]].rename(columns=str.lower)
            if interval == "10m":
                df = df.resample("10min").agg(
                    {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
                )
            df["volume"] = df["volume"].fillna(0.0)
            df = df.dropna(subset=["close"])
            cache.cache_set_json(
                key,
                {"index": [str(i) for i in df.index], "rows": df[_OHLC_COLS].values.tolist()},
                _INTRADAY_TTL_SEC,
            )
            return df
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("yfinance intraday attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1.0 * (attempt + 1))
    raise DataUnavailableError(f"yfinance intraday failed after retries: {last_exc}")


# --------------------------------------------------------------------------- #
# Ticker intel: earnings date, analyst actions, insiders, institutions.
# UI-only enrichment (not an agent tool); cached ~6h; every section degrades
# to [] independently because each yfinance endpoint fails on its own schedule.
# --------------------------------------------------------------------------- #
_INTEL_TTL_SEC = 6 * 3600.0


def _ts_str(x) -> str | None:
    try:
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def get_intel(ticker: str) -> dict:
    """Earnings calendar + analyst rating changes + insider transactions +
    top institutional holders for one ticker."""
    t = ticker.upper()
    if config.use_mock_data():
        return mock_data.generate_intel(t)

    key = f"intel:v1:{t}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached

    import yfinance as yf

    tk = yf.Ticker(t)
    out: dict = {"ticker": t}

    # .calendar needs no extra deps (unlike .earnings_dates, which wants lxml)
    # and carries the dividend dates too.
    try:
        cal = tk.calendar or {}
        earnings = cal.get("Earnings Date") or []
        out["next_earnings"] = _ts_str(earnings[0]) if earnings else None
        out["ex_dividend_date"] = _ts_str(cal.get("Ex-Dividend Date"))
    except Exception:  # noqa: BLE001
        out["next_earnings"] = None
        out["ex_dividend_date"] = None

    upgrades: list[dict] = []
    try:
        ud = tk.upgrades_downgrades.sort_index(ascending=False).head(6)
        for when, row in ud.iterrows():
            upgrades.append(
                {
                    "date": _ts_str(when),
                    "firm": str(row.get("Firm", "")),
                    "action": str(row.get("Action", "")),
                    "from_grade": str(row.get("FromGrade", "") or ""),
                    "to_grade": str(row.get("ToGrade", "") or ""),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    out["upgrades"] = upgrades

    insiders: list[dict] = []
    try:
        it = tk.insider_transactions.head(6)
        for _, row in it.iterrows():
            d = row.to_dict()
            shares = d.get("Shares")
            value = d.get("Value")
            insiders.append(
                {
                    "date": _ts_str(d.get("Start Date") or d.get("Date")),
                    "insider": str(d.get("Insider", "")),
                    "position": str(d.get("Position", "") or ""),
                    "transaction": str(d.get("Transaction", "") or d.get("Text", "") or ""),
                    "shares": float(shares) if shares == shares and shares is not None else None,
                    "value": float(value) if value == value and value is not None else None,
                }
            )
    except Exception:  # noqa: BLE001
        pass
    out["insiders"] = insiders

    holders: list[dict] = []
    try:
        ih = tk.institutional_holders.head(5)
        for _, row in ih.iterrows():
            d = row.to_dict()
            pct = d.get("pctHeld", d.get("% Out"))
            shares = d.get("Shares")
            holders.append(
                {
                    "holder": str(d.get("Holder", "")),
                    "pct_held": float(pct) if pct == pct and pct is not None else None,
                    "shares": float(shares) if shares == shares and shares is not None else None,
                    "reported": _ts_str(d.get("Date Reported")),
                }
            )
    except Exception:  # noqa: BLE001
        pass
    out["institutional"] = holders

    cache.cache_set_json(key, out, _INTEL_TTL_SEC)
    return out


# --------------------------------------------------------------------------- #
# Fundamentals, dividends, market overview, movers — all free/keyless yfinance
# endpoints. Each is mock-twinned, cached, and degrades to None/[] per field
# because every yfinance endpoint fails on its own schedule.
# --------------------------------------------------------------------------- #
_FUND_TTL_SEC = 24 * 3600.0   # statements change quarterly
_DIV_TTL_SEC = 24 * 3600.0
_MKT_TTL_SEC = 60.0           # index levels move all day
_MOVERS_TTL_SEC = 300.0


def _stmt_val(df, row: str, col: int = 0):
    """One cell of a yfinance financial-statement frame, or None."""
    try:
        v = df.loc[row].iloc[col]
        return float(v) if v == v and v is not None else None
    except Exception:  # noqa: BLE001
        return None


def get_fundamentals(ticker: str) -> dict:
    """Key lines from the latest annual statements: revenue (+growth), margins,
    net income, free cash flow, debt/cash/equity."""
    t = ticker.upper()
    if config.use_mock_data():
        return mock_data.generate_fundamentals(t)

    key = f"fund:v1:{t}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached

    import yfinance as yf

    tk = yf.Ticker(t)
    out: dict = {"ticker": t, "period": None}

    revenue = revenue_prior = net_income = gross_profit = None
    try:
        inc = tk.income_stmt
        out["period"] = _ts_str(inc.columns[0])
        revenue = _stmt_val(inc, "Total Revenue")
        revenue_prior = _stmt_val(inc, "Total Revenue", 1)
        net_income = _stmt_val(inc, "Net Income")
        gross_profit = _stmt_val(inc, "Gross Profit")
    except Exception:  # noqa: BLE001
        pass
    out["revenue"] = revenue
    out["revenue_prior"] = revenue_prior
    out["revenue_growth"] = (
        round(revenue / revenue_prior - 1.0, 4) if revenue and revenue_prior else None
    )
    out["net_income"] = net_income
    out["profit_margin"] = round(net_income / revenue, 4) if net_income is not None and revenue else None
    out["gross_margin"] = round(gross_profit / revenue, 4) if gross_profit is not None and revenue else None

    total_debt = cash = equity = None
    try:
        bal = tk.balance_sheet
        total_debt = _stmt_val(bal, "Total Debt")
        cash = _stmt_val(bal, "Cash And Cash Equivalents")
        equity = _stmt_val(bal, "Stockholders Equity")
    except Exception:  # noqa: BLE001
        pass
    out["total_debt"] = total_debt
    out["cash"] = cash
    out["equity"] = equity
    out["debt_to_equity"] = round(total_debt / equity, 4) if total_debt is not None and equity else None

    try:
        out["free_cash_flow"] = _stmt_val(tk.cashflow, "Free Cash Flow")
    except Exception:  # noqa: BLE001
        out["free_cash_flow"] = None

    cache.cache_set_json(key, out, _FUND_TTL_SEC)
    return out


def get_dividends(ticker: str) -> dict:
    """Dividend history: recent payments, trailing-12-month total + yield, and
    the next ex-dividend date."""
    t = ticker.upper()
    if config.use_mock_data():
        return mock_data.generate_dividends(t)

    key = f"div:v1:{t}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached

    import yfinance as yf

    tk = yf.Ticker(t)
    recent: list[dict] = []
    ttm = 0.0
    try:
        s = tk.dividends
        if s is not None and len(s):
            idx = s.index.tz_localize(None) if getattr(s.index, "tz", None) else s.index
            s = pd.Series(s.to_numpy(), index=idx).dropna()
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
            ttm = float(s[s.index >= cutoff].sum())
            recent = [
                {"date": _ts_str(d), "amount": round(float(a), 4)}
                for d, a in list(s.tail(8).items())[::-1]
            ]
    except Exception as exc:  # noqa: BLE001
        log.warning("Dividend lookup failed for %s: %s", t, exc)

    div_yield = None
    if ttm > 0:
        try:
            quote = get_quote(t)
            price = quote["price"] if quote else float(get_prices([t], 30)[t].iloc[-1])
            div_yield = round(ttm / price, 4) if price else None
        except Exception:  # noqa: BLE001
            pass

    ex_div = None
    try:
        ex_div = _ts_str((tk.calendar or {}).get("Ex-Dividend Date"))
    except Exception:  # noqa: BLE001
        pass

    out = {
        "ticker": t,
        "pays_dividend": ttm > 0,
        "dividend_yield": div_yield,
        "ttm_dividend": round(ttm, 4),
        "recent": recent,
        "ex_dividend_date": ex_div,
    }
    cache.cache_set_json(key, out, _DIV_TTL_SEC)
    return out


_INDICES = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq Composite"),
    ("^DJI", "Dow Jones Industrial Average"),
]


def get_market_overview() -> dict:
    """Index levels + day change for the big three, the VIX, and the 10-year
    Treasury yield (^TNX quotes the yield × 10)."""
    if config.use_mock_data():
        return mock_data.generate_market_overview()

    key = "mkt:v1"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached

    indices = []
    for sym, name in _INDICES:
        q = get_quote(sym)
        if q:
            indices.append(
                {
                    "symbol": sym,
                    "name": name,
                    "level": round(q["price"], 2),
                    "change_pct": round(q.get("change_pct") or 0.0, 4),
                }
            )
    vix_q = get_quote("^VIX")
    vix = (
        {"level": round(vix_q["price"], 2), "change_pct": round(vix_q.get("change_pct") or 0.0, 4)}
        if vix_q
        else None
    )
    # ^TNX classically quotes the yield × 10 (45.2 => 4.52%), but some yfinance
    # versions return the yield directly — normalize either way.
    tnx_q = get_quote("^TNX")
    ten_year = None
    if tnx_q:
        level = tnx_q["price"]
        ten_year = round(level / 10.0 if level > 20 else level, 2)

    out = {"indices": indices, "vix": vix, "ten_year_yield_pct": ten_year}
    if indices:  # don't pin an empty answer for a minute
        cache.cache_set_json(key, out, _MKT_TTL_SEC)
    return out


_SCREEN_KEYS = {"gainers": "day_gainers", "losers": "day_losers", "active": "most_actives"}


def get_movers(category: str = "gainers") -> list[dict]:
    """Today's biggest gainers / losers / most-active stocks via Yahoo's free
    predefined screeners. Returns [] if the screener endpoint is unavailable."""
    cat = (category or "gainers").lower()
    if "los" in cat:
        cat = "losers"
    elif "activ" in cat:
        cat = "active"
    else:
        cat = "gainers"

    if config.use_mock_data():
        return mock_data.generate_movers(cat)

    key = f"movers:v1:{cat}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached

    rows: list[dict] = []
    try:
        import yfinance as yf

        res = yf.screen(_SCREEN_KEYS[cat]) or {}
        for q in (res.get("quotes") or [])[:10]:
            sym = q.get("symbol")
            price = q.get("regularMarketPrice")
            chg = q.get("regularMarketChangePercent")
            if not sym or price is None:
                continue
            rows.append(
                {
                    "ticker": str(sym).upper(),
                    "name": q.get("shortName") or q.get("longName") or str(sym).upper(),
                    "price": round(float(price), 2),
                    # Yahoo reports percent units; normalize to a fraction like
                    # every other change_pct in this codebase.
                    "change_pct": round(float(chg) / 100.0, 4) if chg is not None else None,
                    "volume": float(q["regularMarketVolume"]) if q.get("regularMarketVolume") else None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Movers screen failed for %s: %s", cat, exc)
    if rows:
        cache.cache_set_json(key, rows, _MOVERS_TTL_SEC)
    return rows


def _parse_news_item(item: dict) -> dict | None:
    """Normalize a yfinance news item (handles old flat + new nested schemas)."""
    content = item.get("content") if isinstance(item, dict) else None
    related = item.get("relatedTickers") or []
    if isinstance(content, dict):
        title = content.get("title")
        summary = content.get("summary") or content.get("description") or ""
        publisher = (content.get("provider") or {}).get("displayName") or ""
        url = (
            (content.get("canonicalUrl") or {}).get("url")
            or (content.get("clickThroughUrl") or {}).get("url")
            or ""
        )
        published = content.get("pubDate") or content.get("displayTime") or ""
        related = related or content.get("relatedTickers") or []
    else:
        title = item.get("title")
        summary = item.get("summary", "")
        publisher = item.get("publisher", "")
        url = item.get("link", "")
        ts = item.get("providerPublishTime")
        published = ""
        if ts:
            try:
                published = pd.to_datetime(int(ts), unit="s").isoformat()
            except Exception:  # noqa: BLE001
                published = str(ts)
    if not title:
        return None
    return {
        "title": title,
        "publisher": publisher,
        "url": url,
        "published": published,
        "summary": (summary or "")[:300],
        "tickers": [str(x).upper() for x in related],
    }


# Words to ignore when deriving company-name keywords for news matching.
_CORP_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ltd",
    "limited", "holdings", "group", "the", "and", "lp", "sa", "ag", "nv", "trust",
    "etf", "fund", "index", "class", "ord", "shares", "technologies", "international",
}


def _news_keywords(name: str, symbol: str) -> set[str]:
    """Deterministic identifiers for a ticker: the symbol + significant name words."""
    kws: set[str] = {symbol.lower()}
    for w in re.findall(r"[A-Za-z]+", name.lower()):
        if w not in _CORP_STOPWORDS and len(w) >= 3:
            kws.add(w)
    return kws


def _news_relevant(article: dict, symbol: str, keywords: set[str]) -> bool:
    """True if an article is actually about ``symbol`` — no AI, fully deterministic.

    Trusts Yahoo's own ``relatedTickers`` tagging when present; otherwise matches
    the ticker symbol (2+ chars) or a company-name keyword in the title/summary.
    """
    sym = symbol.upper()
    related = article.get("tickers") or []
    if related:
        return sym in related
    # Match the TITLE only — summaries of generic market articles mention many
    # companies in passing, which produces false positives.
    title = article.get("title", "").lower()
    if len(sym) >= 2 and re.search(rf"\b{re.escape(sym.lower())}\b", title):
        return True
    return any(k in title for k in keywords if k != symbol.lower())


# Shared, all-users news cache (deterministic vetting; no AI involved).
_NEWS_TTL_SEC = 300.0  # 5 minutes


def get_news(ticker: str, limit: int = 12) -> list[dict]:
    """Recent headlines for a ticker, ranked so the most relevant come first.

    Mock mode returns deterministic synthetic headlines. Live mode pulls free,
    keyless news from yfinance, tags each article with ``relevant`` (Yahoo's
    relatedTickers tag, or a ticker/company-name match in the title — no AI),
    and orders relevant articles first while keeping the rest so the list isn't
    sparse. Results are cached for all users for a few minutes.
    """
    if config.use_mock_data():
        return mock_data.generate_news(ticker, limit)

    t = ticker.upper()
    key = f"news:v1:{t}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached[:limit]

    try:
        import yfinance as yf

        raw = yf.Ticker(t).news or []
        parsed = [p for p in (_parse_news_item(it) for it in raw) if p]
        try:
            name = get_company_info([t])[t].get("name", t)
        except Exception:  # noqa: BLE001
            name = t
        keywords = _news_keywords(name, t)
        relevant: list[dict] = []
        other: list[dict] = []
        for a in parsed:
            a["relevant"] = _news_relevant(a, t, keywords)
            (relevant if a["relevant"] else other).append(a)
        ordered = relevant + other  # relevant first, but keep the rest

        # Write-through to Postgres (deduped) when the DB is configured.
        try:
            from .. import db

            if db.db_enabled():
                db.upsert_news(t, ordered)
        except Exception as exc:  # noqa: BLE001
            log.warning("news DB write failed for %s: %s", t, exc)

        cache.cache_set_json(key, ordered, _NEWS_TTL_SEC)
        return ordered[:limit]
    except Exception as exc:  # noqa: BLE001
        log.warning("News lookup failed for %s: %s", ticker, exc)
        # Fall back to persisted history if the DB has any.
        try:
            from .. import db

            if db.db_enabled():
                rows = db.recent_news(t, limit)
                if rows:
                    return rows
        except Exception:  # noqa: BLE001
            pass
        return []


# Shared quote cache so repeated reads of the same ticker within a few seconds
# (e.g. snapshot + technicals on one page load) hit the network once.
_QUOTE_TTL_SEC = 20.0


def get_quote(ticker: str) -> dict | None:
    """Live near-real-time quote from yfinance ``fast_info``.

    Returns ``{"price", "previous_close", "change_pct"}`` (today's move vs the
    previous close), or ``None`` in mock mode or if the lookup fails — callers
    then fall back to the last cached daily close. Memoized (Redis or in-process).
    """
    if config.use_mock_data():
        return None
    t = ticker.upper()
    key = f"q:v1:{t}"
    cached = cache.cache_get_json(key)
    if cached is not None:
        return cached
    result: dict | None = None
    try:
        import yfinance as yf

        fi = yf.Ticker(t).fast_info

        def pick(*keys):
            for k in keys:
                v = None
                if hasattr(fi, "get"):
                    try:
                        v = fi.get(k)
                    except Exception:  # noqa: BLE001
                        v = None
                if v is None:
                    v = getattr(fi, k, None)
                if v not in (None, 0):
                    return float(v)
            return None

        price = pick("lastPrice", "last_price")
        prev = pick("previousClose", "previous_close", "regularMarketPreviousClose")
        if price is not None:
            change = (price / prev - 1.0) if prev else 0.0
            result = {"price": price, "previous_close": prev, "change_pct": change}
    except Exception as exc:  # noqa: BLE001
        log.warning("Live quote failed for %s: %s", t, exc)
        result = None
    if result is not None:
        cache.cache_set_json(key, result, _QUOTE_TTL_SEC)
    return result


# --------------------------------------------------------------------------- #
# Company info (name / sector / description / market cap / P/E)
# --------------------------------------------------------------------------- #
def _info_cache_path(ticker: str):
    return config.PRICE_CACHE_DIR / f"{ticker.upper()}.info.json"


def _read_info_cache(ticker: str) -> dict | None:
    path = _info_cache_path(ticker)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - corrupt cache is rare
        log.warning("Failed to read info cache for %s: %s", ticker, exc)
        return None


def _write_info_cache(ticker: str, info: dict) -> None:
    config.ensure_dirs()
    stamped = {**info, "_cached_at": pd.Timestamp.now().isoformat()}
    _info_cache_path(ticker).write_text(json.dumps(stamped), encoding="utf-8")


def _short_desc(text: str, limit: int = 280) -> str:
    """First couple of sentences of the business summary — the UI wants a
    blurb, not the 10-K intro. Cuts at a sentence boundary when possible."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    best = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if best > 80:
        return cut[: best + 1]
    return cut.rsplit(" ", 1)[0] + "…"


def _opt_float(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _download_info_yf(ticker: str) -> dict:
    """Fetch company info from yfinance ``.info``. Every field is guarded with
    .get because the endpoint is frequently partial. stderr-only logs."""
    import yfinance as yf  # imported lazily so mock mode needs no yfinance

    raw = yf.Ticker(ticker).info or {}
    description = _short_desc((raw.get("longBusinessSummary") or "").strip())
    if not description:
        # yfinance .info frequently comes back partial; for well-known tickers
        # fall back to the curated blurb instead of "No description available."
        description = mock_data.curated_description(ticker) or ""
    # Current yfinance reports dividendYield in PERCENT (AAPL ~0.37 == 0.37%).
    # Convert to a fraction; refuse implausible values rather than display them.
    dy = _opt_float(raw.get("dividendYield"))
    if dy is not None:
        dy = dy / 100.0
        if dy > 0.25:  # >25% yield — almost certainly a unit mix-up
            dy = None
    return {
        "ticker": ticker.upper(),
        "name": raw.get("shortName") or raw.get("longName") or ticker.upper(),
        "sector": raw.get("sector") or "Unknown",
        "industry": raw.get("industry") or None,
        "description": description or "No description available.",
        "website": raw.get("website") or None,
        "country": raw.get("country") or None,
        "employees": raw.get("fullTimeEmployees"),
        "market_cap": raw.get("marketCap"),
        "pe_ratio": raw.get("trailingPE"),
        "forward_pe": _opt_float(raw.get("forwardPE")),
        "dividend_yield": dy,
        "profit_margin": _opt_float(raw.get("profitMargins")),
        "revenue_growth": _opt_float(raw.get("revenueGrowth")),
        "recommendation": raw.get("recommendationKey") or None,
        "analyst_target": _opt_float(raw.get("targetMeanPrice")),
        "analyst_count": raw.get("numberOfAnalystOpinions"),
    }


def _info_is_empty(info: dict, ticker: str) -> bool:
    """True when a live lookup returned essentially nothing — a profile that's
    just the ticker echoed back. Caching that would pin the failure for days."""
    return (
        info.get("name") in (None, "", ticker.upper())
        and info.get("market_cap") is None
        and info.get("description") in ("", "No description available.")
    )


def get_company_info(
    tickers: list[str], force_refresh: bool = False
) -> dict[str, dict]:
    """Map each ticker to ``{ticker, name, sector, description, market_cap, pe_ratio}``.

    Mock mode returns deterministic synthetic profiles. Live mode reads a JSON
    cache and hits yfinance only for tickers missing from cache (or on
    force_refresh), falling back to a synthetic profile if a live lookup fails so
    a single bad ticker never crashes the caller.
    """
    tickers = [t.upper() for t in tickers]
    if not tickers:
        raise DataUnavailableError("No tickers requested.")

    if config.use_mock_data():
        return {t: mock_data.generate_company_info(t) for t in tickers}

    out: dict[str, dict] = {}
    for t in tickers:
        rkey = f"info:v2:{t}"
        if not force_refresh:
            hit = cache.cache_get_json(rkey)
            if hit is not None:
                out[t] = hit
                continue
        info = None if force_refresh else _read_info_cache(t)
        if info is not None and _days_old(info.get("_cached_at")) > _MAX_INFO_AGE_DAYS:
            info = None  # cache too old — refetch
        if info is not None and "industry" not in info:
            info = None  # pre-enrichment cache format — refetch for new fields
        if info is not None and (info.get("dividend_yield") or 0) > 0.25:
            info = None  # cached with the old percent/fraction mix-up — refetch
        if info is not None and len(info.get("description") or "") > 320:
            info = None  # cached long-form description — refetch the blurb
        if info is None:
            try:
                info = _download_info_yf(t)
                if _info_is_empty(info, t):
                    # Don't cache a transient yfinance hiccup for 2 days.
                    raise DataUnavailableError("yfinance returned an empty profile")
                _write_info_cache(t, info)
            except Exception as exc:  # noqa: BLE001
                log.warning("Live info lookup failed for %s: %s; using synthetic.", t, exc)
                info = mock_data.generate_company_info(t)
        clean = {k: v for k, v in info.items() if k != "_cached_at"}
        cache.cache_set_json(rkey, clean, _MAX_INFO_AGE_DAYS * 86400)
        out[t] = clean
    return out
