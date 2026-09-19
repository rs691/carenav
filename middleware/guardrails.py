"""
CareNav Guardrail Middleware
────────────────────────────
Three responsibilities, in order:

  1. PHI scrub (BEFORE the LLM sees the member's message)
     Replaces SSNs, DOBs, account numbers, MRNs with [REDACTED] tokens
     and logs every scrub event for the audit trail.

  2. Tone normalization (AFTER the agent responds)
     Enforces plain-language, empathetic, non-diagnostic tone.
     Per-tenant tone_profile drives the normalization prompt.

  3. Compliance envelope (ALWAYS appended to every response)
     Structured metadata header attached to every outbound message:
     agent, timestamp, confidence, phi_scrubbed, tone_pass.
     Downstream systems (audit log, QA pipeline) consume this.

Usage in graph.py guardrail_check node:
    from middleware.guardrails import GuardrailMiddleware
    mw = GuardrailMiddleware()
    clean_input  = mw.scrub_phi(raw_member_message)
    final_output = await mw.normalize_tone(agent_response, tone_profile)
    envelope     = mw.build_envelope(agent_id, intent, confidence, phi_scrubbed=True)
"""

from __future__ import annotations

import re
import time
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = structlog.get_logger()

# ── PHI patterns ──────────────────────────────────────────────────────────────

PHI_PATTERNS: list[tuple[str, str]] = [
    # SSN:  123-45-6789 or 123456789
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN REDACTED]"),
    (r"\b\d{9}\b", "[SSN REDACTED]"),

    # Date of birth signals
    (r"\b(dob|date of birth|born on)\s*[:\-]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
     "[DOB REDACTED]", ),

    # Member / policy / account IDs (8+ digit strings not already matched)
    (r"\b(?:member|policy|account|mrn|id)[:\s#]*\d{6,}\b", "[ID REDACTED]"),

    # Phone numbers
    (r"\b(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b", "[PHONE REDACTED]"),

    # Email addresses
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL REDACTED]"),
]

_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(pat, re.IGNORECASE), replacement)
    for pat, replacement in PHI_PATTERNS
]


# ── Tone profiles ─────────────────────────────────────────────────────────────

TONE_SYSTEM_PROMPTS: dict[str, str] = {
    "empathetic_plain": (
        "Rewrite the following response in a warm, clear, plain-English tone. "
        "Use simple words. No jargon. Be concise. Start with the direct answer. "
        "Never diagnose or give medical advice. Keep all factual content intact."
    ),
    "plain_language": (
        "Rewrite the following response at a 6th-grade reading level. "
        "Use short sentences. Define any insurance terms in plain words. "
        "Be direct and kind. Keep all factual content intact."
    ),
    "corporate_formal": (
        "Rewrite the following response in a professional, formal tone "
        "appropriate for an employer benefits portal. "
        "Be concise and accurate. Keep all factual content intact."
    ),
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ScrubResult:
    original_length: int
    scrubbed_text: str
    redactions: list[str] = field(default_factory=list)

    @property
    def was_scrubbed(self) -> bool:
        return bool(self.redactions)


@dataclass
class ComplianceEnvelope:
    agent_id: str
    intent: str
    confidence: float
    phi_scrubbed: bool
    tone_pass: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_id,
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "phi_scrubbed": self.phi_scrubbed,
            "tone_pass": self.tone_pass,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
        }


# ── Middleware class ───────────────────────────────────────────────────────────

class GuardrailMiddleware:
    """
    Stateless middleware — safe to instantiate once at app startup
    and share across requests.
    """

    def scrub_phi(self, text: str) -> ScrubResult:
        """
        Scan text for PHI patterns and replace with [REDACTED] tokens.
        Runs BEFORE the member message reaches the LLM.
        """
        scrubbed = text
        redactions: list[str] = []

        for pattern, replacement in _COMPILED:
            matches = pattern.findall(scrubbed)
            if matches:
                scrubbed = pattern.sub(replacement, scrubbed)
                redactions.append(replacement)

        if redactions:
            log.warning(
                "phi_scrubbed",
                redaction_types=redactions,
                original_length=len(text),
                scrubbed_length=len(scrubbed),
            )

        return ScrubResult(
            original_length=len(text),
            scrubbed_text=scrubbed,
            redactions=redactions,
        )

    async def normalize_tone(
        self,
        response_text: str,
        tone_profile: str,
        tenant_id: str = "",
    ) -> tuple[str, bool]:
        """
        Normalize the agent's response to match the tenant's tone profile.

        In production: calls OpenAI with the tone system prompt.
        Here: returns the text as-is with tone_pass=True so the graph
        runs fully offline. Swap the stub block for the real call when
        your OPENAI_API_KEY is set.

        Returns: (normalized_text, tone_pass)
        """
        system_prompt = TONE_SYSTEM_PROMPTS.get(
            tone_profile, TONE_SYSTEM_PROMPTS["empathetic_plain"]
        )

        # ── Stub (no API key required) ────────────────────────────────────────
        # Returns the original text unchanged.
        # Replace this block with the real OpenAI call below when ready.
        normalized = response_text
        tone_pass = True
        # ─────────────────────────────────────────────────────────────────────

        # ── Real implementation (uncomment when OPENAI_API_KEY is set) ───────
        # from langchain_openai import ChatOpenAI
        # from langchain_core.messages import HumanMessage, SystemMessage
        # llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        # result = await llm.ainvoke([
        #     SystemMessage(content=system_prompt),
        #     HumanMessage(content=response_text),
        # ])
        # normalized = result.content
        # tone_pass = True
        # ─────────────────────────────────────────────────────────────────────

        log.info(
            "tone_normalized",
            tenant_id=tenant_id,
            tone_profile=tone_profile,
            tone_pass=tone_pass,
        )
        return normalized, tone_pass

    def build_envelope(
        self,
        agent_id: str,
        intent: str,
        confidence: float,
        phi_scrubbed: bool,
        tone_pass: bool,
        latency_ms: int = 0,
    ) -> ComplianceEnvelope:
        """
        Build the compliance envelope attached to every outbound response.
        Consumed by the audit log, QA pipeline, and eval harness.
        """
        return ComplianceEnvelope(
            agent_id=agent_id,
            intent=intent,
            confidence=confidence,
            phi_scrubbed=phi_scrubbed,
            tone_pass=tone_pass,
            latency_ms=latency_ms,
        )


# ── Module-level singleton ────────────────────────────────────────────────────
# Import this anywhere in the codebase:
#   from middleware.guardrails import guardrail

guardrail = GuardrailMiddleware()