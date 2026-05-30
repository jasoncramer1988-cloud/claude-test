"""Paper-trading simulation of the 'Exchange -> MCP -> Claude Code' loop.

Everything here runs in PAPER mode: market data is synthetic, and the MCP
server's write tools simulate fills instead of hitting a real exchange. The
same code path could drive a live Bybit account by swapping the exchange
backend -- which is exactly the point the architecture diagram makes.
"""

__all__ = [
    "market_data",
    "exchange",
    "risk_gate",
    "mcp_tools",
    "strategy",
    "state",
    "runner",
]
