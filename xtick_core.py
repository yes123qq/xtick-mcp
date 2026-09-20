"""Transport-independent credential and upstream handling; never persists keys."""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit

import httpx


class XTickError(Exception):
    """A safe, user-facing error without upstream URLs or response bodies."""


@dataclass(frozen=True)
class Credential:
    token: str = field(repr=False)
    source: str


def resolve_credential(headers: Mapping[str, str], env: Mapping[str, str]) -> Credential:
    """Headers win; environment fallback requires explicit private mode."""
    mode = env.get("XTICK_CREDENTIAL_MODE", "byok").strip().lower()
    if mode not in {"byok", "private"}:
        raise XTickError("XTICK_CREDENTIAL_MODE must be byok or private.")
    values = [v for k, v in headers.items() if k.lower() == "x-xtick-token"]
    if values:
        if len(values) != 1:
            raise XTickError("Supply exactly one X-XTick-Token header.")
        raw = values[0]
        source = "header"
    elif mode == "private":
        raw = env.get("XTICK_TOKEN", "")
        source = "environment"
    else:
        raise XTickError("No XTick credential. Supply the X-XTick-Token request header.")
    # Reject invalid/empty headers rather than falling back to another identity.
    token = raw.strip()
    if not token or any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise XTickError("The supplied XTick credential is empty or invalid.")
    return Credential(token, source)


class QueryTokenFilter(logging.Filter):
    """HTTPX INFO logs include request URLs; redact their token query value."""
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = re.sub(r"(?i)([?&]token=)[^&\s'\"]*", r"\1[REDACTED]", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def configure_http_logging() -> None:
    logger = logging.getLogger("httpx")
    if not any(isinstance(item, QueryTokenFilter) for item in logger.filters):
        logger.addFilter(QueryTokenFilter())
    # HTTPcore debug output can contain raw request targets. Keep it off.
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def redact_payload(value: Any, token: str) -> Any:
    """Do not return a credential if an upstream response echoes it."""
    if isinstance(value, str):
        for secret in sorted({token, quote(token, safe=""), quote_plus(token)}, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact_payload(item, token) for item in value]
    if isinstance(value, dict):
        return {redact_payload(key, token): redact_payload(item, token) for key, item in value.items()}
    return value


def validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise XTickError("XTICK_BASE_URL must be an HTTPS URL without credentials, query, or fragment.")
    return base_url.rstrip("/")


async def get_json(
    path: str,
    params: dict[str, Any],
    credential: Credential,
    base_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Any:
    """Preserve the existing XTick API mapping; never follow credential redirects."""
    base_url = validate_base_url(base_url)
    configure_http_logging()
    query = {key: value for key, value in params.items() if value is not None}
    query["token"] = credential.token
    try:
        async with httpx.AsyncClient(
            base_url=base_url, timeout=60.0, follow_redirects=False,
            transport=transport, trust_env=False,
        ) as client:
            response = await client.get(path, params=query)
    except httpx.TimeoutException:
        raise XTickError("XTick request timed out.") from None
    except httpx.RequestError:
        raise XTickError("Could not reach XTick.") from None
    if not 200 <= response.status_code < 300:
        raise XTickError(f"XTick returned HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError:
        raise XTickError("XTick returned a non-JSON response.") from None
    return redact_payload(payload, credential.token)
