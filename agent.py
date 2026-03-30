from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from openai import OpenAI

from prompts import (
    FINAL_PLAN_TEMPLATE,
    LLM_FINAL_INSTRUCTIONS,
    LLM_PLANNER_INSTRUCTIONS,
    TOOL_ORDER_HINTS,
    TOOL_REASON_TEMPLATES,
)
from tools import TOOL_DEFINITIONS, get_tool_catalog


@dataclass
class ToolDecision:
    tool: str
    reason: str


def _goal_text(goal: str) -> str:
    return goal.strip().lower()


def _tool_needed(goal: str, tool_name: str) -> bool:
    text = _goal_text(goal)

    keyword_rules: dict[str, tuple[str, ...]] = {
        "weather_tool": ("weather", "rain", "outdoor", "inside", "indoor"),
        "budget_filter": ("budget", "$", "cheap", "afford", "under", "cost"),
        "distance_filter": ("walk", "walking", "near", "distance", "close"),
        "attendee_lookup": (
            "network",
            "people",
            "conference",
            "attendee",
            "socialize",
            "meet",
        ),
        "conversation_starter": (
            "conversation",
            "socialize",
            "network",
            "meet",
            "people",
        ),
        "event_finder": ("event", "music", "show", "after dinner", "nightlife"),
        "restaurant_finder": ("dinner", "food", "restaurant", "eat", "night"),
    }

    keywords = keyword_rules.get(tool_name, ())
    return any(keyword in text for keyword in keywords)


def _build_plan(goal: str, enabled_tools: list[str]) -> list[ToolDecision]:
    plan: list[ToolDecision] = []

    for tool_name in TOOL_ORDER_HINTS:
        if tool_name not in enabled_tools:
            continue
        if _tool_needed(goal, tool_name) or tool_name == "restaurant_finder":
            plan.append(
                ToolDecision(
                    tool=tool_name,
                    reason=TOOL_REASON_TEMPLATES[tool_name].format(goal=goal.strip()),
                )
            )

    if not plan:
        fallback_tool = enabled_tools[0]
        plan.append(
            ToolDecision(
                tool=fallback_tool,
                reason=TOOL_REASON_TEMPLATES[fallback_tool].format(goal=goal.strip()),
            )
        )

    return plan[:5]


def _run_tool(tool_name: str, goal: str, history: list[dict]) -> dict:
    tool_fn: Callable[[str, list[dict]], dict] = TOOL_DEFINITIONS[tool_name]["fn"]
    return tool_fn(goal, history)


def _coerce_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def _llm_build_plan(goal: str, enabled_tools: list[str], api_key: str | None, model: str | None) -> list[ToolDecision]:
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    tool_catalog = json.dumps(get_tool_catalog(enabled_tools), indent=2)
    response = client.responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=LLM_PLANNER_INSTRUCTIONS,
        input=(
            f"User goal:\n{goal.strip()}\n\n"
            f"Enabled tools:\n{tool_catalog}\n\n"
            "Return only JSON with this shape: "
            '{"steps":[{"tool":"tool_name","reason":"why this tool should be used next"}]}. '
            "Use 1 to 5 steps and only select tool names from the enabled tools."
        ),
    )
    payload = _coerce_json(response.output_text)

    steps = payload.get("steps", [])
    plan: list[ToolDecision] = []
    for item in steps:
        tool_name = item.get("tool")
        reason = item.get("reason", "").strip()
        if tool_name in enabled_tools and reason:
            plan.append(ToolDecision(tool=tool_name, reason=reason))

    return plan[:5]


def _llm_format_final_answer(
    goal: str,
    history: list[dict],
    api_key: str | None,
    model: str | None,
) -> str:
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    response = client.responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=LLM_FINAL_INSTRUCTIONS,
        input=(
            f"User goal:\n{goal.strip()}\n\n"
            "Tool observations:\n"
            f"{json.dumps(history, indent=2)}\n\n"
            "Write a polished final plan in markdown with a recommendation, people to meet, "
            "conversation starters, and one short explanation of why the plan fits the goal."
        ),
    )
    return response.output_text.strip()


def _format_final_answer(goal: str, history: list[dict]) -> str:
    latest_by_tool = {item["tool"]: item["result"] for item in history}

    restaurants = latest_by_tool.get("restaurant_finder", {}).get("restaurants", [])
    weather = latest_by_tool.get("weather_tool", {}).get("forecast", "Pleasant weather expected.")
    attendees = latest_by_tool.get("attendee_lookup", {}).get("matches", [])
    conversation = latest_by_tool.get("conversation_starter", {}).get("starters", [])
    events = latest_by_tool.get("event_finder", {}).get("events", [])

    top_restaurant = restaurants[0]["name"] if restaurants else "The Rustic"
    top_budget = restaurants[0].get("estimated_cost", "$35") if restaurants else "$35"
    walking_time = restaurants[0].get("walk_minutes", 12) if restaurants else 12

    attendee_lines = []
    for attendee in attendees[:2]:
        attendee_lines.append(
            f"- **{attendee['name']}** ({attendee['organization']}) - {attendee['role']}"
        )
    attendee_block = "\n".join(attendee_lines) if attendee_lines else "- No attendee matches found"

    starter_lines = [f"- {item}" for item in conversation[:3]]
    starter_block = "\n".join(starter_lines) if starter_lines else "- Ask what they are seeing as the biggest AI opportunity in their plan."

    event_lines = [f"- {item['name']} at {item['time']}" for item in events[:2]]
    event_block = "\n".join(event_lines) if event_lines else "- Keep the evening focused on dinner and networking."

    return FINAL_PLAN_TEMPLATE.format(
        goal=goal.strip(),
        weather=weather,
        restaurant=top_restaurant,
        budget=top_budget,
        walking_time=walking_time,
        attendee_block=attendee_block,
        starter_block=starter_block,
        event_block=event_block,
    )


def run_agent(
    goal: str,
    enabled_tools: list[str],
    mode: str = "Demo Mode",
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    history: list[dict] = []
    warning = None

    if mode == "LLM Mode":
        try:
            plan = _llm_build_plan(goal, enabled_tools, api_key=api_key, model=model)
        except Exception as exc:
            plan = _build_plan(goal, enabled_tools)
            warning = f"LLM planning failed, so the app fell back to Demo Mode planning. Details: {exc}"
    else:
        plan = _build_plan(goal, enabled_tools)

    for step_number, decision in enumerate(plan, start=1):
        result = _run_tool(decision.tool, goal, history)
        history.append(
            {
                "step": step_number,
                "tool": decision.tool,
                "tool_label": TOOL_DEFINITIONS[decision.tool]["label"],
                "reason": decision.reason,
                "result": result,
            }
        )

    mode_used = mode
    if mode == "LLM Mode":
        try:
            final = _llm_format_final_answer(goal, history, api_key=api_key, model=model)
        except Exception as exc:
            final = _format_final_answer(goal, history)
            mode_used = "Demo Mode"
            detail = f"LLM final synthesis failed, so the app used the built-in template instead. Details: {exc}"
            warning = f"{warning}\n\n{detail}" if warning else detail
    else:
        final = _format_final_answer(goal, history)

    return {"history": history, "final": final, "mode_used": mode_used, "warning": warning}
