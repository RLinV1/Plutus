"""Deterministic offline "agent" — runs the full pipeline with no API key.

It parses a natural-language question, picks a tool, calls the shared tool
implementation, and writes a plain-English answer. It is intentionally rule-based
(not an LLM) so the end-to-end demo and the eval harness work with zero
credentials. When you add an ANTHROPIC_API_KEY, the real Claude client in
``client.py`` takes over automatically.

Everything here is educational, not investment advice.
"""

from __future__ import annotations

import re

from .. import tools
from .base import AgentResult

_DISCLAIMER = "This is educational information, not investment advice."

# All-caps tokens that are NOT tickers (so we don't treat "RSI" as a stock).
_STOPWORDS = {
    "A", "AN", "AND", "OR", "THE", "OF", "TO", "ON", "IN", "IS", "IT", "MY",
    "VS", "FOR", "AT", "WITH", "WHAT", "WHY", "HOW", "DOES", "DO", "I", "X", "Y",
    "RSI", "SMA", "PE", "EPS", "ETF", "P", "E", "AI", "US", "USA", "USD", "CEO",
    "CFO", "Q", "OK", "NEWS", "VAR", "EPS", "OK", "VIX",
}

# Friendly company-name aliases so beginners can type "Apple" instead of "AAPL".
_NAME_TO_TICKER = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "amazon": "AMZN",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "johnson & johnson": "JNJ",
    "johnson and johnson": "JNJ",
    "coca-cola": "KO",
    "coca cola": "KO",
    "coke": "KO",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "s&p 500": "SPY",
    "sp500": "SPY",
}


def _extract_tickers(question: str) -> list[str]:
    ql = question.lower()
    out: list[str] = []
    for name, tk in _NAME_TO_TICKER.items():
        if name in ql and tk not in out:
            out.append(tk)
    for tok in re.findall(r"\b([A-Z]{1,5})\b", question):
        if tok not in _STOPWORDS and tok not in out:
            out.append(tok)
    return out


def _extract_period(question: str) -> str:
    ql = question.lower()
    if "5 year" in ql or "five year" in ql or "5y" in ql:
        return "5y"
    if "2 year" in ql or "two year" in ql:
        return "2y"
    if "6 month" in ql or "six month" in ql or "half year" in ql or "6mo" in ql:
        return "6mo"
    if "3 month" in ql or "three month" in ql or "quarter" in ql:
        return "3mo"
    if "week" in ql:
        return "1w"
    if "today" in ql or "day" in ql:
        return "1d"
    if "month" in ql:
        return "1mo"
    # "year", "past year", "12 month", or unspecified
    return "1y"


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def run(question: str, feedback: str | None = None) -> AgentResult:
    q = question.strip()
    ql = q.lower()
    tickers = _extract_tickers(q)
    period = _extract_period(q)
    calls: list[dict] = []

    has_compare = (
        "compare" in ql or " vs " in ql or "versus" in ql or "side by side" in ql
    )
    digest_kw = any(
        k in ql for k in ("digest", "watchlist", "morning brief", "brief on my")
    )
    metric_kw = any(
        k in ql
        for k in (
            "200-day", "200 day", "moving average", "sma", "golden cross",
            "death cross", "rsi", "52-week", "52 week", "52wk", "technical",
        )
    )
    perf_kw = any(
        k in ql
        for k in (
            "how has", "how did", "how is", "performance", "performed",
            "done over", "done this", "return", "gone up", "gone down",
            "past year", "past month", "over the",
        )
    )
    filing_kw = any(
        k in ql
        for k in (
            "risk factor", "risk factors", "10-k", "10k", "what could go wrong",
            "sec filing", "filing", "filings", "annual report",
        )
    )
    risk_kw = any(k in ql for k in ("risk", "risky", "safe", "volatil", "swing"))
    news_kw = any(
        k in ql
        for k in ("news", "headline", "latest on", "what's happening",
                  "whats happening", "announcement", "press")
    )
    _move_word = any(
        k in ql
        for k in (
            "drop", "dropped", "fall", "fell", "falling", "down", "tank", "tanked",
            "plunge", "plunged", "crash", "crashed", "jump", "jumped", "surge",
            "surged", "soar", "soared", "rose", "rise", "rising", "rally", "rallied",
            "gain", "gained", "sink", "sank", "slump", "move", "moved", "moving",
        )
    )
    move_kw = bool(tickers) and (
        any(k in ql for k in ("what happened to", "what drove", "what's behind", "whats behind"))
        or (any(w in ql for w in ("why", "what")) and _move_word)
    )
    knowledge_kw = any(
        k in ql
        for k in (
            "why", "what is a", "what's a", "whats a", "explain", "basics",
            "watch out", "watch for", "how do stock", "how does a", "should i",
            "what does", "tell me what",
        )
    )
    overview_kw = any(
        k in ql
        for k in (
            "how's the market", "hows the market", "how is the market",
            "how are the markets", "market today", "market overview",
            "market doing", "market mood", "vix", "fear gauge", "the indices",
        )
    )
    movers_kw = any(
        k in ql
        for k in (
            "gainers", "losers", "most active", "biggest movers", "top movers",
            "what's moving today", "whats moving today",
        )
    )
    dividend_kw = "dividend" in ql or "payout" in ql
    intel_kw = any(
        k in ql
        for k in (
            "analyst", "upgrade", "downgrade", "price target", "insider",
            "institutional", "earnings date", "next earnings", "report earnings",
            "who owns",
        )
    )
    fundamentals_kw = any(
        k in ql
        for k in (
            "fundamentals", "revenue", "profitab", "profit margin", "margins",
            "balance sheet", "cash flow", "income statement", "net income",
            "how much money does", "debt",
        )
    )

    portfolio_kw = any(
        k in ql
        for k in (
            "portfolio", "my holdings", "my positions", "my stocks",
            "my investments", "my account",
        )
    )

    # --- Route to a primary tool -------------------------------------------- #
    # Portfolio questions are checked FIRST: "how risky is my portfolio?" must
    # hit the portfolio tools, not the single-stock risk branch.
    if portfolio_kw:
        return _route_portfolio(q, ql, tickers, period, calls)

    if digest_kw and tickers:
        out = tools.get_watchlist_digest(tickers[:10], period=period)
        calls.append(
            {"name": "get_watchlist_digest", "input": {"tickers": tickers[:10], "period": period}, "output": out}
        )
        answer = _format_digest(out)

    elif has_compare and len(tickers) >= 2:
        out = tools.compare_stocks(tickers[:3])
        calls.append({"name": "compare_stocks", "input": {"tickers": tickers[:3]}, "output": out})
        answer = _format_compare(out)

    elif move_kw:
        out = tools.explain_price_move(tickers[0], period=period)
        calls.append(
            {"name": "explain_price_move", "input": {"ticker": tickers[0], "period": period}, "output": out}
        )
        answer = _format_price_move(out)

    elif overview_kw and not tickers:
        out = tools.get_market_overview()
        calls.append({"name": "get_market_overview", "input": {}, "output": out})
        answer = _format_market_overview(out)

    elif movers_kw:
        if "loser" in ql or "worst" in ql:
            category = "losers"
        elif "active" in ql:
            category = "active"
        else:
            category = "gainers"
        out = tools.get_market_movers(category)
        calls.append({"name": "get_market_movers", "input": {"category": category}, "output": out})
        answer = _format_movers(out)

    elif dividend_kw and tickers:
        out = tools.get_dividend_info(tickers[0])
        calls.append({"name": "get_dividend_info", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_dividend(out)

    elif intel_kw and tickers:
        out = tools.get_stock_intel(tickers[0])
        calls.append({"name": "get_stock_intel", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_intel(out)

    elif fundamentals_kw and tickers:
        out = tools.get_fundamentals(tickers[0])
        calls.append({"name": "get_fundamentals", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_fundamentals(out)

    elif news_kw and tickers:
        out = tools.get_ticker_news(tickers[0], limit=5)
        calls.append({"name": "get_ticker_news", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_news(out)

    elif metric_kw and tickers:
        out = tools.get_technical_indicators(tickers[0])
        calls.append({"name": "get_technical_indicators", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_technicals(out)

    elif metric_kw and not tickers:
        # A concept question about a metric ("what is a 200-day average?") -> RAG.
        out = tools.search_knowledge(query=q, ticker="", k=3)
        calls.append({"name": "search_knowledge", "input": {"query": q}, "output": out})
        answer = _format_knowledge(out)

    elif perf_kw and tickers:
        out = tools.get_price_performance(tickers[0], period=period)
        calls.append(
            {"name": "get_price_performance", "input": {"ticker": tickers[0], "period": period}, "output": out}
        )
        answer = _format_performance(out)

    elif filing_kw and tickers:
        out = tools.get_filing_risks(tickers[0])
        calls.append({"name": "get_filing_risks", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_filing_risks(out)

    elif risk_kw and tickers:
        out = tools.explain_stock_risk(tickers[0])
        calls.append({"name": "explain_stock_risk", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_risk(out)

    elif knowledge_kw:
        ticker = tickers[0] if tickers else ""
        out = tools.search_knowledge(query=q, ticker=ticker, k=3)
        calls.append({"name": "search_knowledge", "input": {"query": q, "ticker": ticker}, "output": out})
        answer = _format_knowledge(out)

    elif tickers:
        out = tools.get_stock_snapshot(tickers[0])
        calls.append({"name": "get_stock_snapshot", "input": {"ticker": tickers[0]}, "output": out})
        answer = _format_snapshot(out)

    else:
        answer = (
            "I couldn't spot a company or stock in your question. Try e.g. "
            "'Tell me about Apple', 'How has Nvidia done this year?', "
            "'Compare Apple and Microsoft', or 'What is a 200-day moving average?'"
        )

    return AgentResult(answer=answer, tool_calls=calls)


# --- Portfolio routing ------------------------------------------------------ #
def _route_portfolio(
    q: str, ql: str, tickers: list[str], period: str, calls: list[dict]
) -> AgentResult:
    """Sub-route a question about the user's OWN portfolio to a portfolio tool."""
    scenario_kw = any(
        k in ql
        for k in (
            "stress", "scenario", "crash", "crisis", "2008", "covid", "1987",
            "black monday", "recession", "correction", "survive", "handle a",
        )
    )
    whatif = re.search(r"\b(buy|bought|buying|sell|sold|selling)\b", ql) and re.search(
        r"\b(\d+(?:\.\d+)?)\b", ql
    )
    rebalance_kw = "rebalanc" in ql or "target allocation" in ql or "equal weight" in ql
    briefing_kw = any(
        k in ql for k in ("briefing", "brief", "what changed", "morning", "daily update")
    )
    news_kw = any(k in ql for k in ("news", "headline"))
    risk_kw = any(
        k in ql
        for k in (
            "risk", "risky", "volatil", "var", "value at risk", "drawdown",
            "sharpe", "diversif", "concentrat", "correlat", "beta",
        )
    )

    if rebalance_kw:
        out = tools.get_rebalance_plan("default", "equal_weight")
        calls.append(
            {"name": "get_rebalance_plan", "input": {"portfolio": "default", "target": "equal_weight"}, "output": out}
        )
        return AgentResult(answer=_format_rebalance(out), tool_calls=calls)

    if whatif and tickers:
        side = "SELL" if re.search(r"\b(sell|sold|selling)\b", ql) else "BUY"
        shares = float(re.search(r"\b(\d+(?:\.\d+)?)\b", ql).group(1))
        out = tools.simulate_trade(side, tickers[0], shares)
        calls.append(
            {"name": "simulate_trade", "input": {"side": side, "ticker": tickers[0], "shares": shares}, "output": out}
        )
        return AgentResult(answer=_format_what_if(out), tool_calls=calls)

    if scenario_kw:
        out = tools.run_portfolio_scenario(q, "default")
        if "error" in out or "scenarios" in out:
            out = tools.run_portfolio_scenario("covid_2020", "default")
        calls.append(
            {"name": "run_portfolio_scenario", "input": {"scenario": out.get("scenario", "covid_2020")}, "output": out}
        )
        return AgentResult(answer=_format_scenario(out), tool_calls=calls)

    if briefing_kw:
        out = tools.get_portfolio_briefing("default", period)
        calls.append(
            {"name": "get_portfolio_briefing", "input": {"portfolio": "default", "period": period}, "output": out}
        )
        return AgentResult(answer=_format_briefing(out), tool_calls=calls)

    if news_kw:
        out = tools.get_portfolio_news("default")
        calls.append(
            {"name": "get_portfolio_news", "input": {"portfolio": "default"}, "output": out}
        )
        return AgentResult(answer=_format_portfolio_news(out), tool_calls=calls)

    if risk_kw:
        out = tools.get_portfolio_risk_report("default")
        calls.append(
            {"name": "get_portfolio_risk_report", "input": {"portfolio": "default"}, "output": out}
        )
        return AgentResult(answer=_format_portfolio_risk(out), tool_calls=calls)

    out = tools.get_portfolio_overview("default")
    calls.append(
        {"name": "get_portfolio_overview", "input": {"portfolio": "default"}, "output": out}
    )
    return AgentResult(answer=_format_portfolio_overview(out), tool_calls=calls)


# --- Formatters ------------------------------------------------------------- #
def _format_snapshot(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    pe = out.get("pe_ratio")
    pe_txt = (
        f" Its P/E ratio is about {pe} (investors pay roughly ${pe:.0f} for each $1 "
        f"of yearly earnings)."
        if pe is not None
        else ""
    )
    return (
        f"{out['name']} ({out['ticker']}) is a {out['sector']} company. "
        f"{out['description']} "
        f"It trades around ${out['current_price']:.2f}, and on the latest trading "
        f"day it moved {out['change_pct'] * 100:+.2f}%. "
        f"Its market value (market cap) is {out['market_cap_human']}.{pe_txt} "
        f"Day to day, it tends to be {out['movement']}. {_DISCLAIMER}"
    )


def _format_performance(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    direction = "up" if out["return_pct"] >= 0 else "down"
    return (
        f"Over the past {out['period']}, {out['ticker']} is {direction} about "
        f"{out['return_pct']:.2f}%. Its price has been {out['movement']} — "
        f"{out['movement_detail']} {_DISCLAIMER}"
    )


def _format_compare(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't compare those: {out['error']}"
    rows = out["rows"]
    lines = [f"Here's how {', '.join(out['tickers'])} stack up on the basics:", ""]
    header = f"{'Stock':<8}{'Price':>12}{'Today':>10}{'Market cap':>16}{'P/E':>8}  Movement"
    lines.append(header)
    for r in rows:
        pe = f"{r['pe_ratio']:.1f}" if r.get("pe_ratio") is not None else "N/A"
        lines.append(
            f"{r['ticker']:<8}"
            f"{('$' + format(r['current_price'], '.2f')):>12}"
            f"{(format(r['change_pct'] * 100, '+.2f') + '%'):>10}"
            f"{r['market_cap_human']:>16}"
            f"{pe:>8}  {r['movement']}"
        )
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_risk(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't assess that: {out['error']}"
    # Lead with beta as the first number so it reads clearly.
    return (
        f"{out['ticker']} has a beta of {out['beta']:.2f}, meaning it is "
        f"{out['sensitivity']}. Day to day it tends to be {out['movement']}. "
        f"{out['plain_summary']}"
    )


def _format_technicals(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    # Lead with the 200-day average (the headline metric people ask about).
    sma200 = out.get("sma_200")
    sma50 = out.get("sma_50")
    head = (
        f"{out['ticker']}'s 200-day moving average is ${sma200:.2f}."
        if sma200 is not None
        else f"{out['ticker']} doesn't have enough history for a 200-day average yet."
    )
    bits = [head]
    bits.append(f"It's currently around ${out['price']:.2f}, which is {out['trend']}.")
    if sma50 is not None:
        bits.append(f"Its 50-day average is ${sma50:.2f}.")
    if out.get("rsi") is not None:
        bits.append(f"Its 14-day RSI is {out['rsi']:.1f} ({out['rsi_reading']}).")
    if out.get("low_52w") is not None and out.get("high_52w") is not None:
        bits.append(
            f"Over the past year it has ranged from ${out['low_52w']:.2f} to "
            f"${out['high_52w']:.2f} — currently {out['range_reading']}."
        )
    bits.append(_DISCLAIMER)
    return " ".join(bits)


def _format_digest(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't build that digest: {out['error']}"
    items = out.get("items", [])
    if not items:
        return f"Your watchlist looks empty. {_DISCLAIMER}"
    lines = ["Here's your watchlist digest:", ""]
    for it in items:
        if "error" in it:
            lines.append(f"  • {it['ticker']}: couldn't load ({it['error']})")
            continue
        lines.append(
            f"  • {it['ticker']}: {it['move_pct']:+.2f}% over {it['period']} "
            f"({it['movement_label']}, now ${it['current_price']:.2f})"
        )
        for h in it.get("headlines", [])[:2]:
            pub = f" — {h['publisher']}" if h.get("publisher") else ""
            lines.append(f"      - {h['title']}{pub}")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_price_move(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    articles = out.get("articles", [])
    head = (
        f"{out['ticker']} changed {out['move_pct']:+.2f}% over the past "
        f"{out['period']} — it {out['movement_label']}. It now trades around "
        f"${out['current_price']:.2f}."
    )
    lines = [head, ""]
    if articles:
        lines.append("Headlines from that same window that may help explain it:")
        for a in articles[:5]:
            pub = f" — {a['publisher']}" if a.get("publisher") else ""
            lines.append(f"  • {a['title']}{pub}")
    else:
        lines.append("I couldn't find news headlines in that exact window.")
    lines.append("")
    if out.get("note"):
        lines.append(out["note"])
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_filing_risks(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    results = out.get("results", [])
    if not results:
        return f"{out.get('note', 'No SEC filing found.')} {_DISCLAIMER}"
    lines = [
        f"Here's what {out['ticker']}'s SEC filing flags as key risks, in plain English:",
        "",
    ]
    for r in results[:6]:
        snippet = r["text"][:240].rsplit(" ", 1)[0]
        lines.append(f"  • {snippet}")
    lines.append("")
    src = out.get("source", "")
    url = next((r.get("url") for r in results if r.get("url")), "")
    if src:
        lines.append(f"Source: [{src}]" + (f" — {url}" if url else ""))
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_news(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't fetch the news: {out['error']}"
    articles = out.get("articles", [])
    if not articles:
        return f"I couldn't find recent news for {out.get('ticker', '')}. {_DISCLAIMER}"
    lines = [f"Here are the latest headlines for {out['ticker']}:", ""]
    for a in articles[:5]:
        pub = f" — {a['publisher']}" if a.get("publisher") else ""
        lines.append(f"  • {a['title']}{pub}")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_portfolio_overview(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't read your portfolio: {out['error']}"
    if not out.get("holdings"):
        return f"{out.get('note', 'Your portfolio is empty.')} {_DISCLAIMER}"
    t = out["totals"]
    pnl_pct = (
        f" ({t['unrealized_pnl_pct'] * 100:+.2f}%)"
        if t.get("unrealized_pnl_pct") is not None
        else ""
    )
    lines = [
        f"Your portfolio is worth ${t['market_value']:,.2f} on a cost basis of "
        f"${t['cost_basis']:,.2f} — unrealized P&L ${t['unrealized_pnl']:,.2f}{pnl_pct}, "
        f"realized P&L ${t['realized_pnl']:,.2f}.",
        "",
        f"{'Ticker':<8}{'Shares':>10}{'Value':>14}{'Weight':>9}{'P&L %':>9}",
    ]
    for h in out["holdings"]:
        pnl = (
            f"{h['unrealized_pnl_pct'] * 100:+.1f}%"
            if h.get("unrealized_pnl_pct") is not None
            else "N/A"
        )
        lines.append(
            f"{h['ticker']:<8}{h['shares']:>10g}"
            f"{('$' + format(h['market_value'], ',.2f')):>14}"
            f"{(format((h['weight'] or 0) * 100, '.1f') + '%'):>9}{pnl:>9}"
        )
    lines.append("")
    lines.append(f"Concentration: {out['concentration']} — {out['concentration_detail']}")
    for w in out.get("warnings", []):
        lines.append(f"⚠ {w}")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_portfolio_risk(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't assess your portfolio: {out['error']}"
    # plain_summary leads with volatility as the first decimal percentage,
    # which is exactly what the numeric eval extractor reads.
    lines = [
        out["plain_summary"],
        "",
        f"  • Beta vs {out['benchmark']}: {out['beta']:.2f}",
        f"  • Sharpe ratio: {out['sharpe']:.2f}",
        f"  • Max drawdown: {out['max_drawdown'] * 100:.2f}%",
        f"  • Daily VaR(95): {out['var_hist_95'] * 100:.2f}% (~${out['var_hist_95_dollars']:,.0f}); "
        f"CVaR(95): {out['cvar_95'] * 100:.2f}%",
        f"  • Concentration (HHI): {out['hhi']:.2f} — {out['concentration']}",
    ]
    pair = out.get("highest_correlated_pair")
    if pair:
        lines.append(
            f"  • Most correlated pair: {pair['tickers'][0]} & {pair['tickers'][1]} "
            f"({pair['correlation']:.2f}) — they tend to move together."
        )
    return "\n".join(lines)


def _format_portfolio_news(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't fetch your portfolio news: {out['error']}"
    items = out.get("items", [])
    if not items:
        return f"{out.get('note', 'No holdings, so no portfolio news.')} {_DISCLAIMER}"
    lines = ["Here's the latest news across your holdings (biggest positions first):", ""]
    for it in items:
        w = f" ({it['weight'] * 100:.0f}% of portfolio)" if it.get("weight") else ""
        lines.append(f"  {it['ticker']}{w}:")
        for a in it.get("articles", [])[:3]:
            pub = f" — {a['publisher']}" if a.get("publisher") else ""
            lines.append(f"    • {a['title']}{pub}")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_briefing(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't build your briefing: {out['error']}"
    if not out.get("movers"):
        return f"{out.get('note', 'Nothing to brief — no holdings yet.')} {_DISCLAIMER}"
    t = out.get("totals", {})
    day = t.get("day_change_pct")
    day_txt = f"{day * 100:+.2f}%" if day is not None else "n/a"
    lines = [
        f"Portfolio briefing ({out['period']}): your portfolio "
        f"(${t.get('market_value', 0):,.2f}) moved {day_txt} today.",
        "",
    ]
    big = out.get("biggest_mover")
    if big:
        lines.append(
            f"Biggest mover: {big['ticker']} {big['move_pct']:+.2f}% "
            f"({big['movement_label']})."
        )
    for m in out["movers"]:
        if "error" in m:
            lines.append(f"  • {m['ticker']}: couldn't load ({m['error']})")
            continue
        lines.append(f"  • {m['ticker']}: {m['move_pct']:+.2f}% — now ${m['current_price']:.2f}")
        for h in m.get("headlines", [])[:1]:
            pub = f" — {h['publisher']}" if h.get("publisher") else ""
            lines.append(f"      - {h['title']}{pub}")
    for w in out.get("warnings", []):
        lines.append(f"⚠ {w}")
    unread = out.get("unread_notifications", [])
    if unread:
        lines.append(f"You have {len(unread)} unread alert(s); latest: {unread[0]['title']}")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_scenario(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't run that scenario: {out['error']}"
    if "scenarios" in out:
        names = ", ".join(s["id"] for s in out["scenarios"])
        return f"Available stress-test scenarios: {names}. {_DISCLAIMER}"
    lines = [
        f"In a {out['label']} ({out['market_drop_pct']:+.1f}% market move), your "
        f"portfolio would lose an estimated {abs(out['estimated_loss_pct']):.2f}% "
        f"(~${abs(out['estimated_loss']):,.0f}), leaving about "
        f"${out['estimated_value_after']:,.0f} of ${out['total_value']:,.0f}.",
        "",
    ]
    if out.get("vs_daily_var") is not None:
        lines.append(
            f"For scale, that's roughly {out['vs_daily_var']:.0f}× your typical "
            f"bad day (daily 95% VaR)."
        )
    for p in out.get("positions", [])[:6]:
        lines.append(
            f"  • {p['ticker']}: beta {p['beta']:.2f} → est. {p['estimated_move_pct']:+.1f}% "
            f"(${p['estimated_change']:,.0f})"
        )
    lines.append("")
    lines.append(out.get("note", _DISCLAIMER))
    return "\n".join(lines)


def _format_what_if(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't simulate that: {out['error']}"
    tr = out["trade"]
    lines = [
        f"If you {tr['side'].lower()} {tr['shares']:g} {tr['ticker']} "
        f"(~${tr['est_value']:,.0f} at ${tr['est_price']:.2f}):",
        "",
    ]
    before, after = out.get("before"), out.get("after")
    if before is None:
        lines.append(
            f"Starting from an empty portfolio, you'd have volatility of "
            f"{after['volatility_annual_pct']:.2f}% a year and beta {after['beta']:.2f}."
        )
    else:
        rows = [
            ("Volatility (yr)", "volatility_annual_pct", "%"),
            ("Beta", "beta", ""),
            ("Sharpe", "sharpe", ""),
            ("Daily VaR(95)", "var_hist_95_pct", "%"),
            ("Top position", "top_weight_pct", "%"),
        ]
        lines.append(f"{'Metric':<18}{'Before':>10}{'After':>10}")
        for label, key, unit in rows:
            lines.append(
                f"{label:<18}{format(before[key], '.2f') + unit:>10}"
                f"{format(after[key], '.2f') + unit:>10}"
            )
    lines.append("")
    lines.append(out.get("note", _DISCLAIMER))
    return "\n".join(lines)


def _format_rebalance(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't build a rebalance plan: {out['error']}"
    trades = out.get("suggested_trades", [])
    lines = [
        f"To move your ${out['total_value']:,.2f} portfolio to {out['target']}:",
        "",
    ]
    if not trades:
        lines.append("You're already within 0.5% of the target — no trades needed.")
    for tr in trades:
        lines.append(
            f"  • {tr['action']} {tr['shares']:g} {tr['ticker']} (~${tr['est_value']:,.0f})"
        )
    lines.append("")
    lines.append(out.get("note", _DISCLAIMER))
    return "\n".join(lines)


def _format_market_overview(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't check the market: {out['error']}"
    lines = [out.get("plain_summary", "Here's the market right now:"), ""]
    for i in out.get("indices", []):
        lines.append(f"  • {i['name']}: {i['level']:,.2f} ({i['change_pct'] * 100:+.2f}%)")
    vix = out.get("vix")
    if vix:
        lines.append(f"  • VIX: {vix['level']:.2f} — mood: {out.get('mood', 'unknown')}")
    if out.get("ten_year_yield_pct") is not None:
        lines.append(f"  • 10-year Treasury yield: {out['ten_year_yield_pct']:.2f}%")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_movers(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    rows = out.get("rows", [])
    if not rows:
        return f"{out.get('note', 'No mover data right now.')} {_DISCLAIMER}"
    label = {"gainers": "biggest gainers", "losers": "biggest losers", "active": "most active stocks"}
    lines = [f"Today's {label.get(out['category'], 'movers')}:", ""]
    for r in rows:
        chg = f"{r['change_pct'] * 100:+.2f}%" if r.get("change_pct") is not None else "n/a"
        lines.append(f"  • {r['ticker']}: {chg} — ${r['price']:.2f} ({r['name']})")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_dividend(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    lines = [out.get("plain_summary", "")]
    recent = out.get("recent", [])
    if recent:
        lines.append("")
        lines.append("Recent payments per share:")
        for r in recent[:4]:
            lines.append(f"  • {r['date']}: ${r['amount']:.4f}")
    if out.get("ex_dividend_date"):
        lines.append(f"Next ex-dividend date: {out['ex_dividend_date']} (you must own it before then to get the payment).")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_intel(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    lines = [out.get("plain_summary", ""), ""]
    upgrades = out.get("upgrades", [])
    if upgrades:
        lines.append("Recent analyst actions:")
        for u in upgrades[:4]:
            frm = f" (from {u['from_grade']})" if u.get("from_grade") else ""
            lines.append(f"  • {u['date']}: {u['firm']} → {u['to_grade']}{frm}")
    insiders = out.get("insiders", [])
    if insiders:
        lines.append("Recent insider transactions:")
        for i in insiders[:3]:
            val = f" (~${i['value']:,.0f})" if i.get("value") else ""
            lines.append(f"  • {i['date']}: {i['insider']} ({i['position']}) — {i['transaction']}{val}")
    holders = out.get("institutional", [])
    if holders:
        lines.append("Top institutional holders: " + ", ".join(h["holder"] for h in holders[:3]))
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_fundamentals(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't look that up: {out['error']}"
    lines = [out.get("plain_summary", ""), ""]
    rows = [
        ("Revenue", out.get("revenue_human")),
        ("Net income", out.get("net_income_human")),
        ("Free cash flow", out.get("free_cash_flow_human")),
    ]
    for label, val in rows:
        if val:
            lines.append(f"  • {label}: {val}")
    if out.get("gross_margin") is not None:
        lines.append(f"  • Gross margin: {out['gross_margin'] * 100:.1f}%")
    if out.get("debt_to_equity") is not None:
        lines.append(f"  • Debt-to-equity: {out['debt_to_equity']:.2f} ({out.get('debt_reading', '')})")
    if out.get("period"):
        lines.append(f"  • Period: {out['period']}")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def _format_knowledge(out: dict) -> str:
    if "error" in out:
        return f"Sorry, I couldn't search the knowledge library: {out['error']}"
    results = out.get("results", [])
    if not results:
        return (
            "I couldn't find anything in the knowledge library yet — it may not be "
            "ingested. Run `python -m portfolio_risk.rag.ingest` first. " + _DISCLAIMER
        )
    lines = ["Here's what I found:", ""]
    for r in results[:3]:
        snippet = r["text"][:240].rsplit(" ", 1)[0]
        lines.append(f"  - [{r['source']}] {snippet}...")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)
