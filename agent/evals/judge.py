"""The Referee — LLM-as-a-Judge on Gemini (Vertex).

Scores every Player answer for grounding and helpfulness, logs the verdict to
Phoenix as a span annotation, and doubles as the evaluator inside scrimmage
experiments. Labels are football-honest: GOAL (grounded, correct, helpful) or
MISS (hallucinated, unverified, or unhelpful).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))

_JUDGE_TEMPLATE = """You are a strict football referee judging an AI World Cup concierge's answer.

THE FAN ASKED:
{question}

TOOL EVIDENCE THE AGENT RETRIEVED (from its verified knowledge base):
{evidence}

{expected_block}THE AGENT ANSWERED:
{answer}

Judge the answer:
- GOAL (score near 1.0): every factual claim is supported by the tool evidence{expected_clause}; \
if evidence was missing, the agent honestly said it could not verify instead of guessing; \
the answer addresses the fan's actual question.
- MISS (score near 0.0): any factual claim NOT supported by the evidence (hallucination), \
answering from memory when evidence said NOT_FOUND, ignoring the question, or refusing \
despite having evidence.

Partial credit between 0 and 1 for answers that are mostly grounded with minor unsupported detail.

Respond with ONLY this JSON:
{{"label": "GOAL" or "MISS", "score": <float 0..1>, "explanation": "<one or two sharp sentences>"}}"""


def judge_answer(
    question: str,
    answer: str,
    evidence: str = "(no tool calls were made)",
    expected: Optional[str] = None,
) -> dict[str, Any]:
    """Returns {label, score, explanation}. Never raises."""
    expected_block = (
        f"WHAT A CORRECT ANSWER MUST CONTAIN (ground truth):\n{expected}\n\n" if expected else ""
    )
    expected_clause = " and consistent with the ground truth" if expected else ""
    prompt = _JUDGE_TEMPLATE.format(
        question=question,
        evidence=evidence[:8000],
        answer=answer[:4000],
        expected_block=expected_block,
        expected_clause=expected_clause,
    )
    try:
        from google import genai

        client = genai.Client()
        resp = client.models.generate_content(
            model=JUDGE_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        verdict = json.loads(resp.text)
        score = max(0.0, min(1.0, float(verdict.get("score", 0))))
        label = "GOAL" if str(verdict.get("label", "")).upper() == "GOAL" else "MISS"
        return {
            "label": label,
            "score": score,
            "explanation": str(verdict.get("explanation", ""))[:500],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("judge failed: %s", exc)
        return {"label": "MISS", "score": 0.0, "explanation": f"judge error: {exc}"}


def annotate_span(span_id: str, verdict: dict[str, Any]) -> bool:
    """Attach the Referee's verdict to the turn's Phoenix span."""
    try:
        from phoenix.client import Client

        Client().spans.add_span_annotation(
            span_id=span_id,
            annotation_name="referee",
            annotator_kind="LLM",
            label=verdict["label"],
            score=verdict["score"],
            explanation=verdict["explanation"],
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("span annotation failed: %s", exc)
        return False
