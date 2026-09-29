"""
agents/general.py
─────────────────
Answers for signed-in users who aren't linked to a health plan.

No plan documents are available, so answers stay general (how deductibles,
copays, formularies, prior auth and claims usually work) and point the member
to linking their plan for specifics.
"""

from __future__ import annotations

import time

import structlog

from agents.base import AgentResult, MemberContext
from core.llm import get_chat_llm, llm_enabled

log = structlog.get_logger()

SYSTEM_PROMPT = """You are CareNav, a health-benefits guide.
This member has NOT linked a health plan, so you have no plan documents.

- Explain how health insurance generally works in plain, friendly language.
- Never state what "their" plan covers, costs, or requires; you don't know.
- When the answer depends on a specific plan, say so and suggest they link
  their plan in Settings (with the plan code from their member ID card or
  employer) or call the member services number on their card.
- Do not give medical advice or diagnoses.
- Keep answers under 150 words."""

LINK_HINT = (
    "For answers about your specific coverage, link your health plan in "
    "Settings using the plan code from your member ID card or employer."
)


class GeneralAgent:
    """Plan-agnostic benefits guidance for unlinked members."""

    agent_id = "general"
    latency_sla_ms = 15000

    async def run(self, ctx: MemberContext) -> AgentResult:
        start = time.monotonic()

        if not llm_enabled():
            return AgentResult(
                content=(
                    "I can explain how health benefits generally work, but I don't "
                    f"know the details of your plan yet. {LINK_HINT}"
                ),
                confidence=0.7,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            system = SYSTEM_PROMPT
            if ctx.member_line():
                system += "\n\n" + ctx.member_line()
            messages = [SystemMessage(content=system)]
            for turn in ctx.prior_turns[-6:]:
                if isinstance(turn, dict):
                    role, content = turn.get("role", "user"), turn.get("content", "")
                else:
                    role = "assistant" if getattr(turn, "type", "") == "ai" else "user"
                    content = getattr(turn, "content", "")
                if not content or content == ctx.query:
                    continue
                messages.append(
                    AIMessage(content=content) if role == "assistant" else HumanMessage(content=content)
                )
            messages.append(HumanMessage(content=ctx.query))

            response = await get_chat_llm(temperature=0.2).ainvoke(messages)
            content = str(response.content).strip()
        except Exception as e:
            log.error("llm_call_failed", error=str(e), agent=self.agent_id)
            return AgentResult(
                content=f"I couldn't generate an answer just now. {LINK_HINT}",
                confidence=0.0,
                latency_ms=int((time.monotonic() - start) * 1000),
                fallback=True,
            )

        return AgentResult(
            content=content,
            confidence=0.75,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
