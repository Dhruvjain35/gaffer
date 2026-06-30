# Devpost submission: GAFFER

**Title:** GAFFER, the agent that catches and fixes its own lies

**Tagline:** An AI agent that catches and fixes its own lies, live: it referees every answer in Arize Phoenix, coaches itself when it slips, and we even graded the grader. Its use case is the World Cup.

**Track:** Arize
**Live demo:** https://gaffer-734868402447.us-central1.run.app

## Inspiration

For most fans the World Cup is a once-in-a-lifetime trip. They book flights, cross borders, and plan around kickoff times based on whatever an AI tells them. So we asked a few popular assistants real questions: when is the final, can I bring a water bottle into the stadium, what visa do I need. They answered instantly, fluently, and often completely wrong. Confidently wrong is the worst failure mode there is, because nobody double-checks an answer that sounds sure of itself. And the facts move: 104 matches, 16 stadiums, three countries, and FIFA can change its bag policy a week before kickoff. An agent that answers from training data instead of current, cited records gets a real person turned away at a stadium gate.

We did not want one more chatbot that sounds right. We wanted one that can prove it is right, and that fixes itself when it is not. The Arize track was the perfect forcing function: it rewards agents that use their own observability data to improve. That is exactly the loop a trustworthy concierge needs.

## What it does

Most demos ask you to trust the agent. GAFFER lets you break it. Click "inject a hallucination" and watch its own referee stamp the answer false in red, then watch the agent re-answer from verified records and turn green, GOAL, in about ten seconds. That live self-correction, plus the fact that we then **graded the grader** (we wrote 22 fabrications to fool the referee, and it caught all 22, including the subtle ones), is what sets GAFFER apart in a field where "an agent that grades itself" has become table-stakes.

Underneath, it is a World Cup concierge. It answers fan questions about the tournament: stadiums and how to reach them, the schedule, teams and groups, ticketing and IDs, bag and re-entry policies, fan festivals, weather, and city transit. Three things make it different.

1. **It grounds every claim.** The Player agent only answers from a verified knowledge base and cites the exact records it used. Every concrete fact, a date, a venue, a capacity, a price, a rule, is traceable to a source. Anything outside the records is honestly labelled, not invented.

2. **It shows its work in Arize Phoenix.** Every answer is traced end to end with OpenInference. The interface surfaces a live grounding score, the cited sources, and a one-click link that opens the full reasoning trace in Phoenix. Observability is not a back-office dashboard here, it is a feature fans can see.

3. **It coaches itself.** A Referee agent scores every answer GOAL or MISS and files the verdict as a span annotation on that exact trace. When an answer misses, GAFFER re-answers on the spot using only verified evidence, and banks the failure for the coach. The Gaffer reads the game tape through the Phoenix MCP server, drills every miss into a regression dataset, rewrites the Player's prompt, and runs a scrimmage: two Phoenix experiments, old prompt versus new, scored by the Referee. The new prompt is promoted to production only if the data proves it wins. The Player loads its prompt from the Phoenix registry by tag, so the very next question runs on the improved playbook with no redeploy.

On top of the chat, GAFFER has an interactive trip planner. Add the matches you want to catch and it builds one grounded itinerary: venue, transit to the gate, fan festival, and weather for each fixture, with anything uncertain clearly marked. You can then ask the agent to stress-test the whole plan and watch the Referee grade it live.

## How we built it

Two agents built with Google's Agent Development Kit (ADK), the code-first framework in Vertex AI Agent Builder, both on Gemini 3.5 Flash. The Player calls knowledge-base tools that return an explicit `NOT_FOUND` when a fact is not in the corpus, which is what lets the system tell grounded from guessed. The Gaffer is a second ADK agent that holds 16 Phoenix MCP tools through ADK's McpToolset over stdio, so it inspects traces, manages datasets and experiments, and moves prompt tags.

The Referee is an LLM-as-judge, also on Gemini 3.5 Flash. It scores honesty against the retrieved evidence: only concrete facts must be supported, while guidance and itineraries are fine as long as anything uncertain is labelled. A custom OTel span processor pins each verdict to the right root span, written back to Phoenix as a span annotation.

Arize Phoenix Cloud is the spine. Traces and annotations via `arize-phoenix-otel` and OpenInference; the prompt registry holds every playbook version; datasets hold the regression set; experiments run the scrimmages. The registry is also the deployment mechanism: promotion is a tag move, and the Player reads its prompt by tag at session start. Shipping a prompt change is a gated experiment, not a code push. Beyond the full offline coaching session, every chat turn judges itself in real time and, on a MISS, runs an escalating correction loop that re-answers strictly from tool evidence and re-judges, so a fan never leaves with an unverified claim presented as fact.

FastAPI streams both agents over Server-Sent Events so you watch tool calls, the answer, the verdict, and the coaching land token by token. The whole thing, Python agents plus the Node MCP server, ships as one container on Cloud Run. The corpus in `data/*.json` covers 16 host venues, all 48 teams and groups, opening-week fixtures, FIFA fan policies, festivals, weather, and transit, verified from primary sources and fully cited. The same corpus doubles as eval ground truth.

## Challenges we ran into

Making the coaching reliable, not just demoable, was the hard part. Early on a MISS would sometimes be re-answered with a different but still unverified claim, the one thing a trust product cannot do. We fixed it from both ends: we refined the Referee so honest hedging and labelled guidance count as a GOAL while invented specifics count as a MISS, and we turned the single re-answer into an escalating correction loop that ends, in the worst case, with the Player stating only what its tools returned and pointing the fan to official sources. It now converges to an honest answer in every case we tested, which is why fresh questions tend to pass on the first try in the live demo.

The honest infrastructure list, too. Our span recorder silently replaced Phoenix's exporter, so for an hour the annotations pointed at spans that never arrived. The coach once read traces of its own previous sessions, which contain trace dumps, and blew through Gemini's context window, so each agent now traces to its own Phoenix project. A 1 GiB container OOMed when the Gaffer pulled fifty traces in one MCP call. And the MCP upsert tool slugs prompt names, which broke the registry chain until we renamed the prompt to match.

## Accomplishments we are proud of

Numbers from our Phoenix workspace, reproducible there and surfaced live in the app's own Scoreboard page: 21 scrimmage rounds, 12 promotions and 9 refusals, with the production playbook climbing from a referee score of 0.20 to 0.95 on the regression set it is coached against (a sealed holdout is the next hardening step). The agent promoted candidates only when they beat production and refused the rest, including the most recent round where production at 0.95 beat a 0.70 candidate and was left in place. Individual round-to-round gains were mostly within noise (only 1 of 12 promotions cleared a paired-bootstrap floor), so the trend over 21 rounds is the signal, not any single step. 44 experiments and 25 playbook versions sit in Phoenix, every production tag moved by the Gaffer itself after a winning experiment. Questions that scored MISS 0.00 early, stadium rail access, Houston weather, power bank rules, score GOAL 1.00 now. The loop is genuinely closed: trace, judge, drill, rewrite, experiment, gated promotion, with no human in the loop and no redeploy. And we turned observability into something anyone can audit: a live Scoreboard of every scrimmage, grounding and sources on every answer, and a one-click deep link to the exact Phoenix trace.

## What we learned

An eval is a report card until it can gate a deployment. Wired to a prompt registry and an experiment runner, it becomes the deployment pipeline. Tracing is most valuable when it feeds back into the agent: the moment the Referee started writing verdicts onto traces and the coach started reading them, Phoenix stopped being a place we looked at after the fact and became part of the control loop. We also learned that the trustworthy answer is often the one that admits what it does not know, and that an evaluator has to be taught the difference between an unverified fact and honest guidance, or it will punish exactly the humility you want.

## What is next

Coaching sessions triggered by MISS rate instead of a button. Multi-armed coaching, where the Gaffer tests several candidate prompts per scrimmage and keeps the Pareto winner. The full 104-match schedule and live operational data such as gate times and transit alerts. Per-trace deep links and a public, read-only Phoenix view so anyone can audit a specific answer.

## Built with

google-cloud-agent-builder, google-adk, gemini-3.5-flash, vertex-ai, arize-phoenix, openinference, phoenix-mcp, mcp, fastapi, server-sent-events, python, nodejs, docker, google-cloud-run

---

*Fan-made for the Google Cloud Rapid Agent Hackathon. Not affiliated with, sponsored, or endorsed by FIFA. World Cup data compiled from public sources cited in `data/sources.md`.*
