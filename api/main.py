"""CareNav FastAPI application."""
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

from core.tenant import TenantConfig, get_tenant
from orchestrator.graph import graph, MemberSession

app = FastAPI(title="CareNav AI Platform", version="0.1.0")


# ---------------------------------------------------------------------------
# Tenant resolution (JWT → TenantConfig)
# In production: decode JWT, validate claims, load from DB/cache.
# Here: accept tenant_id directly in a header for local dev.
# ---------------------------------------------------------------------------

def resolve_tenant(x_tenant_id: str = Header(...)) -> TenantConfig:
    try:
        return get_tenant(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=401, detail=f"Unknown tenant: {x_tenant_id}")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    member_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    agent_used: str | None
    intent: str | None
    confidence: float | None
    phi_scrubbed: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "carenav"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    tenant: TenantConfig = Depends(resolve_tenant),
):
    initial_state: MemberSession = {
        "tenant_id": tenant.tenant_id,
        "member_id": body.member_id,
        "session_id": body.session_id,
        "plan_name": tenant.plan_name,
        "tone_profile": tenant.tone_profile,
        "enabled_agents": tenant.enabled_agents,
        "messages": [],
        "current_query": body.message,
        "classified_intent": None,
        "intent_confidence": 0.0,
        "active_agent": None,
        "agent_result": None,
        "retrieval_chunks": [{"text": "Sample plan document chunk for demo."}],
        "failure_streak": 0,
    }

    result = await graph.ainvoke(initial_state)

    last_message = result["messages"][-1] if result["messages"] else {}
    meta = last_message.get("metadata", {})

    return ChatResponse(
        reply=last_message.get("content", ""),
        agent_used=meta.get("agent"),
        intent=meta.get("intent"),
        confidence=meta.get("confidence"),
        phi_scrubbed=meta.get("phi_scrubbed", False),
    )