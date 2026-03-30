from __future__ import annotations

import json
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"


def _load_json(filename: str) -> list[dict]:
    with (DATA_DIR / filename).open(encoding="utf-8") as file:
        return json.load(file)


RESTAURANTS = _load_json("restaurants.json")
ATTENDEES = _load_json("attendees.json")
EVENTS = _load_json("events.json")


def restaurant_finder(goal: str, history: list[dict]) -> dict:
    ranked = sorted(
        RESTAURANTS,
        key=lambda item: (item["walk_minutes"], item["price_level"], -int(item["good_for_groups"])),
    )
    return {"restaurants": ranked[:4]}


def weather_tool(goal: str, history: list[dict]) -> dict:
    return {
        "forecast": "Dallas tonight will be 72F, clear, and comfortable for walking between nearby venues.",
        "recommendation": "Outdoor patios are a safe choice, but indoor backups still work well for networking.",
    }


def attendee_lookup(goal: str, history: list[dict]) -> dict:
    text = goal.lower()
    matches = []
    for attendee in ATTENDEES:
        interests = " ".join(attendee["interests"]).lower()
        if "ai" in text and "ai" in interests:
            matches.append(attendee)
        elif any(word in text for word in ("network", "people", "conference", "socialize", "meet")):
            matches.append(attendee)

    return {"matches": matches[:3] or ATTENDEES[:3]}


def conversation_starter(goal: str, history: list[dict]) -> dict:
    attendee_results = next(
        (item["result"] for item in reversed(history) if item["tool"] == "attendee_lookup"),
        {"matches": ATTENDEES[:2]},
    )
    starters = []
    for attendee in attendee_results["matches"][:3]:
        topic = attendee["interests"][0]
        starters.append(
            f"Ask {attendee['name']} how {attendee['organization']} is approaching {topic}."
        )
    starters.append("Compare notes on where agent demos feel real versus where they become too brittle.")
    return {"starters": starters}


def budget_filter(goal: str, history: list[dict]) -> dict:
    restaurants = next(
        (item["result"]["restaurants"] for item in reversed(history) if item["tool"] == "restaurant_finder"),
        RESTAURANTS,
    )
    filtered = [restaurant for restaurant in restaurants if restaurant["price_level"] <= 2]
    return {"restaurants": filtered or restaurants[:2], "constraint": "Kept options at approximately $50 or less per person."}


def distance_filter(goal: str, history: list[dict]) -> dict:
    restaurants = next(
        (item["result"]["restaurants"] for item in reversed(history) if item["tool"] in {"budget_filter", "restaurant_finder"}),
        RESTAURANTS,
    )
    filtered = [restaurant for restaurant in restaurants if restaurant["walk_minutes"] <= 15]
    return {"restaurants": filtered or restaurants[:2], "constraint": "Kept options within an easy walk of the conference area."}


def event_finder(goal: str, history: list[dict]) -> dict:
    return {"events": EVENTS[:3]}


TOOL_DEFINITIONS = {
    "restaurant_finder": {
        "label": "Restaurant Finder",
        "description": "Find Dallas dinner options near the conference area.",
        "fn": restaurant_finder,
    },
    "weather_tool": {
        "label": "Weather Tool",
        "description": "Check tonight's Dallas weather so the plan fits the evening.",
        "fn": weather_tool,
    },
    "attendee_lookup": {
        "label": "Attendee Lookup",
        "description": "Pull conference-safe attendee profiles from a demo dataset.",
        "fn": attendee_lookup,
    },
    "conversation_starter": {
        "label": "Conversation Starter",
        "description": "Generate networking openers based on who the agent found.",
        "fn": conversation_starter,
    },
    "budget_filter": {
        "label": "Budget Filter",
        "description": "Keep the evening inside a reasonable dinner budget.",
        "fn": budget_filter,
    },
    "distance_filter": {
        "label": "Walking Distance Filter",
        "description": "Favor spots within a short walk of the conference footprint.",
        "fn": distance_filter,
    },
    "event_finder": {
        "label": "Event Finder",
        "description": "Suggest a nearby after-dinner stop or live event.",
        "fn": event_finder,
    },
}


def get_tool_catalog(enabled_tools: list[str]) -> list[dict]:
    return [
        {
            "name": tool_name,
            "label": TOOL_DEFINITIONS[tool_name]["label"],
            "description": TOOL_DEFINITIONS[tool_name]["description"],
        }
        for tool_name in enabled_tools
    ]
