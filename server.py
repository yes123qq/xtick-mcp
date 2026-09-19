import os
from typing import Any

import httpx
from fastmcp import FastMCP

BASE_URL = os.getenv("XTICK_BASE_URL", "https://api.xtick.top").rstrip("/")

mcp = FastMCP(
    "XTick Market Data",
    instructions="Read-only market-data tools backed by XTick. Never invent market data when an API call fails.",
)


async def _get_token() -> tuple[str, str]:
    """Resolve XTick token without ever exposing its value.

    Resolution order:
    1. XTICK_TOKEN environment variable
    2. Prefect/Horizon Variable named XTICK_TOKEN
    """
    token = os.getenv("XTICK_TOKEN", "").strip()
    if token:
        return token, "environment"

    try:
        from prefect.variables import Variable

        value = await Variable.get("XTICK_TOKEN", default=None)
        if value is not None and str(value).strip():
            return str(value).strip(), "prefect-variable"
    except Exception as exc:
        # Do not include credentials or potentially sensitive Prefect responses.
        prefect_error = f"{type(exc).__name__}: {exc}"
    else:
        prefect_error = "variable missing or empty"

    raise RuntimeError(
        "XTICK_TOKEN is not configured. Checked environment variable and "
        f"Prefect/Horizon Variable XTICK_TOKEN ({prefect_error})."
    )


async def _get(path: str, params: dict[str, Any]) -> Any:
    token, _ = await _get_token()
    query = {k: v for k, v in params.items() if v is not None}
    query["token"] = token

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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
    """Check whether XTick credentials are available without revealing the token."""
    try:
        _, source = await _get_token()
        return {"configured": True, "source": source}
    except Exception as exc:
        return {"configured": False, "error": str(exc)}


@mcp.tool
async def kline(
    code: str,
    period: str = "1d",
    market_type: int = 1,
    start_date: str | None = None,
    end_date: str | None = None,
    fq: int = 1,
) -> Any:
    """Get historical K-line/candlestick data for a security."""
    return await _get(
        "/doc/kline/market",
        {
            "code": code,
            "period": period,
            "type": market_type,
            "start_date": start_date,
            "end_date": end_date,
            "fq": fq,
        },
    )


@mcp.tool
async def orderbook(code: str, market_type: int = 1) -> Any:
    """Get the five-level order book for a security."""
    return await _get("/doc/order/five", {"code": code, "type": market_type})


@mcp.tool
async def quant_data(code: str, market_type: int = 1) -> Any:
    """Get XTick quantitative data/factors for a security."""
    return await _get("/doc/quant/data", {"code": code, "type": market_type})


@mcp.tool
async def hot_news(
    code: str | None = None, market_type: int | None = None
) -> Any:
    """Get XTick hot market news, optionally filtered by security."""
    return await _get("/doc/hot/news", {"code": code, "type": market_type})


if __name__ == "__main__":
    mcp.run()
