"""FastMCP server: a friendly stock-research assistant exposed over MCP.

Run (stdio):             python -m portfolio_risk.server.mcp_server
Inspect (MCP Inspector): mcp dev src/portfolio_risk/server/mcp_server.py

Design notes:
- The actual logic lives in ``portfolio_risk.tools`` (shared with the mock agent
  and tests). These wrappers only add the MCP schema + docstrings the model sees
  when deciding which tool to call.
- Every tool returns plain JSON-serializable dicts; errors become {"error": ...}.
- NEVER print to stdout — it corrupts the JSON-RPC stream. Logs go to stderr.
- This assistant is educational and does not give investment advice.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .. import config, tools

mcp = FastMCP("stock-research-assistant")


@mcp.tool()
def get_stock_snapshot(ticker: str) -> dict:
    """Get a plain-English overview of a single stock.

    Use this for "tell me about X" / "what is X" / "what's X's price (or P/E,
    market cap)" questions. Returns the company name, sector, a short description
    of what it does, the current price, the latest daily change, market cap, and
    P/E ratio.
    """
    return tools.get_stock_snapshot(ticker)


@mcp.tool()
def get_price_performance(ticker: str, period: str = "1y") -> dict:
    """How a stock has performed over a period, in plain percentage terms.

    Use this for "how has X done" / "X's return this year" questions. ``period``
    is one of 1d, 1w, 1mo, 3mo, 6mo, 1y, 2y, 5y. Returns the total return and a
    friendly movement label ("calm", "average", "bumpy").
    """
    return tools.get_price_performance(ticker, period)


@mcp.tool()
def explain_price_move(ticker: str, period: str = "1d") -> dict:
    """Explain WHY a stock moved by pairing the move with same-window news.

    Use this for "why did X drop / jump / fall / soar", "what happened to X",
    "why is X down today" questions. ``period`` is one of 1d, 1w, 1mo, 3mo, 6mo,
    1y. Returns the move %, a plain movement label, the time window, and the
    headlines from that window so you can connect the move to recent events.
    """
    return tools.explain_price_move(ticker, period)


@mcp.tool()
def compare_stocks(tickers: list[str]) -> dict:
    """Compare a few stocks side by side on the basics.

    Use this for "compare X and Y" questions. Returns one row per ticker with
    name, sector, current price, recent move, market cap, P/E, and how much each
    tends to move.
    """
    return tools.compare_stocks(tickers)


@mcp.tool()
def explain_stock_risk(
    ticker: str, benchmark: str = config.DEFAULT_BENCHMARK
) -> dict:
    """Explain in plain words how risky/volatile a stock tends to be.

    Use this for "is X risky / safe / volatile" questions. Translates the
    stock's volatility and its beta versus the overall market into everyday
    language. Educational only, not investment advice.
    """
    return tools.explain_stock_risk(ticker, benchmark)


@mcp.tool()
def get_technical_indicators(ticker: str) -> dict:
    """Common chart metrics for a stock.

    Use this for "is X above its 200-day average", "what's X's RSI / moving
    average / 52-week range" questions. Returns the 50- and 200-day moving
    averages with a trend read, the 14-day RSI, and the 52-week high/low.
    """
    return tools.get_technical_indicators(ticker)


@mcp.tool()
def get_ticker_news(ticker: str, limit: int = 6) -> dict:
    """Get recent news headlines for a stock (free, via Yahoo Finance).

    Use this for "what's the latest news on X" questions and to ground your
    commentary in recent events. Returns {"ticker", "articles": [{title,
    publisher, url, published, summary}]}.
    """
    return tools.get_ticker_news(ticker, limit)


@mcp.tool()
def get_watchlist_digest(tickers: list[str], period: str = "1d") -> dict:
    """A quick plain-English brief for several stocks at once.

    Use this for "give me a digest / morning brief / what moved on my watchlist"
    over a list of tickers. For each, returns the recent move over ``period`` plus
    the headlines from that same window. ``period`` is one of 1d, 1w, 1mo, ...
    """
    return tools.get_watchlist_digest(tickers, period)


@mcp.tool()
def get_filing_risks(ticker: str, k: int = 6) -> dict:
    """The 'Risk Factors' a company discloses in its SEC 10-K, as cited excerpts.

    Use this for "what are the risks / risk factors for X", "what could go wrong
    with X", "what does X's 10-K / annual report say" questions. Returns excerpts
    to summarize in PLAIN ENGLISH with citations. (For "is X volatile/risky" as a
    stock, use explain_stock_risk instead.)
    """
    return tools.get_filing_risks(ticker, k)


@mcp.tool()
def search_knowledge(query: str, ticker: str = "", k: int = 4) -> dict:
    """Search the plain-English knowledge library and cite the source.

    Use this when asked WHY a company matters, what it does, what to watch out
    for, or to explain an investing concept (P/E, market cap, the 200-day moving
    average, volatility, etc.). Returns {"results": [{text, ticker, source,
    score}]}. If empty, the corpus may not be ingested yet.
    """
    return tools.search_knowledge(query, ticker, k)


@mcp.tool()
def get_fundamentals(ticker: str) -> dict:
    """How the BUSINESS is doing financially (not the stock price).

    Use this for "is X profitable", "how much money does X make", "what's X's
    revenue / margins / debt / free cash flow" questions. Returns the latest
    annual revenue (with growth), gross/net margins, net income, free cash
    flow, and the debt load — each with a plain-English reading.
    """
    return tools.get_fundamentals(ticker)


@mcp.tool()
def get_dividend_info(ticker: str) -> dict:
    """Whether a stock pays a dividend and what it yields.

    Use this for "does X pay a dividend", "what's X's dividend yield", "when
    is the ex-dividend date" questions. Returns recent payments, the trailing
    12-month total, the yield, and the next ex-dividend date.
    """
    return tools.get_dividend_info(ticker)


@mcp.tool()
def get_stock_intel(ticker: str) -> dict:
    """Street activity around a stock: earnings date, analysts, insiders.

    Use this for "when does X report earnings", "what do analysts think of X /
    any upgrades or downgrades", "are insiders buying or selling X", "who owns
    X" questions. Returns the next earnings date, recent analyst rating
    changes, insider transactions (with buy/sell counts), and top
    institutional holders.
    """
    return tools.get_stock_intel(ticker)


@mcp.tool()
def get_market_overview() -> dict:
    """How the OVERALL market is doing today (no ticker needed).

    Use this for "how's the market today", "what's the VIX at", "are markets
    up or down" questions, and to give market context to single-stock answers.
    Returns S&P 500 / Nasdaq / Dow levels and day moves, the VIX 'fear gauge'
    with a mood reading (calm/normal/nervous/fearful), and the 10-year
    Treasury yield.
    """
    return tools.get_market_overview()


@mcp.tool()
def get_market_movers(category: str = "gainers") -> dict:
    """Today's biggest moving stocks across the whole market.

    Use this for "what are today's biggest gainers / losers", "what's moving
    today", "what are the most active stocks" questions. ``category`` is one
    of 'gainers', 'losers', or 'active'. Returns ticker, name, price, day
    change, and volume for each.
    """
    return tools.get_market_movers(category)


@mcp.tool()
def get_portfolio_overview(portfolio: str = "default") -> dict:
    """The user's ACTUAL portfolio: holdings, cost basis, profit/loss, totals.

    Use this when the user asks about THEIR portfolio, holdings, or positions
    ("what do I own", "how is my portfolio doing", "what am I up/down").
    Returns per-holding shares, average cost, current value, unrealized and
    realized P&L, sector allocation, and a concentration reading.
    """
    return tools.get_portfolio_overview(portfolio)


@mcp.tool()
def get_portfolio_risk_report(
    portfolio: str = "default", benchmark: str = config.DEFAULT_BENCHMARK
) -> dict:
    """Risk numbers for the user's WHOLE portfolio (not a single stock).

    Use this for "how risky is my portfolio", "what's my VaR / drawdown /
    diversification". Returns volatility, beta, Sharpe, max drawdown, VaR/CVaR
    (with dollar amounts), a correlation matrix, and concentration. For one
    stock's risk use explain_stock_risk instead.
    """
    return tools.get_portfolio_risk_report(portfolio, benchmark)


@mcp.tool()
def get_portfolio_news(portfolio: str = "default", limit_per_ticker: int = 3) -> dict:
    """Recent headlines mapped to the user's holdings, biggest positions first.

    Use this for "any news on my portfolio / my stocks". For news on one
    specific ticker use get_ticker_news instead.
    """
    return tools.get_portfolio_news(portfolio, limit_per_ticker)


@mcp.tool()
def get_portfolio_briefing(portfolio: str = "default", period: str = "1d") -> dict:
    """A daily-briefing payload for the user's portfolio.

    Use this for "give me my briefing / what changed in my portfolio today /
    morning update". Returns each holding's move with same-window headlines,
    day P&L, the biggest mover, concentration warnings, and unread alerts.
    Lead your summary with the bottom line and flag any warnings.
    """
    return tools.get_portfolio_briefing(portfolio, period)


@mcp.tool()
def run_portfolio_scenario(
    scenario: str = "covid_2020", portfolio: str = "default"
) -> dict:
    """Stress-test the user's portfolio against a named historical crisis.

    Use this for "what if 2008 happened / could my portfolio survive a crash".
    Scenarios: gfc_2008, covid_2020, rates_2022, black_monday, correction_10
    (or 'list' for the catalog). Beta-scaled approximation — present it as an
    estimate, and compare the loss to the portfolio's daily VaR.
    """
    return tools.run_portfolio_scenario(scenario, portfolio)


@mcp.tool()
def simulate_trade(
    side: str, ticker: str, shares: float, portfolio: str = "default"
) -> dict:
    """Hypothetical trade: portfolio risk BEFORE vs AFTER. Never writes anything.

    Use this for "what happens if I buy/sell N shares of X". Returns before /
    after / delta for volatility, beta, Sharpe, VaR, and concentration.
    """
    return tools.simulate_trade(side, ticker, shares, portfolio)


@mcp.tool()
def get_rebalance_plan(portfolio: str = "default", target: str = "equal_weight") -> dict:
    """Suggested trades to move the portfolio toward a target allocation.

    Use this for "how do I rebalance / get back to equal weight". ``target``
    is 'equal_weight' or a JSON object like '{"AAPL": 0.4, "SPY": 0.6}'.
    Educational only — no tax or fee modeling.
    """
    return tools.get_rebalance_plan(portfolio, target)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
