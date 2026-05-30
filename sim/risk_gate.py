"""Risk gate -- every write tool passes through here BEFORE the exchange.

These checks are non-negotiable and sit between the strategy's intent and the
exchange. The strategy can ask for anything; the gate decides what actually
reaches the order book. Mirrors the six gates in the architecture diagram:

    Kill Switch | Daily Loss Cap | Notional Cap | Leverage Cap |
    Price Sanity | Concurrent Cap
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class RiskDecision:
    allowed: bool
    gate: str          # which gate made the call ("" if allowed by all)
    reason: str


@dataclass
class OrderIntent:
    """A proposed write, normalized so the gate can reason about it."""

    action: str                       # "open" | "close" | "set_leverage" | "set_tp_sl"
    symbol: str
    side: Optional[str] = None        # "long" | "short" for opens
    qty: float = 0.0
    leverage: int = 1
    limit_price: Optional[float] = None  # None == market order


class RiskGate:
    def __init__(self, config: dict):
        rg = config["risk_gate"]
        self.kill_switch_file = rg["kill_switch_file"]
        self.daily_loss_cap_pct = rg["daily_loss_cap_pct"]
        self.notional_cap_pct = rg["notional_cap_pct"]
        self.price_sanity_pct = rg["price_sanity_pct"]
        self.max_concurrent = rg["max_concurrent_positions"]
        self.leverage_caps = rg["leverage_caps"]

    def leverage_cap_for(self, symbol: str) -> int:
        return self.leverage_caps.get(symbol, self.leverage_caps.get("default", 1))

    def check(self, intent: OrderIntent, exchange, day_start_nav: float) -> RiskDecision:
        # 1. Kill switch -- halts ALL writes, no exceptions.
        if os.path.exists(self.kill_switch_file):
            return RiskDecision(False, "kill_switch", f"{self.kill_switch_file} present -> all writes halted")

        # Closes and de-risking actions are always allowed past this point
        # (other than the kill switch), since they reduce exposure.
        if intent.action in ("close", "set_tp_sl"):
            return RiskDecision(True, "", "de-risking action allowed")

        nav = exchange.nav()

        # 2. Daily loss cap -- block NEW entries after the day's drawdown limit.
        if intent.action == "open":
            drawdown = (day_start_nav - nav) / day_start_nav if day_start_nav > 0 else 0.0
            if drawdown >= self.daily_loss_cap_pct:
                return RiskDecision(
                    False, "daily_loss_cap",
                    f"daily drawdown {drawdown:.1%} >= cap {self.daily_loss_cap_pct:.1%}",
                )

        # 4. Leverage cap (applies to opens and explicit set_leverage).
        cap = self.leverage_cap_for(intent.symbol)
        if intent.leverage > cap:
            return RiskDecision(
                False, "leverage_cap",
                f"{intent.leverage}x exceeds {intent.symbol} cap of {cap}x",
            )
        if intent.action == "set_leverage":
            return RiskDecision(True, "", "leverage within cap")

        # From here on we are evaluating an "open".
        mark = exchange.market.mark_price(intent.symbol)

        # 3. Notional cap -- single order may not exceed N% of NAV.
        notional = intent.qty * mark
        if notional > self.notional_cap_pct * nav:
            return RiskDecision(
                False, "notional_cap",
                f"notional {notional:.2f} > {self.notional_cap_pct:.0%} of NAV ({self.notional_cap_pct * nav:.2f})",
            )

        # 5. Price sanity -- limit price too far from mark is likely a fat finger.
        if intent.limit_price is not None:
            deviation = abs(intent.limit_price - mark) / mark
            if deviation > self.price_sanity_pct:
                return RiskDecision(
                    False, "price_sanity",
                    f"limit {intent.limit_price} is {deviation:.1%} from mark (cap {self.price_sanity_pct:.0%})",
                )

        # 6. Concurrent cap -- don't open beyond the max number of positions.
        # Scaling into an existing symbol doesn't add a new slot.
        opens_new_slot = intent.symbol not in exchange.positions
        if opens_new_slot and len(exchange.positions) >= self.max_concurrent:
            return RiskDecision(
                False, "concurrent_cap",
                f"already at {len(exchange.positions)} concurrent positions (max {self.max_concurrent})",
            )

        return RiskDecision(True, "", "all gates passed")
