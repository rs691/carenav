"""JWT auth for CareNav API — verifies Supabase access tokens (JWKS ES256 or legacy HS256)."""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from fastapi import Header, HTTPException
from jose import JWTError, jwk, jwt
from jose.exceptions import JWKError

from core.settings import settings
from core.tenant import TenantConfig, get_tenant

# Cache JWKS briefly so we don't hit Discovery on every request
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SEC = 3600


@dataclass
class AuthContext:
    member_id: str
    tenant: TenantConfig
    via: str  # "jwt" | "header"


def _tenant_from_claims(payload: dict) -> str | None:
    app_meta = payload.get("app_metadata") or {}
    user_meta = payload.get("user_metadata") or {}
    return (
        app_meta.get("tenant_id")
        or user_meta.get("tenant_id")
        or payload.get("tenant_id")
    )


def _jwks_url() -> str:
    return settings.jwks_url


def _fetch_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL_SEC:
        return _jwks_cache

    url = _jwks_url()
    if not url:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL (or SUPABASE_JWKS_URL) is not configured",
        )

    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        return _jwks_cache
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to fetch JWKS: {e}") from e


def _signing_key_for_token(token: str):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    alg = header.get("alg", "ES256")

    # Legacy HS256 projects still use the shared JWT secret
    if alg == "HS256":
        secret = settings.supabase_jwt_secret or settings.jwt_secret
        if not secret:
            raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not set")
        return secret, ["HS256"]

    jwks = _fetch_jwks()
    keys = jwks.get("keys") or []
    match = next((k for k in keys if k.get("kid") == kid), None)
    if match is None and len(keys) == 1:
        match = keys[0]
    if match is None:
        # Force refresh once if kid rotated
        global _jwks_fetched_at
        _jwks_fetched_at = 0.0
        jwks = _fetch_jwks()
        keys = jwks.get("keys") or []
        match = next((k for k in keys if k.get("kid") == kid), None)

    if match is None:
        raise HTTPException(
            status_code=401,
            detail=f"No JWKS key for kid={kid}",
        )

    try:
        return jwk.construct(match), [match.get("alg") or alg or "ES256"]
    except JWKError as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWK: {e}") from e


def decode_supabase_jwt(token: str) -> dict:
    """
    Verify a Supabase access token.
    New projects (ai-builds): ES256 via
      https://<ref>.supabase.co/auth/v1/.well-known/jwks.json
    Legacy: HS256 with SUPABASE_JWT_SECRET.
    """
    try:
        key, algorithms = _signing_key_for_token(token)
        return jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
            options={"verify_aud": True},
        )
    except HTTPException:
        raise
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e


async def resolve_auth(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> AuthContext:
    """
    Prefer Bearer JWT (production).
    In development, allow x-tenant-id without a token for local UI testing.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_supabase_jwt(token)
        member_id = payload.get("sub")
        if not member_id:
            raise HTTPException(status_code=401, detail="Token missing subject")

        claim_tenant = _tenant_from_claims(payload) or x_tenant_id
        if not claim_tenant:
            raise HTTPException(
                status_code=401,
                detail="No tenant_id in token app_metadata; set it or pass x-tenant-id",
            )
        try:
            tenant = get_tenant(claim_tenant)
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e)) from e

        return AuthContext(member_id=member_id, tenant=tenant, via="jwt")

    if settings.app_env == "development" and x_tenant_id:
        try:
            tenant = get_tenant(x_tenant_id)
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e)) from e
        return AuthContext(member_id="dev-member", tenant=tenant, via="header")

    raise HTTPException(
        status_code=401,
        detail="Authorization Bearer token required (or x-tenant-id in development)",
    )
