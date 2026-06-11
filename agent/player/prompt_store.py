"""Prompt deployment via Phoenix: the Player pulls its system instruction from
the Phoenix prompt registry by tag at session start.

Phoenix IS the deploy mechanism: the Gaffer promotes a new prompt version by
moving the `production` tag, and the next Player session plays with the new
playbook — no redeploy, no code change. Falls back to the baseline prompt when
Phoenix is unreachable or no version is tagged yet.
"""

from __future__ import annotations

import logging
import os
import time

from agent.player.prompt import BASELINE_INSTRUCTION, PLAYER_PROMPT_NAME, PRODUCTION_TAG

logger = logging.getLogger(__name__)

_TTL_SECONDS = 15  # demo-friendly: a promoted prompt is live on the next question
_cache: dict[str, tuple[float, str, str]] = {}


def _fetch_from_phoenix(tag: str) -> tuple[str, str] | None:
    """Returns (instruction_text, version_id) or None."""
    try:
        from phoenix.client import Client

        client = Client()
        prompt = client.prompts.get(prompt_identifier=PLAYER_PROMPT_NAME, tag=tag)
        # PromptVersion -> openai/google format dict; extract the system message text.
        version_id = getattr(prompt, "id", "unknown")
        fmt = prompt.format()
        messages = fmt.get("messages") if isinstance(fmt, dict) else getattr(fmt, "messages", None)
        if messages:
            for m in messages:
                if m.get("role") == "system":
                    content = m.get("content")
                    if isinstance(content, str) and content.strip():
                        return content, version_id
                    if isinstance(content, list):
                        text = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                        if text.strip():
                            return text, version_id
        return None
    except Exception as exc:  # noqa: BLE001 — any Phoenix failure must not take the Player down
        logger.warning("Phoenix prompt fetch failed (%s); using fallback", exc)
        return None


def get_player_instruction(tag: str = PRODUCTION_TAG) -> tuple[str, str]:
    """Returns (instruction_text, source_label). Cached for _TTL_SECONDS."""
    if not (os.environ.get("PHOENIX_API_KEY") or "").strip():
        return BASELINE_INSTRUCTION, "baseline (Phoenix not configured)"
    now = time.time()
    hit = _cache.get(tag)
    if hit and now - hit[0] < _TTL_SECONDS:
        return hit[1], hit[2]
    fetched = _fetch_from_phoenix(tag)
    if fetched:
        text, version_id = fetched
        label = f"phoenix:{PLAYER_PROMPT_NAME}@{tag} ({version_id[:8]})"
        _cache[tag] = (now, text, label)
        return text, label
    _cache[tag] = (now, BASELINE_INSTRUCTION, "baseline (no tagged version)")
    return BASELINE_INSTRUCTION, "baseline (no tagged version)"
