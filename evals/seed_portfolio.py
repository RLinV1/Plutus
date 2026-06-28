"""Deterministic demo portfolio shared by tests and the eval harness.

All trade dates sit inside the mock price calendar (which starts 2021-01-04),
so everything works offline under USE_MOCK_DATA=1. The same seed is used for
eval ground truth and the agent run, so both compute against identical state.
"""

from __future__ import annotations

SEED_TXNS: list[tuple[str, str, float, float, str]] = [
    # (ticker, side, shares, price, trade_date)
    ("AAPL", "BUY", 10, 130.0, "2021-02-01"),
    ("MSFT", "BUY", 8, 230.0, "2021-02-01"),
    ("NVDA", "BUY", 12, 130.0, "2021-03-01"),
    ("JNJ", "BUY", 15, 160.0, "2021-03-15"),
    ("AAPL", "BUY", 5, 140.0, "2021-06-15"),
    ("NVDA", "SELL", 2, 180.0, "2021-08-02"),
]


def ensure_seeded(portfolio: str = "default") -> None:
    """Idempotent: load the demo transactions unless the portfolio has any."""
    from portfolio_risk.portfolio import store

    if store.list_transactions(portfolio):
        return
    for ticker, side, shares, price, when in SEED_TXNS:
        store.add_transaction(portfolio, ticker, side, shares, price, trade_date=when)
