"""Pure technical-indicator helpers computed from a price series.

These are the "metrics people actually ask about" — moving averages, RSI, and
the 52-week range. Like ``risk/metrics.py`` they take data in and have no I/O, so
they are deterministic and unit-testable. They operate on a *price* Series
(adjusted close), not returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _as_series(prices) -> pd.Series:
    s = prices if isinstance(prices, pd.Series) else pd.Series(prices, dtype=float)
    return s.dropna().astype(float)


def sma(prices, window: int) -> float:
    """Simple moving average: the mean of the last ``window`` closing prices.

    Returns NaN if there aren't enough data points yet (e.g. asking for a
    200-day average from only 100 days of history).
    """
    s = _as_series(prices)
    if len(s) < window:
        return float("nan")
    return float(s.iloc[-window:].mean())


def rsi(prices, window: int = 14) -> float:
    """Relative Strength Index (0-100) using Wilder's smoothing.

    Measures recent momentum. Conventionally, >70 is "overbought" and <30 is
    "oversold". Returns NaN if there isn't enough history.
    """
    s = _as_series(prices)
    if len(s) <= window:
        return float("nan")
    delta = s.diff().dropna()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    # Wilder's smoothing via an exponential moving average with alpha = 1/window.
    avg_gain = gains.ewm(alpha=1.0 / window, adjust=False).mean().iloc[-1]
    avg_loss = losses.ewm(alpha=1.0 / window, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def fifty_two_week_range(prices, window: int = 252) -> tuple[float, float, float]:
    """Return ``(low, high, position)`` over roughly the last year.

    ``position`` is where the latest price sits in that range, 0.0 (at the low)
    to 1.0 (at the high). Uses up to ``window`` most-recent points.
    """
    s = _as_series(prices)
    if s.empty:
        return (float("nan"), float("nan"), float("nan"))
    recent = s.iloc[-window:]
    low = float(recent.min())
    high = float(recent.max())
    last = float(s.iloc[-1])
    span = high - low
    position = 0.5 if span == 0 else (last - low) / span
    return (low, high, float(np.clip(position, 0.0, 1.0)))
