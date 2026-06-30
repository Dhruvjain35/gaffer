"""Collect a golden set: run a diverse question bank through the live GAFFER agent,
capture each answer + the production referee's GOAL/MISS verdict + the evidence, so a
human can independently re-label and we can score the referee (Cohen's kappa).
Writes /tmp/golden_raw.json for labeling."""
import json, urllib.request, concurrent.futures as cf

URL = "https://gaffer-734868402447.us-central1.run.app/api/chat"

# Diverse bank: grounded (venues/policies/schedule/transit), out-of-scope (hotels/flights/
# gossip/live), tricky premises, and small-talk. Designed to stress the "lean GOAL" judge.
QUESTIONS = [
    "When and where is the 2026 World Cup final?",
    "What is the capacity of MetLife Stadium?",
    "Which cities have rail straight to the stadium?",
    "Can I bring a clear bag and a power bank into the stadium?",
    "What does a transit ticket to MetLife on final day cost?",
    "Tell me about Estadio Azteca's World Cup history.",
    "Do I need a visa to follow my team across all three host countries?",
    "What is the re-entry policy if I leave the stadium during a match?",
    "Which group is Japan in?",
    "What's the weather like in Houston for the group stage?",
    "Where is the opening match and who plays?",
    "Can I bring a vuvuzela and a professional camera into the stadium?",
    "What's the smoking and vaping policy in the stadiums?",
    "How do I get to SoFi Stadium without a car?",
    "Is there a fan festival in Mexico City and where?",
    "What ID do I need to pick up will-call tickets?",
    "Are outside food and water bottles allowed inside?",
    "What's the cheapest hotel near MetLife Stadium and what does it cost?",
    "Which airline has the cheapest flights from London to New York for the final?",
    "Who is going to win the 2026 World Cup final?",
    "What was the score of the Brazil match yesterday?",
    "What time does the Netherlands vs Japan opening match start?",
    "Did Messi confirm he is playing in 2026?",
    "What's the best restaurant near Arrowhead Stadium?",
    "How much are resale tickets going for on the secondary market?",
    "Can children under 5 get in free, and do they need a ticket?",
    "What accessibility services do the stadiums offer for wheelchair users?",
    "Are service animals allowed inside the venues?",
    "What's the alcohol policy at the stadiums?",
    "Which stadium has the highest altitude and how does it affect play?",
    "What's the prohibited items list for the stadiums?",
    "How early should I arrive before kickoff at MetLife?",
    "Is the final stadium air-conditioned?",
    "What payment methods are accepted inside the stadiums?",
    "Hey, what can you help me with?",
    "Thanks, that was really helpful!",
    "Plan my whole trip if I'm following Mexico through the group stage.",
    "What's the flag and banner policy for fans?",
]


def ask(q):
    body = json.dumps({"message": q}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    ans, ev_label, ev_score, sources, tools = "", None, None, 0, []
    try:
        with urllib.request.urlopen(req, timeout=140) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    e = json.loads(line[5:].strip())
                except Exception:
                    continue
                t = e.get("type")
                if t == "text" and not e.get("revision"):
                    ans += e.get("text", "")
                elif t == "text" and e.get("revision"):
                    ans = e.get("text", "")  # final coached answer wins
                elif t == "eval":
                    ev_label = e.get("label"); ev_score = e.get("grounding")
                    sources = e.get("sources", 0); tools = e.get("tools", [])
    except Exception as exc:
        return {"q": q, "error": str(exc)[:120]}
    return {"q": q, "answer": ans.strip(), "referee": ev_label, "grounding": ev_score,
            "sources": sources, "tools": tools}


def main():
    out = []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(ask, QUESTIONS):
            out.append(r)
            print(f"[{r.get('referee','ERR'):>4}] {r['q'][:60]}")
    json.dump(out, open("/tmp/golden_raw.json", "w"), indent=2)
    ok = [r for r in out if "error" not in r]
    print(f"\ncollected {len(ok)}/{len(out)} (referee GOAL={sum(1 for r in ok if r.get('referee')=='GOAL')} MISS={sum(1 for r in ok if r.get('referee')=='MISS')})")


if __name__ == "__main__":
    main()
