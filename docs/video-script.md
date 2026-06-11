# GAFFER — 3-minute demo video script

**Setup before recording:** run `uv run python -m scripts.seed_playbook` (production tag → baseline v1).
Open two browser tabs: (1) the Cloud Run app, (2) Phoenix (Tracing → gaffer-pitch project).
Record screen + voiceover (QuickTime/CapCut). English. Calm pace — don't rush, don't speed up audio.

---

## 0:00–0:15 — The hook (app on screen, THE PITCH visible)

> "The World Cup kicks off today. This is GAFFER — a matchday concierge for 104 matches across
> three countries. But here's the thing: this agent gets *measurably better while you watch* —
> because its coach is also an agent, and the film room is Arize Phoenix."

## 0:15–0:50 — The failure (live)

Ask: **"Tell me about the atmosphere at Estadio Azteca for the opener"** → red ✕ MISS verdict appears.
Ask: **"Do I need a visa to follow my team across all three countries?"** → another MISS.

> "Every answer is traced to Phoenix and scored live by a Gemini judge — the Referee.
> Our rookie playbook answers from memory instead of its verified knowledge base. Hallucinated
> details, unverified claims. In a stadium context, that gets a fan turned away at the gate.
> Watch the scoreboard: two misses, filed as span annotations on the exact traces."

Quick flash to Phoenix tab: show the trace waterfall + red `referee` annotation. (5 seconds.)

## 0:50–2:00 — The coaching session (the centerpiece)

Click **▸ COACHING SESSION**. Let THE FILM ROOM stream. Narrate over it:

> "Now the Gaffer goes to work — a second Gemini agent connected to Phoenix through Arize's
> official MCP server. Watch its moves, live:
> — It pulls the game tape: failed traces, judge annotations. [point at get-spans calls]
> — It names the failure pattern: answering from memory instead of checking tools.
> — It drills every miss into a permanent regression dataset. [add-dataset-examples]
> — It rewrites the playbook and versions it in Phoenix's prompt registry. [upsert-prompt]
> — And here's the part I love: it does NOT trust its own rewrite. It runs a scrimmage —
> two Phoenix experiments, old playbook versus new, every answer scored by the Referee.
> Only because the new playbook WINS does it promote: the production tag moves. [promotion banner]
> The Player pulls its prompt from Phoenix by tag — so this IS the deployment. No redeploy,
> no human, evidence-gated."

(While scrimmage runs, cut to Phoenix tab: Datasets → training-ground-wc26 drills; Experiments view with both scrimmage runs side by side.)

## 2:00–2:35 — The payoff (live)

Back to THE PITCH. Re-ask the SAME two questions → both come back ⚽ GOAL 1.0.

> "Same questions, ninety seconds later. Goal. Goal. The scoreboard tells the story —
> and the regression dataset guarantees these failures stay fixed forever."

## 2:35–3:00 — The close (app + architecture slide or README diagram)

> "GAFFER is Gemini on Google Cloud's Agent Development Kit, Cloud Run, and Arize Phoenix doing
> what observability should do: not just watching agents fail — coaching them until they don't.
> Swap the knowledge base, and this loop ships ANY production agent's prompts like code: through CI.
> Trace it. Judge it. Drill it. Prove it. Promote it. That's GAFFER."

---

**Checklist after recording:** target ≤2:50 (hard cap 3:00 — judges stop watching there) ·
English audio · upload YouTube as **PUBLIC** (rules require publicly visible) ·
no third-party logos beyond product UIs · no music you don't have rights to ·
never show FIFA imagery — word marks in our own UI only.
