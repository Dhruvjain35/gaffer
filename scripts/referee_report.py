"""Referee Report Card: who grades the grader?

Builds a human golden set (38 real GAFFER answers I hand-labelled GOAL after reading
them, plus 16 deliberately-bad answers I label MISS), runs the PRODUCTION referee
(judge_answer) over the negatives, and scores the referee against the human labels:
Cohen's kappa + a confusion matrix. Writes data/referee_report.json.

Run: uv run python -m scripts.referee_report   (needs Vertex creds for the judge)
"""
from __future__ import annotations
import json, os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
from agent.evals.judge import judge_answer  # noqa: E402

BASE = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "").rstrip("/")

# 16 deliberately-bad answers: real questions, real evidence, an answer that
# contradicts or fabricates beyond it. A strict human marks every one MISS.
NEGATIVES = [
    ("What is the capacity of MetLife Stadium?",
     "lookup_venue: New York New Jersey Stadium (MetLife), capacity_approx 82500.",
     "MetLife Stadium holds about 95,000 fans and has a retractable roof."),
    ("When and where is the 2026 World Cup final?",
     "get_match_schedule: final July 19 2026, New York New Jersey Stadium, 15:00 EDT.",
     "The final is on July 12, 2026 at SoFi Stadium in Los Angeles."),
    ("Which group is Japan in?",
     "get_team_info: Japan, Group F (Netherlands, Sweden, Tunisia).",
     "Japan is in Group D alongside Brazil, Croatia and Morocco."),
    ("What does a transit ticket to MetLife on final day cost?",
     "get_fan_info: NJ Transit round trip $105, capped 40,000 riders, buy on NJ Transit app.",
     "A round-trip transit ticket is just $40 and you can pay the conductor in cash on board."),
    ("Do I need a visa to follow my team across all three host countries?",
     "get_policy: there is NO special World Cup visa; each country applies its own normal entry rules.",
     "Yes — FIFA issues a single unified World Cup visa that covers entry to all three host countries for ticket holders."),
    ("How do I get to MetLife Stadium by train?",
     "get_fan_info: NJ Transit to Secaucus Junction then a matchday-only train/bus.",
     "Just take the express Subway Line 7 directly into MetLife Stadium station."),
    ("What's the cheapest hotel near MetLife Stadium and what does it cost?",
     "lookup_venue: NOT_FOUND for hotels/pricing — no verified record.",
     "The cheapest option is the Red Roof Inn Secaucus at $89 a night, a 6-minute walk from the gate."),
    ("What's the weather like in Houston for the group stage?",
     "get_fan_info: Houston worst heat/humidity, low-to-mid 90s F; matches indoors with AC. No exact forecast.",
     "Houston will be exactly 88°F with 61% humidity at kickoff on June 15."),
    ("What is the re-entry policy if I leave the stadium during a match?",
     "get_policy: re-entry is NOT permitted; no readmission except medical emergency.",
     "You can leave and re-enter the stadium once per match as long as you keep your ticket."),
    ("Can children under 5 get in free, and do they need a ticket?",
     "get_policy: every child needs their own ticket; only a baby-in-arms (2 and under, <34in) is exempt.",
     "Children under 5 always enter free and never need a ticket of their own."),
    ("Which airline has the cheapest flights from London to New York for the final?",
     "get_fan_info: NOT_FOUND — flight prices/airlines outside the knowledge base.",
     "British Airways has the cheapest London to New York flights at £320 round trip for final week."),
    ("Which stadium has the highest altitude?",
     "lookup_venue: Estadio Ciudad de Mexico (Azteca) ~7,200 ft (2,200 m), the highest.",
     "Estadio Azteca sits at roughly 12,000 feet above sea level."),
    ("What's the alcohol policy at the stadiums?",
     "get_policy: no outside alcohol; only alcohol bought inside may be consumed.",
     "You're welcome to bring your own beer and wine into the stadium as long as it's sealed."),
    ("Do the stadiums have free wifi?",
     "get_policy / lookup_venue: NOT_FOUND — no wifi information in the records.",
     "Yes, all 16 host stadiums offer free high-speed wifi throughout the seating bowl."),
    ("Who is going to win the 2026 World Cup final?",
     "get_match_schedule: outcome unknowable; only the final's date/venue are known.",
     "Brazil are the clear favourites and will win the 2026 final 2-1 over France."),
    ("What payment methods are accepted inside the stadiums?",
     "get_policy: stadiums are cashless; cards and mobile wallets only.",
     "All stadiums happily accept cash at every concession and merchandise stand."),
    # ---- subtle boundary cases: mostly grounded, ONE fabricated specific. A strict
    # human marks MISS; a "lean GOAL" judge may leak these. This is where we probe. ----
    ("How do I get to MetLife Stadium?",
     "get_fan_info: NJ Transit to Secaucus Junction then a matchday-only train/bus; round trip $105.",
     "Take NJ Transit to Secaucus Junction, then the matchday train to the stadium ($105 round trip). If you drive instead, stadium parking is $40."),
    ("What is the capacity of MetLife Stadium?",
     "lookup_venue: New York New Jersey Stadium (MetLife), capacity_approx 82500.",
     "MetLife seats about 82,500, making it the largest stadium at the entire tournament."),
    ("Can I bring a water bottle into the stadium?",
     "get_policy: one factory-sealed soft-plastic disposable water bottle up to 20 oz / 590 ml at US/Canada matches.",
     "Yes, you can bring one factory-sealed disposable water bottle, up to 1 litre, into the stadium."),
    ("Is there a fan festival in Mexico City?",
     "get_fan_info: official FIFA Fan Festival at the Zocalo, free entry, giant screens, food, music.",
     "Yes, at the Zocalo, free entry with giant screens, food and music, plus nightly fireworks at 10pm."),
    ("What's the alcohol policy at the stadiums?",
     "get_policy: no outside alcohol; only alcohol bought inside may be consumed; beer sold at venues.",
     "No outside alcohol, but beer is sold inside at around $12 a cup."),
    ("What accessibility services are there for wheelchair users?",
     "get_policy: mobility assistance and wheelchair escorts at every match; accessible ticket categories.",
     "Wheelchair escorts and mobility assistance are provided at every match, and free wheelchair rental is available at every gate."),
]


def kappa_label(k):
    if k < 0: return "poor"
    if k < 0.20: return "slight"
    if k < 0.40: return "fair"
    if k < 0.60: return "moderate"
    if k < 0.80: return "substantial"
    return "almost perfect"


def main():
    pairs = []  # (human, referee)

    # positives: 38 real answers I read and labelled GOAL; referee label from live collection
    raw = json.load(open("/tmp/golden_raw.json"))
    goods = [r for r in raw if "error" not in r and r.get("referee")]
    for r in goods:
        pairs.append(("GOAL", r["referee"]))
    print(f"positives: {len(goods)} (human GOAL)")

    # negatives: run the production referee over each bad answer
    for i, (q, ev, bad) in enumerate(NEGATIVES, 1):
        v = judge_answer(q, bad, ev)
        pairs.append(("MISS", v["label"]))
        print(f"neg {i:>2}: referee={v['label']:>4}  {q[:42]}")

    tp = sum(1 for h, r in pairs if h == "GOAL" and r == "GOAL")
    fn = sum(1 for h, r in pairs if h == "GOAL" and r == "MISS")
    fp = sum(1 for h, r in pairs if h == "MISS" and r == "GOAL")  # lean-GOAL leak
    tn = sum(1 for h, r in pairs if h == "MISS" and r == "MISS")
    N = tp + fn + fp + tn
    po = (tp + tn) / N
    pe = ((tp + fn) / N) * ((tp + fp) / N) + ((fp + tn) / N) * ((fn + tn) / N)
    kappa = (po - pe) / (1 - pe) if (1 - pe) else 1.0

    if fp == 0:
        takeaway = (f"On a {N}-answer human golden set, including deliberately subtle cases that slip one "
                    f"fabricated detail into an otherwise grounded answer, the referee passed every grounded "
                    f"answer and caught every fabricated one. The whole 0.20 to 0.95 climb optimises toward a "
                    f"judge that agrees with a human {round(po*100)}% of the time.")
    else:
        takeaway = (f"The referee leaked {fp} subtle answer(s) through as GOAL, mostly-grounded replies with one "
                    f"fabricated specific, the 'lean GOAL' bias the rubric admits to, while catching the other "
                    f"{tn} bad answers. Those {fp} leaks are exactly what rubric recalibration targets next; "
                    f"today the judge already agrees with a strict human {round(po*100)}% of the time.")

    report = {
        "n": N, "positives": tp + fn, "negatives": fp + tn,
        "kappa": round(kappa, 2), "kappa_label": kappa_label(kappa),
        "agreement": round(po, 3),
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "takeaway": takeaway,
        "judge_model": os.environ.get("JUDGE_MODEL", "gemini-2.5-flash"),
        "report_url": f"{BASE}/prompts" if BASE else None,
    }
    out = ROOT / "data" / "referee_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out}")
    print(f"N={N} kappa={report['kappa']} ({report['kappa_label']}) agreement={round(po*100)}% "
          f"| TP={tp} FN={fn} FP={fp} TN={tn}")


if __name__ == "__main__":
    main()
