AGENT_DEFINITION = (
    "An AI agent is a system where an AI model can reason about a goal and take "
    "actions, such as using tools or retrieving information, to achieve it."
)

CONFERENCE_TALK_TRACK = (
    "Simple framing for the room: a chatbot answers questions, while an agent can "
    "take actions to accomplish a goal."
)

TOOL_ORDER_HINTS = [
    "weather_tool",
    "restaurant_finder",
    "conversation_starter",
    "event_finder",
    "discord_message_sender",
]

TOOL_REASON_TEMPLATES = {
    "weather_tool": "Step 1: Check whether the Dallas weather supports the kind of evening described in '{goal}'.",
    "restaurant_finder": "Find dinner options that could support the goal: '{goal}'.",
    "conversation_starter": "Prepare a few specific conversation starters so the networking plan feels actionable.",
    "event_finder": "Add an optional after-dinner stop to make the evening feel complete.",
    "discord_message_sender": "If the user wants an action taken or a recap delivered, send a short Discord channel summary after the planning steps.",
}

FINAL_PLAN_TEMPLATE = """
### Recommended Evening

**Goal:** {goal}

**Weather check:** {weather}

**Dinner recommendation:** **{restaurant}**
- Estimated cost: {budget}
- Approximate travel time: about {walking_time} minutes

**People to meet**
{attendee_block}

**Conversation starters**
{starter_block}

**Optional next stop**
{event_block}

### Why the agent chose this
It used the tools you enabled, gathered a few observations, and then refined the plan into something practical for the conference setting.
""".strip()

LLM_PLANNER_INSTRUCTIONS = """
You are planning tool usage for a conference-safe Dallas evening planner agent.
Pick only from the enabled tools provided by the application.
Plan 1 to 5 steps.
Prefer a sensible order: gather context first, then refine, then support networking.
Only use the discord_message_sender after there is enough information in prior tool results to send a useful summary.
Return JSON only. Do not include markdown fences or commentary.
""".strip()

LLM_FINAL_INSTRUCTIONS = """
You are the final presenter-facing voice for a conference-safe agent demo.
Use the tool observations provided by the application.
Do not invent restaurants, attendees, weather, or events beyond those observations.
Write concise markdown that feels polished and useful for a live demo.
""".strip()
