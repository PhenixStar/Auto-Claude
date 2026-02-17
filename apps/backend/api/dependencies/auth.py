"""
Authentication Dependency
=========================

Bearer-token authentication for the Auto Claude API.

Reads the expected token from the ``AUTO_CLAUDE_API_TOKEN`` environment
variable and validates incoming ``Authorization: Bearer <token>`` headers
using constant-time comparison to prevent timing attacks.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _get_expected_token() -> str | None:
    """Return the configured API token, or None if auth is disabled."""
    return os.environ.get("AUTO_CLAUDE_API_TOKEN") or None


async def verify_auth(request: Request) -> None:
    """FastAPI dependency that enforces Bearer-token authentication.

    Skipped when ``AUTO_CLAUDE_API_TOKEN`` is not set (local-dev mode).
    """
    expected = _get_expected_token()
    if expected is None:
        # Auth disabled — no token configured
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
        )

    provided = auth_header[7:]  # strip "Bearer " prefix

    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid API token")


def verify_websocket_token(token: str | None) -> bool:
    """Validate a token for WebSocket connections.

    Returns True if the token is valid or auth is disabled.
    """
    expected = _get_expected_token()
    if expected is None:
        return True
    if not token:
        return False
    return hmac.compare_digest(token, expected)
