from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Citation:
    source_doc: str
    chunk_id: str
    relevance_score: float
    text_snippet: str


@dataclass
class AgentResult:
    content: str
    confidence: float           # 0.0–1.0; below 0.6 triggers fallback
    latency_ms: int
    sources: list[Citation] = field(default_factory=list)
    fallback: bool = False
    structured: dict | None = None


@dataclass
class MemberContext:
    tenant_id: str
    member_id: str
    session_id: str
    query: str
    plan_name: str
    tone_profile: str
    prior_turns: list[dict] = field(default_factory=list)
    retrieved_chunks: list[dict] = field(default_factory=list)


@runtime_checkable
class AgentContract(Protocol):
    """Every agent — internal or third-party — implements this interface."""
    agent_id: str
    latency_sla_ms: int         # hard SLA; orchestrator enforces via asyncio.wait_for

    async def run(self, ctx: MemberContext) -> AgentResult:
        ...