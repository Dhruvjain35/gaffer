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

    results: dict[str, Any] = {}
    for side, instruction in (
        ("current", current_instruction),
        ("candidate", candidate_instruction),
    ):

        def task(input):  # noqa: A002
            return _answer_once_sync(instruction, _question_text(input))

        experiment = run_experiment(
            dataset=dataset,
            task=task,
            evaluators=[referee],
            experiment_name=f"scrimmage-{side}-{secrets.token_hex(3)}",
            print_summary=False,
            concurrency=1,  # stay under fresh-account Vertex burst quotas
        )
        scores: list[float] = []
        per_example: list[dict[str, Any]] = []
        try:
            runs = experiment.get("task_runs") if isinstance(experiment, dict) else None
            evals = None
            if runs is None and hasattr(experiment, "as_dataframe"):
                df = experiment.as_dataframe()
                runs = df.to_dict("records")
            if hasattr(experiment, "get_evaluations"):
                evals = experiment.get_evaluations()
                if hasattr(evals, "to_dict"):
                    for rec in evals.to_dict("records"):
                        if rec.get("score") is not None:
                            scores.append(float(rec["score"]))
                            per_example.append(
                                {"label": rec.get("label"), "score": rec.get("score")}
                            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("experiment result parsing fallback: %s", exc)
        results[side] = {
            "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
            "n": len(scores),
            "per_example": per_example,
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
