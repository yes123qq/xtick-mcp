import os
from typing import Any

import httpx
from fastmcp import Context, FastMCP

BASE_URL = os.getenv("XTICK_BASE_URL", "https://api.xtick.top").rstrip("/")

mcp = FastMCP(
    "XTick Market Data",
    instructions="XTick market data MCP. XTick token can be supplied by MCP client header X-XTick-Token or server environment XTICK_TOKEN.",
)


async def _token(ctx: Context | None = None) -> str:
    # Public MCP deployment: allow each client to provide its own XTick key.
    if ctx is not None:
        try:
            token = ctx.request_context.request.headers.get("X-XTick-Token", "")
            if token:
                return token.strip()
        except Exception:
            pass

    # Private deployment fallback.
    token = os.getenv("XTICK_TOKEN", "").strip()
    if token:
        return token

    raise RuntimeError(
        "No XTick token provided. Configure MCP client header X-XTick-Token "
        "or server environment variable XTICK_TOKEN."
    )


async def _get(path: str, params: dict[str, Any], ctx: Context | None = None) -> Any:
    query = {k: v for k, v in params.items() if v is not None}
    query["token"] = await _token(ctx)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        response = await client.get(path, params=query)
        response.raise_for_status()
        return response.json()


@mcp.tool
async def credential_status(ctx: Context) -> dict[str, Any]:
    """Check whether an XTick credential was supplied without exposing it."""
    try:
        await _token(ctx)
        return {"configured": True}
    except Exception:
        return {"configured": False}


@mcp.tool
async def daily_kline(code: str, start_date: str, end_date: str, ctx: Context, market_type: int = 1, fq: int = 1) -> Any:
    """Get historical daily K-line data."""
    return await _get("/doc/kline/market", {
        "type": market_type,
        "code": code,
        "period": "1d",
        "fq": fq,
        "startDate": start_date,
        "endDate": end_date,
    }, ctx)


@mcp.tool
async def minute_kline(code: str, start_date: str, end_date: str, ctx: Context, period: str = "1m", market_type: int = 1, fq: int = 1) -> Any:
    """Get historical minute K-line data. Supported periods: 1m,5m,15m,30m,1h."""
    return await _get("/doc/kline/market", {
        "type": market_type,
        "code": code,
        "period": period,
        "fq": fq,
        "startDate": start_date,
        "endDate": end_date,
    }, ctx)


@mcp.tool
async def historical_ticks(code: str, trade_date: str, ctx: Context, market_type: int = 1) -> Any:
    """Get historical tick/fenbi data."""
    return await _get("/doc/core/fenbi", {
        "type": market_type,
        "code": code,
        "tradeDate": trade_date,
    }, ctx)


@mcp.tool
async def historical_auction_detail(code: str, trade_date: str, ctx: Context, market_type: int = 1) -> Any:
    """Get historical opening auction detail."""
    return await _get("/doc/hot/biddetail", {
        "type": market_type,
        "code": code,
        "tradeDate": trade_date,
    }, ctx)


@mcp.tool
async def orderbook(code: str, ctx: Context, market_type: int = 1) -> Any:
    """Get current five-level order book."""
    return await _get("/doc/order/five", {"type": market_type, "code": code}, ctx)


if __name__ == "__main__":
    mcp.run()
