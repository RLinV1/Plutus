"""Paper-trading account: cash math, fill validation, reset. Offline mock data."""

from __future__ import annotations

import pytest

from portfolio_risk import config
from portfolio_risk.portfolio import paper


@pytest.fixture
def paper_db(portfolio_db):
    yield


def test_fresh_account_is_all_cash(paper_db):
    acct = paper.account_state()
    assert acct["cash"] == acct["start_cash"] == config.paper_start_cash()
    assert acct["positions_value"] == 0.0
    assert acct["return_pct"] == 0.0
    assert acct["positions"] == []


def test_buy_fills_at_market_and_reduces_cash(paper_db):
    out = paper.execute_trade("BUY", "AAPL", 10)
    assert "error" not in out
    fill = out["fill"]
    assert fill["side"] == "BUY" and fill["shares"] == 10
    assert fill["price"] > 0  # mock mode fills at the last synthetic close
    acct = out["account"]
    assert acct["cash"] == pytest.approx(
        acct["start_cash"] - 10 * fill["price"], abs=0.05
    )
    assert acct["positions"][0]["ticker"] == "AAPL"
    # Total value conserved at the moment of the fill (bought at current price).
    assert acct["total_value"] == pytest.approx(acct["start_cash"], rel=1e-3)


def test_insufficient_cash_rejected(paper_db):
    out = paper.execute_trade("BUY", "AAPL", 10_000_000)
    assert "error" in out
    assert "Not enough paper cash" in out["error"]
    assert paper.account_state()["n_trades"] == 0


def test_oversell_rejected_and_sell_returns_cash(paper_db):
    paper.execute_trade("BUY", "MSFT", 5)
    bad = paper.execute_trade("SELL", "MSFT", 6)
    assert "error" in bad
    ok = paper.execute_trade("SELL", "MSFT", 5)
    assert "error" not in ok
    acct = ok["account"]
    assert acct["positions"] == []
    # Bought and sold at the same mock close — cash round-trips.
    assert acct["cash"] == pytest.approx(acct["start_cash"], rel=1e-6)


def test_validation_and_reset(paper_db):
    assert "error" in paper.execute_trade("HOLD", "AAPL", 1)
    assert "error" in paper.execute_trade("BUY", "AAPL", 0)
    assert "error" in paper.execute_trade("BUY", "", 1)

    paper.execute_trade("BUY", "AAPL", 3)
    out = paper.reset_account()
    assert out["deleted"] == 1
    assert out["account"]["cash"] == out["account"]["start_cash"]
