"""CSV import: header aliases, sign conventions, dirty values, dry-run safety."""

from __future__ import annotations

from portfolio_risk.portfolio import csv_import, store


def test_minimal_headers():
    text = "ticker,side,shares,price,date\nAAPL,BUY,10,150.25,2021-02-01\n"
    out = csv_import.parse_csv(text)
    assert out["errors"] == []
    assert out["rows"] == [
        {
            "ticker": "AAPL",
            "side": "BUY",
            "shares": 10.0,
            "price": 150.25,
            "fees": 0.0,
            "trade_date": "2021-02-01",
            "note": "",
        }
    ]


def test_fidelity_style():
    text = (
        "Run Date,Action,Symbol,Description,Quantity,Price ($),Commission ($)\n"
        "02/01/2021,YOU BOUGHT,MSFT,MICROSOFT CORP,8,\"$230.00\",$4.95\n"
        "08/02/2021,YOU SOLD,NVDA,NVIDIA CORP,-2,\"$180.00\",\n"
    )
    out = csv_import.parse_csv(text)
    assert out["errors"] == []
    assert len(out["rows"]) == 2
    buy, sell = out["rows"]
    assert (buy["ticker"], buy["side"], buy["shares"], buy["price"], buy["fees"]) == (
        "MSFT", "BUY", 8.0, 230.0, 4.95
    )
    assert buy["trade_date"] == "2021-02-01"
    assert (sell["side"], sell["shares"]) == ("SELL", 2.0)


def test_negative_quantity_means_sell_without_action_column():
    text = "Symbol,Quantity,Price,Date\nAAPL,-5,140.00,2021-06-15\n"
    out = csv_import.parse_csv(text)
    assert out["rows"][0]["side"] == "SELL"
    assert out["rows"][0]["shares"] == 5.0


def test_bad_rows_reported_not_fatal():
    text = (
        "ticker,side,shares,price,date\n"
        "AAPL,BUY,10,150,2021-02-01\n"
        "MSFT,BUY,not_a_number,230,2021-02-01\n"
        "NVDA,BUY,5,130,99/99/9999\n"
        ",,,,\n"
        "KO,BUY,0,55,2021-02-01\n"
    )
    out = csv_import.parse_csv(text)
    assert len(out["rows"]) == 1
    assert out["rows"][0]["ticker"] == "AAPL"
    assert len(out["errors"]) == 3  # bad number, bad date, zero shares


def test_missing_required_columns():
    out = csv_import.parse_csv("foo,bar\n1,2\n")
    assert out["rows"] == []
    assert "Missing required column" in out["errors"][0]


def test_commit_writes_through_store(portfolio_db):
    text = "ticker,side,shares,price,date\nAAPL,BUY,10,150,2021-02-01\n"
    parsed = csv_import.parse_csv(text)
    written = csv_import.commit_rows("csvtest", parsed["rows"])
    assert len(written) == 1
    assert store.list_transactions("csvtest")[0]["ticker"] == "AAPL"
