"""The Scrimmage — Phoenix experiments as a promotion gate.

Plays the current production playbook and the Gaffer's candidate against the
"training-ground" regression dataset. The Referee scores both. The Gaffer may
only promote a playbook that wins here — evidence over vibes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from typing import Any

logger = logging.getLogger(__name__)

DATASET_NAME = "training-ground-wc26"

# Rapid gate: bound the promotion scrimmage to a diverse, capped sample so a
# coaching session stays fast even as the regression dataset grows. The full
# dataset still accumulates every drilled failure; the gate samples it evenly.
# Set SCRIMMAGE_MAX_EXAMPLES=0 to score the entire dataset (slower, exhaustive).
def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else default


SCRIMMAGE_MAX_EXAMPLES = _env_int("SCRIMMAGE_MAX_EXAMPLES", 8)
# How many examples to score in parallel per side. The scrimmage is wall-clock
# bound by Gemini latency, so concurrency is the real speedup; both sides also run
# at once. Tune down if Vertex quota throttles (the executor retries on 429s).
SCRIMMAGE_CONCURRENCY = _env_int("SCRIMMAGE_CONCURRENCY", 8)


def _cap_dataset(dataset: Any, limit: int) -> tuple[Any, str]:
    """Down-sample to an evenly-spaced (diverse) subset of <= limit examples via
    the public to_dict/from_dict round-trip. Returns (dataset, human note)."""
    from phoenix.client.resources.datasets import Dataset

    total = len(dataset.examples)
    if limit <= 0 or total <= limit:
        return dataset, f"{total} examples (full dataset)"
    # Evenly-spaced sample that includes BOTH endpoints (linspace), so the most
    # recently drilled failure (appended last) is never silently skipped. Yields
    # at most `limit` distinct, ascending indices.
    if limit == 1:
        keep = [0]
    else:
        keep = sorted({round(i * (total - 1) / (limit - 1)) for i in range(limit)})
    payload = dataset.to_dict()
    payload["examples"] = [payload["examples"][i] for i in keep]
    return Dataset.from_dict(payload), f"{len(keep)} of {total} (rapid gate sample)"


async def _answer_once_async(instruction: str, question: str) -> dict[str, str]:
    """Run one Player turn with the given instruction and return {answer, evidence}.
    The evidence is the tool output the candidate actually retrieved, captured
    exactly as production captures it so the scrimmage grades grounding the same
    way the live Referee does. Awaited directly by the async experiment executor,
    so many examples run concurrently (the scrimmage's main speedup)."""
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.adk.tools import FunctionTool
    from google.genai import types
    from openinference.instrumentation import dangerously_using_project

    from agent.player.tools.knowledge import ALL_TOOLS

    candidate = Agent(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        name="gaffer_player_scrimmage",
        instruction=instruction,
        tools=[FunctionTool(func=f) for f in ALL_TOOLS],
    )
    runner = InMemoryRunner(agent=candidate, app_name="gaffer_scrimmage")
    sid = secrets.token_hex(6)
    await runner.session_service.create_session(
        app_name="gaffer_scrimmage", user_id="scrimmage", session_id=sid
    )
    final = ""
    evidence: list[str] = []
    # Scrimmage turns get their own project: only real fan turns belong in "gaffer".
    with dangerously_using_project("gaffer-scrimmage"):
        async for event in runner.run_async(
            user_id="scrimmage",
            session_id=sid,
            new_message=types.Content(role="user", parts=[types.Part(text=question)]),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    fr = getattr(part, "function_response", None)
                    if fr is not None:
                        full = json.dumps(fr.response, ensure_ascii=False, default=str)
                        evidence.append(f"[{fr.name}] {full[:4000]}")
                    if getattr(part, "text", None) and not getattr(event, "partial", False):
                        final = part.text
    return {"answer": final, "evidence": "\n".join(evidence)}


def _expected_text(expected: Any) -> str:
    if expected is None:
        return ""
    if isinstance(expected, dict):
        for key in ("must_contain", "answer", "output", "expected"):
            if key in expected and expected[key]:
                return str(expected[key])
        return json.dumps(expected, ensure_ascii=False)
    return str(expected)


def _question_text(inp: Any) -> str:
    if isinstance(inp, dict):
        for key in ("question", "input", "message"):
            if key in inp and inp[key]:
                return str(inp[key])
        return json.dumps(inp, ensure_ascii=False)
    return str(inp)


def _summarize_experiment(experiment: Any) -> dict[str, Any]:
    scores: list[float] = []
    per_example: list[dict[str, Any]] = []
    for run in experiment.get("evaluation_runs", []):
        result = getattr(run, "result", None)
        if result is None:
            per_example.append({"error": getattr(run, "error", "no result")})
            continue
        score = result.get("score")
        if score is not None:
            scores.append(float(score))
        per_example.append(
            {
                "label": result.get("label"),
                "score": score,
                "explanation": (result.get("explanation") or "")[:160],
            }
        )
    return {
        "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
        "n": len(scores),
        "experiment_id": experiment.get("experiment_id"),
        "per_example": per_example,
    }


async def _run_scrimmage_async(candidate_instruction: str) -> dict[str, Any]:
    from phoenix.client import Client
    from phoenix.client.experiments import async_run_experiment

    from agent.evals.judge import judge_answer
    from agent.player.prompt_store import get_player_instruction

    try:
        dataset = Client().datasets.get_dataset(dataset=DATASET_NAME)
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"Dataset '{DATASET_NAME}' not found ({exc}). "
            "Add the failed cases as drills first (add-dataset-examples), then scrimmage.",
        }

    dataset, sample_note = _cap_dataset(dataset, SCRIMMAGE_MAX_EXAMPLES)
    current_instruction, current_source = get_player_instruction()

    async def referee(input, output, expected):  # noqa: A002 — names bound by phoenix
        # Grade grounding against the evidence the candidate actually retrieved
        # (same standard as the live Referee) AND consistency with ground truth, so a
        # scrimmage win predicts live behaviour. The blocking judge call runs in a
        # thread so evaluations score concurrently too.
        if isinstance(output, dict):
            answer = output.get("answer", "")
            evidence = output.get("evidence", "") or "(no tool calls were made)"
        else:
            answer, evidence = str(output or ""), "(no tool calls were made)"
        return await asyncio.to_thread(
            judge_answer, _question_text(input), str(answer or ""), evidence, _expected_text(expected)
        )

    async def _play_side(side: str, instruction: str) -> dict[str, Any]:
        async def task(input):  # noqa: A002
            return await _answer_once_async(instruction, _question_text(input))

        experiment = await async_run_experiment(
            dataset=dataset,
            task=task,
            evaluators=[referee],
            experiment_name=f"scrimmage-{side}-{secrets.token_hex(3)}",
            print_summary=False,
            timeout=120,
            concurrency=SCRIMMAGE_CONCURRENCY,
        )
        return _summarize_experiment(experiment)

    # Both sides play at once; within each side every example is scored concurrently.
    current_side, candidate_side = await asyncio.gather(
        _play_side("current", current_instruction),
        _play_side("candidate", candidate_instruction),
    )
    results: dict[str, Any] = {"current": current_side, "candidate": candidate_side}
    cur, cand = current_side["avg_score"], candidate_side["avg_score"]
    results["current"]["instruction_source"] = current_source
    results["dataset_sample"] = sample_note
    results["verdict"] = (
        "CANDIDATE WINS — promotion justified"
        if cand is not None and cur is not None and cand > cur
        else "CANDIDATE DOES NOT WIN — do not promote"
    )
    return results


async def run_scrimmage(candidate_instruction: str) -> str:
    """Scrimmage the candidate playbook against the current production playbook
    on the 'training-ground' regression dataset; the Referee scores both sides.

    Args:
      candidate_instruction: The full text of the proposed new system instruction.

    Returns:
      JSON with avg_score for 'current' and 'candidate', per-example scores, and a verdict.
    """
    result = await _run_scrimmage_async(candidate_instruction)
    return json.dumps(result, ensure_ascii=False)
