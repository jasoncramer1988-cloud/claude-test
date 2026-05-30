# CLAUDE.md

Guidance for working in this repository.

## What this is

A **paper-trading simulation** of the "Exchange → MCP → Claude Code" architecture.
It runs entirely offline with synthetic market data and simulated fills. There is
**no live exchange connection, no API keys, and no real money** anywhere in this
repo. Keep it that way unless the user explicitly asks to build a live backend —
and if they do, treat it as a high-stakes change they must own and review.

## Layout

```
config/strategy.yaml   strategy + risk parameters (edit here, not in code)
sim/market_data.py     synthetic GBM price feed (deterministic by seed)
sim/exchange.py        paper exchange: fills, PnL, TP/SL  (swap for live backend)
sim/risk_gate.py       6 non-negotiable pre-trade checks
sim/mcp_tools.py       MCP tool surface (reads + gated/audited writes)
sim/strategy.py        deterministic momentum stand-in for the reasoning loop
sim/state.py           jsonl decision/audit logs + equity curve
sim/runner.py          ties it together, drives the cycle loop
run_sim.py             CLI entry point
tests/                 pytest unit tests for the gate and exchange
```

## Commands

```bash
python3 run_sim.py --cycles 1000 --seed 42   # run a backtest
python3 run_sim.py --halt                     # show the kill switch blocking writes
python3 -m pytest tests/ -q                    # run the test suite
```

## Conventions

- Only `PyYAML` is required at runtime; everything else is stdlib. Don't add
  heavyweight deps (numpy, pandas) without a reason — sizing/EMA math is plain
  Python on purpose.
- Every order goes through `MCPTools` → `RiskGate`. Never let strategy code call
  `PaperExchange` directly; that would bypass the gate and the audit log.
- The risk gate is non-negotiable. If you change a cap, change it in
  `config/strategy.yaml`, and add/adjust a test in `tests/test_risk_gate.py`.
- Runs write to `runs/` (gitignored). Logs are truncated at the start of each run.
