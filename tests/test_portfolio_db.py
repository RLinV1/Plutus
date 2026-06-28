"""CRUD round-trips for the portfolio store on a temp SQLite file."""

from __future__ import annotations

from datetime import datetime

import pytest

from portfolio_risk.portfolio import store


def test_portfolio_create_and_dedupe(portfolio_db):
    a = store.get_or_create_portfolio("default")
    b = store.get_or_create_portfolio("default")
    assert a["id"] == b["id"]
    store.get_or_create_portfolio("retirement")
    names = [p["name"] for p in store.list_portfolios()]
    assert names == ["default", "retirement"]


def test_transaction_round_trip(portfolio_db):
    t = store.add_transaction(
        "default", "aapl", "buy", 10, 150.0, fees=1.0, trade_date="2021-02-01"
    )
    assert t["ticker"] == "AAPL"
    assert t["side"] == "BUY"
    assert t["trade_date"] == "2021-02-01"

    rows = store.list_transactions("default")
    assert len(rows) == 1
    assert rows[0]["shares"] == 10.0

    assert store.delete_transaction(t["id"]) is True
    assert store.list_transactions("default") == []
    assert store.delete_transaction(99999) is False


def test_transactions_isolated_per_portfolio(portfolio_db):
    store.add_transaction("default", "AAPL", "BUY", 1, 100, trade_date="2021-02-01")
    store.add_transaction("ira", "MSFT", "BUY", 2, 200, trade_date="2021-02-01")
    assert [t["ticker"] for t in store.list_transactions("default")] == ["AAPL"]
    assert [t["ticker"] for t in store.list_transactions("ira")] == ["MSFT"]


def test_transaction_validation(portfolio_db):
    with pytest.raises(ValueError):
        store.add_transaction("default", "AAPL", "HOLD", 1, 100)
    with pytest.raises(ValueError):
        store.add_transaction("default", "AAPL", "BUY", 0, 100)
    with pytest.raises(ValueError):
        store.add_transaction("default", "AAPL", "BUY", 1, -5)
    with pytest.raises(ValueError):
        store.add_transaction("default", "", "BUY", 1, 100)


def test_alert_rule_crud(portfolio_db):
    r = store.add_alert_rule("NVDA", "price_above", 150.0)
    assert r["enabled"] is True
    assert r["cooldown_minutes"] == 240

    with pytest.raises(ValueError):
        store.add_alert_rule("NVDA", "nonsense", 1.0)

    updated = store.update_alert_rule(r["id"], enabled=False, threshold=160.0)
    assert updated["enabled"] is False
    assert updated["threshold"] == 160.0
    assert store.list_alert_rules(enabled_only=True) == []

    store.mark_rule_triggered(r["id"], datetime(2021, 6, 1, 12, 0))
    rules = store.list_alert_rules()
    assert rules[0]["last_triggered_at"].startswith("2021-06-01")

    assert store.delete_alert_rule(r["id"]) is True
    assert store.list_alert_rules() == []


def test_delete_rule_that_already_fired(portfolio_db):
    """Regression: notifications referencing a rule must not block its delete."""
    r = store.add_alert_rule("AAPL", "price_above", 100.0)
    store.add_notification("AAPL above $100", ticker="AAPL", rule_id=r["id"])
    assert store.delete_alert_rule(r["id"]) is True
    assert store.list_alert_rules() == []
    # The notification history survives, just detached from the dead rule.
    notes = store.list_notifications()
    assert len(notes) == 1


def test_notifications(portfolio_db):
    store.add_notification("NVDA above $150", ticker="NVDA", payload={"price": 151.2})
    store.add_notification("AAPL moved 3%", ticker="AAPL")
    unread = store.list_notifications(unread_only=True)
    assert len(unread) == 2
    # Newest first.
    assert unread[0]["title"] == "AAPL moved 3%"
    assert unread[1]["payload"] == {"price": 151.2}

    n = store.mark_notifications_read([unread[0]["id"]])
    assert n == 1
    assert len(store.list_notifications(unread_only=True)) == 1
    assert store.mark_notifications_read() == 1  # rest
    assert store.list_notifications(unread_only=True) == []
