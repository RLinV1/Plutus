"""Clerk JWT authentication for FastAPI.

Set CLERK_JWKS_URL to enable per-user auth. When unset, all requests use
'anonymous' as the user_id (local dev without a Clerk account).

Get your JWKS URL from:
  Clerk Dashboard → API Keys → Advanced → JWKS URL
"""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")

_jwks_client = None
_bearer = HTTPBearer(auto_error=False)

if CLERK_JWKS_URL:
    try:
        from jwt import PyJWKClient

        _jwks_client = PyJWKClient(CLERK_JWKS_URL, cache_keys=True)
    except Exception:  # noqa: BLE001
        pass


async def get_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Verify Clerk JWT and return the user's sub (user_id).

    Returns 'anonymous' when CLERK_JWKS_URL is not configured.
    Raises 401 when auth is configured but the token is missing or invalid.
    """
    if _jwks_client is None:
        return "anonymous"
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        import jwt

        signing_key = _jwks_client.get_signing_key_from_jwt(credentials.credentials)
        data = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
        )
        return data["sub"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
