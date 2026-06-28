"""Pure portfolio-risk metrics.

All functions take *returns* (not prices) and have no I/O — they are fully
deterministic and unit-testable. Implementations are intentionally written to
agree with ``empyrical-reloaded`` where an equivalent exists (see tests), so the
numbers can be cross-checked against an independent library.

Sign conventions (locked in tests):
- VaR / CVaR are returned as **positive loss fractions** (a 0.03 VaR means a
  3% loss). They describe how much you could lose.
- Max drawdown is returned as a **negative fraction** (-0.20 means a 20% peak-
  to-trough decline).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..config import TRADING_DAYS

ArrayLike = "np.ndarray | pd.Series | list"


def _as_1d(returns) -> np.ndarray:
    arr = np.asarray(returns, dtype=float).ravel()
    return arr[~np.isnan(arr)]


# --------------------------------------------------------------------------- #
# Single-series metrics
# --------------------------------------------------------------------------- #
def annualized_volatility(returns, periods: int = TRADING_DAYS) -> float:
    """Annualized standard deviation of returns (sample std, ddof=1)."""
    r = _as_1d(returns)
    return float(np.std(r, ddof=1) * np.sqrt(periods))


def sharpe_ratio(returns, rf_annual: float = 0.0, periods: int = TRADING_DAYS) -> float:
    """Annualized Sharpe ratio.

    Matches ``empyrical.sharpe_ratio(returns, risk_free=rf_annual/periods)``:
    excess = returns - per-period rf; mean(excess)/std(excess, ddof=1)*sqrt(P).
    """
    r = _as_1d(returns)
    rf_period = rf_annual / periods
    excess = r - rf_period
    sd = np.std(excess, ddof=1)
    if sd == 0:
        return float("nan")
    return float(np.mean(excess) / sd * np.sqrt(periods))


def beta(asset_returns, benchmark_returns) -> float:
    """Beta of an asset vs a benchmark: cov(a, b) / var(b) (ddof=1, aligned)."""
    a = np.asarray(asset_returns, dtype=float).ravel()
    b = np.asarray(benchmark_returns, dtype=float).ravel()
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    if len(a) < 2:
        return float("nan")
    cov = np.cov(a, b, ddof=1)
    var_b = cov[1, 1]
    if var_b == 0:
        return float("nan")
    return float(cov[0, 1] / var_b)


def max_drawdown(returns) -> float:
    """Largest peak-to-trough decline of cumulative wealth (negative fraction)."""
    r = _as_1d(returns)
    if r.size == 0:
        return float("nan")
    wealth = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(wealth)
    drawdown = wealth / peak - 1.0
    return float(drawdown.min())


def correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlation of the columns (assets)."""
    return returns_df.corr()


# --------------------------------------------------------------------------- #
# Value at Risk family (positive loss fractions)
# --------------------------------------------------------------------------- #
def value_at_risk_historical(returns, level: float = 0.95) -> float:
    """Historical VaR: negative of the (1-level) return quantile."""
    r = _as_1d(returns)
    q = np.percentile(r, 100.0 * (1.0 - level))
    return float(-q)


def value_at_risk_parametric(returns, level: float = 0.95) -> float:
    """Gaussian (variance-covariance) VaR using sample mean/std (ddof=1)."""
    r = _as_1d(returns)
    mu = np.mean(r)
    sigma = np.std(r, ddof=1)
    z = norm.ppf(1.0 - level)  # negative for level>0.5
    return float(-(mu + sigma * z))


def conditional_var(returns, level: float = 0.95) -> float:
    """Conditional VaR / Expected Shortfall (positive loss fraction).

    Matches ``empyrical.conditional_value_at_risk``: mean of the worst
    ``(1-level)`` fraction of returns, negated.
    """
    r = _as_1d(returns)
    cutoff = 1.0 - level
    idx = int((len(r) - 1) * cutoff)
    worst = np.partition(r, idx)[: idx + 1]
    return float(-np.mean(worst))


# --------------------------------------------------------------------------- #
# Portfolio-level (vector) metrics
# --------------------------------------------------------------------------- #
def portfolio_returns(returns_df: pd.DataFrame, weights: np.ndarray) -> pd.Series:
    """Daily portfolio return series for the given column-aligned weights."""
    w = np.asarray(weights, dtype=float)
    return returns_df.mul(w, axis=1).sum(axis=1)


def portfolio_expected_return(
    weights: np.ndarray, mean_returns: np.ndarray, periods: int = TRADING_DAYS
) -> float:
    """Annualized expected return: (w . mean_daily) * periods."""
    w = np.asarray(weights, dtype=float)
    mu = np.asarray(mean_returns, dtype=float)
    return float(np.dot(w, mu) * periods)


def portfolio_volatility(
    weights: np.ndarray, cov: np.ndarray, periods: int = TRADING_DAYS
) -> float:
    """Annualized portfolio volatility: sqrt(w' Σ w) * sqrt(periods).

    ``cov`` is the daily covariance matrix (e.g. returns_df.cov()).
    """
    w = np.asarray(weights, dtype=float)
    cov = np.asarray(cov, dtype=float)
    daily_var = float(w @ cov @ w)
    daily_var = max(daily_var, 0.0)
    return float(np.sqrt(daily_var) * np.sqrt(periods))


def value_at_risk_monte_carlo(
    mean_returns: np.ndarray,
    cov: np.ndarray,
    weights: np.ndarray,
    level: float = 0.95,
    n_sims: int = 10000,
    seed: int = 0,
) -> float:
    """Monte-Carlo VaR: simulate multivariate-normal daily returns and take the
    (1-level) quantile of simulated portfolio P/L. Positive loss fraction.

    Deterministic for a fixed ``seed``. For Gaussian inputs this converges to
    the parametric portfolio VaR.
    """
    mean = np.asarray(mean_returns, dtype=float)
    cov = np.asarray(cov, dtype=float)
    w = np.asarray(weights, dtype=float)
    rng = np.random.default_rng(seed)
    sims = rng.multivariate_normal(mean, cov, size=n_sims)
    pnl = sims @ w
    q = np.percentile(pnl, 100.0 * (1.0 - level))
    return float(-q)
