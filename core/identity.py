"""
core/identity.py
────────────────
Member identity: match a signed-in user to a roster member (or a plan group),
and record the result in Supabase Auth app_metadata so it rides along in the
JWT (tenant_id, member_record_id, onboarded).

All calls use the service role; roster tables have no client write access.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

from core.settings import settings

log = structlog.get_logger()

_PROFILE_TTL_SEC = 300
_profile_cache: dict[str, tuple[float, "MemberProfile"]] = {}


class IdentityError(Exception):
    """Raised when identity can't be resolved (bad input, not configured, taken)."""


@dataclass
class MemberProfile:
    record_id: str
    tenant_id: str
    member_number: str
    group_number: str
    first_name: str
    last_name: str
    coverage_tier: str
    effective_date: str | None

    @classmethod
    def from_row(cls, row: dict) -> "MemberProfile":
        return cls(
            record_id=str(row["id"]),
            tenant_id=row["tenant_id"],
            member_number=row["member_number"],
            group_number=row["group_number"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            coverage_tier=row.get("coverage_tier") or "Individual",
            effective_date=row.get("effective_date"),
        )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def to_public(self) -> dict:
        return {
            "member_number": self.member_number,
            "group_number": self.group_number,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "coverage_tier": self.coverage_tier,
            "effective_date": self.effective_date,
        }


def _require_config() -> None:
    if not settings.supabase_url or not settings.service_role_key:
        raise IdentityError("Member lookup isn't configured (SUPABASE_URL / service key)")


def _headers() -> dict[str, str]:
    key = settings.service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}{path}"


def _norm(value: str) -> str:
    return value.strip().upper()


_MEMBER_COLUMNS = (
    "id,tenant_id,member_number,group_number,first_name,last_name,"
    "coverage_tier,effective_date,user_id"
)


async def find_member(member_number: str, group_number: str) -> dict | None:
    _require_config()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            _url("/rest/v1/members"),
            headers=_headers(),
            params={
                "member_number": f"eq.{_norm(member_number)}",
                "group_number": f"eq.{_norm(group_number)}",
                "select": _MEMBER_COLUMNS,
            },
        )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


async def find_group_tenant(group_number: str) -> str | None:
    _require_config()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            _url("/rest/v1/plan_groups"),
            headers=_headers(),
            params={
                "group_number": f"eq.{_norm(group_number)}",
                "active": "is.true",
                "select": "tenant_id",
            },
        )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["tenant_id"] if rows else None


async def get_member_profile(record_id: str) -> MemberProfile | None:
    """Roster row for a linked user, cached briefly so every chat turn stays fast."""
    cached = _profile_cache.get(record_id)
    if cached and time.monotonic() - cached[0] < _PROFILE_TTL_SEC:
        return cached[1]
    if not settings.supabase_url or not settings.service_role_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _url("/rest/v1/members"),
                headers=_headers(),
                params={"id": f"eq.{record_id}", "select": _MEMBER_COLUMNS},
            )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        log.warning("member_profile_load_failed", error=str(e))
        return None
    if not rows:
        return None
    profile = MemberProfile.from_row(rows[0])
    _profile_cache[record_id] = (time.monotonic(), profile)
    return profile


async def release_members(user_id: str) -> None:
    _require_config()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            _url("/rest/v1/members"),
            headers=_headers(),
            params={"user_id": f"eq.{user_id}"},
            json={"user_id": None, "claimed_at": None},
        )
    resp.raise_for_status()
    _profile_cache.clear()


async def claim_member(record_id: str, user_id: str) -> None:
    """Attach a roster row to the user; fails if another user already claimed it."""
    _require_config()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            _url("/rest/v1/members"),
            headers={**_headers(), "Prefer": "return=representation"},
            params={"id": f"eq.{record_id}", "or": f"(user_id.is.null,user_id.eq.{user_id})"},
            json={"user_id": user_id, "claimed_at": datetime.now(timezone.utc).isoformat()},
        )
    resp.raise_for_status()
    if not resp.json():
        raise IdentityError("That member ID is already linked to another account")
    _profile_cache.pop(record_id, None)


async def update_app_metadata(user_id: str, changes: dict) -> None:
    """Merge into auth app_metadata; a None value removes the key."""
    _require_config()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(
            _url(f"/auth/v1/admin/users/{user_id}"),
            headers=_headers(),
            json={"app_metadata": changes},
        )
    resp.raise_for_status()
