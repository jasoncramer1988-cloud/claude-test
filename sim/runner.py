"""Simulation runner -- wires every component together and drives the loop.

One cycle == one market tick, standing in for the diagram's cron cadence:
    position_check_every cycles -> manage open positions   ("*/1 min")
    entry_scan_every cycles     -> scan for new entries     ("*/15 min")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

try:
    import yaml  # optional: only needed to read the .yaml config
except ImportError:  # pragma: no cover
    yaml = None

from .exchange import PaperExchange
from .market_data import MarketData
from .mcp_tools import MCPTools
from .risk_gate import RiskGate
from .state import EquityPoint, StateStore
from .strategy import MomentumStrategy


@dataclass
class SimReport:
    cycles: int
    starting_balance: float
    final_nav: float
    realized_pnl: float
    total_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: float
    total_fees: float
    out_dir: str


def load_config(path: str) -> dict:
    """Load the strategy/risk config.

    Prefers the YAML file if PyYAML is installed; otherwise transparently falls
    back to the bundled JSON copy (config/strategy.json) so the simulation runs
    with zero third-party dependencies -- nothing to pip install.
    """
    if path.endswith((".yaml", ".yml")) and yaml is not None:
        with open(path) as fh:
            return yaml.safe_load(fh)

    # Fall back to the JSON sibling (same content, no dependency needed).
    json_path = path
    if path.endswith((".yaml", ".yml")):
        json_path = os.path.splitext(path)[0] + ".json"
    with open(json_path) as fh:
        return json.load(fh)


class Simulation:
    def __init__(self, config: dict, seed: int = 42, out_dir: str = "runs/latest"):
        self.config = config
        symbols = config["allowed_pairs"]
        self.market = MarketData(symbols, seed=seed)
        self.exchange = PaperExchange(self.market, config["account"]["starting_balance"])
        self.risk_gate = RiskGate(config)
        self.state = StateStore(out_dir)
        self.tools = MCPTools(self.market, self.exchange, self.risk_gate, self.state)
        self.strategy = MomentumStrategy(self.tools, config)
        self.out_dir = out_dir
        self._entry_every = config["schedule"]["entry_scan_every"]
        self._check_every = config["schedule"]["position_check_every"]

    def run(self, cycles: int, verbose: bool = False) -> SimReport:
        for cycle in range(1, cycles + 1):
            # 1. New market data arrives.
            self.market.tick()
            self.exchange.set_cycle(cycle)

            # 2. Exchange triggers any TP/SL the new mark crossed.
            self.exchange.check_tp_sl()

            # 3. Position check (every cycle) then entry scan (periodic).
            if cycle % self._check_every == 0:
                self.strategy.manage_positions(cycle)
            if cycle % self._entry_every == 0:
                self.strategy.entry_scan(cycle)

            # 4. Record equity for the dashboard.
            bal = self.exchange.wallet_balance()
            self.state.record_equity(EquityPoint(
                cycle=cycle,
                nav=bal["nav"],
                cash=bal["cash"],
                unrealized_pnl=bal["unrealized_pnl"],
                open_positions=len(self.exchange.positions),
            ))
            if verbose and cycle % max(1, cycles // 20) == 0:
                print(f"  cycle {cycle:>5}  NAV {bal['nav']:>10.2f}  "
                      f"open {len(self.exchange.positions)}  trades {len(self.exchange.trade_history)}")

        # Close out anything still open so the final NAV is fully realized.
        for symbol in list(self.exchange.positions):
            self.tools.close_position(symbol, reason="end_of_sim")

        self.state.flush_equity_csv()
        return self._report(cycles)

    def _report(self, cycles: int) -> SimReport:
        start = self.exchange.starting_balance
        final_nav = self.exchange.nav()
        navs = [p.nav for p in self.state.equity_curve] or [start]
        peak = navs[0]
        max_dd = 0.0
        for nav in navs:
            peak = max(peak, nav)
            if peak > 0:
                max_dd = max(max_dd, (peak - nav) / peak)

        trades = self.exchange.trade_history
        wins = sum(1 for t in trades if t.realized_pnl > 0)
        total_fees = sum(t.fees for t in trades)

        return SimReport(
            cycles=cycles,
            starting_balance=start,
            final_nav=final_nav,
            realized_pnl=self.exchange.cash - start,
            total_return_pct=(final_nav - start) / start * 100 if start else 0.0,
            max_drawdown_pct=max_dd * 100,
            num_trades=len(trades),
            win_rate_pct=(wins / len(trades) * 100) if trades else 0.0,
            total_fees=total_fees,
            out_dir=self.out_dir,
        )
