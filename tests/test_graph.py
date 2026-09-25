"""
Tests for the LangGraph orchestration layer.
All tests run offline — no API keys, no Supabase, no Qdrant needed.
"""
import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.graph import graph, MemberSession


def make_session(query: str, enabled_agents=None, prior_turns=None) -> MemberSession:
    return MemberSession(
        tenant_id="tenant_bcbs",
        member_id="member_001",
        session_id="sess_test",
        plan_name="BlueCross Premier PPO",
        tone_profile="empathetic_plain",
        enabled_agents=enabled_agents or ["benefits", "formulary", "claims", "prior_auth", "escalation"],
        messages=prior_turns or [],
        current_query=query,
        classified_intent=None,
        intent_confidence=0.0,
        active_agent=None,
        agent_result=None,
        retrieval_chunks=[{"text": "Your plan covers MRI with a $150 copay.", "source_doc": "benefits.pdf", "section": "Section 4", "chunk_index": 0, "score": 0.91, "stale": False}],
        failure_streak=0,
        phi_scrubbed=False,
        tone_pass=False,
    )


# ── Routing tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_benefits_query_routes_to_benefits_agent():
    with patch("rag.retriever.retrieve", new=AsyncMock(return_value=[
        {"text": "MRI covered at $150 copay.", "source_doc": "benefits.pdf",
         "section": "Section 4", "chunk_index": 0, "score": 0.91, "stale": False}
    ])):
        result = await graph.ainvoke(make_session("Is my MRI covered under my plan?"))
    assert result["active_agent"] == "benefits"
    assert result["classified_intent"] == "benefits_lookup"


@pytest.mark.asyncio
async def test_escalation_keyword_routes_to_escalation():
    result = await graph.ainvoke(make_session("I need to speak with a human representative."))
    assert result["active_agent"] == "escalation"


@pytest.mark.asyncio
async def test_disabled_agent_falls_back_to_escalation():
    result = await graph.ainvoke(
        make_session("What's my deductible?", enabled_agents=["escalation"])
    )
    assert result["active_agent"] == "escalation"


@pytest.mark.asyncio
async def test_circuit_breaker_fires_after_three_failures():
    session = make_session("Is my prescription covered?")
    session["failure_streak"] = 3
    result = await graph.ainvoke(session)
    assert result["active_agent"] == "escalation"


@pytest.mark.asyncio
async def test_tenant_id_preserved_through_graph():
    with patch("rag.retriever.retrieve", new=AsyncMock(return_value=[])):
        result = await graph.ainvoke(make_session("Coverage question"))
    assert result["tenant_id"] == "tenant_bcbs"


# ── PHI scrubbing tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phi_scrubbed_flag_set_when_ssn_in_query():
    with patch("rag.retriever.retrieve", new=AsyncMock(return_value=[])):
        result = await graph.ainvoke(
            make_session("My SSN is 123-45-6789, is my MRI covered?")
        )
    assert result["phi_scrubbed"] is True


@pytest.mark.asyncio
async def test_clean_query_does_not_set_phi_flag():
    with patch("rag.retriever.retrieve", new=AsyncMock(return_value=[])):
        result = await graph.ainvoke(make_session("What is my deductible?"))
    assert result["phi_scrubbed"] is False


# ── Multi-turn context test ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prior_turns_carried_into_state():
    prior = [
        {"role": "user", "content": "What is my deductible?"},
        {"role": "assistant", "content": "Your deductible is $1,500.", "agent_id": "benefits"},
    ]
    with patch("rag.retriever.retrieve", new=AsyncMock(return_value=[
        {"text": "Specialist copay is $50.", "source_doc": "benefits.pdf",
         "section": "Section 5", "chunk_index": 1, "score": 0.88, "stale": False}
    ])):
        result = await graph.ainvoke(
            make_session("What about my specialist copay?", prior_turns=prior)
        )
    # Prior turns injected — agent had context of prior exchange
    assert result["active_agent"] == "benefits"
    assert len(result["messages"]) > 0