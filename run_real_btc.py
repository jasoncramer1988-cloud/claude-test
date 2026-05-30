#!/usr/bin/env python3
"""Backtest the strategy on REAL recent Bitcoin market data.

Pulls actual hourly BTC/USD prices (public feed, no account, no keys) and replays
them through the same paper engine -- so you can see how the model would have
behaved in the current market with a chosen starting capital.

    python3 run_real_btc.py --capital 10000 --days 90

This is a backtest on real data. It does NOT connect to any exchange, place any
orders, or move any money.
"""

from __future__ import annotations

import argparse
import os

from sim.real_market_data import RealMarketData, fetch_btc_closes
from sim.runner import Simulation, load_config


def main() -> None:
    p = argparse.ArgumentParser(description="Backtest on real BTC market data")
    p.add_argument("--capital", type=float, default=10000.0, help="starting USD capital")
    p.add_argument("--days", type=int, default=90, help="how many days of history (2-90 = hourly)")
    p.add_argument("--config", default="config/strategy.yaml")
    p.add_argument("--out", default="runs/real_btc")
    args = p.parse_args()

    config = load_config(args.config)
    # This run is BTC-only with the requested capital.
    config["allowed_pairs"] = ["BTCUSDT"]
    config["account"]["starting_balance"] = args.capital

    print(f"Fetching {args.days} days of real BTC/USD hourly prices ...")
    closes = fetch_btc_closes(args.days)
    market = RealMarketData("BTCUSDT", closes)
    cycles = market.total_cycles
    print(f"Got {len(closes)} candles. "
          f"Price range over window: {min(closes):,.0f} -> {max(closes):,.0f} USD")
    print(f"Backtesting {cycles} hourly cycles on REAL data "
          f"with {args.capital:,.0f} USD starting capital.\n")

    sim = Simulation(config, out_dir=args.out, market=market)
    report = sim.run(cycles, verbose=False)

    # Buy-and-hold benchmark over the same (post-warmup) window for context.
    bh_return = (closes[-1] / closes[50] - 1) * 100

    print("=" * 56)
    print("  REAL-DATA BTC BACKTEST")
    print("=" * 56)
    print(f"  Data source        : CoinGecko (real BTC/USD, hourly)")
    print(f"  Window             : last {args.days} days ({cycles} hourly cycles)")
    print(f"  Starting capital   : {report.starting_balance:>14,.2f} USD")
    print(f"  Final NAV          : {report.final_nav:>14,.2f} USD")
    print(f"  Strategy return    : {report.total_return_pct:>13.2f} %")
    print(f"  Buy & hold (BTC)   : {bh_return:>13.2f} %")
    print(f"  Max drawdown       : {report.max_drawdown_pct:>13.2f} %")
    print(f"  Trades             : {report.num_trades}")
    print(f"  Win rate           : {report.win_rate_pct:>13.2f} %")
    print(f"  Fees paid          : {report.total_fees:>14,.2f} USD")
    print("=" * 56)
    print(f"  Logs/equity in: {report.out_dir}/")
    print("=" * 56)
    print("\n  NOTE: backtest on real data, no live trading, no funds moved.")


if __name__ == "__main__":
    main()
