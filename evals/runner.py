"""
Offline eval harness — routing accuracy against golden_set.csv.

No API keys, Supabase, or Qdrant required (retrieval is mocked empty where needed).

Usage:
    python evals/runner.py
    python evals/runner.py --save-baseline
    python evals/runner.py --baseline evals/results/baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.graph import MemberSession, graph  # noqa: E402

GOLDEN_PATH = Path(__file__).parent / "golden_set.csv"
RESULTS_DIR = Path(__file__).parent / "results"
BASELINE_PATH = RESULTS_DIR / "baseline.json"

DEFAULT_CHUNKS = [
    {
        "text": "MRI is covered with a $150 copay in-network.",
        "source_doc": "benefits.pdf",
        "section": "Section 4",
        "chunk_index": 0,
        "score": 0.91,
        "stale": False,
    }
]


def make_session(query: str) -> MemberSession:
    return MemberSession(
        tenant_id="tenant_bcbs",
        member_id="member_eval",
        session_id="sess_eval",
        plan_name="BlueCross Premier PPO",
        tone_profile="empathetic_plain",
        enabled_agents=["benefits", "formulary", "claims", "prior_auth", "escalation"],
        messages=[],
        current_query=query,
        classified_intent=None,
        intent_confidence=0.0,
        active_agent=None,
        agent_result=None,
        retrieval_chunks=[],
        failure_streak=0,
        phi_scrubbed=False,
        tone_pass=False,
    )


def load_golden() -> list[dict]:
    with open(GOLDEN_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def run_case(row: dict) -> dict:
    query = row["query"]
    mock_retrieve = AsyncMock(return_value=DEFAULT_CHUNKS)
    with (
        patch("rag.retriever.retrieve", mock_retrieve),
        patch("agents.benefits.retrieve", mock_retrieve),
        patch("agents.rag_lookup.retrieve", mock_retrieve),
    ):
        result = await graph.ainvoke(make_session(query))

    intent_ok = result.get("classified_intent") == row["expected_intent"]
    agent_ok = result.get("active_agent") == row["expected_agent"]

    return {
        "query": query,
        "expected_intent": row["expected_intent"],
        "actual_intent": result.get("classified_intent"),
        "expected_agent": row["expected_agent"],
        "actual_agent": result.get("active_agent"),
        "intent_ok": intent_ok,
        "agent_ok": agent_ok,
        "pass": intent_ok and agent_ok,
    }


async def run_all() -> dict:
    rows = load_golden()
    cases = [await run_case(row) for row in rows]
    passed = sum(1 for c in cases if c["pass"])
    total = len(cases)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": total,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "cases": cases,
    }


def compare_to_baseline(report: dict, baseline: dict) -> list[str]:
    errors: list[str] = []
    base_acc = baseline.get("accuracy")
    if base_acc is not None and report["accuracy"] < base_acc:
        errors.append(
            f"Accuracy regressed: {report['accuracy']} < baseline {base_acc}"
        )

    base_by_query = {c["query"]: c for c in baseline.get("cases", [])}
    for case in report["cases"]:
        prev = base_by_query.get(case["query"])
        if prev and prev.get("pass") and not case["pass"]:
            errors.append(
                f"Regression on query {case['query']!r}: "
                f"was pass, now intent={case['actual_intent']} agent={case['actual_agent']}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="CareNav offline eval harness")
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--baseline", type=Path, default=None)
    args = parser.parse_args()

    report = asyncio.run(run_all())
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    out_path = RESULTS_DIR / "latest.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Eval: {report['passed']}/{report['total']} passed (accuracy={report['accuracy']})")

    if args.save_baseline:
        BASELINE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Baseline saved to {BASELINE_PATH}")
        return 0

    baseline_path = args.baseline or BASELINE_PATH
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        errors = compare_to_baseline(report, baseline)
        if errors:
            for err in errors:
                print(f"FAIL: {err}")
            return 1

    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
