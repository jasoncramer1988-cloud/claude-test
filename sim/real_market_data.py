"""Real-market replay feed -- drop-in for the synthetic MarketData.

Replays *actual* recent Bitcoin prices (pulled from a public market-data API)
through the same engine the paper simulator uses, so a backtest reflects the
current BTC market instead of a random walk. Read-only public data: no API
keys, no account, no orders -- this never touches a real exchange.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Dict, List

from .market_data import Kline


def fetch_btc_closes(days: int = 90) -> List[float]:
    """Hourly BTC/USD closes for the last `days` days (public, no auth)."""
    url = (
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        f"?vs_currency=usd&days={days}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "paper-sim/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return [float(p[1]) for p in data["prices"]]


class RealMarketData:
    """Replays a real price series with the MarketData interface."""

    def __init__(self, symbol: str, closes: List[float], warmup: int = 50):
        self.symbol = symbol
        self._closes = closes
        self._klines: List[Kline] = []
        prev = closes[0]
        for c in closes:
            self._klines.append(Kline(open=prev, high=max(prev, c), low=min(prev, c),
                                      close=c, volume=0.0))
            prev = c
        # Pointer starts after a warmup window so EMAs have history at cycle 1.
        self._i = min(warmup, len(closes) - 1)
        self.total_cycles = len(closes) - self._i - 1

    @property
    def symbols(self) -> List[str]:
        return [self.symbol]

    def tick(self) -> None:
        if self._i < len(self._klines) - 1:
            self._i += 1

    def get_klines(self, symbol: str, n: int = 50) -> List[Kline]:
        return list(self._klines[max(0, self._i - n + 1):self._i + 1])

    def mark_price(self, symbol: str) -> float:
        return self._klines[self._i].close

    def get_ticker(self, symbol: str) -> Dict[str, float]:
        last = self.mark_price(symbol)
        spread = last * 0.0001
        return {"symbol": symbol, "last_price": last, "mark_price": last,
                "bid": last - spread, "ask": last + spread}

    def get_orderbook(self, symbol: str, depth: int = 5) -> Dict[str, list]:
        mark = self.mark_price(symbol)
        tick = mark * 0.0001
        return {
            "symbol": symbol,
            "bids": [[round(mark - tick * (i + 1), 2), 1.0] for i in range(depth)],
            "asks": [[round(mark + tick * (i + 1), 2), 1.0] for i in range(depth)],
        }

    def get_funding_rate(self, symbol: str) -> float:
        return 0.0001
