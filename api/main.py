"""CareNav FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.session import load_session, save_turn, Turn, close_pool
from core.settings import settings
from middleware.auth import AuthContext, resolve_auth
from orchestrator.graph import graph, MemberSession


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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "carenav"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    auth: AuthContext = Depends(resolve_auth),
):
    tenant = auth.tenant
    # Prefer JWT subject; body.member_id only for unauthenticated local header mode
    member_id = auth.member_id if auth.via == "jwt" else (body.member_id or auth.member_id)

    session = await load_session(
        session_id=body.session_id,
        tenant_id=tenant.tenant_id,
        member_id=member_id,
    )

    await save_turn(
        session_id=body.session_id,
        tenant_id=tenant.tenant_id,
        turn=Turn(role="user", content=body.message),
    )

    initial_state: MemberSession = {
        "tenant_id": tenant.tenant_id,
        "member_id": member_id,
        "session_id": body.session_id,
        "plan_name": tenant.plan_name,
        "tone_profile": tenant.tone_profile,
        "enabled_agents": tenant.enabled_agents,
        "messages": [
            *session.prior_turns,
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
        turn_count=session.turn_count + 2,
    )
