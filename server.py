import os
from typing import Any

import httpx
from fastmcp import FastMCP

BASE_URL = os.getenv("XTICK_BASE_URL", "https://api.xtick.top").rstrip("/")

mcp = FastMCP(
    "XTick Market Data",
    instructions=(
        "Read-only XTick market-data tools. Use daily_kline for daily bars, "
        "minute_kline for historical minute bars, historical_ticks for historical "
        "tick/trade data, and historical_auction_detail for opening-auction details."
    ),
)


def _token() -> str:
    token = os.getenv("XTICK_TOKEN", "").strip()
    if not token:
        raise RuntimeError("XTICK_TOKEN environment variable is not configured")
    return token


async def _get(path: str, params: dict[str, Any]) -> Any:
    query = {k: v for k, v in params.items() if v is not None}
    query["token"] = _token()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        response = await client.get(path, params=query)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"XTick returned non-JSON (HTTP {response.status_code})"
            ) from exc


@mcp.tool
async def credential_status() -> dict[str, Any]:
    """Check whether XTICK_TOKEN is present without exposing its value."""
    token = os.getenv("XTICK_TOKEN", "").strip()
    return {"configured": bool(token), "source": "environment" if token else None}


@mcp.tool
async def daily_kline(
    code: str,
    start_date: str,
    end_date: str,
    market_type: int = 1,
    fq: int = 1,
) -> Any:
    """Get historical daily K-line bars.

    Dates use YYYY-MM-DD. market_type: 1=A-share, 2=index, 3=HK,
    4=ETF, 5=convertible bond. fq: 1=unadjusted, 2=forward,
    3=backward, 4=ratio-forward, 5=ratio-backward.
    """
    return await _get("/doc/kline/market", {
        "type": market_type,
        "code": code,
        "fq": fq,
        "period": "1d",
        "startDate": start_date,
        "endDate": end_date,
    })


@mcp.tool
async def minute_kline(
    code: str,
    start_date: str,
    end_date: str,
    period: str = "1m",
    market_type: int = 1,
    fq: int = 1,
) -> Any:
    """Get historical minute K-line bars.

    period must be one of 1m, 5m, 15m, 30m, 1h. XTick documents a
    maximum 31-day span per request for minute data.
    """
    allowed = {"1m", "5m", "15m", "30m", "1h"}
    if period not in allowed:
        raise ValueError(f"period must be one of {sorted(allowed)}")
    return await _get("/doc/kline/market", {
        "type": market_type,
        "code": code,
        "fq": fq,
        "period": period,
        "startDate": start_date,
        "endDate": end_date,
    })


@mcp.tool
async def historical_ticks(
    code: str,
    trade_date: str,
    market_type: int = 1,
) -> Any:
    """Get historical per-trade/tick data for one security and trading date.

    trade_date uses YYYY-MM-DD.
    """
    return await _get("/doc/core/fenbi", {
        "type": market_type,
        "code": code,
        "tradeDate": trade_date,
    })


@mcp.tool
async def historical_auction_detail(
    code: str,
    trade_date: str,
    market_type: int = 1,
) -> Any:
    """Get all opening call-auction detail records for one security/date.

    XTick's biddetail endpoint is updated after the 09:25 opening auction.
    trade_date uses YYYY-MM-DD.
    """
    return await _get("/doc/hot/biddetail", {
        "type": market_type,
        "code": code,
        "tradeDate": trade_date,
    })


@mcp.tool
async def auction_history(
    code: str,
    start_date: str,
    end_date: str,
    seq: int = 0,
    market_type: int = 1,
) -> Any:
    """Get historical auction snapshots over a date range.

    seq=0 returns the 09:25 record; seq=1 returns the previous auction record.
    Use historical_auction_detail when all auction records for one date are needed.
    """
    if seq not in (0, 1):
        raise ValueError("seq must be 0 or 1")
    return await _get("/doc/hot/bidhistory", {
        "type": market_type,
        "code": code,
        "seq": seq,
        "startDate": start_date,
        "endDate": end_date,
    })


@mcp.tool
async def orderbook(code: str, market_type: int = 1) -> Any:
    """Get the current five-level order book for a security."""
    return await _get("/doc/order/five", {"type": market_type, "code": code})


@mcp.tool
async def historical_orderbook(
    code: str,
    trade_date: str,
    market_type: int = 1,
) -> Any:
    """Get historical five-level/depth market data for one trading date."""
    return await _get("/doc/order/history", {
        "type": market_type,
        "code": code,
        "tradeDate": trade_date,
    })


@mcp.tool
async def quant_data(
    field: str = "all",
    market_type: int = 1,
) -> Any:
    """Get real-time XTick quantitative factors. field may be all or selected fields."""
    return await _get("/doc/quant/data", {"type": market_type, "field": field})


@mcp.tool
async def hot_news(minutes: int = 30, trade_date: str | None = None) -> Any:
    """Get financial news. minutes>0 gets recent news; minutes=0 uses trade_date."""
    return await _get("/doc/hot/news", {
        "minutes": minutes,
        "tradeDate": trade_date,
    })


if __name__ == "__main__":
    mcp.run()
