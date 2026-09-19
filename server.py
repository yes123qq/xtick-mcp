import os
from typing import Any

import httpx
from fastmcp import FastMCP

BASE_URL = os.getenv("XTICK_BASE_URL", "https://api.xtick.top").rstrip("/")
TOKEN = os.getenv("XTICK_TOKEN", "")

mcp = FastMCP(
    "XTick Market Data",
    instructions="Read-only market-data tools backed by XTick. Never invent market data when an API call fails.",
)

async def _get(path: str, params: dict[str, Any]) -> Any:
    if not TOKEN:
        raise RuntimeError("XTICK_TOKEN is not configured on the server")
    query = {k: v for k, v in params.items() if v is not None}
    query["token"] = TOKEN
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        response = await client.get(path, params=query)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"XTick returned non-JSON (HTTP {response.status_code})") from exc

@mcp.tool
async def kline(code: str, period: str = "1d", market_type: int = 1,
                start_date: str | None = None, end_date: str | None = None,
                fq: int = 1) -> Any:
    """Get historical K-line/candlestick data for a security."""
    return await _get("/doc/kline/market", {
        "code": code, "period": period, "type": market_type,
        "start_date": start_date, "end_date": end_date, "fq": fq,
    })

@mcp.tool
async def orderbook(code: str, market_type: int = 1) -> Any:
    """Get the five-level order book for a security."""
    return await _get("/doc/order/five", {"code": code, "type": market_type})

@mcp.tool
async def quant_data(code: str, market_type: int = 1) -> Any:
    """Get XTick quantitative data/factors for a security."""
    return await _get("/doc/quant/data", {"code": code, "type": market_type})

@mcp.tool
async def hot_news(code: str | None = None, market_type: int | None = None) -> Any:
    """Get XTick hot market news, optionally filtered by security."""
    return await _get("/doc/hot/news", {"code": code, "type": market_type})

if __name__ == "__main__":
    mcp.run()
