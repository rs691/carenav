"""
agents/benefits.py
──────────────────
Answers coverage and benefits questions.

Flow per request:
  1. Retrieve top-5 chunks from the tenant's Qdrant collection
  2. Build a prompt from the versioned registry, injecting chunks + prior turns
  3. Call OpenAI with structured output
  4. Return AgentResult with citations

Falls back gracefully if retrieval returns nothing or the LLM call fails.
"""

from __future__ import annotations

import asyncio
import time
import structlog

from agents.base import AgentContract, AgentResult, Citation, MemberContext
from core.settings import settings
from prompts.registry import registry
from rag.retriever import retrieve

log = structlog.get_logger()


class BenefitsAgent:
    """Answers coverage and benefits questions using retrieved plan documents."""

    agent_id = "benefits"
    latency_sla_ms = 5000

    async def run(self, ctx: MemberContext) -> AgentResult:
        start = time.monotonic()

        # ── Step 1: Retrieve relevant chunks ──────────────────────────────────
        chunks = await retrieve(
            query=ctx.query,
            tenant_id=ctx.tenant_id,
            doc_type="benefits",
            top_k=5,
        )

        # No chunks found — fall back to escalation
        if not chunks:
            log.warning("no_chunks_retrieved", tenant_id=ctx.tenant_id, query=ctx.query)
            return AgentResult(
                content=(
                    "I wasn't able to find specific coverage details in your plan documents. "
                    "Let me connect you with a specialist who can help directly."
                ),
                confidence=0.3,
                latency_ms=int((time.monotonic() - start) * 1000),
                fallback=True,
            )

        # ── Step 2: Build prompt ───────────────────────────────────────────────
        # Format retrieved chunks as numbered context blocks
        context_block = "\n\n".join(
            f"[{i+1}] (Source: {c['source_doc']}, Section: {c['section']})\n{c['text']}"
            for i, c in enumerate(chunks)
        )

        # Format prior turns for conversation history
        history_block = ""
        if ctx.prior_turns:
            history_lines = []
            for turn in ctx.prior_turns[-6:]:  # last 3 exchanges
                if isinstance(turn, dict):
                    role_key = turn.get("role", "user")
                    content = turn.get("content", "")
                else:
                    role_key = getattr(turn, "type", "user")
                    if role_key in ("human", "user"):
                        role_key = "user"
                    elif role_key in ("ai", "assistant"):
                        role_key = "assistant"
                    content = getattr(turn, "content", str(turn))
                label = "Member" if role_key == "user" else "Assistant"
                history_lines.append(f"{label}: {content}")
            history_block = "\n".join(history_lines)

        system_prompt = registry.get(
            "benefits_lookup",
            plan_name=ctx.plan_name,
            tone_profile=ctx.tone_profile,
        )

        user_message = f"""
Conversation history:
{history_block if history_block else "This is the first message."}

Retrieved plan document sections:
{context_block}

Member question: {ctx.query}

Answer the member's question using only the retrieved sections above.
Cite the source number [1], [2], etc. for each fact you state.
If the answer is not in the retrieved sections, say so clearly.
""".strip()

        # ── Step 3: LLM call ───────────────────────────────────────────────────
        if not settings.openai_api_key:
            # No API key — return mock so tests pass offline
            return self._mock_result(ctx, chunks, start)

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=0,
                api_key=settings.openai_api_key,
            )

            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ])

            content = response.content

        except Exception as e:
            log.error("llm_call_failed", error=str(e), agent=self.agent_id)
            return AgentResult(
                content=(
                    "I ran into a problem generating a full answer from your plan documents. "
                    "Please try again, or I can connect you with a specialist."
                ),
                confidence=0.0,
                latency_ms=int((time.monotonic() - start) * 1000),
                fallback=True,
            )

        # ── Step 4: Build citations ────────────────────────────────────────────
        citations = [
            Citation(
                source_doc=c["source_doc"],
                chunk_id=f"chunk_{c['chunk_index']}",
                relevance_score=c["score"],
                text_snippet=c["text"][:120],
            )
            for c in chunks
        ]

        latency = int((time.monotonic() - start) * 1000)
        log.info(
            "benefits_agent_complete",
            tenant_id=ctx.tenant_id,
            latency_ms=latency,
            chunks_used=len(chunks),
            stale_chunks=sum(1 for c in chunks if c.get("stale")),
        )

        return AgentResult(
            content=content,
            confidence=0.87,
            latency_ms=latency,
            sources=citations,
        )

    def _mock_result(
        self,
        ctx: MemberContext,
        chunks: list[dict],
        start: float,
    ) -> AgentResult:
        """Offline mock — returned when OPENAI_API_KEY is not set."""
        return AgentResult(
            content=(
                f"Based on your {ctx.plan_name} plan, here's what I found: "
                f"[mock answer for: {ctx.query}] "
                f"(Retrieved {len(chunks)} chunks — set OPENAI_API_KEY for real answers.)"
            ),
            confidence=0.87,
            latency_ms=int((time.monotonic() - start) * 1000),
            sources=[
                Citation(
                    source_doc=chunks[0]["source_doc"],
                    chunk_id=f"chunk_{chunks[0]['chunk_index']}",
                    relevance_score=chunks[0]["score"],
                    text_snippet=chunks[0]["text"][:120],
                )
            ],
        )