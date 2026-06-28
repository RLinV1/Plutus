from __future__ import annotations

import pytest

from portfolio_risk.risk.portfolio import (
    Portfolio,
    PortfolioError,
    compute_portfolio_report,
)


def test_validate_rejects_empty():
    with pytest.raises(PortfolioError):
        Portfolio({}).validate()


def test_normalize_sums_to_one():
    p = Portfolio({"A": 3.0, "B": 1.0}).normalized()
    assert sum(p.holdings.values()) == pytest.approx(1.0)
    assert p.holdings["A"] == pytest.approx(0.75)


def test_weights_order():
    p = Portfolio({"A": 0.6, "B": 0.4})
    assert list(p.weights(["B", "A"])) == pytest.approx([0.4, 0.6])


def test_report_has_all_metrics(returns_df, benchmark_series):
    p = Portfolio({"AAA": 0.5, "BBB": 0.3, "CCC": 0.2})
    rep = compute_portfolio_report(p, returns_df, benchmark_series)
    for key in (
        "expected_return", "volatility", "sharpe", "beta", "max_drawdown",
        "var_hist_95", "var_param_95", "var_mc_95", "cvar_95",
    ):
        assert key in rep
        assert isinstance(rep[key], float)
    assert rep["max_drawdown"] <= 0
    assert rep["var_hist_95"] >= 0


def test_report_missing_ticker_raises(returns_df, benchmark_series):
    p = Portfolio({"ZZZ": 1.0})
    with pytest.raises(PortfolioError):
        compute_portfolio_report(p, returns_df, benchmark_series)
