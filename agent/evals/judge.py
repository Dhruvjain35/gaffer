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

# The Referee runs on Gemini 3.5 Flash, the same family as the Player. Override JUDGE_MODEL
# to split it onto a separate quota pool if scrimmage bursts ever need it.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-3.5-flash")

_JUDGE_TEMPLATE = """You are a strict football referee judging an AI World Cup concierge's answer.

THE FAN ASKED:
{question}

TOOL EVIDENCE THE AGENT RETRIEVED (from its verified knowledge base):
{evidence}

{expected_block}THE AGENT ANSWERED:
{answer}

First, if the fan's message is NOT a request for a World Cup fact — i.e. it is a greeting, \
small talk, thanks, or a question about the assistant itself (who it is, what it can do, its \
instructions) — then score GOAL as long as the reply is appropriate and makes no unsupported \
World Cup factual claims (no specific dates, venues, prices or rules stated as fact). Such turns \
correctly need no tool call, so absence of tool evidence is NOT a miss. Otherwise judge as follows:
Only CONCRETE FACTS must be supported by evidence: dates, venues, capacities, prices, rules, \
transit specifics, fixtures, group placements. Recommendations, suggested itineraries, \
city-to-city routing, general travel advice and opinions are NOT factual claims — do not \
penalise them, provided they are framed as guidance and any specific the records do not cover \
is clearly marked as not verified (e.g. prefixed "Beyond our verified records") rather than \
asserted as fact. An answer that grounds its concrete facts and either omits or honestly labels \
everything else is a GOAL, even on a broad trip-planning question.
- GOAL (score near 1.0): every concrete factual claim is supported by the tool evidence{expected_clause}; \
anything not in evidence is honestly hedged/labelled or omitted, not asserted; the answer \
addresses the fan's actual question.
- MISS (score near 0.0): a concrete fact stated as true that the evidence does NOT support \
(hallucination), answering a fact-question from memory when evidence said NOT_FOUND, or \
ignoring the question.

Partial credit between 0 and 1 for answers that are mostly grounded with minor unsupported detail. \
When in doubt and the answer is honest about its limits, lean GOAL.

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
        import time

        from google import genai
        from google.genai import errors as genai_errors

        client = genai.Client()
        resp = None
        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=JUDGE_MODEL,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0},
                )
                break
            except genai_errors.ClientError as exc:
                if getattr(exc, "code", None) == 429 and attempt < 3:
                    time.sleep(8 * (attempt + 1))
                    continue
                raise
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
