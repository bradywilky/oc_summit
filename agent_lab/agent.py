from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Iterator

from openai import OpenAI

from prompts import (
    LLM_FINAL_INSTRUCTIONS,
    LLM_PLANNER_INSTRUCTIONS,
)
from tools import TOOL_DEFINITIONS, get_tool_catalog


@dataclass
class ToolDecision:
    tool: str
    reason: str


def _run_tool(tool_name: str, goal: str, history: list[dict], context: dict | None = None) -> dict:
    tool_fn: Callable[[str, list[dict], dict | None], dict] = TOOL_DEFINITIONS[tool_name]["fn"]
    return tool_fn(goal, history, context)


def _goal_requests_message_delivery(goal: str) -> bool:
    normalized = goal.lower()
    delivery_phrases = (
        "send the final plan",
        "send final plan",
        "send the plan",
        "send plan",
        "message me",
        "send me",
        "send it",
        "as a message",
        "to discord",
        "discord",
    )
    return any(phrase in normalized for phrase in delivery_phrases)


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


def _format_conversation_context(conversation_history: list[dict] | None) -> str:
    if not conversation_history:
        return "No prior conversation."

    lines: list[str] = []
    for turn in conversation_history:
        role = turn.get("role", "user").capitalize()
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "No prior conversation."


def _llm_format_final_answer(
    goal: str,
    history: list[dict],
    conversation_history: list[dict] | None,
    api_key: str | None,
    model: str | None,
) -> str:
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    conversation_context = _format_conversation_context(conversation_history)
    response = client.responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=LLM_FINAL_INSTRUCTIONS,
        input=(
            f"User goal:\n{goal.strip()}\n\n"
            f"Conversation so far:\n{conversation_context}\n\n"
            "Tool observations:\n"
            f"{json.dumps(history, indent=2)}\n\n"
            "Write a polished final plan in markdown with a recommendation, people to meet, "
            "conversation starters, and one short explanation of why the plan fits the goal."
        ),
    )
    return response.output_text.strip()


def _prepare_agent_run(
    goal: str,
    api_key: str | None = None,
    model: str | None = None,
    context: dict | None = None,
    conversation_history: list[dict] | None = None,
) -> tuple[list[dict], dict, str]:
    history: list[dict] = []
    tool_context = dict(context or {})
    if api_key or os.getenv("OPENAI_API_KEY"):
        tool_context["openai_api_key"] = api_key or os.getenv("OPENAI_API_KEY")
    if model or os.getenv("OPENAI_MODEL"):
        tool_context["openai_model"] = model or os.getenv("OPENAI_MODEL")
    effective_goal = goal.strip()
    if conversation_history:
        conversation_context = _format_conversation_context(conversation_history)
        effective_goal = (
            "Continue this conversation with awareness of the previous turns.\n\n"
            f"Conversation so far:\n{conversation_context}\n\n"
            f"Latest user request:\n{goal.strip()}"
        )
    return history, tool_context, effective_goal


def run_agent_stream(
    goal: str,
    enabled_tools: list[str],
    api_key: str | None = None,
    model: str | None = None,
    context: dict | None = None,
    conversation_history: list[dict] | None = None,
) -> Iterator[dict]:
    history, tool_context, effective_goal = _prepare_agent_run(
        goal,
        api_key=api_key,
        model=model,
        context=context,
        conversation_history=conversation_history,
    )

    yield {
        "type": "status",
        "phase": "planning",
        "message": "Building the tool plan.",
    }

    try:
        plan = _llm_build_plan(effective_goal, enabled_tools, api_key=api_key, model=model)
    except Exception as exc:
        result = {
            "history": [],
            "final": "The agent could not build a plan because LLM planning failed.",
            "mode_used": "LLM Mode",
            "warning": f"LLM planning failed. Details: {exc}",
        }
        yield {
            "type": "error",
            "phase": "planning",
            "message": result["final"],
            "warning": result["warning"],
        }
        yield {"type": "done", **result}
        return

    should_send_discord = (
        "discord_message_sender" in enabled_tools
        and (
            _goal_requests_message_delivery(effective_goal)
            or any(decision.tool == "discord_message_sender" for decision in plan)
        )
    )
    planning_steps = [decision for decision in plan if decision.tool != "discord_message_sender"]
    yield {
        "type": "plan",
        "steps": [
            {
                "tool": decision.tool,
                "tool_label": TOOL_DEFINITIONS[decision.tool]["label"],
                "reason": decision.reason,
            }
            for decision in planning_steps
        ],
        "will_send_discord": should_send_discord,
    }

    for step_number, decision in enumerate(planning_steps, start=1):
        yield {
            "type": "step_started",
            "step": step_number,
            "tool": decision.tool,
            "tool_label": TOOL_DEFINITIONS[decision.tool]["label"],
            "reason": decision.reason,
        }
        result = _run_tool(decision.tool, effective_goal, history, tool_context)
        step_record = {
            "step": step_number,
            "tool": decision.tool,
            "tool_label": TOOL_DEFINITIONS[decision.tool]["label"],
            "reason": decision.reason,
            "result": result,
        }
        history.append(step_record)
        yield {
            "type": "step_completed",
            **step_record,
        }

    yield {
        "type": "status",
        "phase": "finalizing",
        "message": "Writing the final recommendation.",
    }
    try:
        final = _llm_format_final_answer(
            goal,
            history,
            conversation_history,
            api_key=api_key,
            model=model,
        )
        warning = None
    except Exception as exc:
        final = "The agent completed its tool runs, but LLM final synthesis failed."
        warning = f"LLM final synthesis failed. Details: {exc}"
    yield {
        "type": "final",
        "final": final,
        "warning": warning,
    }

    if should_send_discord:
        delivery_context = dict(tool_context)
        delivery_context["final_message"] = final
        yield {
            "type": "step_started",
            "step": len(history) + 1,
            "tool": "discord_message_sender",
            "tool_label": TOOL_DEFINITIONS["discord_message_sender"]["label"],
            "reason": "Send the final plan as a Discord message because the goal requested message delivery.",
        }
        result = _run_tool("discord_message_sender", effective_goal, history, delivery_context)
        step_record = {
            "step": len(history) + 1,
            "tool": "discord_message_sender",
            "tool_label": TOOL_DEFINITIONS["discord_message_sender"]["label"],
            "reason": "Send the final plan as a Discord message because the goal requested message delivery.",
            "result": result,
        }
        history.append(step_record)
        yield {
            "type": "step_completed",
            **step_record,
        }

    yield {"type": "done", "history": history, "final": final, "mode_used": "LLM Mode", "warning": warning}


def run_agent(
    goal: str,
    enabled_tools: list[str],
    api_key: str | None = None,
    model: str | None = None,
    context: dict | None = None,
    conversation_history: list[dict] | None = None,
) -> dict:
    final_result: dict | None = None
    for event in run_agent_stream(
        goal,
        enabled_tools,
        api_key=api_key,
        model=model,
        context=context,
        conversation_history=conversation_history,
    ):
        if event.get("type") == "done":
            final_result = {
                "history": event.get("history", []),
                "final": event.get("final", ""),
                "mode_used": event.get("mode_used", "LLM Mode"),
                "warning": event.get("warning"),
            }

    if final_result is None:
        return {
            "history": [],
            "final": "The agent stopped before producing a final result.",
            "mode_used": "LLM Mode",
            "warning": "The streaming run finished without a terminal event.",
        }
    return final_result
