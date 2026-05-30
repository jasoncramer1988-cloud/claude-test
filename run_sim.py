#!/usr/bin/env python3
"""Entry point for the paper-trading simulation.

Examples
--------
    python3 run_sim.py                       # default 500 cycles
    python3 run_sim.py --cycles 2000 --seed 7
    python3 run_sim.py --halt                # demo the kill switch
"""

from __future__ import annotations

import argparse
import os

from sim.runner import Simulation, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit-style perpetuals paper-trading simulation")
    parser.add_argument("--config", default="config/strategy.yaml", help="strategy/risk config")
    parser.add_argument("--cycles", type=int, default=500, help="number of market ticks to simulate")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible runs")
    parser.add_argument("--out", default="runs/latest", help="output directory for logs/equity curve")
    parser.add_argument("--quiet", action="store_true", help="suppress per-cycle progress")
    parser.add_argument("--halt", action="store_true",
                        help="create the kill-switch file before running (demonstrates the gate)")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.halt:
        kill_file = config["risk_gate"]["kill_switch_file"]
        open(kill_file, "w").close()
        print(f"[kill switch] created {kill_file} -- all writes will be rejected\n")

    sim = Simulation(config, seed=args.seed, out_dir=args.out)
    print(f"Running {args.cycles} cycles (seed {args.seed}) on {', '.join(config['allowed_pairs'])}")
    print(f"Starting balance: {config['account']['starting_balance']:.2f} USDT\n")

    report = sim.run(args.cycles, verbose=not args.quiet)

    print("\n" + "=" * 52)
    print("  SIMULATION REPORT")
    print("=" * 52)
    print(f"  Cycles             : {report.cycles}")
    print(f"  Starting balance   : {report.starting_balance:>12.2f} USDT")
    print(f"  Final NAV          : {report.final_nav:>12.2f} USDT")
    print(f"  Total return       : {report.total_return_pct:>11.2f} %")
    print(f"  Max drawdown       : {report.max_drawdown_pct:>11.2f} %")
    print(f"  Trades             : {report.num_trades}")
    print(f"  Win rate           : {report.win_rate_pct:>11.2f} %")
    print(f"  Fees paid          : {report.total_fees:>12.2f} USDT")
    print("=" * 52)
    print(f"  Logs   : {os.path.join(report.out_dir, 'decisions.jsonl')}")
    print(f"           {os.path.join(report.out_dir, 'audit.jsonl')}")
    print(f"  Equity : {os.path.join(report.out_dir, 'equity_curve.csv')}")
    print("=" * 52)

    if args.halt:
        print("\n[kill switch] note: with HALT active, expect 0 trades -- every write was gated.")


if __name__ == "__main__":
    main()
