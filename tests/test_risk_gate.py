"""Tests for the risk gate -- the non-negotiable layer in front of the exchange."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.exchange import PaperExchange
from sim.market_data import MarketData
from sim.risk_gate import OrderIntent, RiskGate


def make_gate(tmp_kill_file, **overrides):
    config = {
        "risk_gate": {
            "kill_switch_file": tmp_kill_file,
            "daily_loss_cap_pct": 0.05,
            "notional_cap_pct": 0.30,
            "price_sanity_pct": 0.08,
            "max_concurrent_positions": 3,
            "leverage_caps": {"BTCUSDT": 10, "ETHUSDT": 5, "default": 3},
        }
    }
    config["risk_gate"].update(overrides)
    return RiskGate(config)


def make_exchange(balance=5000.0):
    market = MarketData(["BTCUSDT", "ETHUSDT", "SOLUSDT"], seed=1)
    return PaperExchange(market, balance), market


def test_kill_switch_blocks_all_writes():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        kill_file = f.name
    try:
        gate = make_gate(kill_file)
        ex, _ = make_exchange()
        intent = OrderIntent(action="open", symbol="BTCUSDT", side="long", qty=0.01, leverage=3)
        decision = gate.check(intent, ex, day_start_nav=ex.nav())
        assert not decision.allowed
        assert decision.gate == "kill_switch"
    finally:
        os.remove(kill_file)


def test_leverage_cap_rejects_excess():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, _ = make_exchange()
    intent = OrderIntent(action="open", symbol="ETHUSDT", side="long", qty=0.01, leverage=8)
    decision = gate.check(intent, ex, day_start_nav=ex.nav())
    assert not decision.allowed
    assert decision.gate == "leverage_cap"


def test_leverage_cap_allows_within_limit():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, _ = make_exchange()
    intent = OrderIntent(action="open", symbol="BTCUSDT", side="long", qty=0.001, leverage=10)
    decision = gate.check(intent, ex, day_start_nav=ex.nav())
    assert decision.allowed


def test_notional_cap_rejects_oversized_order():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, market = make_exchange(balance=5000.0)
    # NAV 5000, cap 30% -> 1500. One BTC at ~68k is way over.
    intent = OrderIntent(action="open", symbol="BTCUSDT", side="long", qty=1.0, leverage=10)
    decision = gate.check(intent, ex, day_start_nav=ex.nav())
    assert not decision.allowed
    assert decision.gate == "notional_cap"


def test_price_sanity_rejects_far_limit():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, market = make_exchange()
    mark = market.mark_price("BTCUSDT")
    intent = OrderIntent(action="open", symbol="BTCUSDT", side="long", qty=0.001,
                         leverage=3, limit_price=mark * 1.2)
    decision = gate.check(intent, ex, day_start_nav=ex.nav())
    assert not decision.allowed
    assert decision.gate == "price_sanity"


def test_concurrent_cap_rejects_fourth_position():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, _ = make_exchange()
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        ex.place_order(sym, "long", 0.001, 3)
    # A fourth distinct symbol would exceed the cap of 3.
    ex.market._symbols["XRPUSDT"] = ex.market._symbols["BTCUSDT"]  # alias for the test
    intent = OrderIntent(action="open", symbol="XRPUSDT", side="long", qty=0.001, leverage=3)
    decision = gate.check(intent, ex, day_start_nav=ex.nav())
    assert not decision.allowed
    assert decision.gate == "concurrent_cap"


def test_daily_loss_cap_blocks_new_entries():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, _ = make_exchange(balance=5000.0)
    # Simulate a 6% drawdown vs day-start NAV.
    day_start = 5000.0
    ex.cash = 4700.0
    intent = OrderIntent(action="open", symbol="BTCUSDT", side="long", qty=0.001, leverage=3)
    decision = gate.check(intent, ex, day_start_nav=day_start)
    assert not decision.allowed
    assert decision.gate == "daily_loss_cap"


def test_closes_allowed_even_in_drawdown():
    gate = make_gate("/tmp/_no_such_halt_file_")
    ex, _ = make_exchange(balance=5000.0)
    ex.cash = 4000.0  # deep drawdown
    intent = OrderIntent(action="close", symbol="BTCUSDT")
    decision = gate.check(intent, ex, day_start_nav=5000.0)
    assert decision.allowed  # de-risking is always allowed (unless kill switch)
