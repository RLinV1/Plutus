"""Portfolio tools end-to-end on a seeded temp DB under deterministic mock data."""

from __future__ import annotations

import json

import pytest

from evals.seed_portfolio import ensure_seeded
from portfolio_risk import tools
from portfolio_risk.agent import mock_agent


@pytest.fixture
def seeded(portfolio_db):
    ensure_seeded()
    yield


def _assert_json_clean(obj, path="root"):
    """Every leaf must be JSON-native (no numpy scalars, no NaN)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_json_clean(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_json_clean(v, f"{path}[{i}]")
    else:
        assert obj is None or isinstance(obj, (str, int, float, bool)), (
            f"{path} has non-JSON type {type(obj)}"
        )
        if isinstance(obj, float):
            assert obj == obj, f"{path} is NaN"
    json.dumps(obj)  # the ultimate check


def test_overview_totals_and_weights(seeded):
    out = tools.get_portfolio_overview()
    assert "error" not in out
    _assert_json_clean(out)
    tickers = [h["ticker"] for h in out["holdings"]]
    assert sorted(tickers) == ["AAPL", "JNJ", "MSFT", "NVDA"]
    # AAPL: 15 shares (10 + 5); NVDA: 10 (12 - 2)
    by = {h["ticker"]: h for h in out["holdings"]}
    assert by["AAPL"]["shares"] == 15
    assert by["NVDA"]["shares"] == 10
    weights = sum(h["weight"] for h in out["holdings"])
    assert weights == pytest.approx(1.0, abs=1e-3)
    assert out["totals"]["market_value"] > 0
    assert out["totals"]["realized_pnl"] != 0  # the NVDA sell realized something
    assert out["concentration"] in (
        "all in one position", "highly concentrated", "concentrated",
        "moderately diversified", "well diversified",
    )


def test_risk_report_is_deterministic_and_clean(seeded):
    a = tools.get_portfolio_risk_report()
    b = tools.get_portfolio_risk_report()
    assert "error" not in a
    _assert_json_clean(a)
    # Monte Carlo VaR is seeded — identical across calls.
    assert a["var_mc_95"] == b["var_mc_95"]
    assert a["volatility"] == b["volatility"]
    assert a["volatility"] > 0
    assert a["var_hist_95"] > 0
    # var_hist_95 is rounded to 4dp in the payload; dollars come from the
    # unrounded value, so allow that rounding slack.
    assert a["var_hist_95_dollars"] == pytest.approx(
        a["var_hist_95"] * a["market_value"], rel=5e-3
    )
    n = len(a["correlation"]["tickers"])
    assert len(a["correlation"]["matrix"]) == n
    assert a["highest_correlated_pair"] is not None


def test_scenario_stress_math(seeded):
    out = tools.run_portfolio_scenario("covid_2020")
    assert "error" not in out
    _assert_json_clean(out)
    assert out["method"] == "beta_approximation"
    assert out["estimated_loss"] < 0  # a crash loses money
    assert out["estimated_value_after"] == pytest.approx(
        out["total_value"] + out["estimated_loss"], abs=0.05
    )
    # Per-position losses sum to the total.
    assert sum(p["estimated_change"] for p in out["positions"]) == pytest.approx(
        out["estimated_loss"], abs=0.05
    )
    listing = tools.run_portfolio_scenario("list")
    assert {s["id"] for s in listing["scenarios"]} >= {"gfc_2008", "covid_2020"}
    # Aliases resolve.
    alias = tools.run_portfolio_scenario("a 2008 style crash")
    assert alias["scenario"] == "gfc_2008"


def test_simulate_trade_read_only_with_sane_deltas(seeded):
    before_txns = len(
        __import__("portfolio_risk.portfolio.store", fromlist=["store"]).list_transactions(
            "default"
        )
    )
    out = tools.simulate_trade("BUY", "NVDA", 100)
    assert "error" not in out
    _assert_json_clean(out)
    # A huge buy of one name concentrates the portfolio.
    assert out["after"]["top_weight_pct"] > out["before"]["top_weight_pct"]
    assert out["deltas"]["top_weight_pct"] > 0
    # Nothing was written.
    after_txns = len(
        __import__("portfolio_risk.portfolio.store", fromlist=["store"]).list_transactions(
            "default"
        )
    )
    assert after_txns == before_txns

    err = tools.simulate_trade("SELL", "JNJ", 999)
    assert "error" in err
    err2 = tools.simulate_trade("SELL", "KO", 1)  # not held
    assert "error" in err2


def test_rebalance_plan_targets_equal_weight(seeded):
    out = tools.get_rebalance_plan()
    assert "error" not in out
    _assert_json_clean(out)
    tw = out["target_weights"]
    assert all(w == pytest.approx(0.25, abs=1e-6) for w in tw.values())
    # Buys and sells should roughly net out (rebalance, not deposit).
    net = sum(
        t["est_value"] * (1 if t["action"] == "BUY" else -1)
        for t in out["suggested_trades"]
    )
    assert abs(net) < 0.02 * out["total_value"]

    custom = tools.get_rebalance_plan("default", '{"AAPL": 0.5, "SPY": 0.5}')
    assert "error" not in custom
    assert custom["target_weights"]["SPY"] == pytest.approx(0.5)
    # Everything not in the target gets sold.
    sells = {t["ticker"] for t in custom["suggested_trades"] if t["action"] == "SELL"}
    assert {"MSFT", "NVDA", "JNJ"} <= sells


def test_briefing_and_news(seeded):
    b = tools.get_portfolio_briefing()
    assert "error" not in b
    _assert_json_clean(b)
    assert len(b["movers"]) == 4
    assert b["biggest_mover"] is not None

    n = tools.get_portfolio_news()
    assert "error" not in n
    weights = [it["weight"] for it in n["items"]]
    assert weights == sorted(weights, reverse=True)
    assert all(it["articles"] for it in n["items"])


def test_empty_portfolio_is_friendly(portfolio_db):
    out = tools.get_portfolio_overview("empty")
    assert "error" not in out
    assert out["holdings"] == []
    assert "No current holdings" in out["note"]
    risk = tools.get_portfolio_risk_report("empty")
    assert "error" in risk


def test_mock_agent_portfolio_routing(seeded):
    cases = {
        "How risky is my portfolio?": "get_portfolio_risk_report",
        "Give me an overview of my portfolio": "get_portfolio_overview",
        "Give me my portfolio briefing for today": "get_portfolio_briefing",
        "How would my portfolio handle a COVID-style crash?": "run_portfolio_scenario",
        "Any news on my holdings?": "get_portfolio_news",
        "Rebalance my portfolio to equal weight": "get_rebalance_plan",
        "What would buying 10 shares of NVDA do to my portfolio?": "simulate_trade",
    }
    for question, expected_tool in cases.items():
        res = mock_agent.run(question)
        assert expected_tool in res.tool_names(), (
            f"{question!r} routed to {res.tool_names()}, expected {expected_tool}"
        )
        assert res.answer and "Sorry" not in res.answer.split("\n")[0], (
            f"{question!r} produced: {res.answer[:120]}"
        )
    # Single-stock questions must still route to single-stock tools.
    res = mock_agent.run("Is Apple risky?")
    assert res.tool_names() == ["explain_stock_risk"]
