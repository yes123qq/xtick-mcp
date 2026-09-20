"""Read-only XTick MCP server. Public deployments default to per-request BYOK."""
import argparse
import os
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from starlette.requests import Request
from starlette.responses import JSONResponse

from xtick_core import XTickError, get_json, resolve_credential

BASE_URL = os.getenv("XTICK_BASE_URL", "https://api.xtick.top")
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}

mcp = FastMCP(
    "XTick Market Data",
    instructions=(
        "Read-only XTick market data. Each client supplies its own X-XTick-Token "
        "HTTP header. Never ask for credentials as tool arguments or in chat. "
        "credential_status checks credential presence, not validity or data access."
    ),
    mask_error_details=True,
)


def _credential():
    # FastMCP's HTTP helper, NOT ctx.request_context.request.headers.
    return resolve_credential(get_http_headers(), os.environ)


async def _get(path: str, params: dict[str, Any]) -> Any:
    try:
        return await get_json(path, params, _credential(), BASE_URL)
    except XTickError as exc:
        raise ToolError(str(exc)) from None


@mcp.tool(annotations={**READ_ONLY, "openWorldHint": False})
async def credential_status() -> dict[str, Any]:
    """Check credential presence/source without revealing it or calling XTick."""
    try:
        credential = _credential()
    except XTickError as exc:
        return {"configured": False, "source": None, "validated": False, "reason": str(exc)}
    return {"configured": True, "source": credential.source, "validated": False}


@mcp.tool(annotations=READ_ONLY)
async def daily_kline(
    code: str, start_date: str, end_date: str, market_type: int = 1, fq: int = 1,
) -> Any:
    """Get historical daily K-line data; dates use YYYY-MM-DD."""
    return await _get("/doc/kline/market", {
        "type": market_type, "code": code, "period": "1d", "fq": fq,
        "startDate": start_date, "endDate": end_date,
    })


@mcp.tool(annotations=READ_ONLY)
async def minute_kline(
    code: str, start_date: str, end_date: str,
    period: Literal["1m", "5m", "15m", "30m", "1h"] = "1m",
    market_type: int = 1, fq: int = 1,
) -> Any:
    """Get historical minute K-line data; dates use YYYY-MM-DD."""
    return await _get("/doc/kline/market", {
        "type": market_type, "code": code, "period": period, "fq": fq,
        "startDate": start_date, "endDate": end_date,
    })


@mcp.tool(annotations=READ_ONLY)
async def historical_ticks(code: str, trade_date: str, market_type: int = 1) -> Any:
    """Get historical tick/fenbi data for a YYYY-MM-DD trading date."""
    return await _get("/doc/core/fenbi", {
        "type": market_type, "code": code, "tradeDate": trade_date,
    })


@mcp.tool(annotations=READ_ONLY)
async def historical_auction_detail(code: str, trade_date: str, market_type: int = 1) -> Any:
    """Get historical opening auction detail for a YYYY-MM-DD trading date."""
    return await _get("/doc/hot/biddetail", {
        "type": market_type, "code": code, "tradeDate": trade_date,
    })


@mcp.tool(annotations=READ_ONLY)
async def orderbook(code: str, market_type: int = 1) -> Any:
    """Get the current five-level order book; this is not historical depth."""
    return await _get("/doc/order/five", {"type": market_type, "code": code})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness only; no credentials, configuration values, or upstream calls."""
    return JSONResponse({"status": "ok", "service": "xtick-mcp"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["stdio", "http"],
                        default=os.getenv("MCP_TRANSPORT", "stdio"))
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=os.getenv("PORT", "8000"))
    args = parser.parse_args()
    if args.transport not in {"stdio", "http"}:
        parser.error("MCP_TRANSPORT must be stdio or http")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", host=args.host, port=args.port, path="/mcp")


if __name__ == "__main__":
    main()
