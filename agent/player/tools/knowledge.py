"""The Player's knowledge tools — grounded lookups over the curated WC2026 corpus.

Each tool returns a JSON string of matching records, or a clear NOT_FOUND marker.
The corpus lives in data/*.json and doubles as eval ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

_cache: dict[str, Any] = {}


def _load(name: str) -> Any:
    if name not in _cache:
        path = DATA_DIR / f"{name}.json"
        _cache[name] = json.loads(path.read_text()) if path.exists() else None
    return _cache[name]


def _units(obj: Any, key: str = "") -> list[tuple[str, Any]]:
    """Flatten one level into (searchable_text, record) units, keeping key names
    searchable so 'bag' matches the bag_policy section."""
    if obj is None:
        return []
    units: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "_meta":
                continue
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for item in v:
                    units.append((json.dumps(item, ensure_ascii=False).lower(), item))
            else:
                text = (k + " " + json.dumps(v, ensure_ascii=False)).lower().replace("_", " ")
                units.append((text, {k: v}))
    elif isinstance(obj, list):
        for item in obj:
            units.append((json.dumps(item, ensure_ascii=False).lower(), item))
    return units


def _search(obj: Any, terms: list[str]) -> list[Any]:
    """Rank flattened records by matched-term count; all-term matches first."""
    if not terms:
        return []
    scored = []
    for text, record in _units(obj):
        hits = sum(1 for t in terms if t in text)
        if hits:
            scored.append((hits == len(terms), hits, scored.__len__(), record))
    scored.sort(key=lambda s: (not s[0], -s[1], s[2]))
    return [record for _, _, _, record in scored]


def _result(matches: list[Any], topic: str, query: str) -> str:
    if not matches:
        return json.dumps({
            "status": "NOT_FOUND",
            "topic": topic,
            "query": query,
            "note": "No verified record in the knowledge base. Do NOT answer from memory; tell the fan you can't verify this.",
        })
    return json.dumps({"status": "ok", "topic": topic, "matches": matches[:8]}, ensure_ascii=False)


def lookup_venue(query: str) -> str:
    """Look up World Cup 2026 stadium facts: name, city, capacity, transit access, quirks.

    Args:
      query: Stadium name, city, or country (e.g. "Estadio Azteca", "Dallas", "Canada").
    """
    terms = [t for t in query.lower().split() if len(t) > 1]
    return _result(_search(_load("venues"), terms), "venues", query)


def get_match_schedule(query: str) -> str:
    """Look up WC2026 fixtures: opening match, first-week group games, knockout dates, the final.

    Args:
      query: Team, city, venue, stage or date fragment (e.g. "Mexico June 11", "final", "Group A").
    """
    terms = [t for t in query.lower().split() if len(t) > 1]
    return _result(_search(_load("schedule"), terms), "schedule", query)


def get_team_info(query: str) -> str:
    """Look up a qualified team's group assignment from the December 2025 draw.

    Args:
      query: Team or group (e.g. "Brazil", "Group C").
    """
    terms = [t for t in query.lower().split() if len(t) > 1]
    return _result(_search(_load("teams"), terms), "teams", query)


def get_policy(topic: str) -> str:
    """Look up verified fan policies: bag rules, prohibited items, tickets/ID, re-entry, borders/visas, alcohol.

    Args:
      topic: Policy topic (e.g. "bag size", "ESTA", "re-entry", "alcohol").
    """
    terms = [t for t in topic.lower().split() if len(t) > 1]
    return _result(_search(_load("policies"), terms), "policies", topic)


def get_fan_info(query: str) -> str:
    """Look up fan-experience info: FIFA Fan Festival sites, weather by host city, transit tips.

    Args:
      query: Host city or topic (e.g. "Miami weather", "fan festival Toronto", "transit Los Angeles").
    """
    terms = [t for t in query.lower().split() if len(t) > 1]
    return _result(_search(_load("fan_info"), terms), "fan_info", query)


ALL_TOOLS = [lookup_venue, get_match_schedule, get_team_info, get_policy, get_fan_info]
