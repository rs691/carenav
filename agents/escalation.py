import time
from agents.base import AgentResult, MemberContext


class EscalationAgent:
    agent_id = "escalation"
    latency_sla_ms = 1000

    async def run(self, ctx: MemberContext) -> AgentResult:
        start = time.monotonic()
        return AgentResult(
            content=(
                "I want to make sure you get the most accurate answer. "
                "I'm connecting you with a benefits specialist who can help. "
                "Expected wait time: under 3 minutes."
            ),
            confidence=1.0,
            latency_ms=int((time.monotonic() - start) * 1000),
        )