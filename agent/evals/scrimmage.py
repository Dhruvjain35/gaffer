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


def _answer_once_sync(instruction: str, question: str) -> str:
    """Run one Player turn with the given instruction in a private event loop.
    Used inside experiment tasks (each task call runs in a worker thread)."""

    async def _run() -> str:
        from google.adk.agents import Agent
        from google.adk.runners import InMemoryRunner
        from google.adk.tools import FunctionTool
        from google.genai import types

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
        async for event in runner.run_async(
            user_id="scrimmage",
            session_id=sid,
            new_message=types.Content(role="user", parts=[types.Part(text=question)]),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None) and not getattr(event, "partial", False):
                        final = part.text
        return final

    import time

    for attempt in range(3):
        try:
            return asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            if "RESOURCE_EXHAUSTED" in str(exc) and attempt < 2:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    return ""


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


def _run_scrimmage_sync(candidate_instruction: str) -> dict[str, Any]:
    from phoenix.client import Client
    from phoenix.client.experiments import run_experiment

    from agent.evals.judge import judge_answer
    from agent.player.prompt_store import get_player_instruction

    client = Client()
    try:
        dataset = client.datasets.get_dataset(dataset=DATASET_NAME)
    except Exception as exc:  # noqa: BLE001
        return {
            "error": f"Dataset '{DATASET_NAME}' not found ({exc}). "
            "Add the failed cases as drills first (add-dataset-examples), then scrimmage.",
        }

    current_instruction, current_source = get_player_instruction()

    def referee(input, output, expected):  # noqa: A002 — names bound by phoenix
        verdict = judge_answer(
            question=_question_text(input),
            answer=str(output or ""),
            evidence="(scrimmage: judge against ground truth)",
            expected=_expected_text(expected),
        )
        return verdict  # {label, score, explanation}

    def _play_side(side: str, instruction: str) -> dict[str, Any]:
        def task(input):  # noqa: A002
            return _answer_once_sync(instruction, _question_text(input))

        experiment = run_experiment(
            dataset=dataset,
            task=task,
            evaluators=[referee],
            experiment_name=f"scrimmage-{side}-{secrets.token_hex(3)}",
            print_summary=False,
            timeout=120,
        )
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

    # Both sides play at the same time — independent experiments, half the wall clock.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_current = pool.submit(_play_side, "current", current_instruction)
        fut_candidate = pool.submit(_play_side, "candidate", candidate_instruction)
        results: dict[str, Any] = {
            "current": fut_current.result(),
            "candidate": fut_candidate.result(),
        }

    cur, cand = results["current"]["avg_score"], results["candidate"]["avg_score"]
    results["current"]["instruction_source"] = current_source
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
    result = await asyncio.to_thread(_run_scrimmage_sync, candidate_instruction)
    return json.dumps(result, ensure_ascii=False)
