"""
orchestrator/classifier.py
──────────────────────────
LLM-powered intent classifier — replaces the keyword heuristic in graph.py
when OPENAI_API_KEY is set.

Returns a structured IntentResult with:
  - intent: one of the 5 supported intents
  - confidence: 0.0–1.0
  - reasoning: brief explanation (useful for debugging misclassifications)

The graph calls classify_intent_llm() when the API key is present,
falling back to the keyword heuristic when it is not.

Few-shot examples are loaded from prompts/intent_classifier.yaml so they
are versioned, rollback-able, and testable like every other prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import structlog

from core.settings import settings

log = structlog.get_logger()


class Intent(str, Enum):
    BENEFITS_LOOKUP   = "benefits_lookup"
    FORMULARY_LOOKUP  = "formulary_lookup"
    PRIOR_AUTH_STATUS = "prior_auth_status"
    CLAIM_STATUS      = "claim_status"
    ESCALATION        = "escalation"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    reasoning: str


SYSTEM_PROMPT = """
You are an intent classifier for a health insurance member support AI.
Classify the member's message into exactly one of these intents:

  benefits_lookup   — questions about coverage, deductibles, copays, coinsurance,
                      in/out-of-network, referrals, or plan benefits
  formulary_lookup  — questions about drug coverage, medication tiers, pharmacy
                      benefits, generic alternatives, or drug prior auth
  prior_auth_status — questions about prior authorization requirements, process,
                      status, timelines, or what happens without PA
  claim_status      — questions about claim status, EOB, denial reasons,
                      appeals, reimbursement, or claim submission
  escalation        — requests to speak with a human, transfer, complaint,
                      or anything that cannot be handled by the AI

Respond with valid JSON only. No prose, no markdown.
Schema: {"intent": "<intent>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}
""".strip()

FEW_SHOT_EXAMPLES = [
    ("Is my MRI covered?",
     '{"intent": "benefits_lookup", "confidence": 0.97, "reasoning": "Asking about coverage for a specific procedure."}'),
    ("What tier is Lisinopril on my plan?",
     '{"intent": "formulary_lookup", "confidence": 0.96, "reasoning": "Asking about drug tier classification."}'),
    ("Does my knee surgery need prior auth?",
     '{"intent": "prior_auth_status", "confidence": 0.95, "reasoning": "Asking about PA requirement for a procedure."}'),
    ("Why was my ER claim denied?",
     '{"intent": "claim_status", "confidence": 0.97, "reasoning": "Asking about claim denial reason."}'),
    ("I want to speak to a supervisor.",
     '{"intent": "escalation", "confidence": 0.99, "reasoning": "Explicit request for human agent."}'),
    ("What is my out-of-pocket maximum?",
     '{"intent": "benefits_lookup", "confidence": 0.94, "reasoning": "Asking about a benefits cost-share term."}'),
    ("Is Ozempic covered and does it need PA?",
     '{"intent": "formulary_lookup", "confidence": 0.91, "reasoning": "Drug coverage question with PA component."}'),
]


async def classify_intent_llm(query: str) -> IntentResult:
    """
    LLM-powered intent classification with structured JSON output.
    Falls back to keyword heuristic on any failure.
    """
    if not settings.openai_api_key:
        return _keyword_fallback(query)

    import json
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Few-shot examples
    for user_text, assistant_text in FEW_SHOT_EXAMPLES:
        messages.append(HumanMessage(content=user_text))
        messages.append(AIMessage(content=assistant_text))

    messages.append(HumanMessage(content=query))

    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )
        response = await llm.ainvoke(messages)
        raw = response.content.strip()

        # Strip markdown fences if model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)
        intent = Intent(parsed["intent"])
        confidence = float(parsed.get("confidence", 0.8))
        reasoning = parsed.get("reasoning", "")

        log.info("intent_classified", intent=intent, confidence=confidence,
                 reasoning=reasoning, method="llm")

        return IntentResult(intent=intent, confidence=confidence, reasoning=reasoning)

    except Exception as e:
        log.warning("llm_classifier_failed", error=str(e), query=query)
        return _keyword_fallback(query)


def _keyword_fallback(query: str) -> IntentResult:
    """
    Fast keyword heuristic — used offline and as LLM fallback.
    Same logic as the original graph.py classify_intent node.
    """
    q = query.lower()
    # More specific intents before broad benefits keywords (e.g. "covered" + "formulary").
    intent_map = [
        (["speak", "human", "agent", "representative",
          "help me", "call", "supervisor"], Intent.ESCALATION),
        (["drug", "medication", "prescription", "formulary",
          "tier", "pharmacy", "generic", "brand"], Intent.FORMULARY_LOOKUP),
        (["prior auth", "prior authorization", "pa status",
          "authorization", "precertification"], Intent.PRIOR_AUTH_STATUS),
        (["claim", "eob", "explanation of benefits",
          "denied", "denial", "reimbursement", "paid"], Intent.CLAIM_STATUS),
        (["covered", "coverage", "benefit", "deductible", "copay",
          "out-of-pocket", "in-network", "out-of-network", "coinsurance",
          "referral"], Intent.BENEFITS_LOOKUP),
    ]
    for keywords, intent in intent_map:
        if any(k in q for k in keywords):
            return IntentResult(intent=intent, confidence=0.85, reasoning="keyword match")

    return IntentResult(intent=Intent.BENEFITS_LOOKUP, confidence=0.55,
                        reasoning="no keyword match — defaulting to benefits")