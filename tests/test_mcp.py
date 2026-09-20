"""Real FastMCP smoke tests; install project dependencies before running."""
import pytest

pytest.importorskip("fastmcp")
from fastmcp import Client
import server


@pytest.mark.asyncio
async def test_tool_schema_and_missing_credentials(monkeypatch):
    monkeypatch.setenv("XTICK_CREDENTIAL_MODE", "byok")
    monkeypatch.setenv("XTICK_TOKEN", "must-not-be-shared")
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {
            "credential_status", "daily_kline", "minute_kline", "historical_ticks",
            "historical_auction_detail", "orderbook",
        }
        for tool in tools:
            assert tool.annotations.readOnlyHint is True
            assert "token" not in tool.inputSchema.get("properties", {})
            assert "ctx" not in tool.inputSchema.get("properties", {})
        status = await client.call_tool("credential_status", {})
        assert status.data["configured"] is False
        assert status.data["validated"] is False


@pytest.mark.asyncio
async def test_private_presence_does_not_validate_key(monkeypatch):
    monkeypatch.setenv("XTICK_CREDENTIAL_MODE", "private")
    monkeypatch.setenv("XTICK_TOKEN", "fake-private-key")
    async with Client(server.mcp) as client:
        status = await client.call_tool("credential_status", {})
        assert status.data == {"configured": True, "source": "environment", "validated": False}


def test_http_headers_are_request_scoped(monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setenv("XTICK_CREDENTIAL_MODE", "byok")
    monkeypatch.setenv("XTICK_TOKEN", "must-not-be-shared")
    seen = []

    async def fake_get(path, params, credential, base_url):
        seen.append(credential.token)
        return {"code": params["code"]}

    monkeypatch.setattr(server, "get_json", fake_get)
    app = server.mcp.http_app(stateless_http=True, json_response=True)
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app) as client:
        initialized = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "xtick-test", "version": "1"}},
        })
        assert initialized.status_code == 200
        headers["MCP-Protocol-Version"] = initialized.json()["result"]["protocolVersion"]
        for index, key in enumerate(["first-client-key", "second-client-key"]):
            response = client.post("/mcp", headers={**headers, "X-XTick-Token": key}, json={
                "jsonrpc": "2.0", "id": index + 2, "method": "tools/call",
                "params": {"name": "orderbook", "arguments": {"code": "000001"}},
            })
            assert response.status_code == 200
            assert not response.json()["result"].get("isError", False)
            assert key not in response.text
        assert seen == ["first-client-key", "second-client-key"]
        missing = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "orderbook", "arguments": {"code": "000001"}},
        })
        assert missing.json()["result"]["isError"] is True
        assert len(seen) == 2  # No cached key and no environment fallback.
        assert client.get("/health").json() == {"status": "ok", "service": "xtick-mcp"}
