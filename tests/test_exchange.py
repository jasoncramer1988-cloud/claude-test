"""Tests for the paper exchange: fills, PnL accounting, and TP/SL triggers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sim.exchange import PaperExchange
from sim.market_data import MarketData


def make_exchange(balance=5000.0):
    market = MarketData(["BTCUSDT"], seed=3)
    return PaperExchange(market, balance), market


def test_open_and_close_long_profit():
    ex, market = make_exchange()
    sym = "BTCUSDT"
    entry_mark = market.mark_price(sym)
    res = ex.place_order(sym, "long", 0.01, 5)
    assert res.ok
    assert sym in ex.positions

    # Force price up 10% and close.
    market._symbols[sym].price = entry_mark * 1.10
    close = ex.close_position(sym)
    assert close.ok
    assert sym not in ex.positions
    # Long that moved +10% should net a profit after fees/slippage.
    assert ex.cash > 5000.0
    assert ex.trade_history[-1].realized_pnl > 0


def test_open_and_close_short_profit():
    ex, market = make_exchange()
    sym = "BTCUSDT"
    entry_mark = market.mark_price(sym)
    ex.place_order(sym, "short", 0.01, 5)
    market._symbols[sym].price = entry_mark * 0.90
    ex.close_position(sym)
    assert ex.cash > 5000.0
    assert ex.trade_history[-1].realized_pnl > 0


def test_insufficient_margin_rejected():
    ex, market = make_exchange(balance=100.0)
    # 1 BTC notional at ~68k far exceeds 100 USDT of margin even at 5x.
    res = ex.place_order("BTCUSDT", "long", 1.0, 5)
    assert not res.ok
    assert "margin" in res.detail


def test_stop_loss_triggers():
    ex, market = make_exchange()
    sym = "BTCUSDT"
    mark = market.mark_price(sym)
    ex.place_order(sym, "long", 0.01, 5)
    ex.set_tp_sl(sym, stop_loss=mark * 0.98)
    # Drop below the stop.
    market._symbols[sym].price = mark * 0.97
    results = ex.check_tp_sl()
    assert len(results) == 1
    assert sym not in ex.positions
    assert ex.trade_history[-1].reason == "stop_loss"


def test_take_profit_triggers():
    ex, market = make_exchange()
    sym = "BTCUSDT"
    mark = market.mark_price(sym)
    ex.place_order(sym, "long", 0.01, 5)
    ex.set_tp_sl(sym, take_profit=mark * 1.04)
    market._symbols[sym].price = mark * 1.05
    ex.check_tp_sl()
    assert sym not in ex.positions
    assert ex.trade_history[-1].reason == "take_profit"


def test_scale_in_averages_entry():
    ex, market = make_exchange()
    sym = "BTCUSDT"
    ex.place_order(sym, "long", 0.01, 5)
    first_entry = ex.positions[sym].entry_price
    market._symbols[sym].price *= 1.05
    ex.place_order(sym, "long", 0.01, 5)
    pos = ex.positions[sym]
    assert abs(pos.qty - 0.02) < 1e-9
    # Averaged entry should sit between the two fills.
    assert first_entry < pos.entry_price


def test_opposing_order_rejected():
    ex, market = make_exchange()
    sym = "BTCUSDT"
    ex.place_order(sym, "long", 0.01, 5)
    res = ex.place_order(sym, "short", 0.01, 5)
    assert not res.ok
    assert "opposing" in res.detail
