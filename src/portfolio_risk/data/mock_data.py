"""Deterministic synthetic price data — the default, fully-offline data source.

Generates geometric-Brownian-motion adjusted-close series with per-ticker drift,
volatility, and a correlated market factor (so beta vs the benchmark is sensible).
Output is reproducible for a fixed seed, which keeps tests and evals stable.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

# Per-ticker (annual_drift, annual_vol, beta_to_market). Unknown tickers get a
# deterministic profile derived from the ticker string.
_PROFILES: dict[str, tuple[float, float, float]] = {
    "SPY": (0.08, 0.16, 1.00),
    "AAPL": (0.18, 0.28, 1.15),
    "MSFT": (0.16, 0.26, 1.05),
    "NVDA": (0.30, 0.45, 1.55),
    "TSLA": (0.20, 0.55, 1.45),
    "JNJ": (0.06, 0.14, 0.60),
    "KO": (0.05, 0.13, 0.55),
    "AMZN": (0.17, 0.32, 1.20),
    "GOOGL": (0.15, 0.27, 1.05),
    "JPM": (0.10, 0.24, 1.10),
}


def _profile(ticker: str) -> tuple[float, float, float]:
    if ticker in _PROFILES:
        return _PROFILES[ticker]
    h = int(hashlib.sha256(ticker.encode()).hexdigest(), 16)
    drift = 0.04 + (h % 20) / 100.0          # 0.04 .. 0.23
    vol = 0.15 + ((h >> 8) % 35) / 100.0     # 0.15 .. 0.49
    beta = 0.6 + ((h >> 16) % 110) / 100.0   # 0.60 .. 1.69
    return drift, vol, beta


# Realistic names/sectors/blurbs for the demo tickers, so the offline experience
# looks believable. Unknown tickers fall back to a deterministic synthetic profile.
_KNOWN_INFO: dict[str, tuple[str, str, str]] = {
    "SPY": ("SPDR S&P 500 ETF Trust", "Index Fund",
            "An exchange-traded fund that tracks the S&P 500 — a basket of 500 "
            "large U.S. companies, often used as a stand-in for 'the market'."),
    "AAPL": ("Apple Inc.", "Technology",
             "Designs and sells iPhones, Macs, iPads, wearables, and a growing "
             "set of services like the App Store, iCloud, and Apple Music."),
    "MSFT": ("Microsoft Corporation", "Technology",
             "Makes Windows and Office, runs the Azure cloud platform, owns "
             "LinkedIn and Xbox, and is a major investor in AI."),
    "NVDA": ("NVIDIA Corporation", "Technology",
             "Designs the graphics chips (GPUs) that power video games and, more "
             "importantly today, the data-center hardware behind modern AI."),
    "TSLA": ("Tesla, Inc.", "Consumer Discretionary",
             "Builds electric vehicles and battery/energy-storage products, and "
             "is working on self-driving software and robotics."),
    "JNJ": ("Johnson & Johnson", "Healthcare",
            "A large, diversified healthcare company spanning prescription "
            "medicines and medical devices."),
    "KO": ("The Coca-Cola Company", "Consumer Staples",
           "Sells soft drinks and other beverages worldwide — a classic example "
           "of a steady consumer-staples business."),
    "AMZN": ("Amazon.com, Inc.", "Consumer Discretionary",
             "Runs the world's largest online store and the AWS cloud platform, "
             "plus advertising, streaming, and devices."),
    "GOOGL": ("Alphabet Inc.", "Technology",
              "The parent company of Google Search, YouTube, Android, and the "
              "Google Cloud platform; most revenue comes from advertising."),
    "JPM": ("JPMorgan Chase & Co.", "Financials",
            "One of the largest U.S. banks, offering consumer banking, credit "
            "cards, investment banking, and asset management."),
}

_SECTORS = [
    "Technology", "Healthcare", "Consumer Staples", "Financials",
    "Energy", "Industrials", "Consumer Discretionary", "Utilities",
]


def generate_news(ticker: str, limit: int = 8) -> list[dict]:
    """Deterministic synthetic headlines (offline default). Clearly labeled fake."""
    t = ticker.upper()
    name = _KNOWN_INFO[t][0] if t in _KNOWN_INFO else f"{t} Corporation"
    templates = [
        (f"{name} reports quarterly earnings", "Synthetic Newswire"),
        (f"Analysts weigh in on {name}'s outlook", "Mock Markets"),
        (f"{name} announces a new product line", "Demo Daily"),
        (f"What investors should know about {name}", "Offline Observer"),
        (f"{name} shares move with sector trends", "Sample Street Journal"),
        (f"{name} expands operations", "Placeholder Press"),
        (f"{name} faces competitive pressure", "Example Examiner"),
        (f"A closer look at {name}'s fundamentals", "Test Tribune"),
    ]
    return [
        {
            "title": title,
            "publisher": pub,
            "url": "",
            "published": "",
            "summary": "Synthetic offline news item for demo/testing — not a real article.",
            "relevant": True,
        }
        for title, pub in templates[: max(0, limit)]
    ]


_GENERIC_RISKS = [
    "Competition: rivals could win customers with cheaper or better products, "
    "putting pressure on sales and profit margins.",
    "Economic conditions: a slowdown, higher interest rates, or weaker consumer "
    "spending could reduce demand for the company's products.",
    "Regulation and legal: new laws, lawsuits, or government action could raise "
    "costs or limit how the business operates.",
    "Supply chain: disruptions to suppliers or manufacturing could delay products "
    "and increase costs.",
    "Execution and people: failing to execute the strategy or to retain key "
    "talent could hurt future results.",
]

_SECTOR_RISKS = {
    "Technology": "Rapid technology change: products can become obsolete quickly, "
    "and heavy research spending may not pay off.",
    "Healthcare": "Clinical and approval risk: trials can fail and regulators can "
    "reject or restrict products, with long, costly development cycles.",
    "Financials": "Credit and rate risk: loan defaults, market swings, or interest-"
    "rate moves can sharply affect earnings.",
    "Consumer Staples": "Input costs: swings in commodity and packaging prices can "
    "squeeze margins on everyday products.",
    "Consumer Discretionary": "Demand sensitivity: sales depend on discretionary "
    "spending, which falls fast when budgets tighten.",
    "Energy": "Commodity prices: results swing with volatile oil and gas prices "
    "and with energy-transition policy.",
    "Industrials": "Cyclicality: demand tracks the broader economy and large "
    "capital projects that can be delayed.",
    "Utilities": "Regulation and capital: heavy regulation and large infrastructure "
    "spending constrain returns.",
    "Index Fund": "Market risk: the fund moves with the overall market and offers "
    "no protection in a broad downturn.",
}


def generate_filing_risks(ticker: str, limit: int = 6) -> list[dict]:
    """Deterministic synthetic '10-K risk factors' (offline default). Clearly
    labeled fake; mirrors the shape of ``search_knowledge`` results so the agent
    and the groundedness checker treat it like any other retrieved source."""
    t = ticker.upper()
    if t in _KNOWN_INFO:
        sector = _KNOWN_INFO[t][1]
    else:
        h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
        sector = _SECTORS[h % len(_SECTORS)]
    risks: list[str] = []
    if sector in _SECTOR_RISKS:
        risks.append(_SECTOR_RISKS[sector])
    risks.extend(_GENERIC_RISKS)
    source = f"MOCK 10-K Risk Factors ({t})"
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={t}&type=10-K"
    return [
        {
            "text": r,
            "source": source,
            "url": url,
            "ticker": t,
            "score": round(1.0 - i * 0.05, 4),
        }
        for i, r in enumerate(risks[: max(0, limit)])
    ]


def curated_description(ticker: str) -> str | None:
    """The hand-written company blurb for well-known tickers, or None.

    Used by the LIVE data path as a fallback when yfinance's flaky ``.info``
    endpoint returns a profile without a business summary.
    """
    known = _KNOWN_INFO.get(ticker.upper())
    return known[2] if known else None


_KNOWN_INDUSTRY: dict[str, str] = {
    "SPY": "Index Fund",
    "AAPL": "Consumer Electronics",
    "MSFT": "Software — Infrastructure",
    "NVDA": "Semiconductors",
    "TSLA": "Auto Manufacturers",
    "JNJ": "Drug Manufacturers",
    "KO": "Beverages — Non-Alcoholic",
    "AMZN": "Internet Retail",
    "GOOGL": "Internet Content & Information",
    "JPM": "Banks — Diversified",
}

_RECOMMENDATIONS = ["buy", "hold", "overweight", "underperform"]


def generate_company_info(ticker: str) -> dict:
    """Deterministic synthetic company profile (offline default).

    Mirrors the contract of the live ``market_data.get_company_info`` per-ticker
    value (incl. the enriched yfinance fields: industry, employees, dividend
    yield, margins, analyst view). Every field is derived purely from the ticker
    string (hash) or the known-ticker tables, so the same ticker always yields
    the same profile — which keeps tests/evals stable.
    """
    t = ticker.upper()
    h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
    if t in _KNOWN_INFO:
        name, sector, description = _KNOWN_INFO[t]
    else:
        name = f"{t} Corporation"
        sector = _SECTORS[h % len(_SECTORS)]
        description = (
            f"{name} is a {sector.lower()} company. (This is a synthetic, "
            f"offline profile generated for demo and testing — not a real company.)"
        )
    market_cap = 5e9 + (h % 2950) * 1e9        # ~$5B .. ~$3T, deterministic
    pe_ratio = round(8.0 + (h >> 24) % 40, 1)  # 8.0 .. 47.x
    return {
        "ticker": t,
        "name": name,
        "sector": sector,
        "industry": _KNOWN_INDUSTRY.get(t, f"{sector} (synthetic)"),
        "description": description,
        "website": None,  # no fake URLs — the UI simply omits the link
        "country": "United States",
        "employees": int(1_000 + (h >> 4) % 200_000),
        "market_cap": float(market_cap),
        "pe_ratio": float(pe_ratio),
        "forward_pe": round(pe_ratio * 0.9, 1),
        "dividend_yield": round(((h >> 12) % 60) / 1000.0, 4),  # 0 .. 5.9%
        "profit_margin": round(0.05 + ((h >> 20) % 30) / 100.0, 4),
        "revenue_growth": round(-0.05 + ((h >> 28) % 40) / 100.0, 4),
        "recommendation": _RECOMMENDATIONS[h % len(_RECOMMENDATIONS)],
        "analyst_target": None,  # mock has no meaningful target price
        "analyst_count": int(5 + (h >> 8) % 40),
    }


def generate_ohlc(ticker: str, days: int = 504, seed: int = 42) -> pd.DataFrame:
    """Deterministic synthetic OHLCV derived from the GBM closes.

    open = previous close; high/low bracket open/close by a small hash-seeded
    spread; volume is hash-seeded. Same ticker + days -> identical frame, which
    keeps candlestick tests/evals stable offline.
    """
    t = ticker.upper()
    closes = generate_prices([t], days=days, seed=seed)[t]
    h = int(hashlib.sha256((t + ":ohlc").encode()).hexdigest(), 16)
    rng = np.random.default_rng(h % (2**32))
    n = len(closes)
    spread = np.abs(rng.normal(0.004, 0.003, size=n)) + 0.0005
    opens = closes.shift(1).fillna(closes.iloc[0])
    high = np.maximum(opens.to_numpy(), closes.to_numpy()) * (1.0 + spread)
    low = np.minimum(opens.to_numpy(), closes.to_numpy()) * (1.0 - spread)
    volume = rng.integers(2_000_000, 80_000_000, size=n).astype(float)
    return pd.DataFrame(
        {
            "open": opens.to_numpy(),
            "high": high,
            "low": low,
            "close": closes.to_numpy(),
            "volume": volume,
        },
        index=closes.index,
    )


# Bars per trading day (09:30–16:00) for each supported intraday interval.
_INTRADAY_BARS = {"1m": 390, "10m": 39, "1h": 7}
_INTRADAY_MINUTES = {"1m": 1, "10m": 10, "1h": 60}


def generate_intraday_ohlc(
    ticker: str, period: str = "1d", interval: str = "1h"
) -> pd.DataFrame:
    """Deterministic synthetic intraday OHLCV — mirrors get_intraday_ohlc.

    A hash-seeded random walk starting from the ticker's last synthetic daily
    close, stamped onto 09:30–16:00 sessions of the last mock calendar day(s).
    """
    t = ticker.upper()
    days = 5 if period == "1w" else 1
    per_day = _INTRADAY_BARS.get(interval, 7)
    n = per_day * days
    closes = generate_prices([t], days=60)[t]
    base = float(closes.iloc[-1])

    h = int(hashlib.sha256(f"{t}:intraday:{period}:{interval}".encode()).hexdigest(), 16)
    rng = np.random.default_rng(h % (2**32))
    step_vol = _profile(t)[1] / np.sqrt(252.0 * per_day)
    rets = rng.normal(0.0, step_vol, size=n)
    close_path = base * np.cumprod(1.0 + rets)
    opens = np.concatenate([[base], close_path[:-1]])
    spread = np.abs(rng.normal(0.0008, 0.0005, size=n)) + 0.0002
    high = np.maximum(opens, close_path) * (1.0 + spread)
    low = np.minimum(opens, close_path) * (1.0 - spread)
    volume = rng.integers(50_000, 5_000_000, size=n).astype(float)

    minutes = _INTRADAY_MINUTES.get(interval, 60)
    times: list[pd.Timestamp] = []
    for d in closes.index[-days:]:
        start = pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=30)
        times.extend(start + pd.Timedelta(minutes=minutes * i) for i in range(per_day))
    return pd.DataFrame(
        {"open": opens, "high": high, "low": low, "close": close_path, "volume": volume},
        index=pd.DatetimeIndex(times[:n]),
    )


_MOCK_FIRMS = [
    "Synthetic Securities", "Mock Capital", "Placeholder Partners",
    "Example Equity Research", "Offline Analytics", "Demo Brokerage",
]
_GRADES = ["Buy", "Hold", "Overweight", "Neutral", "Outperform"]
_ACTIONS = ["up", "down", "init", "main"]
_MOCK_INSIDERS = [
    ("J. Doe", "CEO"), ("A. Smith", "CFO"), ("R. Roe", "Director"),
    ("M. Major", "COO"), ("S. Sample", "President"),
]
_MOCK_HOLDERS = [
    "Vanguard Group (synthetic)", "BlackRock (synthetic)", "State Street (synthetic)",
    "Fidelity (synthetic)", "Geode Capital (synthetic)",
]


def generate_intel(ticker: str) -> dict:
    """Deterministic synthetic ticker intel — mirrors market_data.get_intel."""
    t = ticker.upper()
    h = int(hashlib.sha256((t + ":intel").encode()).hexdigest(), 16)
    upgrades = [
        {
            "date": f"2021-0{1 + (h >> (8 * i)) % 9}-{1 + (h >> (8 * i + 4)) % 27:02d}",
            "firm": _MOCK_FIRMS[(h >> (4 * i)) % len(_MOCK_FIRMS)],
            "action": _ACTIONS[(h >> (5 * i)) % len(_ACTIONS)],
            "from_grade": _GRADES[(h >> (6 * i)) % len(_GRADES)],
            "to_grade": _GRADES[(h >> (7 * i + 2)) % len(_GRADES)],
        }
        for i in range(4)
    ]
    insiders = [
        {
            "date": f"2021-0{1 + (h >> (9 * i)) % 9}-{1 + (h >> (9 * i + 3)) % 27:02d}",
            "insider": _MOCK_INSIDERS[(h >> (3 * i)) % len(_MOCK_INSIDERS)][0],
            "position": _MOCK_INSIDERS[(h >> (3 * i)) % len(_MOCK_INSIDERS)][1],
            "transaction": "Sale" if (h >> (2 * i)) % 2 else "Purchase",
            "shares": float(1_000 + (h >> (10 * i)) % 50_000),
            "value": float(100_000 + (h >> (11 * i)) % 5_000_000),
        }
        for i in range(3)
    ]
    holders = [
        {
            "holder": name,
            "pct_held": round(0.02 + ((h >> (6 * i)) % 70) / 1000.0, 4),
            "shares": float(10_000_000 + (h >> (7 * i)) % 900_000_000),
            "reported": "2021-06-30",
        }
        for i, name in enumerate(_MOCK_HOLDERS)
    ]
    return {
        "ticker": t,
        "next_earnings": f"2021-1{(h % 3)}-{1 + (h >> 5) % 27:02d}",
        "ex_dividend_date": f"2021-0{1 + (h >> 16) % 9}-{1 + (h >> 9) % 27:02d}",
        "upgrades": upgrades,
        "insiders": insiders,
        "institutional": holders,
    }


def generate_fundamentals(ticker: str) -> dict:
    """Deterministic synthetic fundamentals — mirrors market_data.get_fundamentals.

    Derived from the same hash-seeded company profile (market cap, margins,
    growth) so the numbers stay consistent with ``generate_company_info``.
    """
    t = ticker.upper()
    info = generate_company_info(t)
    h = int(hashlib.sha256((t + ":fund").encode()).hexdigest(), 16)
    market_cap = float(info["market_cap"])
    profit_margin = float(info["profit_margin"])
    revenue_growth = float(info["revenue_growth"])
    ps_ratio = 2.0 + h % 9                        # price/sales 2..10
    revenue = market_cap / ps_ratio
    net_income = revenue * profit_margin
    gross_margin = min(profit_margin + 0.15 + ((h >> 6) % 20) / 100.0, 0.90)
    free_cash_flow = net_income * (0.7 + ((h >> 9) % 50) / 100.0)
    total_debt = market_cap * (((h >> 12) % 40) / 100.0)
    cash = market_cap * (0.02 + ((h >> 16) % 18) / 100.0)
    equity = market_cap * (0.20 + ((h >> 20) % 50) / 100.0)
    return {
        "ticker": t,
        "period": "FY2020",
        "revenue": round(revenue, 0),
        "revenue_prior": round(revenue / (1.0 + revenue_growth), 0),
        "revenue_growth": round(revenue_growth, 4),
        "gross_margin": round(gross_margin, 4),
        "profit_margin": round(profit_margin, 4),
        "net_income": round(net_income, 0),
        "free_cash_flow": round(free_cash_flow, 0),
        "total_debt": round(total_debt, 0),
        "cash": round(cash, 0),
        "equity": round(equity, 0),
        "debt_to_equity": round(total_debt / equity, 4) if equity else None,
        "note": "Synthetic offline fundamentals for demo/testing — not real financials.",
    }


def generate_dividends(ticker: str) -> dict:
    """Deterministic synthetic dividend history — mirrors market_data.get_dividends.

    Quarterly payments sized from the profile's dividend yield and the last
    synthetic close, dated inside the mock price calendar.
    """
    t = ticker.upper()
    info = generate_company_info(t)
    y = float(info["dividend_yield"] or 0.0)
    closes = generate_prices([t], days=504)[t]
    price = float(closes.iloc[-1])
    if y < 0.001:
        return {
            "ticker": t,
            "pays_dividend": False,
            "dividend_yield": 0.0,
            "ttm_dividend": 0.0,
            "recent": [],
            "ex_dividend_date": None,
        }
    quarterly = price * y / 4.0
    # Every ~63rd business day from the end of the mock calendar, newest first.
    idx = closes.index
    recent = [
        {"date": str(idx[-(1 + 63 * i)].date()), "amount": round(quarterly * (0.98 ** i), 4)}
        for i in range(min(8, len(idx) // 63))
    ]
    h = int(hashlib.sha256((t + ":div").encode()).hexdigest(), 16)
    return {
        "ticker": t,
        "pays_dividend": True,
        "dividend_yield": round(y, 4),
        "ttm_dividend": round(sum(r["amount"] for r in recent[:4]), 4),
        "recent": recent,
        "ex_dividend_date": f"2021-0{1 + (h >> 4) % 9}-{1 + (h >> 9) % 27:02d}",
    }


_MOCK_INDICES = [
    ("^GSPC", "S&P 500", 4500.0),
    ("^IXIC", "Nasdaq Composite", 14000.0),
    ("^DJI", "Dow Jones Industrial Average", 35000.0),
]


def generate_market_overview() -> dict:
    """Deterministic synthetic market overview — mirrors get_market_overview."""
    indices = []
    for sym, name, base in _MOCK_INDICES:
        h = int(hashlib.sha256((sym + ":mkt").encode()).hexdigest(), 16)
        indices.append(
            {
                "symbol": sym,
                "name": name,
                "level": round(base * (1.0 + (h % 200) / 1000.0), 2),
                "change_pct": round((-15 + (h >> 8) % 31) / 1000.0, 4),  # -1.5%..+1.5%
            }
        )
    h = int(hashlib.sha256(b"^VIX:mkt").hexdigest(), 16)
    return {
        "indices": indices,
        "vix": {
            "level": round(12.0 + h % 18, 2),
            "change_pct": round((-15 + (h >> 8) % 31) / 1000.0, 4),
        },
        "ten_year_yield_pct": round(3.0 + ((h >> 16) % 20) / 10.0, 2),
        "note": "Synthetic offline market data for demo/testing.",
    }


def generate_movers(category: str = "gainers") -> list[dict]:
    """Deterministic synthetic market movers — mirrors market_data.get_movers.

    Day moves come from each ticker's own single-ticker GBM series (the same
    series the snapshot tools see), so the mock stays self-consistent.
    """
    rows = []
    for t in sorted(_PROFILES):
        closes = generate_prices([t], days=60)[t]
        change = float(closes.iloc[-1] / closes.iloc[-2] - 1.0)
        h = int(hashlib.sha256((t + ":vol").encode()).hexdigest(), 16)
        rows.append(
            {
                "ticker": t,
                "name": _KNOWN_INFO[t][0] if t in _KNOWN_INFO else f"{t} Corporation",
                "price": round(float(closes.iloc[-1]), 2),
                "change_pct": round(change, 4),
                "volume": float(2_000_000 + h % 80_000_000),
            }
        )
    cat = (category or "gainers").lower()
    if "los" in cat:
        rows.sort(key=lambda r: r["change_pct"])
    elif "activ" in cat:
        rows.sort(key=lambda r: -r["volume"])
    else:
        rows.sort(key=lambda r: -r["change_pct"])
    return rows[:5]


def generate_prices(
    tickers: list[str],
    days: int = 504,
    seed: int = 42,
    start: str = "2021-01-04",
) -> pd.DataFrame:
    """Adjusted-close matrix (index=business days, cols=tickers).

    A shared market factor drives common variation; each ticker adds idiosyncratic
    noise scaled so its realized beta and volatility match its profile.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    dates = pd.bdate_range(start=start, periods=days)

    # Shared market factor (excess daily returns around its own drift).
    m_drift, m_vol, _ = _PROFILES["SPY"]
    market = rng.normal(0.0, m_vol * np.sqrt(dt), size=days)

    cols: dict[str, np.ndarray] = {}
    for t in tickers:
        drift, vol, b = _profile(t)
        # Decompose vol into market-driven and idiosyncratic parts.
        sys_vol = abs(b) * m_vol
        idio_var = max(vol**2 - sys_vol**2, (0.05 * vol) ** 2)
        idio = rng.normal(0.0, np.sqrt(idio_var) * np.sqrt(dt), size=days)
        daily = drift * dt + b * market + idio
        price = 100.0 * np.cumprod(1.0 + daily)
        cols[t] = price

    return pd.DataFrame(cols, index=dates)
