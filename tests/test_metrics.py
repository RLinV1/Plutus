"""Golden-value tests for the risk math.

Two layers of assurance:
1. Fixed hand-computed numbers on tiny inputs (no dependency).
2. Cross-checks against ``empyrical-reloaded`` on the fixture series.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import norm

from portfolio_risk.risk import metrics


# --------------------------------------------------------------------------- #
# Fixed hand-computed cases
# --------------------------------------------------------------------------- #
def test_historical_var_fixed():
    r = np.array([-0.05, -0.02, 0.0, 0.01, 0.03])
    # np.percentile(r, 5) = -0.05 + 0.2*(0.03) = -0.044  ->  VaR = 0.044
    assert metrics.value_at_risk_historical(r, 0.95) == pytest.approx(0.044, abs=1e-9)


def test_max_drawdown_fixed():
    r = np.array([0.10, -0.50, 0.10])
    # wealth: 1.10, 0.55, 0.605; peak 1.10 -> min dd = 0.55/1.10 - 1 = -0.5
    assert metrics.max_drawdown(r) == pytest.approx(-0.5, abs=1e-9)


def test_var_signs_and_positivity():
    r = np.array([-0.05, -0.02, 0.0, 0.01, 0.03])
    assert metrics.value_at_risk_historical(r, 0.95) > 0
    assert metrics.value_at_risk_parametric(r, 0.95) > 0
    assert metrics.conditional_var(r, 0.95) >= metrics.value_at_risk_historical(r, 0.95) - 1e-9


def test_parametric_var_matches_closed_form():
    r = np.array([0.01, -0.02, 0.015, -0.005, 0.0, 0.02, -0.03])
    mu, sigma = np.mean(r), np.std(r, ddof=1)
    expected = -(mu + sigma * norm.ppf(0.05))
    assert metrics.value_at_risk_parametric(r, 0.95) == pytest.approx(expected, rel=1e-9)


def test_portfolio_vol_single_asset_equals_annualized_vol(returns_series):
    cov = np.array([[returns_series.var(ddof=1)]])
    pv = metrics.portfolio_volatility(np.array([1.0]), cov)
    av = metrics.annualized_volatility(returns_series)
    assert pv == pytest.approx(av, rel=1e-9)


def test_monte_carlo_var_converges_to_parametric():
    mean = np.array([0.0005, 0.0003])
    cov = np.array([[0.013**2, 0.00005], [0.00005, 0.011**2]])
    w = np.array([0.6, 0.4])
    port_mean = float(w @ mean)
    port_sigma = float(np.sqrt(w @ cov @ w))
    parametric = -(port_mean + port_sigma * norm.ppf(0.05))
    mc = metrics.value_at_risk_monte_carlo(mean, cov, w, 0.95, n_sims=20000, seed=0)
    assert mc == pytest.approx(parametric, rel=0.05)


def test_monte_carlo_var_deterministic():
    mean = np.array([0.0005, 0.0003])
    cov = np.array([[0.013**2, 0.0], [0.0, 0.011**2]])
    w = np.array([0.5, 0.5])
    a = metrics.value_at_risk_monte_carlo(mean, cov, w, seed=42)
    b = metrics.value_at_risk_monte_carlo(mean, cov, w, seed=42)
    assert a == b


# --------------------------------------------------------------------------- #
# Cross-checks vs empyrical-reloaded
# --------------------------------------------------------------------------- #
def test_vs_empyrical(returns_series, benchmark_series):
    empyrical = pytest.importorskip("empyrical")
    r = returns_series

    assert metrics.annualized_volatility(r) == pytest.approx(
        empyrical.annual_volatility(r), rel=1e-6
    )
    assert metrics.sharpe_ratio(r, rf_annual=0.0) == pytest.approx(
        empyrical.sharpe_ratio(r, risk_free=0.0), rel=1e-6
    )
    assert metrics.sharpe_ratio(r, rf_annual=0.02) == pytest.approx(
        empyrical.sharpe_ratio(r, risk_free=0.02 / 252), rel=1e-6
    )
    assert metrics.max_drawdown(r) == pytest.approx(
        empyrical.max_drawdown(r), rel=1e-6
    )
    assert metrics.value_at_risk_historical(r, 0.95) == pytest.approx(
        -empyrical.value_at_risk(r, cutoff=0.05), rel=1e-6
    )
    assert metrics.conditional_var(r, 0.95) == pytest.approx(
        -empyrical.conditional_value_at_risk(r, cutoff=0.05), rel=1e-6
    )
    assert metrics.beta(r, benchmark_series) == pytest.approx(
        empyrical.beta(r, benchmark_series), rel=1e-6
    )
