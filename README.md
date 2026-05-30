# Exchange → MCP → Claude Code — Paper-Trading Simulation

A runnable, dependency-light simulation of the architecture in
*"How to Connect an Exchange to Claude Code"*: a perpetuals exchange feeding an
MCP tool layer, a risk gate that every write must pass, a reasoning/strategy
loop, and a state store that records decisions, an audit trail, and an equity
curve.

Everything runs in **paper mode**. Market data is synthetic and the MCP
server's *write* tools simulate fills — **no exchange, no API keys, no real
money**. The same code path could drive a live Bybit account by swapping the
exchange backend; the strategy and tool layers above it would not change. That
is the whole point the diagram makes ("same code can run paper mode").

> ⚠️ This is an educational simulation of a *system design*. It is **not**
> trading advice and the bundled momentum rule is a deliberately simple,
> transparent placeholder — not a profitable strategy. If you ever wire the
> exchange backend to real funds, that is entirely your responsibility.

## Easiest way (Windows): just double-click

1. Make sure **Python 3** is installed (https://www.python.org/downloads/ — tick
   *"Add Python to PATH"* during install).
2. **Double-click `run.bat`.**

A window opens, runs a 1000-cycle backtest, prints the report, and pops open a
chart of the simulated account value. The window stays open until you press a
key. No terminal, no commands, and **nothing to pip install** — the config has a
JSON fallback so PyYAML is optional.

## Running from a terminal (any OS)

```bash
python3 run_sim.py                      # 500 cycles, default config
python3 run_sim.py --cycles 2000 --seed 7
python3 run_sim.py --halt               # demonstrate the kill switch (0 trades)
python3 plot_equity.py runs/latest      # render runs/latest/equity_curve.png

python3 -m pytest tests/ -q             # 15 unit tests for the gate + exchange
```

PyYAML is optional (`pip install pyyaml` if you want to edit the `.yaml`
config); without it the simulator reads the bundled `config/strategy.json`.

Output lands in `runs/latest/`:

| File                | Contents                                              |
| ------------------- | ----------------------------------------------------- |
| `decisions.jsonl`   | what the strategy decided each cycle and why          |
| `audit.jsonl`       | every write, whether the gate passed it, and the fill |
| `equity_curve.csv`  | NAV / cash / unrealized PnL / open positions per cycle |

## How the code maps to the diagram

| Diagram box                       | Module                  |
| --------------------------------- | ----------------------- |
| Bybit Exchange (source of truth)  | `sim/exchange.py` (paper backend) + `sim/market_data.py` (synthetic feed) |
| Bybit MCP Server — the bridge     | `sim/mcp_tools.py` (read + write tools) |
| Risk Gate (6 gates)               | `sim/risk_gate.py`      |
| Claude Code reasoning loop        | `sim/strategy.py` (deterministic stand-in) |
| State store (logs + DB)           | `sim/state.py`          |
| Trigger / scheduler               | `sim/runner.py` (cycle cadence) |

### The MCP tool surface (`sim/mcp_tools.py`)

Reads (no side effects):
`get_klines`, `get_orderbook`, `get_ticker`, `get_funding_rate`,
`get_wallet_balance`, `get_positions`, `get_open_orders`, `get_trade_history`.

Writes (pass the risk gate, then logged to `audit.jsonl`):
`place_order`, `cancel_order`, `set_leverage`, `set_tp_sl`, `close_position`.

### The risk gate (`sim/risk_gate.py`)

Every write is checked *before* it reaches the exchange. The strategy can ask
for anything; the gate decides what actually executes.

1. **Kill switch** — if `/tmp/HALT_TRADING` exists, *all* writes are rejected.
2. **Daily loss cap** — once the day's drawdown hits −5% of NAV, new entries are
   blocked (de-risking closes are still allowed).
3. **Notional cap** — a single order may not exceed 30% of NAV.
4. **Leverage cap** — per-symbol max leverage (BTC ≤ 10×, ETH/SOL ≤ 5×).
5. **Price sanity** — a limit price more than ±8% from mark is rejected.
6. **Concurrent cap** — opening beyond the max number of positions is rejected.

De-risking actions (`close_position`, `set_tp_sl`) always pass — except the kill
switch, which stops everything.

## Configuration

All strategy and risk parameters live in [`config/strategy.yaml`](config/strategy.yaml)
— the diagram's "editable strategy prompt". Change the pairs, EMA periods, risk
caps, or schedule there; no code edits needed.

## What's intentionally simplified

- **Synthetic prices** (geometric Brownian motion), not real Bybit data — so
  runs are deterministic and reproducible by seed.
- **Immediate market fills** with fixed slippage + taker fee; no resting
  limit-order book, so `get_open_orders` is always empty and `cancel_order` is a
  no-op (both kept for surface parity with the real MCP server).
- **The strategy is a placeholder.** Swapping in a real reasoning loop means
  replacing `sim/strategy.py`; the tools and gate beneath it are unchanged.

## Going live (the parts this sim deliberately omits)

To point this at a real account you would replace `PaperExchange` with a Bybit
REST/WebSocket client and supply trade-only, IP-whitelisted API keys to a
dedicated sub-account. The MCP tool layer, risk gate, strategy, and state store
stay as-is. **This repository does not include live-trading code, and you should
test extensively on TESTNET before risking any capital.**
