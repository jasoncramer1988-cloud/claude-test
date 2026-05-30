"""The MCP tool layer -- the bridge between the reasoning loop and the exchange.

This mirrors the 'Bybit MCP Server' box in the architecture diagram. It exposes
the same two families of tools:

    READS  (no side effects):
        get_klines, get_orderbook, get_ticker, get_funding_rate,
        get_wallet_balance, get_positions, get_open_orders, get_trade_history

    WRITES (pass through the risk gate, then logged to the audit trail):
        place_order, cancel_order, set_leverage, set_tp_sl, close_position

In a real deployment each method would call Bybit. Here it calls the paper
exchange. The strategy code above never knows the difference -- which is the
whole "same code can run paper mode" point.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from .exchange import OrderResult, PaperExchange
from .market_data import MarketData
from .risk_gate import OrderIntent, RiskGate
from .state import StateStore


class MCPTools:
    def __init__(self, market: MarketData, exchange: PaperExchange,
                 risk_gate: RiskGate, state: StateStore):
        self.market = market
        self.exchange = exchange
        self.risk_gate = risk_gate
        self.state = state
        self.day_start_nav = exchange.nav()

    # --- READ tools -----------------------------------------------------

    def get_klines(self, symbol: str, n: int = 50) -> List[dict]:
        return [asdict(k) for k in self.market.get_klines(symbol, n)]

    def get_orderbook(self, symbol: str, depth: int = 5) -> dict:
        return self.market.get_orderbook(symbol, depth)

    def get_ticker(self, symbol: str) -> dict:
        return self.market.get_ticker(symbol)

    def get_funding_rate(self, symbol: str) -> float:
        return self.market.get_funding_rate(symbol)

    def get_wallet_balance(self) -> dict:
        return self.exchange.wallet_balance()

    def get_positions(self) -> List[dict]:
        return self.exchange.get_positions()

    def get_open_orders(self) -> List[dict]:
        # This sim fills market orders immediately, so there are never resting
        # orders. The tool still exists to match the real MCP surface.
        return []

    def get_trade_history(self, last_cycles: Optional[int] = None) -> List[dict]:
        return self.exchange.get_trade_history(last_cycles)

    # --- WRITE tools (gated + audited) ----------------------------------

    def _gated(self, intent: OrderIntent, execute) -> OrderResult:
        decision = self.risk_gate.check(intent, self.exchange, self.day_start_nav)
        if not decision.allowed:
            self.state.log_audit({
                "event": "write_rejected",
                "action": intent.action,
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": round(intent.qty, 6),
                "leverage": intent.leverage,
                "gate": decision.gate,
                "reason": decision.reason,
            })
            return OrderResult(False, f"[{decision.gate}] {decision.reason}")

        result = execute()
        self.state.log_audit({
            "event": "write_executed" if result.ok else "write_failed",
            "action": intent.action,
            "symbol": intent.symbol,
            "side": intent.side,
            "qty": round(intent.qty, 6),
            "leverage": intent.leverage,
            "fill_price": result.fill_price,
            "detail": result.detail,
        })
        return result

    def place_order(self, symbol: str, side: str, qty: float, leverage: int,
                    limit_price: Optional[float] = None) -> OrderResult:
        intent = OrderIntent(
            action="open", symbol=symbol, side=side, qty=qty,
            leverage=leverage, limit_price=limit_price,
        )
        return self._gated(intent, lambda: self.exchange.place_order(symbol, side, qty, leverage))

    def close_position(self, symbol: str, qty: Optional[float] = None,
                       reason: str = "strategy_exit") -> OrderResult:
        intent = OrderIntent(action="close", symbol=symbol, qty=qty or 0.0)
        return self._gated(intent, lambda: self.exchange.close_position(symbol, qty, reason))

    def set_leverage(self, symbol: str, leverage: int) -> OrderResult:
        intent = OrderIntent(action="set_leverage", symbol=symbol, leverage=leverage)
        return self._gated(intent, lambda: self.exchange.set_leverage(symbol, leverage))

    def set_tp_sl(self, symbol: str, take_profit: Optional[float] = None,
                  stop_loss: Optional[float] = None) -> OrderResult:
        intent = OrderIntent(action="set_tp_sl", symbol=symbol)
        return self._gated(
            intent,
            lambda: self.exchange.set_tp_sl(symbol, take_profit, stop_loss),
        )

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        # No resting orders in this sim; provided for surface parity.
        return OrderResult(True, f"no resting order {order_id} on {symbol} to cancel")
