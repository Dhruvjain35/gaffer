"""GAFFER server — streams the Player and the Gaffer to the matchday UI.

Endpoints:
  POST /api/chat   {message, session_id}  -> SSE: meta, tool_call, tool_result, text, eval, done
  POST /api/coach  {}                     -> SSE: same event shapes (the Gaffer's narration)
  GET  /api/state                         -> current playbook source, model, config status
  GET  /                                  -> the matchday UI (web/index.html)
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from agent.evals.judge import annotate_span, judge_answer  # noqa: E402
from agent.instrumentation import latest_root_span  # noqa: E402
from agent.player.agent import player_agent  # noqa: E402
from agent.player.prompt_store import get_player_instruction  # noqa: E402

app = FastAPI(title="GAFFER")

PLAYER_APP = "gaffer_player"
GAFFER_APP = "gaffer_coach"

_player_runner = InMemoryRunner(agent=player_agent, app_name=PLAYER_APP)
_gaffer_runner = None
_known_sessions: set[tuple[str, str]] = set()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _gaffer():
    global _gaffer_runner
    if _gaffer_runner is None:
        from agent.gaffer.agent import gaffer_agent  # lazy: needs Phoenix env + npx

        _gaffer_runner = InMemoryRunner(agent=gaffer_agent, app_name=GAFFER_APP)
    return _gaffer_runner


async def _ensure_session(runner: InMemoryRunner, app_name: str, user_id: str, session_id: str):
    key = (app_name, session_id)
    if key not in _known_sessions:
        try:
            await runner.session_service.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
        except Exception:  # noqa: BLE001 — already exists
            pass
        _known_sessions.add(key)


async def _stream_run(runner, user_id: str, session_id: str, message: str):
    """Yields (event_dict, final_text, evidence) — final two only meaningful at end."""
    final_text = ""
    evidence: list[str] = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            fc = getattr(part, "function_call", None)
            if fc:
                yield {"type": "tool_call", "name": fc.name, "args": fc.args or {}}, final_text, evidence
            fr = getattr(part, "function_response", None)
            if fr:
                full = json.dumps(fr.response, ensure_ascii=False, default=str)
                evidence.append(f"[{fr.name}] {full[:4000]}")  # judge sees full evidence
                yield {"type": "tool_result", "name": fr.name, "preview": full[:600]}, final_text, evidence
            text = getattr(part, "text", None)
            if text and not getattr(event, "partial", False):
                final_text = text
                yield {"type": "text", "text": text}, final_text, evidence


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = (body.get("message") or "").strip()[:2000]
    session_id = body.get("session_id") or secrets.token_hex(8)
    if not message:
        return {"error": "empty message"}

    async def gen():
        await _ensure_session(_player_runner, PLAYER_APP, "fan", session_id)
        instruction, source = get_player_instruction()
        yield _sse({"type": "meta", "session_id": session_id, "playbook": source})
        final_text, evidence = "", []
        try:
            async for event, final_text, evidence in _stream_run(
                _player_runner, "fan", session_id, message
            ):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)[:300]})
            return
        # The Referee scores the turn and files it to Phoenix.
        span = latest_root_span()
        verdict = await asyncio.to_thread(
            judge_answer,
            message,
            final_text,
            "\n".join(evidence) or "(no tool calls were made)",
        )
        annotated = False
        if span:
            annotated = await asyncio.to_thread(annotate_span, span["span_id"], verdict)
        yield _sse(
            {
                "type": "eval",
                **verdict,
                "trace_id": span["trace_id"] if span else None,
                "annotated": annotated,
            }
        )
        yield _sse({"type": "done", "playbook": source})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/coach")
async def coach():
    async def gen():
        session_id = secrets.token_hex(8)
        try:
            runner = _gaffer()
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": f"Gaffer unavailable: {exc}"[:300]})
            return
        await _ensure_session(runner, GAFFER_APP, "coach", session_id)
        yield _sse({"type": "meta", "session_id": session_id, "playbook": "coaching session"})
        try:
            async for event, _, _ in _stream_run(
                runner, "coach", session_id, "Run a coaching session now."
            ):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)[:300]})
            return
        yield _sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/state")
async def state():
    instruction, source = get_player_instruction()
    return {
        "playbook": source,
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        "phoenix": bool(os.environ.get("PHOENIX_API_KEY")),
        "phoenix_url": os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", ""),
        "instruction_preview": instruction[:400],
    }


@app.get("/")
async def index():
    return FileResponse(ROOT / "web" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
