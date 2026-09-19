# XTick MCP

Read-only XTick market-data MCP server built with FastMCP and intended for deployment on Horizon.

## MCP tools

- `kline` — historical K-line/candlestick data
- `orderbook` — five-level order book
- `quant_data` — XTick quantitative data/factors
- `hot_news` — hot market news

## Secret configuration

Set the token on the deployment platform, not in GitHub:

```text
XTICK_TOKEN=your-token
```

Optional:

```text
XTICK_BASE_URL=https://api.xtick.top
```

Never commit your real XTick token. Local `.env` files are ignored.

## Local development

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
export XTICK_TOKEN='your-token'
fastmcp dev server.py:mcp
```

## Horizon deployment

1. Connect this GitHub repository to Horizon.
2. Use this server entrypoint:

```text
server.py:mcp
```

3. Add `XTICK_TOKEN` as a deployment environment variable/secret.
4. Deploy.
5. Copy Horizon's remote MCP URL into your MCP client.

The XTick token stays server-side and is never an MCP tool argument.

## Design

The initial tool surface is intentionally small and read-only. Validate endpoint parameters against the XTick documentation/account you use before adding more APIs.
