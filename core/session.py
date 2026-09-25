"""
core/session.py
───────────────
Multi-turn persistence via Supabase.

Priority:
  1. Supabase REST (service role) — works from Windows even when db.* is IPv6-only
  2. asyncpg pooler DSN — optional when DATABASE_URL reaches Postgres
  3. In-memory — development fallback
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import httpx
import structlog

from core.settings import settings

log = structlog.get_logger()


@dataclass
class Turn:
    role: str
    content: str
    agent_id: str | None = None
    intent: str | None = None
    confidence: float | None = None
    phi_scrubbed: bool = False
    latency_ms: int = 0
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "agent_id": self.agent_id,
            "intent": self.intent,
            "confidence": self.confidence,
            "phi_scrubbed": self.phi_scrubbed,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
        }


@dataclass
class Session:
    session_id: str
    tenant_id: str
    member_id: str
    turns: list[Turn] = field(default_factory=list)
    created_at: str = ""

    @property
    def prior_turns(self) -> list[dict]:
        return [t.to_dict() for t in self.turns]

    @property
    def last_agent(self) -> str | None:
        for turn in reversed(self.turns):
            if turn.role == "assistant" and turn.agent_id:
                return turn.agent_id
        return None

    @property
    def turn_count(self) -> int:
        return len(self.turns)


_memory_sessions: dict[tuple[str, str], Session] = {}
_pool = None
_force_memory = False
_rest_disabled = False


def _memory_key(session_id: str, tenant_id: str) -> tuple[str, str]:
    return (tenant_id, session_id)


def _rest_enabled() -> bool:
    return (
        not _rest_disabled
        and bool(settings.supabase_url)
        and bool(settings.service_role_key)
    )


def _rest_headers() -> dict[str, str]:
    key = settings.service_role_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _rest_url(path: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{path.lstrip('/')}"


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _load_session_memory(session_id: str, tenant_id: str, member_id: str) -> Session:
    key = _memory_key(session_id, tenant_id)
    session = _memory_sessions.get(key)
    if session is None:
        session = Session(session_id=session_id, tenant_id=tenant_id, member_id=member_id)
        _memory_sessions[key] = session
    elif session.member_id != member_id:
        session.member_id = member_id
    log.info(
        "session_loaded",
        session_id=session_id,
        tenant_id=tenant_id,
        turn_count=len(session.turns),
        persistence="memory",
    )
    return session


async def _load_session_rest(session_id: str, tenant_id: str, member_id: str) -> Session:
    async with httpx.AsyncClient(timeout=20.0) as client:
        # Upsert session
        upsert = await client.post(
            _rest_url("sessions"),
            headers={
                **_rest_headers(),
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            params={"on_conflict": "id"},
            json={
                "id": session_id,
                "tenant_id": tenant_id,
                "member_id": member_id,
            },
        )
        if upsert.status_code >= 400:
            raise RuntimeError(f"sessions upsert failed: {upsert.status_code} {upsert.text}")

        # Touch updated_at
        await client.patch(
            _rest_url("sessions"),
            headers=_rest_headers(),
            params={"id": f"eq.{session_id}", "tenant_id": f"eq.{tenant_id}"},
            json={"member_id": member_id},
        )

        turns_resp = await client.get(
            _rest_url("turns"),
            headers=_rest_headers(),
            params={
                "session_id": f"eq.{session_id}",
                "tenant_id": f"eq.{tenant_id}",
                "order": "created_at.asc",
                "select": "role,content,agent_id,intent,confidence,phi_scrubbed,latency_ms,created_at",
            },
        )
        if turns_resp.status_code >= 400:
            raise RuntimeError(f"turns fetch failed: {turns_resp.status_code} {turns_resp.text}")

        rows = turns_resp.json()

    turns = [
        Turn(
            role=row["role"],
            content=row["content"],
            agent_id=row.get("agent_id"),
            intent=row.get("intent"),
            confidence=row.get("confidence"),
            phi_scrubbed=bool(row.get("phi_scrubbed")),
            latency_ms=int(row.get("latency_ms") or 0),
            created_at=str(row.get("created_at") or ""),
        )
        for row in rows
    ]

    log.info(
        "session_loaded",
        session_id=session_id,
        tenant_id=tenant_id,
        turn_count=len(turns),
        persistence="supabase_rest",
    )
    return Session(
        session_id=session_id,
        tenant_id=tenant_id,
        member_id=member_id,
        turns=turns,
    )


async def _save_turn_rest(session_id: str, tenant_id: str, turn: Turn) -> None:
    payload = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "tenant_id": tenant_id,
        "role": turn.role,
        "content": turn.content,
        "agent_id": turn.agent_id,
        "intent": turn.intent,
        "confidence": turn.confidence,
        "phi_scrubbed": turn.phi_scrubbed,
        "latency_ms": turn.latency_ms,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            _rest_url("turns"),
            headers={**_rest_headers(), "Prefer": "return=minimal"},
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"turn insert failed: {resp.status_code} {resp.text}")

    log.info(
        "turn_saved",
        session_id=session_id,
        tenant_id=tenant_id,
        role=turn.role,
        agent_id=turn.agent_id,
        persistence="supabase_rest",
    )


async def load_session(
    session_id: str,
    tenant_id: str,
    member_id: str,
) -> Session:
    global _rest_disabled

    if _rest_enabled():
        try:
            return await _load_session_rest(session_id, tenant_id, member_id)
        except Exception as e:
            log.warning("session_rest_failed", error=str(e))
            if settings.app_env != "development":
                raise
            _rest_disabled = True

    if settings.app_env == "development" or not _rest_enabled():
        return _load_session_memory(session_id, tenant_id, member_id)

    raise RuntimeError("No working Supabase persistence backend")


async def save_turn(
    session_id: str,
    tenant_id: str,
    turn: Turn,
) -> None:
    global _rest_disabled

    if _rest_enabled():
        try:
            await _save_turn_rest(session_id, tenant_id, turn)
            return
        except Exception as e:
            log.warning("turn_rest_failed", error=str(e))
            if settings.app_env != "development":
                raise
            _rest_disabled = True

    key = _memory_key(session_id, tenant_id)
    session = _memory_sessions.get(key)
    if session is None:
        session = Session(session_id=session_id, tenant_id=tenant_id, member_id="")
        _memory_sessions[key] = session
    session.turns.append(turn)
    log.info(
        "turn_saved",
        session_id=session_id,
        tenant_id=tenant_id,
        role=turn.role,
        agent_id=turn.agent_id,
        persistence="memory",
    )


async def get_session_summary(
    session_id: str,
    tenant_id: str,
) -> dict:
    if _rest_enabled():
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                sess = await client.get(
                    _rest_url("sessions"),
                    headers=_rest_headers(),
                    params={
                        "id": f"eq.{session_id}",
                        "tenant_id": f"eq.{tenant_id}",
                        "select": "id,member_id,created_at",
                    },
                )
                if sess.status_code >= 400 or not sess.json():
                    return {}
                row = sess.json()[0]
                turns = await client.get(
                    _rest_url("turns"),
                    headers=_rest_headers(),
                    params={
                        "session_id": f"eq.{session_id}",
                        "tenant_id": f"eq.{tenant_id}",
                        "select": "id",
                    },
                )
                count = len(turns.json()) if turns.status_code < 400 else 0
                return {
                    "session_id": row["id"],
                    "member_id": row["member_id"],
                    "created_at": str(row.get("created_at") or ""),
                    "turn_count": count,
                }
        except Exception as e:
            log.warning("session_summary_rest_failed", error=str(e))

    key = _memory_key(session_id, tenant_id)
    session = _memory_sessions.get(key)
    if not session:
        return {}
    return {
        "session_id": session.session_id,
        "member_id": session.member_id,
        "created_at": session.created_at,
        "turn_count": session.turn_count,
    }
