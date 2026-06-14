"""End-to-end self-test: run the REAL Player (with a chosen playbook) and the REAL
Referee over a battery of fan questions, scoring each turn exactly the way
production does — answer grounded against the tool evidence the Player retrieved.

This is the "unbreakable" check: in-scope questions must ground to a GOAL, and
out-of-scope questions must earn a GOAL via an honest "I can't verify that"
rather than a hallucinated MISS.

    uv run python -m scripts.selftest_player                 # hardened playbook
    uv run python -m scripts.selftest_player --baseline      # weak baseline (for contrast)
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from agent.player.prompt import BASELINE_INSTRUCTION, HARDENED_INSTRUCTION  # noqa: E402

# (question, in_scope) — in_scope means a grounded answer is expected;
# out-of-scope means an honest "can't verify" is the correct (GOAL) behaviour.
BATTERY: list[tuple[str, bool]] = [
    ("Can I bring alcohol?", True),
    ("Can I smoke or vape inside the stadium?", True),
    ("Can I bring my camera? What about a drone?", True),
    ("Can I bring a flag and a flagpole?", True),
    ("Can I bring a stroller for my toddler?", True),
    ("Do toddlers need their own ticket?", True),
    ("Can I bring outside food or snacks?", True),
    ("Can I bring my service dog? What about my emotional support animal?", True),
    ("Is there wheelchair accessible seating and how do I get it?", True),
    ("Are the stadiums cashless or can I pay cash?", True),
    ("Can I bring a backpack?", True),
    ("What time do gates open and when should I arrive?", True),
    ("Can I bring medication and an EpiPen?", True),
    ("How do I get to MetLife Stadium and does it have AC?", True),
    ("When is the final and where?", True),
    ("Who is in Group C?", True),
    # out-of-scope — the correct behaviour is an honest defer, which should score GOAL
    ("What's the cheapest hotel near SoFi Stadium?", False),
    ("Who's going to win the World Cup and who's the best player?", False),
]


async def _answer(instruction: str, question: str) -> tuple[str, str]:
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.adk.tools import FunctionTool
    from google.genai import types

    from agent.player.tools.knowledge import ALL_TOOLS

    agent = Agent(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        name="selftest_player",
        instruction=instruction,
        tools=[FunctionTool(func=f) for f in ALL_TOOLS],
    )
    runner = InMemoryRunner(agent=agent, app_name="selftest")
    sid = secrets.token_hex(6)
    await runner.session_service.create_session(app_name="selftest", user_id="t", session_id=sid)
    final, evidence = "", []
    async for event in runner.run_async(
        user_id="t", session_id=sid,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            fr = getattr(part, "function_response", None)
            if fr is not None:
                evidence.append(f"[{fr.name}] {json.dumps(fr.response, ensure_ascii=False, default=str)[:4000]}")
            if getattr(part, "text", None) and not getattr(event, "partial", False):
                final = part.text
    return final, "\n".join(evidence) or "(no tool calls were made)"


def _answer_with_retry(instruction: str, question: str) -> tuple[str, str]:
    import time
    for attempt in range(3):
        try:
            return asyncio.run(_answer(instruction, question))
        except Exception as exc:  # noqa: BLE001
            if "RESOURCE_EXHAUSTED" in str(exc) and attempt < 2:
                time.sleep(12 * (attempt + 1))
                continue
            raise


def main() -> None:
    from agent.evals.judge import judge_answer

    baseline = "--baseline" in sys.argv
    instruction = BASELINE_INSTRUCTION if baseline else HARDENED_INSTRUCTION
    limit = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), len(BATTERY))
    label = "BASELINE" if baseline else "HARDENED"
    print(f"=== Self-test: {label} playbook · {min(limit, len(BATTERY))} questions ===\n")

    goals = 0
    rows = []
    for question, in_scope in BATTERY[:limit]:
        answer, evidence = _answer_with_retry(instruction, question)
        verdict = judge_answer(question, answer, evidence)
        is_goal = verdict["label"] == "GOAL"
        goals += is_goal
        rows.append((is_goal, verdict["score"], question, verdict["explanation"]))
        print(f"{'GOAL' if is_goal else 'MISS'} {verdict['score']:.2f} | {'in ' if in_scope else 'out'} | {question}")
        if not is_goal:
            print(f"      why: {verdict['explanation']}")
            print(f"      answer: {answer[:240]}")

    n = len(rows)
    print(f"\n=== {goals}/{n} GOAL ({100*goals//n if n else 0}%) ===")
    if goals < n:
        print("MISSES remain — fix data/prompt before promoting.")
        sys.exit(1)
    print("100% GOAL — playbook is grounded and honest across the battery.")


if __name__ == "__main__":
    main()
