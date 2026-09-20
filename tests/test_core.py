import asyncio
import logging
from urllib.parse import quote

import httpx
import pytest

from xtick_core import (
    Credential, QueryTokenFilter, XTickError, get_json,
    redact_payload, resolve_credential, validate_base_url,
)

TOKEN = "fake-test-key+/="


@pytest.mark.parametrize("name", ["X-XTick-Token", "x-xtick-token", "X-XTICK-TOKEN"])
def test_header_case_and_priority(name):
    credential = resolve_credential({name: " client-key "}, {
        "XTICK_CREDENTIAL_MODE": "private", "XTICK_TOKEN": "server-key",
    })
    assert credential.token == "client-key"
    assert credential.source == "header"
    assert "client-key" not in repr(credential)


def test_public_mode_ignores_server_token():
    with pytest.raises(XTickError, match="header"):
        resolve_credential({}, {"XTICK_TOKEN": "must-not-be-shared"})


def test_private_environment_fallback():
    credential = resolve_credential({}, {"XTICK_CREDENTIAL_MODE": "private", "XTICK_TOKEN": TOKEN})
    assert credential.token == TOKEN
    assert credential.source == "environment"


@pytest.mark.parametrize("value", ["", "   ", "a\nb", "a\rb", "\tkey", "key\x7f"])
def test_invalid_header_never_falls_back(value):
    with pytest.raises(XTickError):
        resolve_credential({"X-XTick-Token": value}, {
            "XTICK_CREDENTIAL_MODE": "private", "XTICK_TOKEN": "server-key",
        })


def test_invalid_mode_fails_closed():
    with pytest.raises(XTickError, match="mode|MODE"):
        resolve_credential({"X-XTick-Token": TOKEN}, {"XTICK_CREDENTIAL_MODE": "typo"})


def test_duplicate_header_casing_rejected():
    with pytest.raises(XTickError, match="exactly one"):
        resolve_credential({"X-XTick-Token": "a", "x-xtick-token": "b"}, {})


@pytest.mark.parametrize("url", [
    "http://api.example.test", "https://user:pass@api.example.test",
    "https://api.example.test?token=x", "https://api.example.test#fragment", "not-a-url",
])
def test_unsafe_base_urls_rejected(url):
    with pytest.raises(XTickError):
        validate_base_url(url)


def test_https_base_url():
    assert validate_base_url("https://api.example.test/") == "https://api.example.test"


def test_payload_redaction():
    result = redact_payload({"data": [{"url": "?token=" + quote(TOKEN, safe=""), "token": TOKEN}], "n": 3}, TOKEN)
    assert result == {"data": [{"url": "?token=[REDACTED]", "token": "[REDACTED]"}], "n": 3}


def test_httpx_logging_redacted():
    record = logging.LogRecord("httpx", logging.INFO, "test", 1, "HTTP Request: %s", (
        "https://api.example.test/doc?token=" + quote(TOKEN, safe="") + "&code=000001",), None)
    assert QueryTokenFilter().filter(record)
    assert quote(TOKEN, safe="") not in record.getMessage()
    assert "token=[REDACTED]&code=000001" in record.getMessage()


@pytest.mark.asyncio
async def test_query_mapping_and_json():
    def handler(request):
        assert request.url.path == "/doc/order/five"
        assert request.url.params["token"] == TOKEN
        assert request.url.params["code"] == "000001"
        assert "optional" not in request.url.params
        return httpx.Response(200, json={"data": [1, 2]})
    result = await get_json("/doc/order/five", {"code": "000001", "optional": None},
                            Credential(TOKEN, "header"), "https://api.example.test",
                            transport=httpx.MockTransport(handler))
    assert result == {"data": [1, 2]}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
async def test_safe_http_errors_and_no_redirect(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=TOKEN, headers={"Location": "https://other.example.test"})
    with pytest.raises(XTickError) as error:
        await get_json("/doc/order/five", {}, Credential(TOKEN, "header"),
                       "https://api.example.test", transport=httpx.MockTransport(handler))
    assert str(error.value) == f"XTick returned HTTP {status}."
    assert TOKEN not in str(error.value)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_non_json_response():
    with pytest.raises(XTickError, match="non-JSON"):
        await get_json("/doc/order/five", {}, Credential(TOKEN, "header"),
                       "https://api.example.test", transport=httpx.MockTransport(
                           lambda request: httpx.Response(200, text=TOKEN)))


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
async def test_safe_network_errors(error_type):
    def handler(request):
        raise error_type("private " + TOKEN, request=request)
    with pytest.raises(XTickError) as error:
        await get_json("/doc/order/five", {}, Credential(TOKEN, "header"),
                       "https://api.example.test", transport=httpx.MockTransport(handler))
    assert TOKEN not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.asyncio
async def test_concurrent_credentials_stay_isolated():
    async def handler(request):
        await asyncio.sleep(0)
        # Return an unrelated user marker; the token itself must never be returned.
        return httpx.Response(200, json={"user": request.url.params["code"]})
    async def call(index):
        credential = resolve_credential({"x-xtick-token": f"secret-{index}"}, {})
        def check(request):
            assert request.url.params["token"] == f"secret-{index}"
            return handler(request)
        return await get_json("/doc/order/five", {"code": str(index)}, credential,
                              "https://api.example.test", transport=httpx.MockTransport(check))
    results = await asyncio.gather(*(call(index) for index in range(12)))
    assert results == [{"user": str(index)} for index in range(12)]
