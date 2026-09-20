# XTick MCP

Read-only XTick market-data MCP server. Version 0.3.0 fixes the public BYOK
credential path and adds an explicit Streamable HTTP entrypoint.

## Public deployment: each client supplies its own key

The default is `XTICK_CREDENTIAL_MODE=byok`. Send `X-XTick-Token` on **every**
MCP HTTP request that invokes a data tool. The server resolves the current
request's credential without saving it in a file, database, global variable,
or MCP session. It forwards that key to the configured XTick API only for
that request. The key is therefore visible transiently to this server and
the upstream API; BYOK does not mean the server never receives the key.

Do **not** set `XTICK_TOKEN` on a public hosted service. In default BYOK mode
an accidentally configured environment token is ignored. Only an explicitly
private deployment may use `XTICK_CREDENTIAL_MODE=private` with `XTICK_TOKEN`.
Even in private mode, a supplied header takes precedence. An empty or invalid
header fails rather than switching to the environment identity.

`credential_status` reports presence and source, not validity. Its
`validated` field is always false: only a successful live XTick query can
establish that the key and account permissions work.

## Actual tools

| Tool | Existing upstream mapping |
| --- | --- |
| `credential_status` | Local check; no upstream call |
| `daily_kline` | `/doc/kline/market`, `period=1d` |
| `minute_kline` | `/doc/kline/market`, periods `1m`, `5m`, `15m`, `30m`, `1h` |
| `historical_ticks` | `/doc/core/fenbi` |
| `historical_auction_detail` | `/doc/hot/biddetail` |
| `orderbook` | `/doc/order/five`, current five-level order book |

These endpoint paths preserve the previous implementation; this release
does not claim fresh verification of XTick's API contract, data availability,
subscription entitlements, or historical coverage. No order placement or
trading action is exposed. Tokens are not tool arguments.

## Install and run

Requires Python 3.11+.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -e '.[test]'
python -m pytest -q
```

### Remote HTTP service

```bash
python server.py --transport http --host 0.0.0.0 --port 8000
```

The MCP endpoint is `/mcp`; liveness is `/health`. Use HTTPS at the hosting
platform/reverse proxy. The health endpoint does not check XTick connectivity.
`PORT`, `HOST`, and `MCP_TRANSPORT` can also configure the entrypoint. Arguments
override environment values. No real key is needed to start or list tools.

A FastMCP-native host can import `server.py:mcp` and provide its own HTTP
transport. The CLI options above apply to `python server.py`, not to a host
that imports the `mcp` object directly.

### ModelScope configuration

The source repository and runtime configuration are separate from the final
public MCP endpoint. A GitHub URL is not an MCP server URL.

For a managed runner that installs this project and launches stdio, the
repository-root command is:

```json
{
  "mcpServers": {
    "xtick": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

**Important:** stdio cannot carry HTTP request headers. A hosted stdio gateway
will not automatically pass `X-XTick-Token` into this Python process. Do not
assume this configuration alone implements public BYOK. Prefer a native
HTTP deployment of the server for request-header BYOK. A platform that only
supports stdio needs a separately verified, per-client credential bridge;
never solve that by adding one shared public environment token.

For an HTTP/container runner, use the HTTP command above, expose its assigned
port, and configure the platform's HTTP MCP URL using the actual generated
HTTPS endpoint. Exact platform UI fields and header forwarding still need
to be verified on the deployed service.

### Header-capable MCP client

The following Python example reads the key from the **client machine's**
environment and sends it to the remote service. It does not store a server key.
Set `XTICK_MCP_URL` to the real deployed HTTPS endpoint ending in `/mcp`.

```python
import asyncio
import os
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def main():
    transport = StreamableHttpTransport(
        os.environ['XTICK_MCP_URL'],
        headers={'X-XTick-Token': os.environ['XTICK_TOKEN']},
    )
    async with Client(transport) as client:
        result = await client.call_tool('credential_status', {})
        print(result.data)  # Presence/source only; never the key.

asyncio.run(main())
```

### ChatGPT integration boundary

Fixing HTTP transport and BYOK does **not** finish direct ChatGPT integration.
OpenAI's authentication documentation states that the ChatGPT MCP client
cannot present custom API keys. A public server that requires the custom
`X-XTick-Token` header is therefore not directly compatible with that
connection flow by itself.

Keep the public server secret-free. A header-capable client-side bridge is
one possible integration direction, but its connection path must be tested.
A direct authenticated ChatGPT service instead needs an OAuth-compliant
integration and a deliberate strategy for resolving each user's upstream
XTick credential. This repository does not implement that layer. Do not
put an XTick key in a public URL, tool argument, chat message, or shared server
environment as a workaround. Do not treat ChatGPT's OAuth bearer token as an
XTick API key.

Official references (reviewed 2026-09-19):

- FastMCP HTTP headers: https://gofastmcp.com/servers/dependency-injection
- FastMCP transports: https://gofastmcp.com/deployment/running-server
- OpenAI authentication: https://developers.openai.com/plugins/build/auth
- OpenAI connection testing: https://developers.openai.com/plugins/deploy/connect-chatgpt

## Private/local stdio fallback

Only for a private process controlled by one user:

```bash
export XTICK_CREDENTIAL_MODE=private
# Supply XTICK_TOKEN using your local secret mechanism; never commit it.
python server.py
```

The default transport remains stdio for compatibility. This mode is not a
public multi-user deployment and must not be exposed as a shared service.
`.env.example` is a template, not an automatically loaded secrets file.

## Security and testing notes

The upstream query-string token behavior is preserved. Normal HTTPX URL logs
are redacted, HTTPcore debug logging is disabled, expected HTTP/network errors
are sanitized, upstream echoes of the current key are redacted, and redirects
are not followed. This cannot control a hosting platform's independent access
logs, traces, or the upstream provider's logging; configure those separately.
Only use a trusted HTTPS `XTICK_BASE_URL`, which is operator-controlled.

Tests use fabricated keys and mocked upstream HTTP responses. `test_core.py`
can run with HTTPX and pytest alone. `test_mcp.py` exercises the real FastMCP
schema and HTTP path when FastMCP is installed, and is skipped otherwise.
GitHub Actions installs the project before running both suites. Neither suite
validates paid XTick endpoints or proves the deployed ModelScope/ChatGPT path.
