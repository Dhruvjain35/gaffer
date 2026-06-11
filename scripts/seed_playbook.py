"""Seed Phoenix with the Player's baseline playbook (v1) and tag it production.

Run once after setting PHOENIX_API_KEY / PHOENIX_COLLECTOR_ENDPOINT:
    uv run python -m scripts.seed_playbook
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from phoenix.client import Client  # noqa: E402
from phoenix.client.types import PromptVersion  # noqa: E402

from agent.player.prompt import BASELINE_INSTRUCTION, PLAYER_PROMPT_NAME, PRODUCTION_TAG  # noqa: E402


def main() -> None:
    client = Client()
    prompt = client.prompts.create(
        name=PLAYER_PROMPT_NAME,
        prompt_description="GAFFER Player — WC2026 matchday concierge playbook",
        version=PromptVersion(
            [{"role": "system", "content": BASELINE_INSTRUCTION}],
            model_name="gemini-3.5-flash",
        ),
    )
    print(f"created prompt version: {prompt.id}")
    client.prompts.tags.create(
        prompt_version_id=prompt.id,
        name=PRODUCTION_TAG,
        description="baseline v1 — seeded at kickoff",
    )
    print(f"tagged {PRODUCTION_TAG}: {PLAYER_PROMPT_NAME}@{prompt.id}")


if __name__ == "__main__":
    main()
