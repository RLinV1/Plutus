"""FastAPI backend for the Stock Research Assistant React frontend.

It is a thin HTTP layer over the same ``portfolio_risk.tools`` functions the MCP
server and the agent use — no business logic lives here. Stock data is live
yfinance by default; the agent + RAG are the added layer.

Run:  python -m api.server      (or)   stock-api
Dev frontend talks to it at http://127.0.0.1:8000.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from portfolio_risk import config, tools
from portfolio_risk.agent.client import run_agent, stream_agent_events
from portfolio_risk.data.market_data import get_ohlc, get_prices

from portfolio_risk.portfolio import billing

from .auth import get_user_id
from .billing_routes import router as billing_router
from .portfolio_routes import router as portfolio_router
from .ws import alerts_quotes_loop, hub, stream_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot: ensure schemas; run the alerts/quotes loop for the app's lifetime."""
    try:
        from portfolio_risk import db

        if db.db_enabled():
            db.init_db()
    except Exception:  # noqa: BLE001
        pass
    try:
        from portfolio_risk.portfolio.db import init_portfolio_db

        init_portfolio_db()
    except Exception:  # noqa: BLE001
        pass
    task = (
        asyncio.create_task(alerts_quotes_loop()) if config.run_alerts_loop() else None
    )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Stock Research Assistant API", version="2.0.0", lifespan=lifespan)
app.include_router(portfolio_router)
app.include_router(billing_router)


def _enforce_daily_quota(user_id: str) -> None:
    """Consume one prompt from the user's daily allowance or raise 429.

    The 429 detail is a structured dict so the frontend can show an upgrade
    prompt with the exact plan/limit.
    """
    quota = billing.consume(user_id)
    if not quota["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "daily_limit",
                "message": (
                    f"You've used all {quota['limit']} prompts for today on the "
                    f"{quota['plan'].replace('_', ' ')} plan."
                ),
                **quota,
            },
        )

# ---------------------------------------------------------------------------
# Rate limiting — backed by Redis when available, in-process dict otherwise.
# ---------------------------------------------------------------------------
_rate_store: dict[str, list[float]] = {}

def _check_rate(key: str, limit: int, window: int) -> None:
    """Sliding-window rate limiter. Raises 429 if over limit."""
    import time
    now = time.time()
    redis_url = config.redis_url()
    if redis_url:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(redis_url, decode_responses=True)
            pipe = r.pipeline()
            pipe.zadd(key, {str(now): now})
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            pipe.expire(key, window)
            results = pipe.execute()
            if results[2] > limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")
            return
        except HTTPException:
            raise
        except Exception:
            pass
    # Fallback: in-process dict
    times = [t for t in _rate_store.get(key, []) if now - t < window]
    if len(times) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")
    _rate_store[key] = times + [now]

def _rate_limit(request: Request, limit: int = 60, window: int = 60) -> None:
    ip = request.client.host if request.client else "unknown"
    _check_rate(f"rl:{ip}:{request.url.path}", limit, window)


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    await stream_endpoint(ws)

# The Vite dev server runs on 5173; allow it (and the preview port) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Curated universe for the search autocomplete (symbol -> display name).
# Not exhaustive — live mode accepts ANY ticker the user types; this is just the
# convenience suggestion list.
UNIVERSE: dict[str, str] = {
    # Mega-cap tech / "Magnificent Seven"
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corp.", "NVDA": "NVIDIA Corp.",
    "GOOGL": "Alphabet (Google)", "GOOG": "Alphabet (Google) C",
    "AMZN": "Amazon.com", "META": "Meta Platforms", "TSLA": "Tesla",
    # Software / internet
    "NFLX": "Netflix", "ORCL": "Oracle", "CRM": "Salesforce", "ADBE": "Adobe",
    "CSCO": "Cisco", "IBM": "IBM", "NOW": "ServiceNow", "SNOW": "Snowflake",
    "PLTR": "Palantir", "PANW": "Palo Alto Networks", "CRWD": "CrowdStrike",
    "DDOG": "Datadog", "NET": "Cloudflare", "MDB": "MongoDB", "ZM": "Zoom",
    "SHOP": "Shopify", "UBER": "Uber", "ABNB": "Airbnb", "SPOT": "Spotify",
    "SNAP": "Snap", "PINS": "Pinterest", "RBLX": "Roblox", "COIN": "Coinbase",
    "SQ": "Block (Square)", "PYPL": "PayPal",
    # Semiconductors
    "AMD": "Advanced Micro Devices", "INTC": "Intel", "AVGO": "Broadcom",
    "QCOM": "Qualcomm", "TXN": "Texas Instruments", "MU": "Micron",
    "TSM": "Taiwan Semiconductor", "ASML": "ASML Holding", "AMAT": "Applied Materials",
    "LRCX": "Lam Research", "ARM": "Arm Holdings", "SMCI": "Super Micro Computer",
    # Autos
    "F": "Ford", "GM": "General Motors", "RIVN": "Rivian", "LCID": "Lucid",
    # Consumer / retail
    "DIS": "Walt Disney", "NKE": "Nike", "MCD": "McDonald's", "SBUX": "Starbucks",
    "WMT": "Walmart", "COST": "Costco", "TGT": "Target", "HD": "Home Depot",
    "LOW": "Lowe's", "CMG": "Chipotle", "LULU": "Lululemon", "PG": "Procter & Gamble",
    "KO": "Coca-Cola", "PEP": "PepsiCo", "MDLZ": "Mondelez", "CL": "Colgate-Palmolive",
    # Healthcare / pharma
    "JNJ": "Johnson & Johnson", "LLY": "Eli Lilly", "PFE": "Pfizer", "MRK": "Merck",
    "UNH": "UnitedHealth", "ABBV": "AbbVie", "ABT": "Abbott", "TMO": "Thermo Fisher",
    "DHR": "Danaher", "BMY": "Bristol Myers Squibb", "AMGN": "Amgen",
    "GILD": "Gilead Sciences", "CVS": "CVS Health",
    # Financials
    "JPM": "JPMorgan Chase", "BAC": "Bank of America", "WFC": "Wells Fargo",
    "GS": "Goldman Sachs", "MS": "Morgan Stanley", "C": "Citigroup",
    "AXP": "American Express", "SCHW": "Charles Schwab", "BLK": "BlackRock",
    "BRK-B": "Berkshire Hathaway B", "V": "Visa", "MA": "Mastercard",
    # Energy / industrials
    "XOM": "Exxon Mobil", "CVX": "Chevron", "COP": "ConocoPhillips",
    "SLB": "Schlumberger", "OXY": "Occidental Petroleum", "BA": "Boeing",
    "CAT": "Caterpillar", "GE": "GE Aerospace", "HON": "Honeywell", "UPS": "UPS",
    "LMT": "Lockheed Martin", "RTX": "RTX (Raytheon)", "DE": "Deere", "MMM": "3M",
    # Communications / telecom
    "T": "AT&T", "VZ": "Verizon", "TMUS": "T-Mobile", "CMCSA": "Comcast",
    # ETFs
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq-100 ETF", "VOO": "Vanguard S&P 500",
    "VTI": "Vanguard Total Market", "DIA": "Dow Jones ETF", "IWM": "Russell 2000 ETF",
    "ARKK": "ARK Innovation ETF",
    # More software / semis / hardware
    "INTU": "Intuit", "WDAY": "Workday", "TEAM": "Atlassian", "DOCU": "DocuSign",
    "OKTA": "Okta", "TWLO": "Twilio", "HUBS": "HubSpot", "ZS": "Zscaler",
    "FTNT": "Fortinet", "ANET": "Arista Networks", "CDNS": "Cadence", "SNPS": "Synopsys",
    "DELL": "Dell", "HPQ": "HP Inc.", "HPE": "Hewlett Packard Enterprise",
    "MRVL": "Marvell", "KLAC": "KLA Corp.", "ADI": "Analog Devices", "NXPI": "NXP",
    "MCHP": "Microchip", "ON": "ON Semiconductor", "FICO": "Fair Isaac",
    # More internet / consumer
    "BKNG": "Booking Holdings", "MELI": "MercadoLibre", "DASH": "DoorDash",
    "ETSY": "Etsy", "EBAY": "eBay", "DKNG": "DraftKings", "ROKU": "Roku",
    "TTD": "The Trade Desk", "CHWY": "Chewy", "EXPE": "Expedia", "HOOD": "Robinhood",
    "SOFI": "SoFi", "AFRM": "Affirm",
    # More autos / EV
    "NIO": "NIO", "XPEV": "XPeng", "LI": "Li Auto",
    # More financials
    "PNC": "PNC Financial", "USB": "U.S. Bancorp", "TFC": "Truist", "COF": "Capital One",
    "ICE": "Intercontinental Exchange", "CME": "CME Group", "SPGI": "S&P Global",
    "MCO": "Moody's", "PGR": "Progressive", "MMC": "Marsh McLennan", "BK": "BNY Mellon",
    # More healthcare
    "ISRG": "Intuitive Surgical", "MDT": "Medtronic", "SYK": "Stryker", "ELV": "Elevance",
    "CI": "Cigna", "HCA": "HCA Healthcare", "REGN": "Regeneron", "VRTX": "Vertex",
    "MRNA": "Moderna", "ZTS": "Zoetis", "BSX": "Boston Scientific", "BDX": "Becton Dickinson",
    # More staples / discretionary
    "KHC": "Kraft Heinz", "GIS": "General Mills", "HSY": "Hershey", "STZ": "Constellation Brands",
    "MO": "Altria", "PM": "Philip Morris", "KDP": "Keurig Dr Pepper", "KR": "Kroger",
    "DG": "Dollar General", "DLTR": "Dollar Tree", "ROST": "Ross Stores", "TJX": "TJX",
    "YUM": "Yum! Brands", "WEN": "Wendy's", "EL": "Estée Lauder",
    # More industrials / materials
    "UNP": "Union Pacific", "CSX": "CSX", "NSC": "Norfolk Southern", "FDX": "FedEx",
    "EMR": "Emerson", "ETN": "Eaton", "ITW": "Illinois Tool Works", "GD": "General Dynamics",
    "NOC": "Northrop Grumman", "FCX": "Freeport-McMoRan", "NEM": "Newmont", "NUE": "Nucor",
    "LIN": "Linde", "SHW": "Sherwin-Williams",
    # More energy
    "PSX": "Phillips 66", "VLO": "Valero", "MPC": "Marathon Petroleum", "KMI": "Kinder Morgan",
    "WMB": "Williams Cos.", "EOG": "EOG Resources", "DVN": "Devon Energy", "HAL": "Halliburton",
    # Utilities / REITs
    "NEE": "NextEra Energy", "DUK": "Duke Energy", "SO": "Southern Co.", "AEP": "American Electric",
    "PLD": "Prologis", "AMT": "American Tower", "O": "Realty Income", "SPG": "Simon Property",
    "EQIX": "Equinix", "CCI": "Crown Castle",
    # Media / telecom / travel
    "WBD": "Warner Bros. Discovery", "PARA": "Paramount", "EA": "Electronic Arts",
    "TTWO": "Take-Two", "DAL": "Delta Air Lines", "UAL": "United Airlines",
    "LUV": "Southwest", "MAR": "Marriott", "HLT": "Hilton", "RCL": "Royal Caribbean",
    "CCL": "Carnival",
    # International (ADRs)
    "BABA": "Alibaba", "JD": "JD.com", "PDD": "PDD Holdings", "BIDU": "Baidu",
    "NVO": "Novo Nordisk", "SAP": "SAP", "TM": "Toyota", "SONY": "Sony",
    "SHEL": "Shell", "BP": "BP", "HSBC": "HSBC", "TD": "Toronto-Dominion",
    # Crypto-adjacent
    "MSTR": "Strategy (MicroStrategy)", "MARA": "Marathon Digital", "RIOT": "Riot Platforms",
    # More ETFs
    "VUG": "Vanguard Growth", "VTV": "Vanguard Value", "SCHD": "Schwab Dividend",
    "XLK": "Technology Sector ETF", "XLF": "Financials Sector ETF", "XLE": "Energy Sector ETF",
    "XLV": "Healthcare Sector ETF", "SMH": "Semiconductor ETF", "GLD": "Gold ETF",
    "TLT": "20+ Yr Treasury ETF", "BND": "Total Bond ETF", "EEM": "Emerging Markets ETF",
}

# Map UI period buttons to TRADING-day lookbacks for the price chart
# (~21 trading days per calendar month — using calendar-day counts here makes
# every window reach back further than its label says).
_CHART_DAYS = {"1mo": 21, "6mo": 126, "1y": 252, "5y": 1260, "max": 9000}
_MAX_CHART_POINTS = 800  # downsample longer series so the chart stays snappy


@app.get("/api/health")
def health() -> dict:
    from portfolio_risk import db

    return {
        "ok": True,
        "live_data": not config.use_mock_data(),
        "redis": config.redis_url() is not None,
        "db": db.db_enabled(),
        "rag_backend": config.rag_backend(),
        "ws_clients": hub.count,
        "alert_poll_sec": config.alert_poll_seconds(),
    }


@app.get("/api/universe")
def universe() -> dict:
    return {"tickers": [{"symbol": s, "name": n} for s, n in sorted(UNIVERSE.items())]}


@app.get("/api/snapshot")
def snapshot(ticker: str) -> dict:
    return tools.get_stock_snapshot(ticker)


@app.get("/api/performance")
def performance(ticker: str, period: str = "1y") -> dict:
    return tools.get_price_performance(ticker, period)


@app.get("/api/technicals")
def technicals(ticker: str) -> dict:
    return tools.get_technical_indicators(ticker)


@app.get("/api/risk")
def risk(ticker: str) -> dict:
    return tools.explain_stock_risk(ticker)


@app.get("/api/compare")
def compare(tickers: str) -> dict:
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    return tools.compare_stocks(syms)


@app.get("/api/news")
def news(ticker: str, limit: int = 12) -> dict:
    return tools.get_ticker_news(ticker, limit)


@app.get("/api/explain_move")
def explain_move(ticker: str, period: str = "1d") -> dict:
    return tools.explain_price_move(ticker, period)


@app.get("/api/filing_risks")
def filing_risks(ticker: str, k: int = 6) -> dict:
    return tools.get_filing_risks(ticker, k)


@app.get("/api/digest")
def digest(tickers: str, period: str = "1d") -> dict:
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    return tools.get_watchlist_digest(syms, period)


@app.get("/api/search")
def search(query: str, ticker: str = "") -> dict:
    return tools.search_knowledge(query, ticker, k=4)


@app.get("/api/prices")
def prices(ticker: str, period: str = "1y") -> dict:
    """Closing-price series for the chart, as compact {t, v} points."""
    days = _CHART_DAYS.get(period, 270)
    try:
        df = get_prices([ticker], lookback_days=days)
        col = ticker.upper()
        if col not in df.columns:
            return {"error": f"No price data for {col}."}
        s = df[col].dropna()
        points = [
            {"t": pd.Timestamp(idx).strftime("%Y-%m-%d"), "v": round(float(v), 2)}
            for idx, v in s.items()
        ]
        # Downsample long series (e.g. all-time) so the chart stays responsive,
        # always keeping the most recent point.
        if len(points) > _MAX_CHART_POINTS:
            step = len(points) // _MAX_CHART_POINTS + 1
            sampled = points[::step]
            if sampled[-1] is not points[-1]:
                sampled.append(points[-1])
            points = sampled
        return {"ticker": col, "period": period, "points": points}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


@app.get("/api/market")
def market() -> dict:
    """Index levels + VIX mood + 10-year yield for the MARKET view."""
    return tools.get_market_overview()


@app.get("/api/movers")
def movers(category: str = "gainers") -> dict:
    """Today's biggest gainers / losers / most-active stocks."""
    return tools.get_market_movers(category)


@app.get("/api/fundamentals")
def fundamentals(ticker: str) -> dict:
    return tools.get_fundamentals(ticker)


@app.get("/api/dividends")
def dividends(ticker: str) -> dict:
    return tools.get_dividend_info(ticker)


@app.get("/api/intel")
def intel(ticker: str) -> dict:
    """Earnings date + analyst actions + insiders + institutions (yfinance)."""
    from portfolio_risk.data.market_data import get_intel

    try:
        return get_intel(ticker)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


@app.get("/api/ohlc")
def ohlc(ticker: str, period: str = "1y", interval: str = "1d") -> dict:
    """OHLCV candles for the chart, as compact {t,o,h,l,c,v} points.

    Daily periods (1mo..max) use date-string times; intraday periods (1d, 1w)
    use epoch-second times and an ``interval`` of 1m, 10m, or 1h.
    """
    days = _CHART_DAYS.get(period, 270)
    try:
        if period in ("1d", "1w"):
            from portfolio_risk.data.market_data import get_intraday_ohlc

            bar = interval if interval in ("1m", "10m", "1h") else "1h"
            df = get_intraday_ohlc(ticker, period, bar)
            points = [
                {
                    "t": int(pd.Timestamp(idx).timestamp()),
                    "o": round(float(r["open"]), 2),
                    "h": round(float(r["high"]), 2),
                    "l": round(float(r["low"]), 2),
                    "c": round(float(r["close"]), 2),
                    "v": float(r["volume"]),
                }
                for idx, r in df.iterrows()
            ]
            return {
                "ticker": ticker.upper(),
                "period": period,
                "interval": bar,
                "points": points,
            }
        df = get_ohlc(ticker, lookback_days=days)
        points = [
            {
                "t": pd.Timestamp(idx).strftime("%Y-%m-%d"),
                "o": round(float(r["open"]), 2),
                "h": round(float(r["high"]), 2),
                "l": round(float(r["low"]), 2),
                "c": round(float(r["close"]), 2),
                "v": float(r["volume"]),
            }
            for idx, r in df.iterrows()
        ]
        if len(points) > _MAX_CHART_POINTS:
            step = len(points) // _MAX_CHART_POINTS + 1
            sampled = points[::step]
            if sampled[-1] is not points[-1]:
                sampled.append(points[-1])
            points = sampled
        return {"ticker": ticker.upper(), "period": period, "points": points}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


@app.post("/api/ask")
def ask(payload: dict, request: Request, user_id: str = Depends(get_user_id)) -> dict:
    _rate_limit(request, limit=20, window=60)
    question = (payload or {}).get("question", "").strip()
    if not question:
        return {"error": "Empty question."}
    _enforce_daily_quota(user_id)
    result = run_agent(question)
    return {"answer": result.answer, "tools_used": result.tool_names()}


@app.post("/api/ask_stream")
def ask_stream(payload: dict, request: Request, user_id: str = Depends(get_user_id)) -> StreamingResponse:
    """Stream the agent's progress + answer as Server-Sent Events.

    Events: {"type":"tool","name":...} | {"type":"text","text":...} |
            {"type":"done","tools":[...]} | {"type":"error","error":...}
    """
    _rate_limit(request, limit=20, window=60)
    question = (payload or {}).get("question", "").strip()

    def gen():
        if not question:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Empty question.'})}\n\n"
            return
        for event in stream_agent_events(question):
            yield f"data: {json.dumps(event)}\n\n"

    # Only charge the daily quota for a real (non-empty) question; raises 429
    # (structured detail) before the stream starts when the user is out of quota.
    if question:
        _enforce_daily_quota(user_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
