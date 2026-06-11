"""The Player — Matchday Concierge for World Cup 2026.

ADK agent on Gemini (Vertex). Its system instruction is resolved per-turn from
the Phoenix prompt registry (tag: production), so a Gaffer promotion takes
effect on the very next question.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from agent.instrumentation import setup_tracing  # noqa: E402
from agent.player.prompt_store import get_player_instruction  # noqa: E402
from agent.player.tools.knowledge import ALL_TOOLS  # noqa: E402

setup_tracing()

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def _instruction_provider(_ctx) -> str:
    text, _source = get_player_instruction()
    return text


player_agent = Agent(
    model=MODEL,
    name="gaffer_player",
    description="World Cup 2026 Matchday Concierge — answers fan questions grounded in a verified knowledge base.",
    instruction=_instruction_provider,
    tools=[FunctionTool(func=f) for f in ALL_TOOLS],
)

root_agent = player_agent
