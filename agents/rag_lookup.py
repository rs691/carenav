"""
Shared RAG lookup agent used by formulary, claims, and prior-auth specialties.
"""
from __future__ import annotations

import time

import structlog

from agents.base import AgentResult, Citation, MemberContext
from core.settings import settings
from prompts.registry import registry
from rag.retriever import retrieve

log = structlog.get_logger()


class RagLookupAgent:
    def __init__(
        self,
        agent_id: str,
        doc_type: str,
        prompt_id: str,
        latency_sla_ms: int = 5000,
    ):
        self.agent_id = agent_id
        self.doc_type = doc_type
        self.prompt_id = prompt_id
        self.latency_sla_ms = latency_sla_ms

    async def run(self, ctx: MemberContext) -> AgentResult:
        start = time.monotonic()

        chunks = ctx.retrieved_chunks or await retrieve(
            query=ctx.query,
            tenant_id=ctx.tenant_id,
            doc_type=self.doc_type,
            top_k=5,
        )

        if not chunks:
            log.warning("no_chunks_retrieved", agent=self.agent_id, tenant_id=ctx.tenant_id)
            return AgentResult(
                content=(
                    "I wasn't able to find that in your plan documents. "
                    "I can connect you with a specialist who can help."
                ),
                confidence=0.3,
                latency_ms=int((time.monotonic() - start) * 1000),
                fallback=True,
            )

        context_block = "\n\n".join(
            f"[{i + 1}] (Source: {c['source_doc']}, Section: {c.get('section', '')})\n{c['text']}"
            for i, c in enumerate(chunks)
        )

        try:
            system_prompt = registry.get(
                self.prompt_id,
                plan_name=ctx.plan_name,
                tone_profile=ctx.tone_profile,
            )
        except KeyError:
            system_prompt = (
                f"You are a {self.agent_id} specialist for the {ctx.plan_name} plan. "
                f"Tone: {ctx.tone_profile}. Use only the retrieved sections. Cite [1], [2]."
            )

        user_message = (
            f"Retrieved sections:\n{context_block}\n\n"
            f"Member question: {ctx.query}\n\n"
            "Answer using only the retrieved sections. Cite sources."
        )

        if not settings.openai_api_key:
            return AgentResult(
                content=(
                    f"Based on your {ctx.plan_name} plan ({self.agent_id}): "
                    f"[mock for: {ctx.query}] "
                    f"(Retrieved {len(chunks)} chunks — set OPENAI_API_KEY for live answers.)"
                ),
                confidence=0.85,
                latency_ms=int((time.monotonic() - start) * 1000),
                sources=[
                    Citation(
                        source_doc=chunks[0]["source_doc"],
                        chunk_id=f"chunk_{chunks[0].get('chunk_index', 0)}",
                        relevance_score=chunks[0].get("score", 0.0),
                        text_snippet=chunks[0]["text"][:120],
                    )
                ],
            )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=0,
                api_key=settings.openai_api_key,
            )
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            )
            content = response.content
        except Exception as e:
            log.error("llm_call_failed", error=str(e), agent=self.agent_id)
            return AgentResult(
                content="",
                confidence=0.0,
                latency_ms=int((time.monotonic() - start) * 1000),
                fallback=True,
            )

        return AgentResult(
            content=content,
            confidence=0.85,
            latency_ms=int((time.monotonic() - start) * 1000),
            sources=[
                Citation(
                    source_doc=c["source_doc"],
                    chunk_id=f"chunk_{c.get('chunk_index', 0)}",
                    relevance_score=c.get("score", 0.0),
                    text_snippet=c["text"][:120],
                )
                for c in chunks
            ],
        )
