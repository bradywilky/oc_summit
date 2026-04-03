from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


DATA_DIR = Path(__file__).parent / "data"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search"
FOURSQUARE_API_VERSION = "2025-06-17"
DALLAS_LATITUDE = 32.7767
DALLAS_LONGITUDE = -96.7970
DEFAULT_HOTEL_LOCATION = "Dallas Marriott Downtown, 650 N Pearl St, Dallas, TX 75201"


def _load_json(filename: str) -> list[dict]:
    with (DATA_DIR / filename).open(encoding="utf-8") as file:
        return json.load(file)


RESTAURANTS = _load_json("restaurants.json")
ATTENDEES = _load_json("attendees.json")
EVENTS = _load_json("events.json")


def _price_level_from_foursquare(value: int | None) -> int:
    if value is None:
        return 2
    return min(max(int(value), 1), 4)


def _estimated_cost(price_level: int) -> str:
    return {
        1: "$18",
        2: "$35",
        3: "$60",
        4: "$95",
    }.get(price_level, "$35")


def _good_for_groups(chains: list[dict] | None) -> bool:
    return bool(chains)


def _walk_minutes_from_distance(distance_meters: int) -> int:
    return max(1, round(distance_meters / 80))


def _foursquare_request(params: dict[str, str | int]) -> dict:
    api_key = os.getenv("FOURSQUARE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("FOURSQUARE_API_KEY is not set.")

    url = f"{FOURSQUARE_SEARCH_URL}?{urlencode(params)}"
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    request = Request(
        url,
        headers={
            "accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Places-Api-Version": FOURSQUARE_API_VERSION,
        },
    )

    try:
        with urlopen(request, timeout=15, context=ssl_context) as response:
            payload = json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Foursquare HTTP {exc.code}: {body}") from exc

    return payload


def _fetch_foursquare_restaurants(location: str) -> list[dict]:
    payload = _foursquare_request(
        {
            "near": location,
            "query": "restaurant",
            "limit": 10,
        }
    )

    results = []
    for venue in payload.get("results", []):
        categories = venue.get("categories", [])
        category = categories[0] if categories else {}
        category_label = category.get("name") or category.get("short_name") or "Restaurant"
        distance_meters = int(venue.get("distance", 0))
        walk_minutes = _walk_minutes_from_distance(distance_meters)
        price_level = _price_level_from_foursquare(venue.get("price"))
        formatted_address = venue.get("location", {}).get("formatted_address")
        results.append(
            {
                "name": venue.get("name", "Unknown restaurant"),
                "cuisine": category_label,
                "price_level": price_level,
                "estimated_cost": _estimated_cost(price_level),
                "walk_minutes": walk_minutes,
                "good_for_groups": _good_for_groups(venue.get("chains")),
                "distance_meters": distance_meters,
                "address": formatted_address or "Address unavailable",
            }
        )

    if not results:
        raise ValueError("Foursquare returned no nearby restaurants.")

    return results


def _fetch_foursquare_after_dinner_places(location: str) -> list[dict]:
    query_specs = (
        ("live music", "music"),
        ("rooftop bar", "rooftop"),
        ("comedy club", "comedy"),
        ("cocktail bar", "drinks"),
    )
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    results = []

    for query, fallback_type in query_specs:
        payload = _foursquare_request(
            {
                "near": location,
                "query": query,
                "limit": 4,
            }
        )

        for venue in payload.get("results", []):
            place_id = venue.get("fsq_place_id") or ""
            name = venue.get("name", "Unknown venue")
            normalized_name = name.strip().lower()
            if (place_id and place_id in seen_ids) or normalized_name in seen_names:
                continue

            categories = venue.get("categories", [])
            category = categories[0] if categories else {}
            category_label = category.get("name") or category.get("short_name") or "Nightlife"
            distance_meters = int(venue.get("distance", 0))
            results.append(
                {
                    "name": name,
                    "time": f"{_walk_minutes_from_distance(distance_meters)} min walk",
                    "type": fallback_type,
                    "venue_type": category_label,
                    "address": venue.get("location", {}).get("formatted_address") or "Address unavailable",
                    "distance_meters": distance_meters,
                }
            )
            if place_id:
                seen_ids.add(place_id)
            seen_names.add(normalized_name)

    if not results:
        raise ValueError("Foursquare returned no nearby after-dinner venues.")

    return sorted(results, key=lambda item: item["distance_meters"])


def restaurant_finder(goal: str, history: list[dict], context: dict | None = None) -> dict:
    location = (context or {}).get("hotel_location") or DEFAULT_HOTEL_LOCATION
    try:
        live_results = _fetch_foursquare_restaurants(location)
        ranked = sorted(
            live_results,
            key=lambda item: (item["walk_minutes"], item["price_level"], -int(item["good_for_groups"])),
        )
        return {
            "restaurants": ranked[:4],
            "source": "Foursquare Places API",
            "live": True,
            "search_center": location,
        }
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        ranked = sorted(
            RESTAURANTS,
            key=lambda item: (item["walk_minutes"], item["price_level"], -int(item["good_for_groups"])),
        )
        return {
            "restaurants": ranked[:4],
            "source": "Fallback restaurant dataset",
            "live": False,
            "search_center": location,
            "error": str(exc),
        }


def _fetch_dallas_weather() -> dict:
    params = {
        "latitude": DALLAS_LATITUDE,
        "longitude": DALLAS_LONGITUDE,
        "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Chicago",
        "forecast_days": 1,
    }
    url = f"{OPEN_METEO_FORECAST_URL}?{urlencode(params)}"
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    with urlopen(url, timeout=8, context=ssl_context) as response:
        return json.load(response)


def _describe_weather_code(code: int | None) -> str:
    descriptions = {
        0: "clear",
        1: "mostly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "foggy",
        48: "rime fog",
        51: "light drizzle",
        53: "drizzle",
        55: "dense drizzle",
        61: "light rain",
        63: "rain",
        65: "heavy rain",
        71: "light snow",
        73: "snow",
        75: "heavy snow",
        80: "light showers",
        81: "showers",
        82: "heavy showers",
        95: "thunderstorms",
    }
    return descriptions.get(code, "mixed conditions")


def _build_weather_summary(payload: dict) -> dict:
    current = payload["current"]
    daily = payload["daily"]
    high = round(daily["temperature_2m_max"][0])
    low = round(daily["temperature_2m_min"][0])
    precip_chance = daily["precipitation_probability_max"][0]
    condition = _describe_weather_code(current.get("weather_code"))
    temperature = round(current["temperature_2m"])
    feels_like = round(current["apparent_temperature"])
    wind_speed = round(current["wind_speed_10m"])

    if precip_chance >= 50:
        recommendation = "Plan for an indoor backup because rain is a real possibility."
    elif temperature >= 85 or wind_speed >= 18:
        recommendation = "Outdoor plans still work, but pick a spot with shade or an easy indoor option nearby."
    else:
        recommendation = "Outdoor patios are a safe choice, and walking between nearby venues should be comfortable."

    forecast = (
        f"Dallas is currently {temperature}F and {condition}, feeling like {feels_like}F. "
        f"Today's range is {low}F to {high}F with a top rain chance of {precip_chance}%."
    )
    return {
        "forecast": forecast,
        "recommendation": recommendation,
        "source": "Open-Meteo Forecast API",
        "live": True,
        "observed_at": current["time"],
    }


def weather_tool(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del context
    try:
        payload = _fetch_dallas_weather()
        return _build_weather_summary(payload)
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return {
            "forecast": "Live Dallas weather was unavailable, so the app is using a fallback estimate: mild evening conditions with manageable walking weather.",
            "recommendation": "Outdoor patios are still a reasonable default, but keep an indoor backup in mind.",
            "source": "Fallback weather summary",
            "live": False,
            "error": str(exc),
        }


def attendee_lookup(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del context
    text = goal.lower()
    matches = []
    for attendee in ATTENDEES:
        interests = " ".join(attendee["interests"]).lower()
        if "ai" in text and "ai" in interests:
            matches.append(attendee)
        elif any(word in text for word in ("network", "people", "conference", "socialize", "meet")):
            matches.append(attendee)

    return {"matches": matches[:3] or ATTENDEES[:3]}


def conversation_starter(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del context
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


def budget_filter(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del context
    restaurants = next(
        (item["result"]["restaurants"] for item in reversed(history) if item["tool"] == "restaurant_finder"),
        RESTAURANTS,
    )
    filtered = [restaurant for restaurant in restaurants if restaurant["price_level"] <= 2]
    return {"restaurants": filtered or restaurants[:2], "constraint": "Kept options at approximately $50 or less per person."}


def distance_filter(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del context
    restaurants = next(
        (item["result"]["restaurants"] for item in reversed(history) if item["tool"] in {"budget_filter", "restaurant_finder"}),
        RESTAURANTS,
    )
    filtered = [restaurant for restaurant in restaurants if restaurant["walk_minutes"] <= 15]
    return {"restaurants": filtered or restaurants[:2], "constraint": "Kept options within an easy walk of the conference area."}


def event_finder(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del goal, history
    location = (context or {}).get("hotel_location") or DEFAULT_HOTEL_LOCATION
    try:
        live_results = _fetch_foursquare_after_dinner_places(location)
        return {
            "events": live_results[:3],
            "source": "Foursquare Places API",
            "live": True,
            "search_center": location,
        }
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {
            "events": EVENTS[:3],
            "source": "Fallback event dataset",
            "live": False,
            "search_center": location,
            "error": str(exc),
        }


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
