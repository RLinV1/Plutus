"""Alert engine: pure rule evaluation (every type + cooldown) and a full cycle."""

from __future__ import annotations

from datetime import datetime

from portfolio_risk.portfolio import alerts, store

NOW = datetime(2021, 6, 1, 12, 0, 0)


def _rule(id=1, ticker="AAPL", rule_type="price_above", threshold=100.0, **kw):
    return {
        "id": id,
        "portfolio_id": None,
        "ticker": ticker,
        "rule_type": rule_type,
        "threshold": threshold,
        "enabled": kw.get("enabled", True),
        "cooldown_minutes": kw.get("cooldown_minutes", 240),
        "last_triggered_at": kw.get("last_triggered_at"),
    }


def _state(**kw):
    base = {
        "price": None,
        "change_pct": None,
        "rsi": None,
        "drawdown_pct": None,
        "relevant_news_24h": None,
    }
    base.update(kw)
    return {"AAPL": base}


def test_price_rules():
    assert alerts.evaluate_rules([_rule(threshold=100)], _state(price=101.0), NOW)
    assert not alerts.evaluate_rules([_rule(threshold=100)], _state(price=99.0), NOW)
    below = _rule(rule_type="price_below", threshold=100)
    assert alerts.evaluate_rules([below], _state(price=99.0), NOW)
    assert not alerts.evaluate_rules([below], _state(price=101.0), NOW)


def test_pct_move_rule_uses_absolute_move():
    r = _rule(rule_type="pct_move", threshold=3.0)
    assert alerts.evaluate_rules([r], _state(price=10, change_pct=-0.035), NOW)
    assert alerts.evaluate_rules([r], _state(price=10, change_pct=0.031), NOW)
    assert not alerts.evaluate_rules([r], _state(price=10, change_pct=0.02), NOW)


def test_rsi_and_drawdown_and_news_rules():
    assert alerts.evaluate_rules(
        [_rule(rule_type="rsi_above", threshold=70)], _state(rsi=75.0), NOW
    )
    assert alerts.evaluate_rules(
        [_rule(rule_type="rsi_below", threshold=30)], _state(rsi=25.0), NOW
    )
    assert alerts.evaluate_rules(
        [_rule(rule_type="drawdown", threshold=10)], _state(drawdown_pct=12.5), NOW
    )
    assert alerts.evaluate_rules(
        [_rule(rule_type="news_volume", threshold=5)], _state(relevant_news_24h=6), NOW
    )
    # Missing data never fires.
    assert not alerts.evaluate_rules(
        [_rule(rule_type="rsi_above", threshold=70)], _state(), NOW
    )


def test_disabled_and_unknown_ticker_do_not_fire():
    assert not alerts.evaluate_rules(
        [_rule(enabled=False)], _state(price=101.0), NOW
    )
    assert not alerts.evaluate_rules(
        [_rule(ticker="ZZZZ")], _state(price=101.0), NOW
    )


def test_cooldown_suppresses_then_releases():
    fired_recently = _rule(last_triggered_at="2021-06-01T10:30:00")  # 90 min ago
    assert not alerts.evaluate_rules([fired_recently], _state(price=101.0), NOW)
    fired_long_ago = _rule(last_triggered_at="2021-06-01T07:00:00")  # 5 h ago
    assert alerts.evaluate_rules([fired_long_ago], _state(price=101.0), NOW)


def test_hit_payload_shape():
    hits = alerts.evaluate_rules([_rule(threshold=100)], _state(price=105.0), NOW)
    h = hits[0]
    assert h["ticker"] == "AAPL"
    assert h["rule_id"] == 1
    assert "above $100" in h["title"]
    assert h["payload"]["price"] == 105.0


def test_full_cycle_persists_and_cools_down(portfolio_db):
    # A held position + a rule that must fire against mock prices (always > $1).
    store.add_transaction("default", "AAPL", "BUY", 5, 100.0, trade_date="2021-02-01")
    store.add_alert_rule("AAPL", "price_above", 1.0)

    out = alerts.run_alert_cycle(NOW)
    assert "AAPL" in out["quotes"]
    assert len(out["notifications"]) == 1
    assert store.list_notifications(unread_only=True)

    # Second cycle inside the cooldown: quotes still flow, no duplicate alert.
    out2 = alerts.run_alert_cycle(NOW)
    assert out2["notifications"] == []
    assert "AAPL" in out2["quotes"]
