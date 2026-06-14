"""Promote the vetted hardened playbook to Phoenix and tag it production.

The Player fetches its system instruction from the Phoenix prompt registry by the
`production` tag, so this is what actually changes live behaviour (no redeploy
needed for the prompt itself). Run after the self-test passes:

    uv run python -m scripts.promote_playbook

The Gaffer can still coach improvements on top; the scrimmage now grades grounding
the same way production does, so a future promotion can't regress live behaviour.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from phoenix.client import Client  # noqa: E402
from phoenix.client.types import PromptVersion  # noqa: E402

from agent.player.prompt import HARDENED_INSTRUCTION, PLAYER_PROMPT_NAME, PRODUCTION_TAG  # noqa: E402


def main() -> None:
    client = Client()
    version = client.prompts.create(
        name=PLAYER_PROMPT_NAME,
        prompt_description="GAFFER Player — hardened production playbook (grounding discipline)",
        version=PromptVersion(
            [{"role": "system", "content": HARDENED_INSTRUCTION}],
            model_name="gemini-3.5-flash",
        ),
    )
    print(f"created prompt version: {version.id}")
    client.prompts.tags.create(
        prompt_version_id=version.id,
        name=PRODUCTION_TAG,
        description="hardened playbook: grounded answers + honest defer on out-of-scope",
    )
    print(f"tagged {PRODUCTION_TAG}: {PLAYER_PROMPT_NAME}@{version.id}")
    print("Live in <=15s on the next fan question (prompt cache TTL).")


if __name__ == "__main__":
    main()
