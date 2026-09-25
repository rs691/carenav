"""
CareNav LangGraph orchestration graph.

Flow:
  classify_intent → route_to_agent → [benefits | formulary | escalation | ...]
                                    → guardrail_check → respond

State is a typed dict carried through every node. tenant_id is set once
at session init and never re-fetched — it lives in state for the full
conversation lifetime.
"""
from __future__ import annotations

import asyncio
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agents.base import AgentResult, MemberContext
from agents.benefits import BenefitsAgent
from agents.claims import ClaimsAgent
from agents.escalation import EscalationAgent
from agents.formulary import FormularyAgent
from agents.prior_auth import PriorAuthAgent
from middleware.guardrails import guardrail
from orchestrator.classifier import classify_intent_llm

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class MemberSession(TypedDict):
    tenant_id: str
    member_id: str
    session_id: str
    plan_name: str
    tone_profile: str
    enabled_agents: list[str]
    messages: Annotated[list[dict], add_messages]
    current_query: str
    classified_intent: str | None
    intent_confidence: float
    active_agent: str | None
    agent_result: AgentResult | None
    retrieval_chunks: list[dict]
    failure_streak: int             # circuit breaker counter
    phi_scrubbed: bool              # set by guardrail, read by API layer
    tone_pass: bool                 # set by guardrail, read by API layer


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY = {
    "benefits": BenefitsAgent(),
    "formulary": FormularyAgent(),
    "claims": ClaimsAgent(),
    "prior_auth": PriorAuthAgent(),
    "escalation": EscalationAgent(),
}

INTENT_DOC_TYPE = {
    "benefits_lookup": "benefits",
    "formulary_lookup": "formulary",
    "prior_auth_status": "policy",
    "claim_status": "policy",
}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def classify_intent(state: MemberSession) -> dict:
    """
    Classify member query into one of the supported intents.
    Uses the LLM classifier when OPENAI_API_KEY is set; otherwise keyword fallback.
    """
    scrub = guardrail.scrub_phi(state["current_query"])
    clean_query = scrub.scrubbed_text

    result = await classify_intent_llm(clean_query)

    return {
        "current_query": clean_query,
        "classified_intent": result.intent.value,
        "intent_confidence": result.confidence,
        "phi_scrubbed": scrub.was_scrubbed,
    }


async def retrieve_context(state: MemberSession) -> dict:
    """
    Pull tenant-scoped chunks from Qdrant after intent is known.
    On failure (or empty results), keep any pre-seeded chunks so offline
    tests and local demos still work.
    """
    intent = state.get("classified_intent") or ""
    if intent == "escalation":
        return {}

    doc_type = INTENT_DOC_TYPE.get(intent)
    try:
        from rag.retriever import retrieve

        chunks = await retrieve(
            query=state["current_query"],
            tenant_id=state["tenant_id"],
            doc_type=doc_type,
            top_k=5,
        )
    except Exception:
        chunks = []

    if chunks:
        return {"retrieval_chunks": chunks}
    return {}


def route_agent(state: MemberSession) -> str:
    """Edge function: pick the next node based on classified intent."""
    confidence = state.get("intent_confidence", 0.0)
    intent = state.get("classified_intent", "")
    enabled = state.get("enabled_agents", [])
    streak = state.get("failure_streak", 0)

    # Circuit breaker: if 3 consecutive failures, force escalation
    if streak >= 3:
        return "escalation_node"

    # Low confidence: escalate rather than guess
    if confidence < 0.6:
        return "escalation_node"

    intent_to_node = {
        "benefits_lookup": "benefits_node",
        "formulary_lookup": "formulary_node",
        "prior_auth_status": "prior_auth_node",
        "claim_status": "claims_node",
        "escalation": "escalation_node",
    }

    target = intent_to_node.get(intent, "escalation_node")

    # Respect tenant's enabled_agents config
    agent_id = target.replace("_node", "")
    if agent_id not in enabled and agent_id != "escalation":
        return "escalation_node"

    return target


async def run_agent(agent_id: str, state: MemberSession) -> dict:
    """Generic node runner — wraps any AgentContract with SLA enforcement."""
    agent = AGENT_REGISTRY.get(agent_id)
    if not agent:
        return {
            "active_agent": agent_id,
            "agent_result": None,
            "failure_streak": state.get("failure_streak", 0) + 1,
        }

    ctx = MemberContext(
        tenant_id=state["tenant_id"],
        member_id=state["member_id"],
        session_id=state["session_id"],
        query=state["current_query"],
        plan_name=state["plan_name"],
        tone_profile=state["tone_profile"],
        prior_turns=state.get("messages", []),
        retrieved_chunks=state.get("retrieval_chunks", []),
    )

    try:
        result = await asyncio.wait_for(
            agent.run(ctx),
            timeout=agent.latency_sla_ms / 1000,
        )
    except asyncio.TimeoutError:
        result = AgentResult(
            content="",
            confidence=0.0,
            latency_ms=agent.latency_sla_ms,
            fallback=True,
        )

    streak = state.get("failure_streak", 0)
    new_streak = streak + 1 if result.fallback else 0

    return {
        "active_agent": agent_id,
        "agent_result": result,
        "failure_streak": new_streak,
    }


async def benefits_node(state: MemberSession) -> dict:
    return await run_agent("benefits", state)


async def formulary_node(state: MemberSession) -> dict:
    return await run_agent("formulary", state)


async def claims_node(state: MemberSession) -> dict:
    return await run_agent("claims", state)


async def prior_auth_node(state: MemberSession) -> dict:
    return await run_agent("prior_auth", state)


async def escalation_node(state: MemberSession) -> dict:
    return await run_agent("escalation", state)


async def guardrail_check(state: MemberSession) -> dict:
    """
    Tone normalization and compliance envelope via GuardrailMiddleware.
    PHI scrubbing already happened in classify_intent before any LLM call.
    """
    result = state.get("agent_result")
    if not result:
        content = "Something went wrong. Connecting you with a specialist."
        confidence = 0.0
    else:
        content = result.content
        confidence = result.confidence

    # Tone normalization — runs the response through the tenant's tone profile
    normalized, tone_pass = await guardrail.normalize_tone(
        response_text=content,
        tone_profile=state.get("tone_profile", "empathetic_plain"),
        tenant_id=state.get("tenant_id", ""),
    )

    # Compliance envelope — attached to every outbound message
    envelope = guardrail.build_envelope(
        agent_id=state.get("active_agent", "unknown"),
        intent=state.get("classified_intent", "unknown"),
        confidence=confidence,
        phi_scrubbed=state.get("phi_scrubbed", False),
        tone_pass=tone_pass,
        latency_ms=result.latency_ms if result else 0,
    )

    final_message = {
        "role": "assistant",
        "content": normalized,
        "metadata": envelope.to_dict(),
    }

    return {
        "messages": [final_message],
        "tone_pass": tone_pass,
    }


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(MemberSession)

    g.add_node("classify_intent", classify_intent)
    g.add_node("retrieve_context", retrieve_context)
    g.add_node("benefits_node", benefits_node)
    g.add_node("formulary_node", formulary_node)
    g.add_node("claims_node", claims_node)
    g.add_node("prior_auth_node", prior_auth_node)
    g.add_node("escalation_node", escalation_node)
    g.add_node("guardrail_check", guardrail_check)

    g.set_entry_point("classify_intent")
    g.add_edge("classify_intent", "retrieve_context")

    g.add_conditional_edges(
        "retrieve_context",
        route_agent,
        {
            "benefits_node": "benefits_node",
            "formulary_node": "formulary_node",
            "claims_node": "claims_node",
            "prior_auth_node": "prior_auth_node",
            "escalation_node": "escalation_node",
        },
    )

    g.add_edge("benefits_node", "guardrail_check")
    g.add_edge("formulary_node", "guardrail_check")
    g.add_edge("claims_node", "guardrail_check")
    g.add_edge("prior_auth_node", "guardrail_check")
    g.add_edge("escalation_node", "guardrail_check")
    g.add_edge("guardrail_check", END)

    return g.compile()


graph = build_graph()