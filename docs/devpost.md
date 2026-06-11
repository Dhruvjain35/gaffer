# Devpost submission: GAFFER

**Title:** GAFFER, the World Cup concierge that coaches itself

**Tagline:** A fan concierge whose coach is also an agent. Every miss becomes a drill, every drill tests the next playbook, and nothing ships unless it beats the old one.

## Inspiration

The World Cup started this morning. 104 matches, 16 stadiums, three countries, and FIFA changed its water bottle policy eight days ago. An agent that answers bag policy questions from its training data instead of current rules will get a real person turned away at a stadium gate.

I kept thinking about what happens after that bad answer. Someone reads a trace, guesses at a prompt fix, ships it, and hopes. I wanted to see whether the agent could run that loop itself, with evidence at every step, using Phoenix as the machinery rather than just the dashboard.

## What it does

The Player is the concierge. It answers fan questions about venues, fixtures, policies and travel, grounded in a knowledge base I verified against primary sources this morning. Google ADK runs it on gemini-3.5-flash, and OpenInference traces every turn to Phoenix Cloud.

The Referee is a second Gemini model that scores each answer the moment it lands: GOAL if every claim is supported by the tool evidence, MISS if anything came from memory. The verdict is written to Phoenix as a span annotation on that exact trace.

The Gaffer is the coach. When you start a coaching session, it works Arize's Phoenix MCP server live: pulls recent traces and their referee annotations, quotes the failures, writes each one into a regression dataset called training-ground-wc26, fetches the current playbook from the prompt registry, and rewrites it. Then comes the part I care most about. It refuses to trust its own rewrite. It runs two Phoenix experiments, old playbook against new across the whole drill set, referee scoring both sides. Only a winner gets the production tag.

The Player reads its instruction from that tag at session start. So the promotion is the deployment. Ask the failed question again two minutes later and you watch the scoreboard change.

## How I built it

Python ADK agents on Vertex AI, with the Referee on gemini-2.5-flash so scrimmage bursts draw from a separate quota pool. A custom OTel span processor pins each verdict to the right root span. The Gaffer holds 16 Phoenix MCP tools through ADK's McpToolset over stdio. FastAPI streams both agents' tool calls to the browser over SSE, one container on Cloud Run with Node inside for the MCP server.

## Challenges

The honest list. My span recorder silently replaced Phoenix's exporter (replace_default_processor defaults to true), so for an hour the annotations pointed at spans that never arrived. The coach once read traces of its own previous sessions, which contain trace dumps, and blew through Gemini's million token context; each agent now traces to its own Phoenix project. A 1 GiB container OOMed when the Gaffer pulled fifty traces in one MCP call. And the MCP upsert tool slugs prompt names, which broke the registry chain until I renamed the prompt to match.

## Accomplishments

Numbers from my Phoenix workspace, reproducible there: the scrimmage scored the old playbook 0.38 and the coached one 0.60 over the regression set, a 58 percent relative improvement in a single session. Questions that scored MISS 0.00 in the morning (stadium rail access, Houston weather, power bank rules) score GOAL 1.00 now. The registry holds 13 playbook versions, and every production tag was moved by the Gaffer itself after a winning experiment.

## What I learned

An eval is a report card until it can gate a deployment. Wired to a prompt registry and an experiment runner, it becomes the deployment pipeline. Phoenix's MCP server is what makes that possible for an agent rather than a human: observability stops being something you read and becomes something the system acts on.

## What's next

Coaching sessions triggered by MISS rate instead of a button. Human override through Phoenix annotation configs. Per failure mode playbook branches behind Phoenix A/B experiments.

---

**Track:** Arize
**Try it:** https://gaffer-734868402447.us-central1.run.app
**Data sources:** FIFA.com, host city transit authorities, official venue sites, US State Department. Every fact cited in data/sources.md in the repo.
**Built with:** google-adk, gemini, vertex-ai, cloud-run, arize-phoenix, mcp, openinference, fastapi, python
**Disclaimer:** Fan-made demo. Not affiliated with or endorsed by FIFA.
