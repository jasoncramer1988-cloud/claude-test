"""State store -- append-only logs plus the in-memory equity curve.

Mirrors the diagram's state layer: decisions.jsonl (what the strategy decided
and why), audit.jsonl (every write that reached the risk gate and its outcome),
and an equity curve the dashboard would read.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class EquityPoint:
    cycle: int
    nav: float
    cash: float
    unrealized_pnl: float
    open_positions: int


class StateStore:
    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.decisions_path = os.path.join(out_dir, "decisions.jsonl")
        self.audit_path = os.path.join(out_dir, "audit.jsonl")
        self.equity_path = os.path.join(out_dir, "equity_curve.csv")
        self.equity_curve: List[EquityPoint] = []
        # Truncate logs at the start of a run so each run is self-contained.
        open(self.decisions_path, "w").close()
        open(self.audit_path, "w").close()

    def _append(self, path: str, record: dict) -> None:
        record = {"ts": time.time(), **record}
        with open(path, "a") as fh:
            fh.write(json.dumps(record) + "\n")

    def log_decision(self, record: dict) -> None:
        self._append(self.decisions_path, record)

    def log_audit(self, record: dict) -> None:
        self._append(self.audit_path, record)

    def record_equity(self, point: EquityPoint) -> None:
        self.equity_curve.append(point)

    def flush_equity_csv(self) -> None:
        with open(self.equity_path, "w") as fh:
            fh.write("cycle,nav,cash,unrealized_pnl,open_positions\n")
            for p in self.equity_curve:
                fh.write(f"{p.cycle},{p.nav:.4f},{p.cash:.4f},{p.unrealized_pnl:.4f},{p.open_positions}\n")
