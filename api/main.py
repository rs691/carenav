"""CareNav FastAPI application."""
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core import identity
from core.session import SessionAccessError, load_session, save_turn, Turn, close_pool
from core.settings import settings
from core.tenant import get_tenant
from middleware.auth import AuthContext, require_user, resolve_auth
from orchestrator.graph import graph, MemberSession

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_pool()


app = FastAPI(title="CareNav AI Platform", version="0.1.0", lifespan=lifespan)

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
# Dev browsers often hit Next via WSL/Docker bridge IPs (e.g. http://172.22.240.1:3000)
_cors_kwargs: dict = {
    "allow_origins": _cors_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.app_env == "development":
    _cors_kwargs["allow_origin_regex"] = (
        r"https?://("
        r"localhost|127\.0\.0\.1|"
        r"\[::1\]|"
        r"(10|172\.(1[6-9]|2[0-9]|3[0-1])|192\.168)\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?"
    )

app.add_middleware(CORSMiddleware, **_cors_kwargs)


class ChatRequest(BaseModel):
    member_id: str | None = None
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    agent_used: str | None
    intent: str | None
    confidence: float | None
    phi_scrubbed: bool
    turn_count: int


class MeResponse(BaseModel):
    user_id: str
    email: str | None
    full_name: str | None
    first_name: str | None
    onboarded: bool
    linked: bool
    tenant_id: str | None
    plan_name: str | None
    member: dict | None


class VerifyMemberRequest(BaseModel):
    member_number: str | None = None
    group_number: str


async def _profile_for(auth: AuthContext) -> identity.MemberProfile | None:
    if not auth.member_record_id:
        return None
    return await identity.get_member_profile(auth.member_record_id)


async def _me(auth: AuthContext) -> MeResponse:
    profile = await _profile_for(auth)
    full_name = profile.full_name if profile else auth.full_name
    first_name = profile.first_name if profile else (full_name.split()[0] if full_name else None)
    return MeResponse(
        user_id=auth.member_id,
        email=auth.email,
        full_name=full_name,
        first_name=first_name,
        onboarded=auth.onboarded,
        linked=auth.linked,
        tenant_id=auth.tenant.tenant_id if auth.linked else None,
        plan_name=auth.tenant.plan_name if auth.linked else None,
        member=profile.to_public() if profile else None,
    )


def _identity_http_error(e: Exception) -> HTTPException:
    if isinstance(e, identity.IdentityError):
        return HTTPException(status_code=400, detail=str(e))
    log.error("identity_call_failed", error=str(e))
    return HTTPException(status_code=502, detail="Member lookup is unavailable right now")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "carenav"}


@app.get("/me", response_model=MeResponse)
async def me(auth: AuthContext = Depends(require_user)):
    return await _me(auth)


@app.post("/me/member")
async def verify_member(body: VerifyMemberRequest, auth: AuthContext = Depends(require_user)):
    """
    Identify the signed-in user as a plan member.
    member ID + group number -> full member link (profile + plan).
    group number only        -> plan-level link (no personal profile).
    Clients must refresh their session afterwards to pick up the new claims.
    """
    member_number = (body.member_number or "").strip()
    group_number = body.group_number.strip()
    if not group_number:
        raise HTTPException(status_code=400, detail="Group / plan number is required")

    try:
        if member_number:
            row = await identity.find_member(member_number, group_number)
            if not row:
                raise identity.IdentityError(
                    "We couldn't find that member ID and group number together. "
                    "Check your member ID card and try again."
                )
            await identity.release_members(auth.member_id)
            await identity.claim_member(str(row["id"]), auth.member_id)
            await identity.update_app_metadata(
                auth.member_id,
                {"tenant_id": row["tenant_id"], "member_record_id": str(row["id"]), "onboarded": True},
            )
            tenant_id = row["tenant_id"]
        else:
            tenant_id = await identity.find_group_tenant(group_number)
            if not tenant_id:
                raise identity.IdentityError("We don't recognize that group / plan number.")
            await identity.release_members(auth.member_id)
            await identity.update_app_metadata(
                auth.member_id,
                {"tenant_id": tenant_id, "member_record_id": None, "onboarded": True},
            )
    except (identity.IdentityError, httpx.HTTPError) as e:
        raise _identity_http_error(e) from e

    return {"linked": True, "tenant_id": tenant_id, "plan_name": get_tenant(tenant_id).plan_name}


@app.post("/me/skip")
async def skip_identification(auth: AuthContext = Depends(require_user)):
    """Finish onboarding without linking a plan (general answers only)."""
    try:
        await identity.update_app_metadata(auth.member_id, {"onboarded": True})
    except (identity.IdentityError, httpx.HTTPError) as e:
        raise _identity_http_error(e) from e
    return {"onboarded": True, "linked": auth.linked}


@app.delete("/me/member")
async def unlink_member(auth: AuthContext = Depends(require_user)):
    """Remove the plan / member link; the user keeps their account."""
    try:
        await identity.release_members(auth.member_id)
        await identity.update_app_metadata(
            auth.member_id, {"tenant_id": None, "member_record_id": None, "onboarded": True}
        )
    except (identity.IdentityError, httpx.HTTPError) as e:
        raise _identity_http_error(e) from e
    return {"linked": False}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    auth: AuthContext = Depends(resolve_auth),
):
    tenant = auth.tenant
    # Prefer JWT subject; body.member_id only for unauthenticated local header mode
    member_id = auth.member_id if auth.via == "jwt" else (body.member_id or auth.member_id)

    try:
        session = await load_session(
            session_id=body.session_id,
            tenant_id=tenant.tenant_id,
            member_id=member_id,
        )
    except SessionAccessError:
        raise HTTPException(status_code=403, detail="That conversation belongs to another member")

    # In-memory sessions are mutated by save_turn, so snapshot history first.
    prior_turns = session.prior_turns
    prior_count = session.turn_count

    await save_turn(
        session_id=body.session_id,
        tenant_id=tenant.tenant_id,
        turn=Turn(role="user", content=body.message),
    )

    profile = await _profile_for(auth)
    if profile:
        member_profile = profile.to_public()
    elif auth.full_name:
        member_profile = {"first_name": auth.full_name.split()[0]}
    else:
        member_profile = None

    initial_state: MemberSession = {
        "tenant_id": tenant.tenant_id,
        "member_id": member_id,
        "session_id": body.session_id,
        "plan_name": tenant.plan_name,
        "tone_profile": tenant.tone_profile,
        "enabled_agents": tenant.enabled_agents,
        "messages": [
            *prior_turns,
            {"role": "user", "content": body.message},
        ],
        "current_query": body.message,
        "classified_intent": None,
        "intent_confidence": 0.0,
        "active_agent": None,
        "agent_result": None,
        "retrieval_chunks": [],
        "failure_streak": 0,
        "phi_scrubbed": False,
        "tone_pass": False,
        "member_profile": member_profile,
    }

    result = await graph.ainvoke(initial_state)

    last_message = result["messages"][-1] if result["messages"] else {}
    content = (
        last_message.get("content", "")
        if isinstance(last_message, dict)
        else getattr(last_message, "content", "")
    )

    agent_id = result.get("active_agent")
    intent = result.get("classified_intent")
    confidence = result.get("intent_confidence")
    phi_scrubbed = result.get("phi_scrubbed", False)
    latency_ms = result.get("agent_result").latency_ms if result.get("agent_result") else 0

    await save_turn(
        session_id=body.session_id,
        tenant_id=tenant.tenant_id,
        turn=Turn(
            role="assistant",
            content=content,
            agent_id=agent_id,
            intent=intent,
            confidence=confidence,
            phi_scrubbed=phi_scrubbed,
            latency_ms=latency_ms,
        ),
    )

    return ChatResponse(
        reply=content,
        agent_used=agent_id,
        intent=intent,
        confidence=confidence,
        phi_scrubbed=phi_scrubbed,
        turn_count=prior_count + 2,
    )
