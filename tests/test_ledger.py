"""Pure ledger math: average cost, realized/unrealized P&L, value history, TWR."""

from __future__ import annotations

import pandas as pd
import pytest

from portfolio_risk.portfolio import ledger


def _txn(ticker, side, shares, price, date, fees=0.0, id=None):
    return {
        "id": id,
        "ticker": ticker,
        "side": side,
        "shares": shares,
        "price": price,
        "fees": fees,
        "trade_date": date,
    }


def test_average_cost_basic():
    res = ledger.compute_holdings(
        [
            _txn("AAPL", "BUY", 10, 100.0, "2021-02-01"),
            _txn("AAPL", "BUY", 10, 200.0, "2021-03-01"),
        ]
    )
    p = res["positions"]["AAPL"]
    assert p["shares"] == 20
    assert p["avg_cost"] == pytest.approx(150.0)
    assert p["cost_basis"] == pytest.approx(3000.0)
    assert res["warnings"] == []


def test_sell_realizes_pnl_at_average_cost():
    res = ledger.compute_holdings(
        [
            _txn("AAPL", "BUY", 10, 100.0, "2021-02-01"),
            _txn("AAPL", "BUY", 10, 200.0, "2021-03-01"),
            _txn("AAPL", "SELL", 5, 180.0, "2021-04-01"),
        ]
    )
    p = res["positions"]["AAPL"]
    # avg cost 150; sell 5 @ 180 -> realized 5*30 = 150
    assert p["realized_pnl"] == pytest.approx(150.0)
    assert p["shares"] == 15
    assert p["avg_cost"] == pytest.approx(150.0)  # average cost unchanged by a sell
    assert p["cost_basis"] == pytest.approx(2250.0)
    assert res["realized_pnl_total"] == pytest.approx(150.0)


def test_fees_increase_cost_and_reduce_realized():
    res = ledger.compute_holdings(
        [
            _txn("KO", "BUY", 10, 50.0, "2021-02-01", fees=10.0),
            _txn("KO", "SELL", 10, 60.0, "2021-03-01", fees=5.0),
        ]
    )
    p = res["positions"]["KO"]
    # avg cost = 510/10 = 51; realized = 10*(60-51) - 5 = 85
    assert p["realized_pnl"] == pytest.approx(85.0)
    assert p["shares"] == 0.0
    assert p["avg_cost"] is None


def test_oversell_is_clipped_with_warning():
    res = ledger.compute_holdings(
        [
            _txn("MSFT", "BUY", 5, 200.0, "2021-02-01"),
            _txn("MSFT", "SELL", 8, 250.0, "2021-03-01"),
        ]
    )
    p = res["positions"]["MSFT"]
    assert p["shares"] == 0.0
    assert p["realized_pnl"] == pytest.approx(5 * 50.0)
    assert len(res["warnings"]) == 1
    assert "clipped" in res["warnings"][0]


def test_unknown_side_raises():
    with pytest.raises(ledger.LedgerError):
        ledger.compute_holdings([_txn("AAPL", "SHORT", 1, 100.0, "2021-02-01")])


def test_held_tickers_sorted_and_nonzero_only():
    txns = [
        _txn("NVDA", "BUY", 1, 500.0, "2021-02-01"),
        _txn("AAPL", "BUY", 1, 100.0, "2021-02-01"),
        _txn("AAPL", "SELL", 1, 120.0, "2021-03-01"),
    ]
    assert ledger.held_tickers(txns) == ["NVDA"]


def test_shares_matrix_step_function_and_snap_forward():
    idx = pd.bdate_range("2021-02-01", periods=10)  # Mon Feb 1 .. Fri Feb 12
    txns = [
        _txn("AAPL", "BUY", 10, 100.0, "2021-01-15"),  # before window -> initial
        _txn("AAPL", "BUY", 5, 100.0, "2021-02-06"),   # Saturday -> snaps to Mon 8th
        _txn("AAPL", "SELL", 3, 100.0, "2021-02-10"),
    ]
    m = ledger.shares_matrix(txns, idx)
    assert m.loc["2021-02-01", "AAPL"] == 10
    assert m.loc["2021-02-05", "AAPL"] == 10
    assert m.loc["2021-02-08", "AAPL"] == 15  # Saturday buy effective Monday
    assert m.loc["2021-02-10", "AAPL"] == 12
    assert m.loc["2021-02-12", "AAPL"] == 12


def test_value_series_matches_hand_computation():
    idx = pd.bdate_range("2021-02-01", periods=3)
    prices = pd.DataFrame({"AAPL": [100.0, 110.0, 120.0]}, index=idx)
    txns = [
        _txn("AAPL", "BUY", 2, 100.0, "2021-02-01"),
        _txn("AAPL", "BUY", 1, 110.0, "2021-02-02"),
    ]
    v = ledger.portfolio_value_series(txns, prices)
    assert v.iloc[0] == pytest.approx(200.0)
    assert v.iloc[1] == pytest.approx(330.0)
    assert v.iloc[2] == pytest.approx(360.0)


def test_twr_ignores_deposits():
    """A mid-period buy (new money) must NOT spike the time-weighted return."""
    idx = pd.bdate_range("2021-02-01", periods=3)
    prices = pd.DataFrame({"AAPL": [100.0, 100.0, 100.0]}, index=idx)  # flat price
    txns = [
        _txn("AAPL", "BUY", 1, 100.0, "2021-02-01"),
        _txn("AAPL", "BUY", 9, 100.0, "2021-02-02"),  # big deposit, no performance
    ]
    v = ledger.portfolio_value_series(txns, prices)
    f = ledger.flows_series(txns, idx)
    r = ledger.time_weighted_returns(v, f)
    # Price never moved, so every time-weighted return must be ~0.
    assert (r.abs() < 1e-12).all()


def test_twr_pure_price_move():
    idx = pd.bdate_range("2021-02-01", periods=3)
    prices = pd.DataFrame({"AAPL": [100.0, 110.0, 99.0]}, index=idx)
    txns = [_txn("AAPL", "BUY", 10, 100.0, "2021-02-01")]
    v = ledger.portfolio_value_series(txns, prices)
    r = ledger.time_weighted_returns(v, ledger.flows_series(txns, idx))
    assert r.iloc[0] == pytest.approx(0.10)
    assert r.iloc[1] == pytest.approx(-0.10)


def test_twr_skips_days_before_first_position():
    idx = pd.bdate_range("2021-02-01", periods=5)
    prices = pd.DataFrame({"AAPL": [100.0] * 5}, index=idx)
    txns = [_txn("AAPL", "BUY", 1, 100.0, "2021-02-03")]
    v = ledger.portfolio_value_series(txns, prices)
    r = ledger.time_weighted_returns(v, ledger.flows_series(txns, idx))
    # Days with zero prior value are skipped, not infinite/NaN.
    assert r.notna().all()
    assert (r.index >= pd.Timestamp("2021-02-04")).all()
