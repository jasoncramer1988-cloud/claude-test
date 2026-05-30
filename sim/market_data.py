"""Synthetic market-data feed.

Stands in for Bybit's REST + WebSocket market endpoints. Each symbol's price
follows a geometric Brownian motion so the simulation produces realistic
trends, pullbacks, and the occasional whipsaw. The feed is deterministic for a
given seed, which keeps backtests reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Kline:
    """A single OHLCV candle."""

    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class _SymbolState:
    price: float
    drift: float          # per-tick expected log-return
    volatility: float     # per-tick log-return stddev
    funding_rate: float
    klines: List[Kline] = field(default_factory=list)


# Reasonable starting points so the numbers look like the real market.
_DEFAULTS = {
    "BTCUSDT": dict(price=68000.0, drift=0.0002, volatility=0.004, funding_rate=0.0001),
    "ETHUSDT": dict(price=3500.0, drift=0.0001, volatility=0.006, funding_rate=0.0001),
    "SOLUSDT": dict(price=160.0, drift=0.0003, volatility=0.010, funding_rate=0.00015),
}


class MarketData:
    """Deterministic synthetic feed for a fixed set of symbols."""

    def __init__(self, symbols: List[str], seed: int = 42, history: int = 200):
        self._rng = random.Random(seed)
        self._symbols: Dict[str, _SymbolState] = {}
        for sym in symbols:
            cfg = _DEFAULTS.get(sym, dict(price=100.0, drift=0.0, volatility=0.008, funding_rate=0.0001))
            self._symbols[sym] = _SymbolState(**cfg)
        # Warm up history so EMAs have something to chew on from cycle 0.
        for _ in range(history):
            self.tick()

    @property
    def symbols(self) -> List[str]:
        return list(self._symbols)

    def tick(self) -> None:
        """Advance every symbol by one candle."""
        for state in self._symbols.values():
            open_ = state.price
            ret = state.drift + state.volatility * self._rng.gauss(0.0, 1.0)
            close = open_ * math.exp(ret)
            # Intra-candle wick noise.
            wick = abs(self._rng.gauss(0.0, state.volatility)) * open_
            high = max(open_, close) + wick
            low = min(open_, close) - wick
            volume = abs(self._rng.gauss(1000.0, 250.0))
            state.klines.append(Kline(open_, high, low, close, volume))
            state.price = close
            # Funding drifts slowly and mean-reverts toward zero.
            state.funding_rate += self._rng.gauss(0.0, 0.00002)
            state.funding_rate *= 0.999

    # --- read endpoints (mirror the MCP read tools) ---------------------

    def get_klines(self, symbol: str, n: int = 50) -> List[Kline]:
        return list(self._symbols[symbol].klines[-n:])

    def mark_price(self, symbol: str) -> float:
        return self._symbols[symbol].price

    def get_ticker(self, symbol: str) -> Dict[str, float]:
        last = self._symbols[symbol].price
        spread = last * 0.0001
        return {
            "symbol": symbol,
            "last_price": last,
            "mark_price": last,
            "bid": last - spread,
            "ask": last + spread,
        }

    def get_orderbook(self, symbol: str, depth: int = 5) -> Dict[str, list]:
        mark = self._symbols[symbol].price
        tick = mark * 0.0001
        bids = [[round(mark - tick * (i + 1), 4), round(self._rng.uniform(0.5, 5.0), 3)] for i in range(depth)]
        asks = [[round(mark + tick * (i + 1), 4), round(self._rng.uniform(0.5, 5.0), 3)] for i in range(depth)]
        return {"symbol": symbol, "bids": bids, "asks": asks}

    def get_funding_rate(self, symbol: str) -> float:
        return self._symbols[symbol].funding_rate
