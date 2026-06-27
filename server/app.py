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


def _structured(response) -> dict | None:
    """Pull the tool's structured records out of an ADK function_response so the UI
    can render them as visible 'evidence' cards. Tools return a JSON string of
    {status, topic, matches:[...]}; ADK wraps it (often under 'result')."""
    val = response
    if isinstance(val, dict):
        val = val.get("result", val)
    try:
        parsed = json.loads(val) if isinstance(val, str) else val
    except Exception:  # noqa: BLE001
        return None
    if isinstance(parsed, dict) and parsed.get("status") == "ok" and isinstance(parsed.get("matches"), list):
        return {"topic": parsed.get("topic"), "matches": parsed["matches"][:6]}
    return None


import re as _re

_WORD = _re.compile(r"[a-z0-9]{3,}")
_STOP = set(
    "the and for you your can are not but with into only one all any from this that they them have "
    "has had will may also when where what which while just like over under about within across "
    "there here their our out off per get got use used bring your you a an of to in on at it is be as "
    "or no yes do does did so if then than more most some such other each both".split()
)


def _grounding(answer: str, evidence_chunks: list[str]) -> dict:
    """Cheap, reproducible grounding pre-screen run alongside the LLM Referee: the
    fraction of the answer's distinct content words that appear in the retrieved
    evidence (lexical overlap). Deterministic, zero-cost, identical every run — a
    stable number to chart next to the LLM judge's nuanced verdict."""
    ev_tokens = set(_WORD.findall(" ".join(evidence_chunks).lower()))
    ans_tokens = {t for t in _WORD.findall((answer or "").lower()) if len(t) >= 4 and t not in _STOP}
    if not ans_tokens:
        return {"grounding": None}
    supported = len(ans_tokens & ev_tokens)
    return {"grounding": round(supported / len(ans_tokens), 3), "supported": supported, "total": len(ans_tokens)}


# The agent's own honesty record across this instance's lifetime — the Referee's
# running scoreline. Surfaced on the homepage as live proof it grades itself.
_RECORD = {"goals": 0, "misses": 0, "gsum": 0.0, "gn": 0}


def _record_verdict(label: str, grounding) -> None:
    if label == "GOAL":
        _RECORD["goals"] += 1
    else:
        _RECORD["misses"] += 1
    if grounding is not None:
        _RECORD["gsum"] += grounding
        _RECORD["gn"] += 1


def _record_summary() -> dict:
    g, m = _RECORD["goals"], _RECORD["misses"]
    total = g + m
    return {
        "goals": g,
        "misses": m,
        "total": total,
        "goal_rate": round(g / total, 3) if total else None,
        "avg_grounding": round(_RECORD["gsum"] / _RECORD["gn"], 3) if _RECORD["gn"] else None,
    }


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
                yield {"type": "tool_result", "name": fr.name, "preview": full[:600],
                       "data": _structured(fr.response)}, final_text, evidence
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
        import time

        await _ensure_session(_player_runner, PLAYER_APP, "fan", session_id)
        instruction, source = get_player_instruction()
        yield _sse({"type": "meta", "session_id": session_id, "playbook": source})
        final_text, evidence = "", []
        tools_used: list[str] = []
        t0 = time.monotonic()
        try:
            async for event, final_text, evidence in _stream_run(
                _player_runner, "fan", session_id, message
            ):
                if event.get("type") == "tool_call" and event.get("name"):
                    tools_used.append(event["name"])
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
        # A deterministic grounding pre-screen runs beside the LLM verdict, plus the
        # turn's provenance — so every answer can show HOW it was produced.
        grounding = _grounding(final_text, evidence)
        _record_verdict(verdict["label"], grounding.get("grounding"))
        yield _sse(
            {
                "type": "eval",
                **verdict,
                **grounding,
                "record": _record_summary(),
                "trace_id": span["trace_id"] if span else None,
                "annotated": annotated,
                "model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "tools": list(dict.fromkeys(tools_used)),
                "sources": len(evidence),
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
        # Coach traces go to their own Phoenix project so the film room
        # ("gaffer") contains only the Player's actual game tape.
        from openinference.instrumentation import dangerously_using_project

        message = "Run a coaching session now."
        for attempt in range(3):
            try:
                with dangerously_using_project("gaffer-coach"):
                    async for event, _, _ in _stream_run(
                        runner, "coach", session_id, message
                    ):
                        yield _sse(event)
                break
            except Exception as exc:  # noqa: BLE001
                if "RESOURCE_EXHAUSTED" in str(exc) and attempt < 2:
                    yield _sse(
                        {
                            "type": "text",
                            "text": "Quota breather — the bench takes thirty seconds, then play resumes.",
                        }
                    )
                    await asyncio.sleep(30)
                    # Same session: the coach keeps its context and picks up where it left off.
                    message = "Continue the coaching session from where you left off."
                    continue
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
        "record": _record_summary(),
    }


def _load_json(name: str):
    try:
        return json.loads((ROOT / "data" / f"{name}.json").read_text())
    except Exception:  # noqa: BLE001
        return {}


# Host-stage tags per FIFA name, derived from the schedule's knockout structure.
_STAGE = {
    "New York New Jersey Stadium": "FINAL",
    "Dallas Stadium": "SEMI-FINAL", "Atlanta Stadium": "SEMI-FINAL",
    "Miami Stadium": "QUARTER-FINAL · 3RD PLACE", "Los Angeles Stadium": "QUARTER-FINAL",
    "Kansas City Stadium": "QUARTER-FINAL", "Boston Stadium": "QUARTER-FINAL",
    "Estadio Ciudad de Mexico (Mexico City Stadium)": "OPENING MATCH",
}


@app.get("/api/venues")
async def venues():
    """The 16 host venues for the venue board, plus the tournament's anchor fixtures."""
    vraw = _load_json("venues").get("venues", [])
    sched = _load_json("schedule")
    out = []
    for v in vraw:
        out.append({
            "name": v.get("stadium_name", "").split(" (")[0],
            "fifa_name": v.get("fifa_name"),
            "city": v.get("city"),
            "country": v.get("country"),
            "capacity": v.get("capacity_approx"),
            "stage": _STAGE.get(v.get("fifa_name", "")),
            "transit": v.get("transit", ""),
        })
    out.sort(key=lambda x: -(x.get("capacity") or 0))
    return {
        "venues": out,
        "opening": sched.get("opening_match", {}),
        "final": sched.get("final", {}),
    }


@app.get("/diagnostics")
async def diagnostics():
    """Tracing health for the control-room 'LIVE TRACING' indicator. OTLP gives no
    receipt, so a configured exporter reads as 'attempted' (honest, CellForge-style)."""
    configured = bool(os.environ.get("PHOENIX_API_KEY"))
    return {
        "tracing": "live" if configured else "local-mirror",
        "status": "attempted_unconfirmed" if configured else "local_only",
        "project": os.environ.get("PHOENIX_PROJECT_NAME", "gaffer-pitch"),
        "exporter": os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", ""),
    }


@app.get("/api/teams")
async def teams_list():
    """All 48 teams grouped, for the 'Follow your team' picker."""
    return {"groups": _load_json("teams").get("groups", {}), "hosts": _load_json("teams").get("hosts", [])}


@app.get("/api/team")
async def team_plan(name: str = ""):
    """A 'Follow your team' itinerary derived from the static schedule + venues:
    the team's group, opponents, opening fixture (venue/city/date), and the road
    ahead (knockout dates + venues). Honest about what isn't drawn yet."""
    teams = _load_json("teams")
    sched = _load_json("schedule")
    venues = {v.get("fifa_name"): v for v in _load_json("venues").get("venues", [])}
    n = (name or "").strip().lower()
    group, members = None, []
    for g, ms in teams.get("groups", {}).items():
        if any(n == t.lower() for t in ms):
            group, members = g, ms
            break
    if not group:
        return {"error": f"'{name}' is not in the 48-team field."}
    canon = next(t for t in members if t.lower() == n)
    opponents = [t for t in members if t != canon]
    fixtures = []
    for fx in sched.get("first_week_fixtures", []):
        if canon.lower() in fx.get("match", "").lower():
            opp = fx["match"].replace(canon, "").replace("vs", "").strip(" -")
            fixtures.append({
                "match": fx.get("match"), "date": fx.get("date"), "opponent": opp,
                "venue": fx.get("venue"), "city": fx.get("city"), "kickoff_et": fx.get("kickoff_et"),
            })
    ks = sched.get("knockout_structure", {})
    road = [
        {"stage": "Round of 32", "window": ks.get("round_of_32", "")},
        {"stage": "Round of 16", "window": ks.get("round_of_16", "")},
    ]
    return {
        "team": canon, "group": group, "opponents": opponents,
        "host": canon in teams.get("hosts", []),
        "fixtures": fixtures, "road": road,
        "final": {"date": sched.get("final", {}).get("date"), "venue": (sched.get("final", {}).get("venue") or "").split(" (")[0], "city": sched.get("final", {}).get("city")},
        "note": "Group fixtures beyond matchday 1 and knockout pairings are set after the draw / group stage.",
    }


@app.get("/")
async def index():
    return FileResponse(ROOT / "web" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")
