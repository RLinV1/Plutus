"""High-level loader used by the MCP tools and the eval harness.

Turns a list of tickers + a benchmark into aligned daily-return objects.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from . import returns as ret
from .market_data import get_prices


def load_returns(
    tickers: list[str],
    benchmark: str = config.DEFAULT_BENCHMARK,
    lookback_days: int = config.DEFAULT_LOOKBACK_DAYS,
) -> tuple[pd.DataFrame, pd.Series]:
    """Return (asset_returns_df, benchmark_returns) aligned on common dates.

    The benchmark is always fetched alongside the assets so beta is computable.
    """
    tickers = [t.upper() for t in tickers]
    benchmark = benchmark.upper()
    all_tickers = list(dict.fromkeys(tickers + [benchmark]))  # de-dupe, keep order

    prices = get_prices(all_tickers, lookback_days=lookback_days)
    all_returns = ret.to_returns(prices, method="simple")

    bench_series = all_returns[benchmark]
    asset_returns = all_returns[[t for t in tickers]]
    aligned_assets, aligned_bench = ret.align(asset_returns, bench_series)
    return aligned_assets, aligned_bench
