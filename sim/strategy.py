"""Strategy engine -- the deterministic stand-in for the reasoning loop.

In the live system this box is Claude reading market data and deciding. Here it
is a transparent, reproducible momentum rule so the simulation is debuggable and
testable. It only ever touches the exchange through the MCP tool layer, so every
order it sends is subject to the same risk gate a real model would face.

    entry_scan()      -> looks for fresh EMA-crossover setups (runs periodically)
    manage_positions() -> time-based exits / housekeeping (runs every cycle)
"""

from __future__ import annotations

from typing import List, Optional

from .mcp_tools import MCPTools


def ema(values: List[float], period: int) -> Optional[float]:
    """Exponential moving average of the last values; None if too short."""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    # Seed with the simple average of the first `period` points.
    avg = sum(values[:period]) / period
    for v in values[period:]:
        avg = v * k + avg * (1 - k)
    return avg


class MomentumStrategy:
    def __init__(self, tools: MCPTools, config: dict):
        self.tools = tools
        s = config["strategy"]
        self.fast = s["fast_ema"]
        self.slow = s["slow_ema"]
        self.threshold = s["signal_threshold"]
        self.risk_per_trade = s["risk_per_trade"]
        self.default_leverage = s["default_leverage"]
        self.stop_loss_pct = s["stop_loss_pct"]
        self.take_profit_pct = s["take_profit_pct"]
        self.max_holding = s["max_holding_cycles"]
        self.allowed_pairs = config["allowed_pairs"]

    def _signal(self, symbol: str) -> Optional[str]:
        """Return 'long', 'short', or None from an EMA crossover."""
        klines = self.tools.get_klines(symbol, n=self.slow + 5)
        closes = [k["close"] for k in klines]
        fast = ema(closes, self.fast)
        slow = ema(closes, self.slow)
        if fast is None or slow is None:
            return None
        separation = (fast - slow) / slow
        if separation > self.threshold:
            return "long"
        if separation < -self.threshold:
            return "short"
        return None

    def _size_position(self, symbol: str, leverage: int) -> float:
        """Risk-based sizing, clamped so it never trips the notional cap.

        Two constraints, take the smaller:
          1. Risk budget: lose at most risk_per_trade of NAV if the stop hits.
          2. Notional cap: stay under the risk gate's per-order notional limit
             (sizing inside the gate beats spamming rejected orders).
        """
        nav = self.tools.get_wallet_balance()["nav"]
        mark = self.tools.get_ticker(symbol)["mark_price"]

        # 1. Loss at stop ~= qty * mark * stop_loss_pct. Solve for qty.
        risk_qty = (nav * self.risk_per_trade) / (mark * self.stop_loss_pct)

        # 2. Leave a little headroom under the cap to absorb slippage.
        cap_notional = self.tools.risk_gate.notional_cap_pct * nav * 0.98
        cap_qty = cap_notional / mark

        return max(min(risk_qty, cap_qty), 0.0)

    def entry_scan(self, cycle: int) -> List[dict]:
        """Look for new setups on symbols we are flat on."""
        decisions = []
        open_symbols = {p["symbol"] for p in self.tools.get_positions()}
        for symbol in self.allowed_pairs:
            if symbol in open_symbols:
                continue
            side = self._signal(symbol)
            if side is None:
                continue

            leverage = min(self.default_leverage, self.tools.risk_gate.leverage_cap_for(symbol))
            qty = self._size_position(symbol, leverage)
            mark = self.tools.get_ticker(symbol)["mark_price"]

            decision = {
                "cycle": cycle,
                "task": "entry_scan",
                "symbol": symbol,
                "intent": f"open {side}",
                "qty": round(qty, 6),
                "leverage": leverage,
                "mark": round(mark, 4),
                "rationale": f"EMA{self.fast}/EMA{self.slow} crossover -> {side}",
            }

            result = self.tools.place_order(symbol, side, qty, leverage)
            decision["outcome"] = result.detail
            decision["executed"] = result.ok

            if result.ok:
                # Attach protective TP/SL right away.
                if side == "long":
                    sl = mark * (1 - self.stop_loss_pct)
                    tp = mark * (1 + self.take_profit_pct)
                else:
                    sl = mark * (1 + self.stop_loss_pct)
                    tp = mark * (1 - self.take_profit_pct)
                self.tools.set_tp_sl(symbol, take_profit=round(tp, 4), stop_loss=round(sl, 4))

            self.tools.state.log_decision(decision)
            decisions.append(decision)
        return decisions

    def manage_positions(self, cycle: int) -> List[dict]:
        """Per-cycle housekeeping: force-exit anything held too long."""
        decisions = []
        for pos in self.tools.get_positions():
            if pos["held_cycles"] >= self.max_holding:
                result = self.tools.close_position(pos["symbol"], reason="max_holding")
                decision = {
                    "cycle": cycle,
                    "task": "manage_positions",
                    "symbol": pos["symbol"],
                    "intent": "close (max holding reached)",
                    "outcome": result.detail,
                    "executed": result.ok,
                }
                self.tools.state.log_decision(decision)
                decisions.append(decision)
        return decisions
