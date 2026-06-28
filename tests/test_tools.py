"""Tool-level + mock-agent tests, all on deterministic mock data (offline)."""

from __future__ import annotations

from portfolio_risk import tools
from portfolio_risk.agent import mock_agent


def test_get_stock_snapshot_mock():
    out = tools.get_stock_snapshot("AAPL")
    assert "error" not in out
    for key in ("ticker", "name", "sector", "current_price", "change_pct",
                "market_cap_human", "pe_ratio", "movement"):
        assert key in out
    assert out["ticker"] == "AAPL"
    assert out["current_price"] > 0


def test_get_price_performance_mock():
    out = tools.get_price_performance("NVDA", period="1y")
    assert "error" not in out
    assert out["period"] == "1y"
    assert "total_return" in out and "return_pct" in out
    assert out["movement"] in ("calm", "average", "bumpy", "unknown")


def test_compare_stocks_mock():
    out = tools.compare_stocks(["AAPL", "MSFT"])
    assert "error" not in out
    assert out["tickers"] == ["AAPL", "MSFT"]
    assert len(out["rows"]) == 2
    assert out["rows"][0]["ticker"] == "AAPL"


def test_compare_stocks_needs_two():
    out = tools.compare_stocks(["AAPL"])
    assert "error" in out


def test_explain_stock_risk_mock():
    out = tools.explain_stock_risk("TSLA")
    assert "error" not in out
    assert out["ticker"] == "TSLA"
    assert out["beta"] == out["beta"]  # not NaN
    assert out["movement"] in ("calm", "average", "bumpy", "unknown")


def test_get_technical_indicators_mock():
    out = tools.get_technical_indicators("AAPL")
    assert "error" not in out
    assert out["sma_200"] is not None
    assert out["sma_50"] is not None
    assert "200-day" in out["trend"]
    assert 0.0 <= out["rsi"] <= 100.0


def test_explain_price_move_mock():
    out = tools.explain_price_move("AAPL", period="6mo")
    assert "error" not in out
    assert out["ticker"] == "AAPL"
    assert out["period"] == "6mo"
    assert "move_pct" in out and "move_frac" in out
    assert out["direction"] in ("up", "down")
    assert out["movement_label"]
    assert isinstance(out["articles"], list)
    assert out["window_start"] <= out["window_end"]


def test_get_filing_risks_mock():
    out = tools.get_filing_risks("AAPL")
    assert "error" not in out
    assert out["ticker"] == "AAPL"
    assert len(out["results"]) > 0
    r = out["results"][0]
    assert r["text"] and r["source"]
    assert "sec.gov" in r["url"]  # every source carries a verifiable link


def test_get_watchlist_digest_mock():
    out = tools.get_watchlist_digest(["AAPL", "MSFT"], period="1mo")
    assert "error" not in out
    assert len(out["items"]) == 2
    it = out["items"][0]
    assert it["ticker"] == "AAPL"
    assert "move_pct" in it and isinstance(it["headlines"], list)


def test_get_watchlist_digest_needs_a_ticker():
    assert "error" in tools.get_watchlist_digest([])


def test_get_fundamentals_mock():
    out = tools.get_fundamentals("AAPL")
    assert "error" not in out
    assert out["ticker"] == "AAPL"
    assert out["revenue"] > 0
    assert out["growth_reading"] and out["margin_reading"] and out["debt_reading"]
    assert out["plain_summary"]


def test_get_dividend_info_mock():
    out = tools.get_dividend_info("KO")
    assert "error" not in out
    assert out["ticker"] == "KO"
    assert "dividend_yield_pct" in out and out["reading"]
    if out["pays_dividend"]:
        assert out["recent"] and out["ttm_dividend"] > 0


def test_get_stock_intel_mock():
    out = tools.get_stock_intel("AAPL")
    assert "error" not in out
    assert out["next_earnings"]
    assert out["upgrades"] and out["insiders"] and out["institutional"]
    # Mock transactions are exactly "Purchase" or "Sale".
    assert out["insider_buys"] + out["insider_sells"] == len(out["insiders"])
    assert out["plain_summary"]


def test_get_market_overview_mock():
    out = tools.get_market_overview()
    assert "error" not in out
    assert len(out["indices"]) == 3
    assert out["vix"]["level"] > 0
    assert out["mood"] in ("calm", "normal", "nervous", "fearful")
    assert out["plain_summary"]


def test_get_market_movers_mock():
    out = tools.get_market_movers("gainers")
    assert out["category"] == "gainers"
    assert len(out["rows"]) == 5
    changes = [r["change_pct"] for r in out["rows"]]
    assert changes == sorted(changes, reverse=True)


def test_get_market_movers_losers_sorted_ascending():
    out = tools.get_market_movers("losers")
    assert out["category"] == "losers"
    changes = [r["change_pct"] for r in out["rows"]]
    assert changes == sorted(changes)


def test_mock_agent_dividend_question():
    res = mock_agent.run("What is Apple's dividend yield?")
    assert "get_dividend_info" in res.tool_names()


def test_mock_agent_fundamentals_question():
    res = mock_agent.run("Is Apple profitable?")
    assert "get_fundamentals" in res.tool_names()


def test_mock_agent_earnings_date_question():
    res = mock_agent.run("When does Apple report earnings?")
    assert "get_stock_intel" in res.tool_names()


def test_mock_agent_analyst_question():
    res = mock_agent.run("Any analyst upgrades for Microsoft lately?")
    assert "get_stock_intel" in res.tool_names()


def test_mock_agent_market_overview_question():
    res = mock_agent.run("How is the market doing today?")
    assert "get_market_overview" in res.tool_names()


def test_mock_agent_movers_question():
    res = mock_agent.run("What are today's biggest gainers?")
    assert "get_market_movers" in res.tool_names()


def test_mock_agent_dividend_concept_stays_rag():
    # "What is a dividend?" has no ticker -> knowledge library, not dividend tool.
    res = mock_agent.run("What is a dividend?")
    assert "search_knowledge" in res.tool_names()
    assert "get_dividend_info" not in res.tool_names()


def test_mock_agent_filing_risks_question():
    res = mock_agent.run("What are the risk factors in Apple's 10-K?")
    assert "get_filing_risks" in res.tool_names()


def test_mock_agent_digest_question():
    res = mock_agent.run("Give me a digest of Apple and Microsoft")
    assert "get_watchlist_digest" in res.tool_names()


def test_mock_agent_is_risky_stays_volatility_not_filing():
    res = mock_agent.run("Is Tesla a risky stock?")
    assert "explain_stock_risk" in res.tool_names()
    assert "get_filing_risks" not in res.tool_names()


def test_mock_agent_why_did_it_move_question():
    res = mock_agent.run("Why did Apple drop this month?")
    assert "explain_price_move" in res.tool_names()


def test_mock_agent_why_risky_is_not_a_move_question():
    # "why ... risky" must route to risk, not the price-move explainer.
    res = mock_agent.run("Why is Tesla so risky?")
    assert "explain_stock_risk" in res.tool_names()
    assert "explain_price_move" not in res.tool_names()


def test_mock_agent_snapshot_question():
    res = mock_agent.run("Tell me about Apple")
    assert "get_stock_snapshot" in res.tool_names()


def test_mock_agent_performance_question():
    res = mock_agent.run("How has Nvidia performed over the past year?")
    assert "get_price_performance" in res.tool_names()
    assert "%" in res.answer


def test_mock_agent_compare_question():
    res = mock_agent.run("Compare Apple and Microsoft")
    assert "compare_stocks" in res.tool_names()


def test_mock_agent_technicals_question():
    res = mock_agent.run("Is Apple above its 200-day average?")
    assert "get_technical_indicators" in res.tool_names()


def test_mock_agent_concept_question_uses_rag():
    res = mock_agent.run("What is a 200-day moving average?")
    assert "search_knowledge" in res.tool_names()


def test_mock_agent_risk_question():
    res = mock_agent.run("Is Tesla a risky stock?")
    assert "explain_stock_risk" in res.tool_names()
