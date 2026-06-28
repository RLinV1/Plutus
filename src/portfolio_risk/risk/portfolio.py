"""Portfolio model and the single-call risk report.

``compute_portfolio_report`` is the canonical aggregation reused by BOTH the
MCP tools and the eval harness's ground-truth generator, so the eval's "truth"
is computed by the exact same engine the agent calls.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import DEFAULT_RF_ANNUAL, TRADING_DAYS
from . import metrics


class PortfolioError(ValueError):
    pass


@dataclass(frozen=True)
class Portfolio:
    """A set of holdings as ticker -> weight."""

    holdings: dict[str, float]

    def tickers(self) -> list[str]:
        return list(self.holdings.keys())

    def weights(self, order: list[str]) -> np.ndarray:
        """Weight vector aligned to ``order`` (e.g. a returns frame's columns)."""
        return np.array([self.holdings[t] for t in order], dtype=float)

    def validate(self) -> None:
        if not self.holdings:
            raise PortfolioError("Portfolio has no holdings.")
        for t, w in self.holdings.items():
            if not isinstance(t, str) or not t.strip():
                raise PortfolioError(f"Invalid ticker: {t!r}")
            if not np.isfinite(w):
                raise PortfolioError(f"Weight for {t} is not finite: {w!r}")
        total = sum(self.holdings.values())
        if total <= 0:
            raise PortfolioError(f"Weights sum to {total}; must be positive.")

    def normalized(self) -> "Portfolio":
        """Return a copy with weights renormalized to sum to 1."""
        total = sum(self.holdings.values())
        return Portfolio({t: w / total for t, w in self.holdings.items()})


def compute_portfolio_report(
    portfolio: Portfolio,
    returns_df: pd.DataFrame,
    benchmark_returns: pd.Series,
    rf_annual: float = DEFAULT_RF_ANNUAL,
    periods: int = TRADING_DAYS,
) -> dict:
    """Compute every headline risk metric for a portfolio.

    Parameters
    ----------
    returns_df: daily returns, columns are the portfolio tickers.
    benchmark_returns: daily returns of the benchmark, aligned to returns_df.
    """
    portfolio.validate()
    p = portfolio.normalized()
    order = list(returns_df.columns)
    missing = [t for t in p.tickers() if t not in order]
    if missing:
        raise PortfolioError(f"Returns frame missing tickers: {missing}")

    w = p.weights(order)
    port_ret = metrics.portfolio_returns(returns_df, w)
    cov = returns_df.cov().to_numpy()
    mean_daily = returns_df.mean().to_numpy()

    report = {
        "tickers": order,
        "weights": [float(x) for x in w],
        "n_days": int(len(returns_df)),
        "rf_annual": float(rf_annual),
        "expected_return": metrics.portfolio_expected_return(w, mean_daily, periods),
        "volatility": metrics.portfolio_volatility(w, cov, periods),
        "sharpe": metrics.sharpe_ratio(port_ret, rf_annual, periods),
        "beta": metrics.beta(port_ret, benchmark_returns),
        "max_drawdown": metrics.max_drawdown(port_ret),
        "var_hist_95": metrics.value_at_risk_historical(port_ret, 0.95),
        "var_param_95": metrics.value_at_risk_parametric(port_ret, 0.95),
        "var_mc_95": metrics.value_at_risk_monte_carlo(mean_daily, cov, w, 0.95),
        "cvar_95": metrics.conditional_var(port_ret, 0.95),
    }
    return report
