from __future__ import annotations

import json
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

import certifi
import requests
from openai import OpenAI


DATA_DIR = Path(__file__).parent / "data"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search"
FOURSQUARE_API_VERSION = "2025-06-17"
DISCORD_API_BASE_URL = "https://discord.com/api/v10"
DALLAS_LATITUDE = 32.7767
DALLAS_LONGITUDE = -96.7970
DEFAULT_HOTEL_LOCATION = "Dallas Marriott Downtown, 650 N Pearl St, Dallas, TX 75201"
DEFAULT_DISCORD_MESSAGE = "Discord placeholder message from Agent Lab. Replace this after setup."
AGENT_POSTS_FILE = DATA_DIR / "agent_posts.json"
AGENT_MESSAGES_FILE = DATA_DIR / "agent_messages.json"
DEV_CONSOLE_STATE_FILE = DATA_DIR / "dev_console_state.json"
AGENT_LAB_POST_MARKER = "[AGENT_LAB_POST]"
AGENT_LAB_COLLAB_MARKER = "[AGENT_LAB_COLLAB]"
AGENT_LAB_DISCUSSION_MARKER = "[AGENT_LAB_DISCUSSION]"
AGENT_LAB_PROPOSAL_MARKER = "[AGENT_LAB_PROPOSAL]"
MAX_DISCORD_MESSAGE_LENGTH = 1900
DEFAULT_LISTEN_WINDOW_MINUTES = 30
NEGOTIATION_MESSAGE_COOLDOWN_SECONDS = 45

PLAN_FLEXIBILITY_STRICT = "structured"
PLAN_FLEXIBILITY_BALANCED = "balanced"
PLAN_FLEXIBILITY_FLEXIBLE = "flexible"
FOLLOW_UP_CONTROL_BALANCED = "balanced"
FOLLOW_UP_CONTROL_AUTONOMOUS = "autonomous"
FOLLOW_UP_CONTROL_APPROVAL_REQUIRED = "approval_required"


def _load_json(filename: str) -> list[dict]:
    with (DATA_DIR / filename).open(encoding="utf-8") as file:
        return json.load(file)


RESTAURANTS = _load_json("restaurants.json")
EVENTS = _load_json("events.json")


def _discord_error_reason(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            message = str(payload.get("message") or "").strip()
            errors = payload.get("errors")
            if message and errors:
                return f"Discord API HTTP {status_code}: {message} ({json.dumps(errors, ensure_ascii=False)})"
            if message:
                return f"Discord API HTTP {status_code}: {message}"

        body = response.text.strip()
        if body:
            return f"Discord API HTTP {status_code}: {body}"
        return f"Discord API HTTP {status_code}"

    if isinstance(exc, requests.Timeout):
        return "Discord request timed out."
    if isinstance(exc, requests.ConnectionError):
        return f"Could not connect to Discord: {exc}"
    return str(exc)

BCBS_PLAN_METADATA_SOURCE = "https://www.bcbs.com/about-us/blue-cross-blue-shield-system/state-health-plan-companies"
BCBS_STATE_PLAN_DIRECTORY = {
    "Alabama": ["Blue Cross and Blue Shield of Alabama"],
    "Alaska": ["Premera Blue Cross and Blue Shield of Alaska"],
    "Arizona": ["Blue Cross Blue Shield of Arizona"],
    "Arkansas": ["Arkansas Blue Cross and Blue Shield"],
    "California": ["Anthem Blue Cross", "Blue Shield of California"],
    "Colorado": ["Anthem Blue Cross and Blue Shield Colorado"],
    "Connecticut": ["Anthem Blue Cross and Blue Shield Connecticut"],
    "Delaware": ["Highmark Blue Cross Blue Shield Delaware"],
    "District of Columbia": ["CareFirst BlueCross BlueShield"],
    "Florida": ["Florida Blue"],
    "Georgia": ["Anthem Blue Cross and Blue Shield of Georgia"],
    "Hawaii": ["Blue Cross and Blue Shield of Hawaii"],
    "Idaho": ["Blue Cross of Idaho", "Regence BlueShield of Idaho"],
    "Illinois": ["Blue Cross and Blue Shield of Illinois"],
    "Indiana": ["Anthem Blue Cross and Blue Shield Indiana"],
    "Iowa": ["Wellmark Blue Cross and Blue Shield"],
    "Kansas": ["Blue Cross and Blue Shield of Kansas"],
    "Kentucky": ["Anthem Blue Cross and Blue Shield Kentucky"],
    "Louisiana": ["Blue Cross and Blue Shield of Louisiana"],
    "Maine": ["Anthem Blue Cross and Blue Shield Maine"],
    "Maryland": ["CareFirst BlueCross BlueShield"],
    "Massachusetts": ["Blue Cross and Blue Shield of Massachusetts"],
    "Michigan": ["Blue Cross Blue Shield of Michigan"],
    "Minnesota": ["Blue Cross and Blue Shield of Minnesota"],
    "Mississippi": ["Blue Cross & Blue Shield of Mississippi"],
    "Missouri": ["Anthem Blue Cross and Blue Shield Missouri", "Blue Cross and Blue Shield of Kansas City"],
    "Montana": ["Blue Cross and Blue Shield of Montana"],
    "Nebraska": ["Blue Cross and Blue Shield of Nebraska"],
    "Nevada": ["Anthem Blue Cross and Blue Shield Nevada"],
    "New Hampshire": ["Anthem Blue Cross and Blue Shield New Hampshire"],
    "New Jersey": ["Horizon Blue Cross and Blue Shield of New Jersey"],
    "New Mexico": ["Blue Cross and Blue Shield of New Mexico"],
    "New York": [
        "Anthem Blue Cross Blue Shield",
        "Highmark Blue Cross Blue Shield of Western New York",
        "Highmark Blue Shield of Northeastern New York",
        "Excellus BlueCross BlueShield",
    ],
    "North Carolina": ["Blue Cross and Blue Shield of North Carolina"],
    "North Dakota": ["Blue Cross Blue Shield of North Dakota"],
    "Ohio": ["Anthem Blue Cross and Blue Shield Ohio"],
    "Oklahoma": ["Blue Cross and Blue Shield of Oklahoma"],
    "Oregon": ["Regence BlueCross BlueShield of Oregon"],
    "Pennsylvania": [
        "Capital Blue Cross",
        "Highmark Blue Shield",
        "Highmark Blue Cross Blue Shield",
        "Independence Blue Cross",
    ],
    "Puerto Rico": ["BlueCross BlueShield of Puerto Rico"],
    "Rhode Island": ["Blue Cross & Blue Shield of Rhode Island"],
    "South Carolina": ["Blue Cross and Blue Shield of South Carolina"],
    "South Dakota": ["Wellmark Blue Cross and Blue Shield"],
    "Tennessee": ["BlueCross BlueShield of Tennessee"],
    "Texas": ["Blue Cross and Blue Shield of Texas"],
    "Utah": ["Regence BlueCross BlueShield of Utah"],
    "Vermont": ["Blue Cross and Blue Shield of Vermont"],
    "Virginia": ["Anthem Blue Cross and Blue Shield Virginia", "CareFirst BlueCross BlueShield"],
    "Washington": ["Premera Blue Cross", "Regence BlueShield"],
    "West Virginia": ["Highmark Blue Cross Blue Shield West Virginia"],
    "Wisconsin": ["Anthem Blue Cross and Blue Shield Wisconsin"],
    "Wyoming": ["Blue Cross Blue Shield of Wyoming"],
}
STATE_ABBREVIATIONS = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "PR": "Puerto Rico",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
STATE_REGION_OVERRIDES = {
    "District of Columbia": {
        "city": "Washington, DC",
        "likely_area": "Washington region",
        "conversation_topics": [
            "Ask how much of their work is tied to federal policy, national accounts, or employer groups in the DC market.",
            "Washington opener: compare favorite neighborhoods for dinner or where they send visitors first.",
            "Talk about balancing fast-moving policy work with practical member experience work on the ground.",
        ],
    },
    "Florida": {
        "city": "Jacksonville",
        "likely_area": "Jacksonville and statewide Florida operations",
    },
    "Illinois": {
        "city": "Chicago",
        "likely_area": "Chicago area",
        "conversation_topics": [
            "Chicago opener: ask which part of the city they end up in most for work and client meetings.",
            "Compare notes on enterprise scale, large employer groups, and how member expectations differ across a big metro.",
            "Ask what trends they are hearing from providers and members across Chicagoland versus downstate Illinois.",
        ],
    },
    "Iowa": {
        "city": "Des Moines",
        "likely_area": "Des Moines area",
        "conversation_topics": [
            "Des Moines opener: ask what part of the city their team is based in and what they like about the local business community.",
            "Talk about how statewide plans balance metro needs with rural provider and member realities across Iowa.",
            "Ask what surprises outsiders about healthcare innovation and employer relationships in Iowa.",
        ],
    },
    "Maryland": {
        "city": "Baltimore-Washington corridor",
        "likely_area": "Baltimore and Washington corridor",
    },
    "Massachusetts": {
        "city": "Boston",
        "likely_area": "Boston area",
    },
    "Michigan": {
        "city": "Detroit",
        "likely_area": "Detroit area",
        "conversation_topics": [
            "Detroit opener: ask how much of their work is centered downtown versus across the broader metro.",
            "Talk about large enterprise operations, service transformation, and the pace of modernization in Michigan.",
            "Ask what local provider or employer dynamics make Michigan different from other BCBS markets.",
        ],
    },
    "Minnesota": {
        "city": "Eagan / Minneapolis-St. Paul",
        "likely_area": "Twin Cities area",
    },
    "New Jersey": {
        "city": "Newark area",
        "likely_area": "North Jersey / Newark area",
    },
    "North Carolina": {
        "city": "Durham / Chapel Hill",
        "likely_area": "Research Triangle area",
    },
    "Pennsylvania": {
        "city": "Philadelphia, Pittsburgh, or Harrisburg",
        "likely_area": "one of the major Pennsylvania BCBS markets",
    },
    "Texas": {
        "city": "Richardson / Dallas-Fort Worth",
        "likely_area": "Dallas-Fort Worth area",
        "conversation_topics": [
            "Texas opener: ask whether their team is more Dallas-area, Austin, Houston, or statewide in how it works together.",
            "Talk about scale, growth, and how a large Texas market changes the way teams prioritize member and provider experience.",
            "Ask what regional differences inside Texas show up most clearly in their product or operations work.",
        ],
    },
    "Virginia": {
        "city": "Richmond or Northern Virginia / DC corridor",
        "likely_area": "Virginia home market",
    },
    "Washington": {
        "city": "Seattle area",
        "likely_area": "Seattle and statewide Washington operations",
    },
}
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


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _restaurant_query(name: str, address: str | None = None) -> str:
    parts = [name.strip()]
    if address and address.strip() and address != "Address unavailable":
        parts.append(address.strip())
    parts.append("Dallas TX")
    return ", ".join(parts)


def _google_maps_url(name: str, address: str | None = None) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(_restaurant_query(name, address))}"


def _booking_search_url(name: str, address: str | None = None) -> str:
    query = _restaurant_query(name, address)
    return f"https://www.opentable.com/s/?term={quote_plus(query)}"


def _website_search_url(name: str, address: str | None = None) -> str:
    query = f"{_restaurant_query(name, address)} official website"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _with_restaurant_links(restaurant: dict) -> dict:
    enriched = dict(restaurant)
    name = enriched.get("name", "Unknown restaurant")
    address = enriched.get("address")
    enriched["maps_url"] = _google_maps_url(name, address)
    enriched["booking_url"] = _booking_search_url(name, address)
    enriched["website_url"] = _website_search_url(name, address)
    enriched["reservable"] = True
    return enriched


def _generic_conversation_topics(state: str) -> list[str]:
    return [
        f"Ask what part of {state} their team is closest to and whether their day-to-day work feels statewide or metro-centered.",
        f"Compare notes on provider, employer, and member expectations in {state} versus other BCBS markets.",
        f"Use a light regional opener: ask what visitors usually misunderstand about working in {state}.",
    ]


def _extract_state_hints(goal: str) -> list[dict]:
    normalized = f" {_normalize_text(goal)} "
    hints: list[dict] = []
    seen_states: set[str] = set()

    if any(token in normalized for token in (" fepoc ", " federal employee program ", " federal employees program ", " fep ")):
        hints.append(
            {
                "kind": "special",
                "key": "fep",
                "organization": "Federal Employee Program (FEP)",
                "state": "Federal / national",
                "city": "National program team",
                "likely_area": "federal employee program operations",
                "conversation_topics": [
                    "Ask how FEP work differs from supporting a single regional plan.",
                    "Talk about what is uniquely complex about serving federal employees, retirees, and their families.",
                    "Compare notes on where national operating models help and where local plan realities still matter.",
                ],
                "confidence": "high",
                "matched_on": "FEP / FEPOC mention",
            }
        )

    for state in BCBS_STATE_PLAN_DIRECTORY:
        normalized_state = f" {_normalize_text(state)} "
        if normalized_state in normalized and state not in seen_states:
            hints.append({"kind": "state", "state": state, "matched_on": state, "confidence": "high"})
            seen_states.add(state)

    for abbreviation, state in STATE_ABBREVIATIONS.items():
        if state in seen_states:
            continue
        if f" {abbreviation.lower()} " in normalized:
            hints.append({"kind": "state", "state": state, "matched_on": abbreviation, "confidence": "medium"})
            seen_states.add(state)

    return hints


def _coerce_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def _llm_infer_bcbs_location_matches(goal: str, context: dict | None = None) -> list[dict]:
    api_key = (context or {}).get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []

    client = OpenAI(api_key=api_key)
    model = (context or {}).get("openai_model") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    state_plan_options = [
        {"state": state, "organizations": companies}
        for state, companies in BCBS_STATE_PLAN_DIRECTORY.items()
    ]
    response = client.responses.create(
        model=model,
        instructions=(
            "You map conference attendee location hints to the most likely regional BCBS Plan. "
            "Dallas is only the conference location and must not be treated as the attendee's home Plan unless the user explicitly says the attendee is from Texas. "
            "Use only the provided BCBS organizations. "
            "Return JSON only with this shape: "
            '{"matches":[{"state":"state","organization":"organization","matched_on":"location text","confidence":"low|medium|high","reason":"short explanation"}]}. '
            "Return up to 3 matches ordered from most likely to least likely. "
            "If the goal does not contain a meaningful attendee home-market clue, return {\"matches\":[]}."
        ),
        input=(
            f"User goal:\n{goal.strip()}\n\n"
            f"Available BCBS organizations by state:\n{json.dumps(state_plan_options, indent=2)}"
        ),
    )
    payload = _coerce_json(response.output_text)
    raw_matches = payload.get("matches", [])
    validated_matches: list[dict] = []
    for match in raw_matches:
        state = match.get("state")
        organization = match.get("organization")
        matched_on = (match.get("matched_on") or "").strip()
        confidence = match.get("confidence", "medium")
        reason = (match.get("reason") or "").strip()
        if state not in BCBS_STATE_PLAN_DIRECTORY:
            continue
        if organization not in BCBS_STATE_PLAN_DIRECTORY[state]:
            continue
        validated_matches.append(
            {
                "state": state,
                "organization": organization,
                "matched_on": matched_on or state,
                "confidence": confidence if confidence in {"low", "medium", "high"} else "medium",
                "reason": reason or f"Inferred from the user's location hint ({matched_on or state}).",
            }
        )
    return validated_matches[:3]


def _infer_bcbs_plan_matches(goal: str, context: dict | None = None) -> list[dict]:
    matches: list[dict] = []

    for hint in _extract_state_hints(goal):
        if hint["kind"] == "special":
            matches.append(
                {
                    "organization": hint["organization"],
                    "state": hint["state"],
                    "city": hint["city"],
                    "likely_area": hint["likely_area"],
                    "conversation_topics": hint["conversation_topics"],
                    "confidence": hint["confidence"],
                    "matched_on": hint["matched_on"],
                    "source": BCBS_PLAN_METADATA_SOURCE,
                    "inference_note": "Matched from a direct Federal Employee Program hint.",
                }
            )
            continue

        state = hint["state"]
        region = STATE_REGION_OVERRIDES.get(state, {})
        city = region.get("city", f"{state} regional market")
        likely_area = region.get("likely_area", f"{state} regional market")
        topics = region.get("conversation_topics", _generic_conversation_topics(state))

        for company in BCBS_STATE_PLAN_DIRECTORY.get(state, []):
            matches.append(
                {
                    "organization": company,
                    "state": state,
                    "city": city,
                    "likely_area": likely_area,
                    "conversation_topics": topics,
                    "confidence": hint["confidence"],
                    "matched_on": hint["matched_on"],
                    "source": BCBS_PLAN_METADATA_SOURCE,
                    "inference_note": f"Inferred from the user's location hint ({hint['matched_on']}).",
                }
            )

    if matches:
        return matches[:4]

    try:
        llm_matches = _llm_infer_bcbs_location_matches(goal, context)
    except Exception:
        llm_matches = []

    for match in llm_matches:
        state = match["state"]
        region = STATE_REGION_OVERRIDES.get(state, {})
        city = region.get("city", f"{state} regional market")
        likely_area = region.get("likely_area", f"{state} regional market")
        topics = region.get("conversation_topics", _generic_conversation_topics(state))
        matches.append(
            {
                "organization": match["organization"],
                "state": state,
                "city": city,
                "likely_area": likely_area,
                "conversation_topics": topics,
                "confidence": match["confidence"],
                "matched_on": match["matched_on"],
                "source": BCBS_PLAN_METADATA_SOURCE,
                "inference_note": match["reason"],
            }
        )

    return matches[:4]


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
            "restaurants": [_with_restaurant_links(item) for item in ranked[:4]],
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
            "restaurants": [_with_restaurant_links(item) for item in ranked[:4]],
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


def conversation_starter(goal: str, history: list[dict], context: dict | None = None) -> dict:
    del history
    inferred_connections = _infer_bcbs_plan_matches(goal, context)
    starters = []
    for inferred in inferred_connections[:3]:
        starters.append(
            f"If they are with {inferred['organization']}, ask whether their work is centered in {inferred['likely_area']} or spread across {inferred['state']}."
        )
        starters.append(inferred["conversation_topics"][0])
        starters.append(inferred["conversation_topics"][1])
    if not starters:
        starters.append("Ask which BCBS Plan or regional market they support most closely.")
        starters.append("Compare notes on where agent demos feel real versus where they become too brittle.")
        starters.append("Ask which member or operator workflow they most want AI to improve this year.")
    else:
        starters.append("Ask which BCBS Plan they support, just to confirm the city-to-Plan inference before you go deeper.")
    return {"starters": starters[:5]}


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


def _build_message_summary(goal: str, history: list[dict]) -> str:
    weather = None
    restaurant = None
    starter = None
    event = None

    for item in history:
        result = item.get("result", {})
        if item.get("tool") == "weather_tool" and not weather:
            weather = result.get("forecast")
        elif item.get("tool") == "restaurant_finder" and not restaurant:
            restaurants = result.get("restaurants") or []
            if restaurants:
                top_pick = restaurants[0]
                restaurant = (
                    f"{top_pick.get('name', 'Top dinner pick')} "
                    f"({top_pick.get('estimated_cost', 'budget TBD')}, "
                    f"{top_pick.get('walk_minutes', '?')} min walk)"
                )
        elif item.get("tool") == "conversation_starter" and not starter:
            starters = result.get("starters") or []
            if starters:
                starter = starters[0]
        elif item.get("tool") == "event_finder" and not event:
            events = result.get("events") or []
            if events:
                top_event = events[0]
                event = f"{top_event.get('name', 'Optional stop')} after dinner"

    lines = ["Agent Lab update:"]
    if restaurant:
        lines.append(f"Dinner: {restaurant}.")
    if weather:
        lines.append(weather)
    if starter:
        lines.append(f"Networking idea: {starter}")
    if event:
        lines.append(f"Optional next stop: {event}.")

    message = " ".join(lines)
    if message == "Agent Lab update:":
        message = DEFAULT_DISCORD_MESSAGE

    if len(message) > 1800:
        message = message[:1797].rstrip() + "..."

    return message


def _discord_request(method: str, endpoint: str, bot_token: str, **kwargs) -> dict | str:
    url = f"{DISCORD_API_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    response = requests.request(method, url, headers=headers, timeout=30, **kwargs)

    try:
        data = response.json()
    except ValueError:
        data = response.text

    response.raise_for_status()
    return data


def _send_discord_message(message: str) -> dict:
    bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.getenv("DISCORD_CHANNEL_ID", "").strip()

    missing_fields = [
        name
        for name, value in (
            ("DISCORD_BOT_TOKEN", bot_token),
            ("DISCORD_CHANNEL_ID", channel_id),
        )
        if not value
    ]
    if missing_fields:
        return {
            "sent": False,
            "setup_required": True,
            "channel_id": channel_id or None,
            "message_preview": message,
            "missing": missing_fields,
            "reason": f"Missing Discord configuration: {', '.join(missing_fields)}.",
            "note": "Discord credentials are not configured yet.",
        }

    try:
        bot_user = _discord_request("GET", "/users/@me", bot_token)
        discord_message = _discord_request(
            "POST",
            f"/channels/{channel_id}/messages",
            bot_token,
            json={"content": message},
        )
    except requests.RequestException as exc:
        reason = _discord_error_reason(exc)
        return {
            "sent": False,
            "setup_required": False,
            "channel_id": channel_id,
            "message_preview": message,
            "error": str(exc),
            "reason": reason,
        }

    return {
        "sent": True,
        "setup_required": False,
        "channel_id": channel_id,
        "message_id": discord_message.get("id") if isinstance(discord_message, dict) else None,
        "bot_username": bot_user.get("username") if isinstance(bot_user, dict) else None,
        "message_preview": message,
    }


def _fetch_discord_messages(limit: int = 50) -> dict:
    bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.getenv("DISCORD_CHANNEL_ID", "").strip()

    missing_fields = [
        name
        for name, value in (
            ("DISCORD_BOT_TOKEN", bot_token),
            ("DISCORD_CHANNEL_ID", channel_id),
        )
        if not value
    ]
    if missing_fields:
        return {
            "fetched": False,
            "setup_required": True,
            "channel_id": channel_id or None,
            "messages": [],
            "missing": missing_fields,
            "reason": f"Missing Discord configuration: {', '.join(missing_fields)}.",
            "note": "Discord credentials are not configured yet.",
        }

    try:
        messages = _discord_request(
            "GET",
            f"/channels/{channel_id}/messages",
            bot_token,
            params={"limit": min(max(limit, 1), 100)},
        )
    except requests.RequestException as exc:
        reason = _discord_error_reason(exc)
        return {
            "fetched": False,
            "setup_required": False,
            "channel_id": channel_id,
            "messages": [],
            "error": str(exc),
            "reason": reason,
        }

    return {
        "fetched": True,
        "setup_required": False,
        "channel_id": channel_id,
        "messages": messages if isinstance(messages, list) else [],
    }


def _read_local_agent_posts() -> list[dict]:
    if not AGENT_POSTS_FILE.exists():
        return []

    try:
        with AGENT_POSTS_FILE.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    posts = payload.get("posts", []) if isinstance(payload, dict) else []
    return posts if isinstance(posts, list) else []


def _write_local_agent_post(post: dict) -> None:
    AGENT_POSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    posts = _read_local_agent_posts()
    posts = [item for item in posts if item.get("participant_id") != post.get("participant_id")]
    posts.append(post)
    posts = sorted(posts, key=lambda item: item.get("posted_at", ""))
    with AGENT_POSTS_FILE.open("w", encoding="utf-8") as file:
        json.dump({"posts": posts[-25:]}, file, indent=2)


def _read_local_agent_messages() -> list[dict]:
    if not AGENT_MESSAGES_FILE.exists():
        return []

    try:
        with AGENT_MESSAGES_FILE.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    return messages if isinstance(messages, list) else []


def _write_local_agent_message(message: dict) -> None:
    AGENT_MESSAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
    messages = _read_local_agent_messages()
    messages.append(message)
    messages = sorted(messages, key=lambda item: item.get("sent_at", ""))
    with AGENT_MESSAGES_FILE.open("w", encoding="utf-8") as file:
        json.dump({"messages": messages[-100:]}, file, indent=2)


def _read_dev_console_state() -> dict:
    if not DEV_CONSOLE_STATE_FILE.exists():
        return {}

    try:
        with DEV_CONSOLE_STATE_FILE.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _write_dev_console_state(payload: dict) -> dict:
    DEV_CONSOLE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DEV_CONSOLE_STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    return payload


def get_discord_oldest_lookback_timestamp() -> str | None:
    payload = _read_dev_console_state()
    value = payload.get("discord_oldest_lookback_timestamp")
    return value.strip() if isinstance(value, str) and value.strip() else None


def set_discord_oldest_lookback_timestamp(timestamp: str | None) -> str | None:
    payload = _read_dev_console_state()
    normalized = timestamp.strip() if isinstance(timestamp, str) else ""
    payload["discord_oldest_lookback_timestamp"] = normalized or None
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_dev_console_state(payload)
    return payload["discord_oldest_lookback_timestamp"]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_lookback_cutoff(
    oldest_lookback_timestamp: str | datetime | None,
    max_age_minutes: int | None,
) -> datetime | None:
    if isinstance(oldest_lookback_timestamp, datetime):
        if oldest_lookback_timestamp.tzinfo is None:
            return oldest_lookback_timestamp.replace(tzinfo=timezone.utc)
        return oldest_lookback_timestamp.astimezone(timezone.utc)

    if isinstance(oldest_lookback_timestamp, str):
        parsed = _parse_timestamp(oldest_lookback_timestamp)
        if parsed is not None:
            return parsed

    if isinstance(max_age_minutes, int) and max_age_minutes > 0:
        return datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

    return None


def _is_recent_post(post: dict, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True

    timestamp = _parse_timestamp(post.get("discord_timestamp")) or _parse_timestamp(post.get("posted_at"))
    if timestamp is None:
        return False
    return timestamp >= cutoff


def _truncate_for_discord(message: str) -> str:
    if len(message) <= MAX_DISCORD_MESSAGE_LENGTH:
        return message
    return message[: MAX_DISCORD_MESSAGE_LENGTH - 3].rstrip() + "..."


def _extract_json_payload(content: str) -> dict:
    if not isinstance(content, str):
        return {}
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if not json_match:
        return {}
    try:
        payload = json.loads(json_match.group(1))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_structured_agent_message(marker: str, title: str, summary: str, payload: dict, lines: list[str]) -> str:
    body_lines = [f"{marker} **{title}**", summary]
    body_lines.extend(line for line in lines if line)
    structured = json.dumps(payload, ensure_ascii=False)
    body = "\n".join(line for line in body_lines if line)
    return _truncate_for_discord(f"{body}\n```json\n{structured}\n```")


def build_agent_intent_message(profile: dict, goal: str) -> str:
    payload = {
        "participant_id": profile.get("participant_id", ""),
        "name": profile.get("name", "Anonymous"),
        "bcbs_plan": profile.get("bcbs_plan", "Unknown BCBS Plan"),
        "job_title": profile.get("job_title", "Conference participant"),
        "restaurant_preferences": profile.get("restaurant_preferences", ""),
        "done_for_day_time": profile.get("done_for_day_time", ""),
        "goal": goal.strip(),
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }
    readable = (
        f"{AGENT_LAB_POST_MARKER} **{payload['name']}'s agent is looking for collaborators.**\n"
        f"Plan: {payload['bcbs_plan']} | Role: {payload['job_title']}\n"
        f"Food preferences: {payload['restaurant_preferences'] or 'Open to ideas'}\n"
        f"Done for the day around: {payload['done_for_day_time'] or 'Time not specified'}\n"
        f"Wants to do: {payload['goal'] or 'Meet people for dinner'}"
    )
    structured = json.dumps(payload, ensure_ascii=False)
    return _truncate_for_discord(f"{readable}\n```json\n{structured}\n```")


def _parse_agent_lab_post(message: dict) -> dict | None:
    content = message.get("content", "")
    if AGENT_LAB_POST_MARKER not in content:
        return None

    payload = _extract_json_payload(content)
    if not payload:
        return None

    author = message.get("author", {}) if isinstance(message.get("author"), dict) else {}
    payload["discord_message_id"] = message.get("id")
    payload["discord_author"] = author.get("username")
    payload["discord_timestamp"] = message.get("timestamp")
    payload["source"] = "discord"
    return payload


def _parse_agent_lab_message(message: dict, marker: str) -> dict | None:
    content = message.get("content", "")
    if marker not in content:
        return None

    payload = _extract_json_payload(content)
    if not payload:
        return None

    author = message.get("author", {}) if isinstance(message.get("author"), dict) else {}
    payload["marker"] = marker
    payload["discord_message_id"] = message.get("id")
    payload["discord_author"] = author.get("username")
    payload["discord_timestamp"] = message.get("timestamp")
    payload["source"] = "discord"
    return payload


def publish_agent_post(profile: dict, goal: str) -> dict:
    message = build_agent_intent_message(profile, goal)
    discord_result = _send_discord_message(message)
    return {
        "posted": bool(discord_result.get("sent")),
        "discord": discord_result,
        "message_preview": message,
    }


def listen_for_agent_posts(
    current_participant_id: str | None = None,
    limit: int = 50,
    max_age_minutes: int | None = DEFAULT_LISTEN_WINDOW_MINUTES,
    oldest_lookback_timestamp: str | datetime | None = None,
) -> dict:
    discord_result = _fetch_discord_messages(limit)
    posts = []
    if discord_result.get("messages"):
        for message in discord_result["messages"]:
            parsed = _parse_agent_lab_post(message)
            if parsed:
                posts.append(parsed)

    cutoff = _resolve_lookback_cutoff(oldest_lookback_timestamp, max_age_minutes)
    if cutoff is not None:
        posts = [post for post in posts if _is_recent_post(post, cutoff)]

    if current_participant_id:
        posts = [post for post in posts if post.get("participant_id") != current_participant_id]

    deduped: dict[str, dict] = {}
    for post in posts:
        key = post.get("participant_id") or post.get("discord_message_id") or post.get("name", "")
        if key:
            deduped[key] = post

    sorted_posts = sorted(
        deduped.values(),
        key=lambda item: item.get("discord_timestamp") or item.get("posted_at") or "",
        reverse=True,
    )
    return {
        "posts": sorted_posts[:limit],
        "discord": discord_result,
        "source": "discord",
        "max_age_minutes": max_age_minutes,
        "oldest_lookback_timestamp": cutoff.isoformat() if cutoff else None,
    }


def _message_targets_participant(message: dict, participant_id: str | None) -> bool:
    if not participant_id:
        return True
    target_ids = message.get("target_participant_ids") or []
    if not target_ids:
        return True
    return participant_id in target_ids


def _message_timestamp_value(message: dict) -> str:
    return message.get("discord_timestamp") or message.get("sent_at") or ""


def listen_for_agent_messages(
    current_participant_id: str | None = None,
    limit: int = 100,
    max_age_minutes: int | None = DEFAULT_LISTEN_WINDOW_MINUTES,
    oldest_lookback_timestamp: str | datetime | None = None,
) -> dict:
    discord_result = _fetch_discord_messages(limit)
    messages = []
    if discord_result.get("messages"):
        for discord_message in discord_result["messages"]:
            for marker in (AGENT_LAB_DISCUSSION_MARKER, AGENT_LAB_PROPOSAL_MARKER):
                parsed = _parse_agent_lab_message(discord_message, marker)
                if parsed:
                    messages.append(parsed)

    cutoff = _resolve_lookback_cutoff(oldest_lookback_timestamp, max_age_minutes)
    if cutoff is not None:
        messages = [message for message in messages if _is_recent_post(message, cutoff)]

    if current_participant_id:
        messages = [
            message
            for message in messages
            if message.get("sender_participant_id") == current_participant_id
            or _message_targets_participant(message, current_participant_id)
        ]

    sorted_messages = sorted(messages, key=_message_timestamp_value, reverse=True)
    return {
        "messages": sorted_messages[:limit],
        "discord": discord_result,
        "source": "discord",
        "max_age_minutes": max_age_minutes,
        "oldest_lookback_timestamp": cutoff.isoformat() if cutoff else None,
    }


def _participant_key(post: dict) -> str:
    return str(post.get("participant_id") or post.get("discord_message_id") or post.get("name", "")).strip()


def _group_signature(profile: dict, collaborators: list[dict]) -> str:
    participant_ids = [_participant_key(profile)]
    participant_ids.extend(_participant_key(post) for post in collaborators)
    normalized = sorted(participant_id for participant_id in participant_ids if participant_id)
    return "|".join(normalized)


def _names_from_posts(posts: list[dict]) -> list[str]:
    return [post.get("name", "another participant") for post in posts if isinstance(post, dict)]


def _text_signals_uncertainty(value: str) -> bool:
    normalized = _normalize_text(value)
    unsure_phrases = (
        "i dont know",
        "dont know",
        "not sure",
        "unsure",
        "open to ideas",
        "help me choose",
        "anything works",
        "no preference",
    )
    return any(phrase in normalized for phrase in unsure_phrases)


def _availability_overlap_hint(profile: dict, collaborators: list[dict]) -> str:
    own_time = profile.get("done_for_day_time", "").strip()
    collaborator_times = [post.get("done_for_day_time", "").strip() for post in collaborators if post.get("done_for_day_time", "").strip()]
    if own_time and collaborator_times:
        return f"You're free around {own_time}, and others are mentioning {', '.join(collaborator_times[:2])}."
    if own_time:
        return f"You're free around {own_time}."
    if collaborator_times:
        return f"Other people are mentioning availability around {', '.join(collaborator_times[:2])}."
    return ""


def _derive_human_follow_up_questions(
    profile: dict,
    incoming_messages: list[dict],
    collaboration: dict | None = None,
    collaborators: list[dict] | None = None,
) -> list[str]:
    questions: list[str] = []
    collaborators = collaborators or []
    diplomacy = profile.get("diplomacy_preferences") or {}
    plan_flexibility = diplomacy.get("plan_flexibility", PLAN_FLEXIBILITY_BALANCED)
    follow_up_control = diplomacy.get("follow_up_control", FOLLOW_UP_CONTROL_BALANCED)
    allow_local_clarifications = follow_up_control != FOLLOW_UP_CONTROL_AUTONOMOUS
    goal = profile.get("goal", "").strip()
    preferences = profile.get("restaurant_preferences", "").strip()
    uncertain = _text_signals_uncertainty(goal) or _text_signals_uncertainty(preferences)
    restaurants = (collaboration or {}).get("restaurants") or []
    events = (collaboration or {}).get("events") or []

    if allow_local_clarifications and not preferences and plan_flexibility in {PLAN_FLEXIBILITY_STRICT, PLAN_FLEXIBILITY_BALANCED}:
        questions.append("What dietary, budget, or vibe constraints should I represent before I lock in a group dinner?")
    elif allow_local_clarifications and uncertain and plan_flexibility == PLAN_FLEXIBILITY_STRICT:
        if restaurants:
            option_names = " or ".join(restaurant.get("name", "that option") for restaurant in restaurants[:2])
            questions.append(
                f"You said you are not sure yet. Based on nearby options, should I optimize more for {option_names}, or keep looking for something different?"
            )
        else:
            questions.append(
                "You said you are not sure yet. Should I optimize first for budget, food style, walking distance, or networking vibe?"
            )

    if allow_local_clarifications and uncertain and plan_flexibility == PLAN_FLEXIBILITY_STRICT:
        if collaborators:
            names = ", ".join(post.get("name", "another participant") for post in collaborators[:3])
            availability_hint = _availability_overlap_hint(profile, collaborators)
            question = f"People with similar plans right now include {names}."
            if availability_hint:
                question = f"{question} {availability_hint}"
            question += " Would you rather I steer toward a quick dinner, a longer networking meal, or dinner plus an after-dinner stop?"
            questions.append(question)
        elif events:
            event_names = " or ".join(event.get("name", "that option") for event in events[:2])
            questions.append(
                f"If dinner goes well, should I bias toward a simple dinner-only plan or leave room for something after, like {event_names}?"
            )

    if allow_local_clarifications and not profile.get("done_for_day_time", "").strip() and plan_flexibility != PLAN_FLEXIBILITY_FLEXIBLE:
        questions.append("What time do you expect to be done for the day so I can suggest plans at the right time?")

    for message in incoming_messages:
        for question in message.get("questions") or []:
            if question and question not in questions:
                questions.append(question)
    return questions[:3]


def _discussion_lines(collaboration: dict, target_names: list[str]) -> list[str]:
    restaurants = collaboration.get("restaurants") or []
    events = collaboration.get("events") or []
    lines = [f"Looping in: {', '.join(target_names)}" if target_names else ""]
    if restaurants:
        lines.append(f"Best dinner candidate so far: {_restaurant_line(restaurants[0])}")
    if events:
        lines.append(f"Optional next stop: {_event_line(events[0])}")
    return lines


def _proposal_lines(collaboration: dict, target_names: list[str]) -> list[str]:
    lines = [f"Potential group: {', '.join(target_names)}" if target_names else ""]
    for step in (collaboration.get("next_steps") or [])[:3]:
        lines.append(f"- {step}")
    return lines


def _build_agent_discussion_payload(
    profile: dict,
    collaboration: dict,
    collaborators: list[dict],
    questions: list[str] | None = None,
    status: str = "discussion",
) -> dict:
    restaurants = collaboration.get("restaurants") or []
    events = collaboration.get("events") or []
    return {
        "sender_participant_id": profile.get("participant_id", ""),
        "sender_name": profile.get("name", "Anonymous"),
        "target_participant_ids": [_participant_key(post) for post in collaborators if _participant_key(post)],
        "target_names": _names_from_posts(collaborators),
        "group_signature": _group_signature(profile, collaborators),
        "summary": collaboration.get("summary", ""),
        "questions": questions or [],
        "next_steps": (collaboration.get("next_steps") or [])[:3],
        "restaurants": [restaurant.get("name", "Dinner option") for restaurant in restaurants[:2]],
        "events": [event.get("name", "After-dinner option") for event in events[:2]],
        "status": status,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


def build_agent_discussion_message(profile: dict, collaboration: dict, collaborators: list[dict], questions: list[str] | None = None) -> str:
    payload = _build_agent_discussion_payload(profile, collaboration, collaborators, questions=questions, status="discussion")
    lines = _discussion_lines(collaboration, payload.get("target_names", []))
    if payload["questions"]:
        lines.append("Questions for agents to check with their humans:")
        lines.extend(f"- {question}" for question in payload["questions"][:3])
    return _build_structured_agent_message(
        AGENT_LAB_DISCUSSION_MARKER,
        f"{profile.get('name', 'An agent')} is comparing notes with other agents.",
        collaboration.get("summary", "I found a few possible collaborators and want to pressure-test a plan."),
        payload,
        lines,
    )


def build_agent_proposal_message(profile: dict, collaboration: dict, collaborators: list[dict]) -> str:
    payload = _build_agent_discussion_payload(profile, collaboration, collaborators, questions=None, status="proposal")
    return _build_structured_agent_message(
        AGENT_LAB_PROPOSAL_MARKER,
        f"{profile.get('name', 'An agent')} has a draft plan ready for human approval.",
        collaboration.get("summary", "A possible group plan is ready."),
        payload,
        _proposal_lines(collaboration, payload.get("target_names", [])),
    )


def _store_agent_message_locally(profile: dict, message: str, marker: str) -> dict:
    payload = _extract_json_payload(message)
    local_message = {
        **payload,
        "marker": marker,
        "sender_participant_id": profile.get("participant_id", ""),
        "sender_name": profile.get("name", "Anonymous"),
        "sent_at": payload.get("sent_at") or datetime.now(timezone.utc).isoformat(),
        "source": "local",
    }
    _write_local_agent_message(local_message)
    return local_message


def post_agent_discussion_message(profile: dict, collaboration: dict, collaborators: list[dict], questions: list[str] | None = None) -> dict:
    message = build_agent_discussion_message(profile, collaboration, collaborators, questions=questions)
    discord_result = _send_discord_message(message)
    local_message = None
    if discord_result.get("sent"):
        local_message = {
            **(_extract_json_payload(message) or {}),
            "marker": AGENT_LAB_DISCUSSION_MARKER,
            "sender_participant_id": profile.get("participant_id", ""),
            "sender_name": profile.get("name", "Anonymous"),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "source": "discord",
            "discord_message_id": discord_result.get("message_id"),
        }
    return {
        "sent": bool(discord_result.get("sent")),
        "discord": discord_result,
        "local_message": local_message,
        "message_preview": message,
    }


def post_agent_proposal_message(profile: dict, collaboration: dict, collaborators: list[dict]) -> dict:
    message = build_agent_proposal_message(profile, collaboration, collaborators)
    discord_result = _send_discord_message(message)
    local_message = None
    if discord_result.get("sent"):
        local_message = {
            **(_extract_json_payload(message) or {}),
            "marker": AGENT_LAB_PROPOSAL_MARKER,
            "sender_participant_id": profile.get("participant_id", ""),
            "sender_name": profile.get("name", "Anonymous"),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "source": "discord",
            "discord_message_id": discord_result.get("message_id"),
        }
    return {
        "sent": bool(discord_result.get("sent")),
        "discord": discord_result,
        "local_message": local_message,
        "message_preview": message,
    }


def _overlap_score(profile: dict, post: dict) -> int:
    score = 0
    profile_prefs = _normalize_text(profile.get("restaurant_preferences", ""))
    post_prefs = _normalize_text(post.get("restaurant_preferences", ""))
    profile_goal = _normalize_text(profile.get("goal", ""))
    post_goal = _normalize_text(post.get("goal", ""))

    if profile.get("bcbs_plan") and profile.get("bcbs_plan") == post.get("bcbs_plan"):
        score += 4
    if profile_prefs and post_prefs:
        score += len(set(profile_prefs.split()) & set(post_prefs.split()))
    if profile_goal and post_goal:
        score += min(4, len(set(profile_goal.split()) & set(post_goal.split())))
    if profile.get("job_title") and post.get("job_title"):
        score += len(set(_normalize_text(profile["job_title"]).split()) & set(_normalize_text(post["job_title"]).split()))
    if profile.get("done_for_day_time") and post.get("done_for_day_time"):
        score += len(
            set(_normalize_text(profile["done_for_day_time"]).split()) & set(_normalize_text(post["done_for_day_time"]).split())
        )
    return score


def _deterministic_collaboration(profile: dict, posts: list[dict]) -> dict:
    ranked = sorted(posts, key=lambda post: _overlap_score(profile, post), reverse=True)
    collaborators = ranked[:3]
    if not collaborators:
        return {
            "summary": "No other agent posts are visible yet. Keep listening, then refresh once more participants publish.",
            "collaborators": [],
            "next_steps": ["Post your intent, then ask nearby participants to do the same."],
        }

    names = ", ".join(post.get("name", "another participant") for post in collaborators)
    next_steps = [
        f"Reply in Discord tagging {names} and suggest forming a dinner group.",
        "Use restaurant preferences to pick a place with the fewest conflicts.",
        "Ask each person to confirm walking distance, budget, and any dietary constraints.",
    ]
    return {
        "summary": f"Your agent found {len(collaborators)} likely collaborator(s): {names}.",
        "collaborators": collaborators,
        "next_steps": next_steps,
    }


def _collaboration_goal(profile: dict, collaborators: list[dict]) -> str:
    goals = [profile.get("goal", "")]
    goals.extend(post.get("goal", "") for post in collaborators)
    preferences = [profile.get("restaurant_preferences", "")]
    preferences.extend(post.get("restaurant_preferences", "") for post in collaborators)
    return (
        "Coordinate a Dallas dinner plan for conference attendees. "
        f"Goals: {' | '.join(item for item in goals if item)}. "
        f"Restaurant preferences: {' | '.join(item for item in preferences if item)}."
    )


def _build_collaboration_venue_plan(profile: dict, collaborators: list[dict], context: dict | None = None) -> dict:
    goal = _collaboration_goal(profile, collaborators)
    tool_context = {"hotel_location": (context or {}).get("hotel_location") or DEFAULT_HOTEL_LOCATION}
    restaurants = restaurant_finder(goal, [], tool_context)
    events = event_finder(goal, [], tool_context)
    ranked_restaurants = sorted(
        restaurants.get("restaurants", []),
        key=lambda item: (
            item.get("price_level", 9) > 2,
            not item.get("good_for_groups", False),
            item.get("walk_minutes", 999),
            item.get("price_level", 9),
        ),
    )
    return {
        "restaurants": ranked_restaurants[:3],
        "restaurant_source": restaurants.get("source", "Unknown source"),
        "restaurant_search_center": restaurants.get("search_center", tool_context["hotel_location"]),
        "restaurant_live": restaurants.get("live", False),
        "restaurant_error": restaurants.get("error"),
        "events": events.get("events", [])[:3],
        "event_source": events.get("source", "Unknown source"),
        "event_search_center": events.get("search_center", tool_context["hotel_location"]),
        "event_live": events.get("live", False),
        "event_error": events.get("error"),
    }


def _restaurant_line(restaurant: dict) -> str:
    details = [
        restaurant.get("cuisine", "Restaurant"),
        restaurant.get("estimated_cost", "cost TBD"),
        f"{restaurant.get('walk_minutes', '?')} min walk",
    ]
    return f"{restaurant.get('name', 'Dinner option')} ({', '.join(details)})"


def _event_line(event: dict) -> str:
    details = [event.get("time"), event.get("venue_type") or event.get("type"), event.get("address")]
    detail_text = ", ".join(str(item) for item in details if item)
    if detail_text:
        return f"{event.get('name', 'After-dinner option')} ({detail_text})"
    return event.get("name", "After-dinner option")


def _build_group_message(profile: dict, collaboration: dict) -> str:
    collaborators = collaboration.get("collaborators") or []
    names = [profile.get("name", "An agent")]
    for collaborator in collaborators:
        if isinstance(collaborator, dict):
            names.append(collaborator.get("name", "another participant"))
        else:
            names.append(str(collaborator))

    lines = [
        f"{AGENT_LAB_COLLAB_MARKER} **{profile.get('name', 'An agent')} found a possible dinner group.**",
        collaboration.get("summary", "A few participants may be good collaborators."),
        f"Group: {', '.join(name for name in names if name)}",
    ]

    restaurants = collaboration.get("restaurants") or []
    if restaurants:
        lines.append("Dinner options:")
        for restaurant in restaurants[:2]:
            lines.append(f"- {_restaurant_line(restaurant)}")

    events = collaboration.get("events") or []
    if events:
        lines.append("After-dinner options:")
        for event in events[:2]:
            lines.append(f"- {_event_line(event)}")

    next_steps = collaboration.get("next_steps") or []
    if next_steps:
        lines.append("Next steps:")
        for step in next_steps[:3]:
            lines.append(f"- {step}")

    return _truncate_for_discord("\n".join(lines))


def synthesize_agent_collaboration(profile: dict, posts: list[dict], context: dict | None = None) -> dict:
    api_key = (context or {}).get("openai_api_key") or os.getenv("OPENAI_API_KEY")
    model = (context or {}).get("openai_model") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    base = _deterministic_collaboration(profile, posts)
    venue_plan = _build_collaboration_venue_plan(profile, base.get("collaborators", []), context)
    if not api_key or not posts:
        collaboration = {**base, **venue_plan, "mode": "deterministic"}
        return {**collaboration, "group_message": _build_group_message(profile, collaboration)}

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(
            model=model,
            instructions=(
                "You are coordinating conference attendee agents. "
                "Use only the provided participant posts and venue options. "
                "Return JSON only with this shape: "
                '{"summary":"short recommendation","collaborators":[{"name":"name","reason":"why"}],"next_steps":["step"]}. '
                "Prefer concrete, friendly collaboration steps that mention the best dinner and after-dinner option names."
            ),
            input=(
                f"Current participant:\n{json.dumps(profile, indent=2)}\n\n"
                f"Visible agent posts:\n{json.dumps(posts[:10], indent=2)}\n\n"
                f"Venue options:\n{json.dumps(venue_plan, indent=2)}"
            ),
        )
        payload = _coerce_json(response.output_text)
    except Exception:
        collaboration = {**base, **venue_plan, "mode": "deterministic fallback"}
        return {**collaboration, "group_message": _build_group_message(profile, collaboration)}

    collaboration = {
        "summary": payload.get("summary") or base["summary"],
        "collaborators": payload.get("collaborators") or base["collaborators"],
        "next_steps": payload.get("next_steps") or base["next_steps"],
        **venue_plan,
        "mode": "LLM Mode",
    }
    return {**collaboration, "group_message": _build_group_message(profile, collaboration)}


def _recent_outbound_message(messages: list[dict], sender_participant_id: str, marker: str, group_signature: str) -> dict | None:
    for message in messages:
        if (
            message.get("sender_participant_id") == sender_participant_id
            and message.get("marker") == marker
            and message.get("group_signature") == group_signature
        ):
            return message
    return None


def _is_within_cooldown(message: dict | None, cooldown_seconds: int = NEGOTIATION_MESSAGE_COOLDOWN_SECONDS) -> bool:
    if not message:
        return False
    timestamp = _parse_timestamp(message.get("discord_timestamp")) or _parse_timestamp(message.get("sent_at"))
    if timestamp is None:
        return False
    return (datetime.now(timezone.utc) - timestamp).total_seconds() < cooldown_seconds


def _message_is_relevant_to_group(message: dict, current_participant_id: str, collaborator_ids: set[str], group_signature: str) -> bool:
    if message.get("group_signature") != group_signature:
        return False
    if message.get("sender_participant_id") == current_participant_id:
        return True

    target_ids = set(message.get("target_participant_ids") or [])
    if not target_ids:
        return True
    return current_participant_id in target_ids or bool(target_ids & collaborator_ids)


def run_agent_negotiation_cycle(
    profile: dict,
    context: dict | None = None,
    state: dict | None = None,
    oldest_lookback_timestamp: str | datetime | None = None,
) -> dict:
    previous_state = dict(state or {})
    diplomacy = profile.get("diplomacy_preferences") or {}
    follow_up_control = diplomacy.get("follow_up_control", FOLLOW_UP_CONTROL_BALANCED)
    posts_result = listen_for_agent_posts(
        profile.get("participant_id"),
        oldest_lookback_timestamp=oldest_lookback_timestamp,
    )
    if not posts_result.get("discord", {}).get("fetched"):
        reason = posts_result.get("discord", {}).get("reason") or "Discord message fetch failed."
        return {
            "status": "discord_error",
            "summary": f"Discord is unavailable, so agent coordination cannot continue. Reason: {reason}",
            "visible_agent_posts": [],
            "discussion_messages": [],
            "collaboration": None,
            "candidate_plan": None,
            "follow_up_questions": [],
            "activity": [f"Discord post lookup failed: {reason}"],
            "state": {"status": "discord_error", "force_new_round": False},
            "listen_result": posts_result,
            "message_result": None,
        }
    visible_posts = posts_result.get("posts", [])
    ranked_posts = sorted(visible_posts, key=lambda post: _overlap_score(profile, post), reverse=True)
    collaborators = ranked_posts[:3]

    message_result = listen_for_agent_messages(
        profile.get("participant_id"),
        oldest_lookback_timestamp=oldest_lookback_timestamp,
    )
    if not message_result.get("discord", {}).get("fetched"):
        reason = message_result.get("discord", {}).get("reason") or "Discord discussion fetch failed."
        return {
            "status": "discord_error",
            "summary": f"Discord is unavailable, so agent coordination cannot continue. Reason: {reason}",
            "visible_agent_posts": visible_posts,
            "discussion_messages": [],
            "collaboration": None,
            "candidate_plan": None,
            "follow_up_questions": [],
            "activity": [f"Discord discussion lookup failed: {reason}"],
            "state": {"status": "discord_error", "force_new_round": False},
            "listen_result": posts_result,
            "message_result": message_result,
        }
    all_messages = message_result.get("messages", [])

    if not collaborators:
        return {
            "status": "waiting_for_agents",
            "summary": "Your agent is monitoring the channel and waiting for another participant agent to appear.",
            "visible_agent_posts": visible_posts,
            "discussion_messages": [],
            "collaboration": None,
            "candidate_plan": None,
            "follow_up_questions": [],
            "activity": ["Monitoring the channel for a compatible collaborator."],
            "state": {"status": "waiting_for_agents"},
            "listen_result": posts_result,
            "message_result": message_result,
        }

    collaboration = synthesize_agent_collaboration(profile, collaborators, context=context)
    group_signature = _group_signature(profile, collaborators)
    collaborator_ids = {_participant_key(post) for post in collaborators if _participant_key(post)}
    relevant_messages = [
        message
        for message in all_messages
        if _message_is_relevant_to_group(message, profile.get("participant_id", ""), collaborator_ids, group_signature)
    ]
    incoming_messages = [
        message for message in relevant_messages if message.get("sender_participant_id") != profile.get("participant_id")
    ]
    follow_up_questions = _derive_human_follow_up_questions(
        profile,
        incoming_messages,
        collaboration=collaboration,
        collaborators=collaborators,
    )
    activity: list[str] = [f"Tracking a possible group with {', '.join(_names_from_posts(collaborators))}."]

    should_force_round = bool(previous_state.get("force_new_round"))
    proposal_ready = bool(incoming_messages) or len(collaborators) >= 2
    recent_discussion = _recent_outbound_message(
        relevant_messages,
        profile.get("participant_id", ""),
        AGENT_LAB_DISCUSSION_MARKER,
        group_signature,
    )
    pending_agent_follow_up = None
    if not proposal_ready and (should_force_round or not _is_within_cooldown(recent_discussion)):
        outbound_questions = [
            "Please confirm your human's dietary needs, budget ceiling, and comfortable walking distance."
        ]
        if follow_up_control == FOLLOW_UP_CONTROL_APPROVAL_REQUIRED:
            pending_agent_follow_up = {
                "collaborators": collaborators,
                "questions": outbound_questions,
                "summary": "Your current diplomacy setting requires your approval before I send another follow-up to the other agents.",
            }
            activity.append("Prepared an agent follow-up and paused until the human approves sending it.")
        else:
            discussion_post = post_agent_discussion_message(profile, collaboration, collaborators, questions=outbound_questions)
            if discussion_post.get("sent") and discussion_post.get("local_message"):
                activity.append("Posted a discussion update so the other agents can compare constraints and preferences.")
                relevant_messages = [discussion_post["local_message"], *relevant_messages]
            else:
                reason = discussion_post.get("discord", {}).get("reason") or "Discord send failed."
                return {
                    "status": "discord_error",
                    "summary": f"Discord is unavailable, so the agent could not continue the negotiation. Reason: {reason}",
                    "visible_agent_posts": visible_posts,
                    "discussion_messages": relevant_messages[:8],
                    "collaboration": collaboration,
                    "candidate_plan": None,
                    "follow_up_questions": [],
                    "pending_agent_follow_up": None,
                    "activity": [*activity, f"Discord discussion send failed: {reason}"],
                    "state": {"status": "discord_error", "group_signature": group_signature, "force_new_round": False},
                    "listen_result": posts_result,
                    "message_result": message_result,
                }

    status = "monitoring"
    candidate_plan = None
    summary = "Your agent is still discussing options with nearby agents."

    if pending_agent_follow_up:
        status = "needs_human_input"
        summary = pending_agent_follow_up["summary"]
    elif follow_up_questions:
        status = "needs_human_input"
        summary = "Another agent needs a little more information before this group can lock a plan."
    elif proposal_ready:
        status = "proposal_ready"
        summary = "The agents have enough overlap to bring you a draft plan for approval."
        candidate_plan = collaboration
    else:
        activity.append("Waiting for at least one other agent to respond before surfacing a plan.")

    return {
        "status": status,
        "summary": summary,
        "visible_agent_posts": visible_posts,
        "discussion_messages": relevant_messages[:8],
        "collaboration": collaboration,
        "candidate_plan": candidate_plan,
        "follow_up_questions": follow_up_questions,
        "pending_agent_follow_up": pending_agent_follow_up,
        "activity": activity,
        "state": {
            "status": status,
            "group_signature": group_signature,
            "force_new_round": False,
            "pending_agent_follow_up": pending_agent_follow_up,
        },
        "listen_result": posts_result,
        "message_result": message_result,
    }


def post_collaboration_reply(profile: dict, collaboration: dict) -> dict:
    message = collaboration.get("group_message") or _build_group_message(profile, collaboration)
    return _send_discord_message(message)


def discord_message_sender(goal: str, history: list[dict], context: dict | None = None) -> dict:
    final_message = (context or {}).get("final_message")
    if isinstance(final_message, str) and final_message.strip():
        message = final_message.strip()
    else:
        message = _build_message_summary(goal, history)
    result = _send_discord_message(message)
    result["goal_excerpt"] = goal.strip()[:140]
    return result


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
    "conversation_starter": {
        "label": "Conversation Starter",
        "description": "Generate networking openers from inferred BCBS Plan or FEP connections.",
        "fn": conversation_starter,
    },
    "event_finder": {
        "label": "Event Finder",
        "description": "Suggest a nearby after-dinner stop or live event.",
        "fn": event_finder,
    },
    "discord_message_sender": {
        "label": "Discord Message Sender",
        "description": "Send a Discord channel message after the agent builds a plan.",
        "fn": discord_message_sender,
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
