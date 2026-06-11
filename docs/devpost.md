# Devpost submission draft — GAFFER

**Title:** GAFFER — the World Cup concierge that coaches itself

**Tagline:** An AI agent whose coach is also an AI agent — with Arize Phoenix as the film room, every miss becomes a drill, every drill becomes a better playbook, and only winning playbooks get promoted.

## Inspiration

The 2026 World Cup kicks off today — 104 matches, 16 stadiums, 3 countries, and millions of fans with urgent, specific questions: *Can I bring my bottle? Is there re-entry? How do I get to MetLife from Manhattan?* A concierge agent that hallucinates a bag policy gets someone turned away at the gate.

Every agent ships with a flawed prompt. Most teams patch by vibes. We asked: what if the agent had a coach — a second agent whose entire job is reviewing the game tape in Arize Phoenix and shipping evidence-gated improvements?

## What it does

- **The Player** (Google ADK + Gemini on Vertex AI) answers fan questions grounded in a verified WC2026 knowledge base (16 venues, 48 teams, fixtures, FIFA policies — every fact sourced and cited). Every turn is traced to Phoenix Cloud via OpenInference auto-instrumentation.
- **The Referee** (Gemini LLM-as-judge) scores every answer live — ⚽ GOAL or ✕ MISS — and files the verdict as a span annotation on the exact Phoenix trace.
- **The Gaffer** (second ADK agent) runs coaching sessions through the **official Phoenix MCP server**: mines failed traces (`list-traces`, `get-spans`, `get-span-annotations`), names the failure patterns, drills every miss into the `training-ground` regression dataset (`add-dataset-examples`), fetches and rewrites the playbook (`get-latest-prompt` → `upsert-prompt`), then runs a **scrimmage**: two Phoenix experiments — current vs candidate prompt over the full regression dataset, both scored by the Referee.
- **Promotion is evidence-gated:** only if the candidate wins does the Gaffer call `add-prompt-version-tag` to move `production`. The Player pulls its instruction from Phoenix's prompt registry by tag — **Phoenix is the deployment mechanism**. Next question, new playbook, zero redeploy.

## How we built it

Python ADK agents on `gemini-3.5-flash` (Vertex AI, global endpoint); `arize-phoenix-otel` `register(auto_instrument=True)` for tracing; a custom OTel span processor pins each judge verdict to its exact root span; Phoenix MCP server (stdio, via ADK `McpToolset`) gives the Gaffer 16 filtered tools; `phoenix.client` powers the prompt registry fetch-by-tag and the scrimmage experiments; FastAPI + SSE streams both agents' tool calls live to a two-panel UI (THE PITCH / THE FILM ROOM); single Cloud Run container (Python + Node for the MCP server).

## Challenges

- Live-swapping prompts safely: solved with Phoenix prompt tags as a deployment gate + a 15s TTL cache + instruction-provider functions in ADK.
- Judging the judge: the Referee needs tool evidence, not just Q&A, so the server threads every tool result into the eval — letting it distinguish *grounded* from *correct-by-luck*.
- Running Phoenix experiments from inside an agent tool call: scrimmages run in worker threads with isolated event loops so the Gaffer can await its own experiment results.

## Accomplishments

A complete, working self-improvement loop — not a mockup: real failures, mined through MCP, fixed by prompt v2, proven by experiments, promoted by tag. Watch the scoreboard change between two identical questions asked 90 seconds apart.

## What we learned

Evals aren't a report card — wired to a prompt registry and an experiment gate, they're a deployment pipeline. Phoenix's MCP server turns observability from something you *read* into something agents can *act on*.

## What's next

Auto-triggered coaching sessions on MISS-rate thresholds; annotation configs for human-in-the-loop verdict overrides; per-failure-mode playbook branches with Phoenix A/B experiments.

---

**Track:** Arize
**Disclaimer:** Fan-made demo; not affiliated with, sponsored or endorsed by FIFA. Data compiled from public sources (cited in repo).
**Data sources:** FIFA.com, host-city transit authorities, official venue sites (full citation list in repo: data/sources.md)
**Built with:** google-adk, gemini-3.5-flash, vertex-ai, arize-phoenix, phoenix-mcp, openinference, fastapi, cloud-run
