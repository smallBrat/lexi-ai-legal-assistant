"""Authentication and JWT utilities for the Lexi API."""

import asyncio
import binascii
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_supabase_url
from app.core.logging import error
from app.core.supabase import get_supabase

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Minimal authenticated user data required by the API."""

    id: str


def verify_token(token: str) -> dict[str, Any] | None:
    """Return a verified Supabase JWT payload when available.

    Phase 15/15.1 hardening, in order of cheapness:
      1. Structural check — a non-3-segment token is malformed, reject
         without a network round-trip to Supabase Auth.
      2. Claim pre-checks — ``role=service_role`` credentials and tokens
         whose ``iss``/``aud`` claims do not match the configured Supabase
         project are rejected before verification.
      3. Cryptographic check — Supabase Auth API ``get_user(token)``
         verifies the signature and expiry server-side.
    A service-role key presented as a bearer token must never authenticate
    an API request, even from a misconfigured client.
    """
    try:
        payload = get_token_payload(token)
        if payload is None:
            # Malformed bearer (not 3 dot-separated segments, bad base64,
            # or non-JSON payload): reject locally, no Supabase call.
            error("JWT verification rejected malformed token")
            return None
        if payload.get("role") == "service_role":
            error("JWT verification rejected service-role credential")
            return None
        # Issuer/audience binding (Phase 15.1): Supabase issues tokens with
        # iss="https://<project-ref>.supabase.co/auth/v1" and
        # aud="authenticated" for user sessions. A token minted for a
        # different project (or an API-key-style audience) must not pass.
        expected_iss = get_supabase_url().rstrip("/") + "/auth/v1"
        token_iss = str(payload.get("iss") or "").rstrip("/")
        if token_iss and token_iss != expected_iss:
            error("JWT verification rejected token from wrong issuer")
            return None
        token_aud = payload.get("aud")
        if token_aud is not None and token_aud != "authenticated":
            error("JWT verification rejected token with unexpected audience")
            return None
        response = get_supabase().auth.get_user(token)
        user = getattr(response, "user", None)
        user_id = getattr(user, "id", None)
        return {"sub": user_id} if user_id else None
    except Exception as exc:  # noqa: BLE001
        error("JWT verification failed", error=str(exc))
        return None


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> AuthenticatedUser:
    """Validate the bearer token through Supabase and return its user id."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = await asyncio.to_thread(verify_token, credentials.credentials)
    user_id = payload.get("sub") if payload else None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthenticatedUser(id=str(user_id))


def extract_token_from_header(
    authorization: str | None,
) -> str | None:
    """Extract JWT token from Authorization header.
    
    Expected format: "Bearer <token>"
    
    Args:
        authorization: The Authorization header value.
        
    Returns:
        The extracted JWT token, or None if the header is malformed.
    """
    if not authorization:
        return None
    
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    
    return None


def get_token_payload(token: str) -> dict[str, Any] | None:
    """Decode a JWT token payload without verification (for debugging).
    
    Note: This does NOT verify the token signature. Only use for
    debugging or internal trusted contexts.
    
    Args:
        token: The JWT token string.
        
    Returns:
        Dict containing the decoded payload, or None if invalid.
    """
    import base64
    import json
    
    try:
        # Split the token and decode the payload segment
        parts = token.split(".")
        if len(parts) != 3:
            return None
        
        # Add padding if needed
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ""
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        return None