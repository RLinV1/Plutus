"""Price -> return transforms and alignment helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def to_returns(prices: pd.DataFrame, method: str = "simple") -> pd.DataFrame:
    """Daily returns from an adjusted-close price matrix.

    method: "simple" (pct change) or "log".
    Drops the leading NaN row.
    """
    if method == "log":
        rets = np.log(prices / prices.shift(1))
    elif method == "simple":
        rets = prices.pct_change()
    else:
        raise ValueError(f"Unknown method: {method!r}")
    return rets.dropna(how="all")


def align(
    returns_df: pd.DataFrame, benchmark: pd.Series
) -> tuple[pd.DataFrame, pd.Series]:
    """Inner-join asset returns and a benchmark series on common dates."""
    joined = returns_df.join(benchmark.rename("__benchmark__"), how="inner").dropna()
    bench = joined.pop("__benchmark__")
    return joined, bench
