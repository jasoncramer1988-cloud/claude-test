"""Paper-trading exchange backend.

Simulates the parts of a Bybit perpetuals sub-account the bot interacts with:
wallet balance, leveraged positions, market-order fills with slippage,
take-profit / stop-loss handling, and realized / unrealized PnL.

In live mode this whole class would be replaced by a thin wrapper around the
Bybit REST/WebSocket API -- the MCP tool layer above it would not change.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .market_data import MarketData


# Taker fee charged on entry and exit notional (Bybit-ish).
TAKER_FEE = 0.00055
# Slippage applied to market fills, as a fraction of price.
SLIPPAGE = 0.0002


@dataclass
class Position:
    symbol: str
    side: str            # "long" or "short"
    qty: float           # contract quantity in base asset
    entry_price: float
    leverage: int
    opened_cycle: int
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None

    @property
    def sign(self) -> int:
        return 1 if self.side == "long" else -1

    @property
    def notional(self) -> float:
        return self.qty * self.entry_price

    @property
    def margin(self) -> float:
        return self.notional / self.leverage

    def unrealized_pnl(self, mark: float) -> float:
        return (mark - self.entry_price) * self.qty * self.sign


@dataclass
class Trade:
    cycle: int
    symbol: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    fees: float
    reason: str
    held_cycles: int


@dataclass
class OrderResult:
    ok: bool
    detail: str
    fill_price: Optional[float] = None
    position: Optional[Position] = None


class PaperExchange:
    """A minimal but self-consistent perpetuals exchange simulator."""

    def __init__(self, market: MarketData, starting_balance: float):
        self.market = market
        self.cash = starting_balance          # realized USDT
        self.starting_balance = starting_balance
        self.positions: Dict[str, Position] = {}
        self.leverage: Dict[str, int] = {}     # per-symbol leverage setting
        self.trade_history: List[Trade] = []
        self._cycle = 0

    # --- account views --------------------------------------------------

    def set_cycle(self, cycle: int) -> None:
        self._cycle = cycle

    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl(self.market.mark_price(p.symbol)) for p in self.positions.values())

    def nav(self) -> float:
        """Net asset value = realized cash + unrealized PnL."""
        return self.cash + self.unrealized_pnl()

    def used_margin(self) -> float:
        return sum(p.margin for p in self.positions.values())

    def free_margin(self) -> float:
        return self.nav() - self.used_margin()

    def wallet_balance(self) -> Dict[str, float]:
        return {
            "currency": "USDT",
            "cash": round(self.cash, 4),
            "unrealized_pnl": round(self.unrealized_pnl(), 4),
            "nav": round(self.nav(), 4),
            "used_margin": round(self.used_margin(), 4),
            "free_margin": round(self.free_margin(), 4),
        }

    # --- order execution ------------------------------------------------

    def place_order(self, symbol: str, side: str, qty: float, leverage: int) -> OrderResult:
        """Open (or add to) a position with a simulated market fill.

        Adding to an existing position is only allowed in the same direction;
        opposing orders should go through close_position first.
        """
        if qty <= 0:
            return OrderResult(False, "qty must be positive")
        mark = self.market.mark_price(symbol)
        # Slippage works against the taker.
        fill = mark * (1 + SLIPPAGE) if side == "long" else mark * (1 - SLIPPAGE)
        fee = qty * fill * TAKER_FEE

        existing = self.positions.get(symbol)
        if existing is not None and existing.side != side:
            return OrderResult(False, f"opposing position open on {symbol}; close it first")

        required_margin = (qty * fill) / leverage
        if required_margin > self.free_margin():
            return OrderResult(
                False,
                f"insufficient margin: need {required_margin:.2f}, free {self.free_margin():.2f}",
            )

        self.cash -= fee
        if existing is None:
            pos = Position(
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=fill,
                leverage=leverage,
                opened_cycle=self._cycle,
            )
            self.positions[symbol] = pos
        else:
            # Weighted-average entry when scaling in.
            total_qty = existing.qty + qty
            existing.entry_price = (existing.entry_price * existing.qty + fill * qty) / total_qty
            existing.qty = total_qty
            pos = existing
        return OrderResult(True, "filled", fill_price=fill, position=pos)

    def close_position(self, symbol: str, qty: Optional[float] = None, reason: str = "manual") -> OrderResult:
        pos = self.positions.get(symbol)
        if pos is None:
            return OrderResult(False, f"no open position on {symbol}")
        close_qty = pos.qty if qty is None else min(qty, pos.qty)
        mark = self.market.mark_price(symbol)
        # Slippage works against the taker on the way out too.
        fill = mark * (1 - SLIPPAGE) if pos.side == "long" else mark * (1 + SLIPPAGE)
        fee = close_qty * fill * TAKER_FEE
        realized = (fill - pos.entry_price) * close_qty * pos.sign
        self.cash += realized - fee

        self.trade_history.append(
            Trade(
                cycle=self._cycle,
                symbol=symbol,
                side=pos.side,
                qty=close_qty,
                entry_price=pos.entry_price,
                exit_price=fill,
                realized_pnl=realized - fee,
                fees=fee,
                reason=reason,
                held_cycles=self._cycle - pos.opened_cycle,
            )
        )

        if close_qty >= pos.qty:
            del self.positions[symbol]
        else:
            pos.qty -= close_qty
        return OrderResult(True, f"closed {close_qty} {symbol} ({reason})", fill_price=fill)

    def set_leverage(self, symbol: str, leverage: int) -> OrderResult:
        self.leverage[symbol] = leverage
        return OrderResult(True, f"leverage for {symbol} set to {leverage}x")

    def set_tp_sl(self, symbol: str, take_profit: Optional[float] = None,
                  stop_loss: Optional[float] = None) -> OrderResult:
        pos = self.positions.get(symbol)
        if pos is None:
            return OrderResult(False, f"no open position on {symbol}")
        if take_profit is not None:
            pos.take_profit = take_profit
        if stop_loss is not None:
            pos.stop_loss = stop_loss
        return OrderResult(True, f"tp/sl set on {symbol}", position=pos)

    # --- per-tick maintenance ------------------------------------------

    def check_tp_sl(self) -> List[OrderResult]:
        """Trigger any TP/SL levels that the current mark has crossed."""
        results: List[OrderResult] = []
        for symbol in list(self.positions):
            pos = self.positions[symbol]
            mark = self.market.mark_price(symbol)
            hit_reason = None
            if pos.side == "long":
                if pos.stop_loss is not None and mark <= pos.stop_loss:
                    hit_reason = "stop_loss"
                elif pos.take_profit is not None and mark >= pos.take_profit:
                    hit_reason = "take_profit"
            else:  # short
                if pos.stop_loss is not None and mark >= pos.stop_loss:
                    hit_reason = "stop_loss"
                elif pos.take_profit is not None and mark <= pos.take_profit:
                    hit_reason = "take_profit"
            if hit_reason:
                results.append(self.close_position(symbol, reason=hit_reason))
        return results

    def get_positions(self) -> List[dict]:
        out = []
        for pos in self.positions.values():
            mark = self.market.mark_price(pos.symbol)
            out.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "qty": round(pos.qty, 6),
                "entry_price": round(pos.entry_price, 4),
                "mark_price": round(mark, 4),
                "leverage": pos.leverage,
                "unrealized_pnl": round(pos.unrealized_pnl(mark), 4),
                "take_profit": pos.take_profit,
                "stop_loss": pos.stop_loss,
                "held_cycles": self._cycle - pos.opened_cycle,
            })
        return out

    def get_trade_history(self, last_cycles: Optional[int] = None) -> List[dict]:
        trades = self.trade_history
        if last_cycles is not None:
            cutoff = self._cycle - last_cycles
            trades = [t for t in trades if t.cycle >= cutoff]
        return [t.__dict__ for t in trades]
