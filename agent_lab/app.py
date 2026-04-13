from __future__ import annotations

import os
import uuid

import streamlit as st

from tools import (
    get_discord_oldest_lookback_timestamp,
    post_collaboration_reply,
    post_agent_discussion_message,
    publish_agent_post,
    run_agent_negotiation_cycle,
    run_agent_negotiation_cycle_stream,
)


AGENT_LOOP_INTERVAL_SECONDS = 10


st.set_page_config(
    page_title="Build Your Dallas Agent",
    page_icon=":robot_face:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def init_state() -> None:
    defaults = {
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "participant_id": str(uuid.uuid4()),
        "participant_name": "",
        "bcbs_plan": "",
        "job_title": "",
        "restaurant_preferences": "",
        "done_for_day_time": "",
        "agent_intent": (
            "Find a dinner group in Dallas where I can meet useful peers, "
            "compare AI agent ideas, and land on a restaurant that works for the group."
        ),
        "visible_agent_posts": [],
        "discussion_messages": [],
        "candidate_plan": None,
        "agent_monitoring_active": False,
        "agent_status": "idle",
        "agent_summary": "Your agent is waiting to be launched.",
        "agent_activity": [],
        "follow_up_questions": [],
        "pending_agent_follow_up": None,
        "agent_chat_messages": [],
        "agent_chat_notes": [],
        "agent_chat_seen_keys": [],
        "last_agent_summary_seen": "",
        "last_publish_result": None,
        "last_plan_result": None,
        "negotiation_state": {},
        "last_cycle_result": None,
        "agent_plan_flexibility": "balanced",
        "agent_follow_up_control": "balanced",
        "profile_editor_open": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def runtime_settings() -> tuple[str, str]:
    return st.session_state.openai_api_key, st.session_state.openai_model


def _discord_reason(payload: dict | None) -> str:
    data = payload or {}
    return data.get("reason") or data.get("error") or "Unknown Discord error."


def _goal_with_chat_context() -> str:
    goal = st.session_state.agent_intent.strip()
    notes = [note.strip() for note in st.session_state.agent_chat_notes if note.strip()]
    if not notes:
        return goal
    note_block = "\n".join(f"- {note}" for note in notes[-6:])
    return f"{goal}\n\nAdditional guidance from the human in chat:\n{note_block}"


def current_profile() -> dict:
    return {
        "participant_id": st.session_state.participant_id,
        "name": st.session_state.participant_name.strip() or "Anonymous",
        "bcbs_plan": st.session_state.bcbs_plan.strip() or "Unknown BCBS Plan",
        "job_title": st.session_state.job_title.strip() or "Conference participant",
        "restaurant_preferences": st.session_state.restaurant_preferences.strip(),
        "done_for_day_time": st.session_state.done_for_day_time.strip(),
        "goal": _goal_with_chat_context(),
        "diplomacy_preferences": {
            "plan_flexibility": st.session_state.agent_plan_flexibility,
            "follow_up_control": st.session_state.agent_follow_up_control,
        },
    }


def profile_can_compact() -> bool:
    return bool(st.session_state.participant_name.strip() and st.session_state.agent_intent.strip())


def append_activity(lines: list[str]) -> None:
    for line in lines:
        if line:
            st.session_state.agent_activity.append(line)
    st.session_state.agent_activity = st.session_state.agent_activity[-12:]


def append_chat_message(role: str, content: str) -> None:
    message = content.strip()
    if not message:
        return
    st.session_state.agent_chat_messages.append({"role": role, "content": message})
    st.session_state.agent_chat_messages = st.session_state.agent_chat_messages[-40:]


def _remember_chat_message(key: str, content: str) -> None:
    if key in st.session_state.agent_chat_seen_keys:
        return
    st.session_state.agent_chat_seen_keys.append(key)
    st.session_state.agent_chat_seen_keys = st.session_state.agent_chat_seen_keys[-80:]
    append_chat_message("assistant", content)


def _friendly_summary_message(status: str, summary: str) -> str:
    if status == "discord_error":
        return f"I hit a Discord problem and cannot continue until it is fixed. {summary}"
    if status == "needs_human_input":
        return f"I am close, but I need one more bit of guidance from you. {summary}"
    if status == "proposal_ready":
        return f"I have a draft evening plan ready for you to look at. {summary}"
    if status == "approved":
        return f"Nice, we are set. {summary}"
    if status == "paused":
        return "I am paused for the moment. When you are ready, relaunch me and I will pick things back up."
    if status == "waiting_for_agents":
        return "I am watching the room for a good match and will let you know as soon as another compatible agent shows up."
    return f"I am working on it. {summary}"


def _friendly_activity_message(line: str) -> str:
    activity_map = {
        "Published this human's intent and started monitoring the agent channel.": (
            "I introduced us to the room and started listening for good dinner matches."
        ),
        "Republished your latest profile and sent the agent back to negotiate.": (
            "I just jumped back into the conversation with your updated preferences."
        ),
        "Human approved the draft plan and the agent posted it to the group channel.": (
            "I shared the approved plan with the group so everyone is aligned."
        ),
        "Captured new guidance from the human in chat.": (
            "I noted your latest guidance and am using it as I refine the plan."
        ),
    }
    return activity_map.get(line, f"Quick update: {line}")


def _friendly_question_message(question: str) -> str:
    return f"Help me steer this a bit: {question}"


def sync_agent_chat_state() -> None:
    summary = st.session_state.agent_summary.strip()
    status = st.session_state.agent_status
    if summary and summary != st.session_state.last_agent_summary_seen:
        append_chat_message("assistant", _friendly_summary_message(status, summary))
        st.session_state.last_agent_summary_seen = summary

    for line in st.session_state.agent_activity:
        _remember_chat_message(f"activity::{line}", _friendly_activity_message(line))

    for question in st.session_state.follow_up_questions:
        _remember_chat_message(f"question::{question}", _friendly_question_message(question))


def reset_agent_chat() -> None:
    st.session_state.agent_chat_messages = []
    st.session_state.agent_chat_notes = []
    st.session_state.agent_chat_seen_keys = []
    st.session_state.last_agent_summary_seen = ""


def _render_status_banner(target) -> None:
    status = st.session_state.agent_status
    summary = st.session_state.agent_summary
    with target.container():
        if status == "proposal_ready":
            st.success(summary)
        elif status == "needs_human_input":
            st.warning(summary)
        elif status == "discord_error":
            st.error(summary)
        else:
            st.info(summary)


def _render_chat_history(target) -> None:
    with target.container():
        if not st.session_state.agent_chat_messages:
            st.caption("Launch the agent and this space will turn into a live conversation with status updates and follow-up questions.")
            return
        for message in st.session_state.agent_chat_messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])


def _apply_cycle_result(result: dict) -> None:
    st.session_state.last_cycle_result = result
    st.session_state.visible_agent_posts = result.get("visible_agent_posts", [])
    st.session_state.discussion_messages = result.get("discussion_messages", [])
    st.session_state.follow_up_questions = result.get("follow_up_questions", [])
    st.session_state.pending_agent_follow_up = result.get("pending_agent_follow_up")
    st.session_state.agent_status = result.get("status", "idle")
    st.session_state.agent_summary = result.get("summary", "")
    st.session_state.negotiation_state = result.get("state", {})

    candidate_plan = result.get("candidate_plan")
    if candidate_plan:
        st.session_state.candidate_plan = candidate_plan
    elif result.get("status") != "proposal_ready":
        st.session_state.candidate_plan = None

    append_activity(result.get("activity", []))
    sync_agent_chat_state()


def run_cycle(
    profile: dict,
    api_key: str,
    model: str,
    *,
    stream_updates: bool = False,
    status_placeholder=None,
    chat_placeholder=None,
) -> None:
    if not stream_updates:
        result = run_agent_negotiation_cycle(
            profile,
            context={"openai_api_key": api_key or None, "openai_model": model or None},
            state=st.session_state.negotiation_state,
            oldest_lookback_timestamp=get_discord_oldest_lookback_timestamp(),
        )
        _apply_cycle_result(result)
        return

    final_result: dict | None = None
    for event in run_agent_negotiation_cycle_stream(
        profile,
        context={"openai_api_key": api_key or None, "openai_model": model or None},
        state=st.session_state.negotiation_state,
        oldest_lookback_timestamp=get_discord_oldest_lookback_timestamp(),
    ):
        if event.get("type") == "status":
            append_chat_message("assistant", event.get("message", ""))
            if chat_placeholder is not None:
                _render_chat_history(chat_placeholder)
            if status_placeholder is not None:
                with status_placeholder.container():
                    st.info(event.get("message", ""))
        elif event.get("type") == "done":
            final_result = event.get("result")

    if final_result is not None:
        _apply_cycle_result(final_result)
        if chat_placeholder is not None:
            _render_chat_history(chat_placeholder)
        if status_placeholder is not None:
            _render_status_banner(status_placeholder)


def launch_agent(profile: dict, api_key: str, model: str, *, status_placeholder=None, chat_placeholder=None) -> None:
    st.session_state.profile_editor_open = False
    reset_agent_chat()
    append_chat_message("assistant", "Launching your agent now. First I am publishing your intent to the room.")
    if chat_placeholder is not None:
        _render_chat_history(chat_placeholder)
    if status_placeholder is not None:
        with status_placeholder.container():
            st.info("Publishing your intent to the shared agent room.")
    st.session_state.last_publish_result = publish_agent_post(profile, profile.get("goal", st.session_state.agent_intent))
    publish_discord = st.session_state.last_publish_result.get("discord", {})
    if not publish_discord.get("sent"):
        st.session_state.agent_monitoring_active = False
        st.session_state.agent_status = "discord_error"
        st.session_state.agent_summary = f"Your agent could not publish to Discord. Reason: {_discord_reason(publish_discord)}"
        st.session_state.candidate_plan = None
        st.session_state.follow_up_questions = []
        st.session_state.pending_agent_follow_up = None
        st.session_state.negotiation_state = {}
        append_activity([f"Discord publish failed: {_discord_reason(publish_discord)}"])
        sync_agent_chat_state()
        if chat_placeholder is not None:
            _render_chat_history(chat_placeholder)
        if status_placeholder is not None:
            _render_status_banner(status_placeholder)
        return
    st.session_state.agent_monitoring_active = True
    st.session_state.agent_status = "monitoring"
    st.session_state.agent_summary = "Your agent posted its intent and started monitoring the shared chat."
    st.session_state.candidate_plan = None
    st.session_state.follow_up_questions = []
    st.session_state.pending_agent_follow_up = None
    st.session_state.negotiation_state = {}
    append_activity(["Published this human's intent and started monitoring the agent channel."])
    sync_agent_chat_state()
    if chat_placeholder is not None:
        _render_chat_history(chat_placeholder)
    run_cycle(
        profile,
        api_key,
        model,
        stream_updates=True,
        status_placeholder=status_placeholder,
        chat_placeholder=chat_placeholder,
    )


def send_back_to_discussion(profile: dict, api_key: str, model: str, *, status_placeholder=None, chat_placeholder=None) -> None:
    st.session_state.profile_editor_open = False
    append_chat_message("assistant", "I am taking your latest guidance back to the other agents now.")
    if chat_placeholder is not None:
        _render_chat_history(chat_placeholder)
    if status_placeholder is not None:
        with status_placeholder.container():
            st.info("Republishing your updated preferences to the room.")
    st.session_state.last_publish_result = publish_agent_post(profile, profile.get("goal", st.session_state.agent_intent))
    publish_discord = st.session_state.last_publish_result.get("discord", {})
    if not publish_discord.get("sent"):
        st.session_state.agent_monitoring_active = False
        st.session_state.agent_status = "discord_error"
        st.session_state.agent_summary = f"Your agent could not republish to Discord. Reason: {_discord_reason(publish_discord)}"
        st.session_state.candidate_plan = None
        st.session_state.pending_agent_follow_up = None
        st.session_state.negotiation_state = {}
        append_activity([f"Discord republish failed: {_discord_reason(publish_discord)}"])
        sync_agent_chat_state()
        if chat_placeholder is not None:
            _render_chat_history(chat_placeholder)
        if status_placeholder is not None:
            _render_status_banner(status_placeholder)
        return
    st.session_state.agent_monitoring_active = True
    st.session_state.agent_status = "monitoring"
    st.session_state.agent_summary = "Your agent is back in the discussion with your latest preferences."
    st.session_state.candidate_plan = None
    st.session_state.pending_agent_follow_up = None
    st.session_state.negotiation_state = {"force_new_round": True}
    append_activity(["Republished your latest profile and sent the agent back to negotiate."])
    sync_agent_chat_state()
    if chat_placeholder is not None:
        _render_chat_history(chat_placeholder)
    run_cycle(
        profile,
        api_key,
        model,
        stream_updates=True,
        status_placeholder=status_placeholder,
        chat_placeholder=chat_placeholder,
    )


def accept_plan(profile: dict) -> None:
    plan = st.session_state.candidate_plan
    if not plan:
        return
    st.session_state.last_plan_result = post_collaboration_reply(profile, plan)
    if st.session_state.last_plan_result.get("sent"):
        st.session_state.agent_monitoring_active = False
        st.session_state.agent_status = "approved"
        st.session_state.agent_summary = "You approved the draft, and your agent sent the plan back to the group."
        append_activity(["Human approved the draft plan and the agent posted it to the group channel."])
    else:
        reason = _discord_reason(st.session_state.last_plan_result)
        st.session_state.agent_monitoring_active = False
        st.session_state.agent_status = "discord_error"
        st.session_state.agent_summary = f"The plan could not be posted to Discord. Reason: {reason}"
        append_activity([f"Discord plan post failed: {reason}"])
    sync_agent_chat_state()


def approve_agent_follow_up(profile: dict) -> None:
    pending = st.session_state.pending_agent_follow_up
    if not pending:
        return
    result = post_agent_discussion_message(
        profile,
        st.session_state.last_cycle_result.get("collaboration", {}),
        pending.get("collaborators", []),
        questions=pending.get("questions"),
    )
    if not result.get("sent"):
        reason = _discord_reason(result.get("discord", {}))
        st.session_state.pending_agent_follow_up = pending
        st.session_state.agent_monitoring_active = False
        st.session_state.agent_status = "discord_error"
        st.session_state.agent_summary = f"The follow-up could not be sent to Discord. Reason: {reason}"
        append_activity([f"Discord follow-up send failed: {reason}"])
        sync_agent_chat_state()
        return
    st.session_state.pending_agent_follow_up = None
    st.session_state.negotiation_state = {"force_new_round": False}
    st.session_state.agent_monitoring_active = True
    st.session_state.agent_status = "monitoring"
    st.session_state.agent_summary = "Your agent sent the approved follow-up and is waiting for more agent replies."
    append_activity(["Human approved an agent-to-agent follow-up message."])
    sync_agent_chat_state()


def render_header() -> None:
    st.title("Build Your Dallas Agent")
    st.write(
        "Each participant gets a personal agent that can watch the shared chat, talk to other agents, "
        "check back with its human when needed, and surface a draft dinner plan for approval."
    )


def render_profile_setup() -> dict:
    st.subheader("Human Profile")
    if profile_can_compact() and not st.session_state.profile_editor_open:
        profile = current_profile()
        left, right = st.columns([4, 1])
        with left:
            st.markdown("**Profile summary**")
            summary_bits = [
                profile.get("bcbs_plan"),
                profile.get("job_title"),
                profile.get("done_for_day_time") and f"Done around {profile.get('done_for_day_time')}",
            ]
            st.caption(" | ".join(bit for bit in summary_bits if bit))
            if profile.get("restaurant_preferences"):
                st.write(f"**Food:** {profile['restaurant_preferences']}")
            st.write(f"**Tonight:** {st.session_state.agent_intent.strip()}")
            st.caption(
                "Your full profile is saved. Open edit mode anytime if you want to adjust details."
            )
        with right:
            if st.button("Edit Profile", use_container_width=True):
                st.session_state.profile_editor_open = True
                st.rerun()
        return profile

    st.text_input("Your name", key="participant_name", placeholder="Alex Lee")
    st.text_input("BCBS Plan", key="bcbs_plan", placeholder="Independence Blue Cross")
    st.text_input("Job title", key="job_title", placeholder="Director, Product Operations")
    st.caption("Share whatever you know. It is completely fine to type `I don't know` and let your agent narrow things down with follow-up questions.")
    st.text_area(
        "Food preferences or constraints",
        key="restaurant_preferences",
        height=90,
        placeholder=(
            "Examples: vegetarian-friendly, not too loud, under $50, quick dinner, "
            "easy walk, good cocktails, or \"I don't know yet\""
        ),
    )
    st.text_input(
        "What time are you done for the day?",
        key="done_for_day_time",
        placeholder="Around 6:30 PM",
        help="This helps your agent suggest plans that fit your evening window.",
    )
    st.text_area(
        "What sounds good tonight?",
        key="agent_intent",
        height=120,
        placeholder=(
            "Examples: meet product people over dinner, find a small group after the keynote, "
            "grab something casual before heading up, or \"I don't know yet, help me choose.\""
        ),
    )
    st.markdown("**Diplomacy personality**")
    st.select_slider(
        "How flexible should your agent be when details are still fuzzy?",
        options=["structured", "balanced", "flexible"],
        format_func=lambda value: {
            "structured": "Structured",
            "balanced": "Balanced",
            "flexible": "Flexible",
        }[value],
        key="agent_plan_flexibility",
        help="Structured agents ask more clarifying questions. Flexible agents make more reasonable assumptions and keep momentum.",
    )
    st.radio(
        "How much freedom should your agent have in follow-up conversations with other agents?",
        options=["balanced", "autonomous", "approval_required"],
        format_func=lambda value: {
            "balanced": "Balanced",
            "autonomous": "Autonomous",
            "approval_required": "Require my approval for each follow-up",
        }[value],
        key="agent_follow_up_control",
        help="This only affects agent-to-agent follow-ups. Final plan approval still stays with you.",
    )
    profile = current_profile()
    helpful_details = [
        label
        for label, value in (
            ("name", st.session_state.participant_name.strip()),
            ("BCBS Plan", st.session_state.bcbs_plan.strip()),
            ("job title", st.session_state.job_title.strip()),
            ("restaurant preferences", st.session_state.restaurant_preferences.strip()),
            ("done-for-the-day time", st.session_state.done_for_day_time.strip()),
        )
        if not value
    ]
    if helpful_details:
        st.caption(f"Optional details that help your agent negotiate faster: {', '.join(helpful_details)}.")
    if profile_can_compact():
        if st.button("Show Profile Summary", use_container_width=True):
            st.session_state.profile_editor_open = False
            st.rerun()
    return profile


def render_publish_status() -> None:
    publish_result = st.session_state.last_publish_result
    if not publish_result:
        return

    discord_result = publish_result.get("discord", {})
    if discord_result.get("sent"):
        st.caption(f"Latest agent post sent to Discord as message `{discord_result.get('message_id')}`.")
    elif discord_result.get("setup_required"):
        st.error(f"Discord is required for agent coordination. {_discord_reason(discord_result)}")
    elif discord_result.get("error"):
        st.error(f"Discord send failed: {_discord_reason(discord_result)}")

    with st.expander("Latest Intent Message"):
        st.text(publish_result.get("message_preview", ""))


def render_collaboration_options(collaboration: dict) -> None:
    restaurants = collaboration.get("restaurants") or []
    events = collaboration.get("events") or []
    restaurant_error = collaboration.get("restaurant_error")
    event_error = collaboration.get("event_error")
    proximity_priority = bool(collaboration.get("proximity_priority"))

    if restaurants:
        st.markdown("**Dinner options**")
        for restaurant in restaurants:
            detail_parts = [
                restaurant.get("cuisine", "Restaurant"),
                restaurant.get("estimated_cost", "cost TBD"),
            ]
            if proximity_priority:
                detail_parts.append(f"{restaurant.get('walk_minutes', '?')} min from hotel")
            details = " | ".join(detail_parts)
            st.write(f"- **{restaurant.get('name', 'Dinner option')}** - {details}")
        st.caption(
            f"Restaurant source: {collaboration.get('restaurant_source', 'Unknown source')} | "
            f"Search area: {collaboration.get('restaurant_search_center', 'Dallas, TX')}"
        )
    elif restaurant_error:
        st.error(f"Restaurant lookup failed: {restaurant_error}")

    if events:
        st.markdown("**After-dinner options**")
        for event in events:
            details = [event.get("venue_type") or event.get("type"), event.get("address")]
            if proximity_priority:
                details.insert(0, event.get("time"))
            detail_text = " | ".join(str(item) for item in details if item)
            suffix = f" - {detail_text}" if detail_text else ""
            st.write(f"- **{event.get('name', 'After-dinner option')}**{suffix}")
        st.caption(
            f"Event source: {collaboration.get('event_source', 'Unknown source')} | "
            f"Search area: {collaboration.get('event_search_center', 'Dallas, TX')}"
        )
    elif event_error:
        st.error(f"Event lookup failed: {event_error}")

    if collaboration.get("group_message"):
        with st.expander("Approved Message Preview"):
            st.text(collaboration["group_message"])


def render_discussion_messages(messages: list[dict]) -> None:
    st.subheader("Agent Conversation")
    if not messages:
        st.caption("No agent-to-agent discussion is visible yet.")
        return

    for message in messages[:6]:
        with st.container(border=True):
            st.markdown(f"**{message.get('sender_name', 'Unknown agent')}**")
            st.write(message.get("summary", "No summary provided."))
            targets = message.get("target_names") or []
            if targets:
                st.caption(f"Talking with: {', '.join(targets)}")
            for question in message.get("questions") or []:
                st.write(f"- {question}")


def render_agent_chat(profile: dict, api_key: str, model: str, *, status_placeholder=None, chat_placeholder=None) -> None:
    st.markdown("**Chat with your Dallas evening planner**")
    sync_agent_chat_state()
    target = chat_placeholder or st.empty()
    _render_chat_history(target)

    prompt_disabled = not st.session_state.agent_monitoring_active and st.session_state.agent_status not in {
        "needs_human_input",
        "proposal_ready",
    }
    user_reply = st.chat_input(
        "Reply with preferences, constraints, or ask the planner to adjust the plan",
        disabled=prompt_disabled,
    )
    if not user_reply:
        return

    append_chat_message("user", user_reply)
    st.session_state.agent_chat_notes.append(user_reply.strip())
    st.session_state.agent_chat_notes = st.session_state.agent_chat_notes[-12:]
    append_activity(["Captured new guidance from the human in chat."])
    append_chat_message("assistant", "Thanks, that helps. I am folding that into the plan now and going back to the other agents.")
    _render_chat_history(target)
    send_back_to_discussion(
        current_profile(),
        api_key,
        model,
        status_placeholder=status_placeholder,
        chat_placeholder=target,
    )
    st.rerun()


def render_posts(posts: list[dict]) -> None:
    st.subheader("Other Agent Posts")
    if not posts:
        st.caption("No other active agent posts are visible yet.")
        return

    for post in posts:
        with st.container(border=True):
            st.markdown(f"**{post.get('name', 'Anonymous')}**")
            st.write(f"{post.get('bcbs_plan', 'Unknown BCBS Plan')} | {post.get('job_title', 'Conference participant')}")
            if post.get("done_for_day_time"):
                st.caption(f"Done for the day around: {post['done_for_day_time']}")
            if post.get("restaurant_preferences"):
                st.caption(f"Food: {post['restaurant_preferences']}")
            st.write(post.get("goal", "Looking for dinner collaborators."))


def render_agent_console(profile: dict, api_key: str, model: str) -> None:
    st.subheader("2. Agent Console")
    st.caption(
        "The agent watches recent shared chat activity and "
        f"refreshes every {AGENT_LOOP_INTERVAL_SECONDS} seconds while monitoring is active."
    )
    status_placeholder = st.empty()
    chat_placeholder = st.empty()

    can_launch = bool(st.session_state.participant_name.strip() and st.session_state.agent_intent.strip())
    left, right = st.columns(2)
    with left:
        if st.button("Launch Agent", type="primary", use_container_width=True, disabled=not can_launch):
            launch_agent(
                profile,
                api_key,
                model,
                status_placeholder=status_placeholder,
                chat_placeholder=chat_placeholder,
            )
    with right:
        if st.button("Pause Monitoring", use_container_width=True, disabled=not st.session_state.agent_monitoring_active):
            st.session_state.agent_monitoring_active = False
            st.session_state.agent_status = "paused"
            st.session_state.agent_summary = "Monitoring is paused until you relaunch the agent."

    _render_status_banner(status_placeholder)
    render_agent_chat(
        profile,
        api_key,
        model,
        status_placeholder=status_placeholder,
        chat_placeholder=chat_placeholder,
    )

    pending_agent_follow_up = st.session_state.pending_agent_follow_up
    if pending_agent_follow_up:
        st.markdown("**Pending agent follow-up**")
        st.write(pending_agent_follow_up.get("summary", "Your agent is waiting for approval to message other agents again."))
        approve_left, approve_right = st.columns(2)
        with approve_left:
            if st.button("Approve Agent Follow-Up", use_container_width=True):
                approve_agent_follow_up(profile)
                st.rerun()
        with approve_right:
            if st.button("Keep Waiting", use_container_width=True):
                st.session_state.agent_monitoring_active = False
                st.session_state.agent_status = "paused"
                st.session_state.agent_summary = "The agent is holding that follow-up until you choose to send it."
                st.rerun()

    candidate_plan = st.session_state.candidate_plan
    if candidate_plan:
        st.markdown(f"**Draft plan:** {candidate_plan.get('summary', '')}")
        for step in candidate_plan.get("next_steps", []):
            st.write(f"- {step}")
        render_collaboration_options(candidate_plan)

        approve_left, approve_right = st.columns(2)
        with approve_left:
            if st.button("Accept Plan", use_container_width=True):
                accept_plan(profile)
        with approve_right:
            if st.button("Send Agent Back To Discussion", use_container_width=True):
                send_back_to_discussion(
                    profile,
                    api_key,
                    model,
                    status_placeholder=status_placeholder,
                    chat_placeholder=chat_placeholder,
                )

    if st.session_state.last_plan_result:
        plan_result = st.session_state.last_plan_result
        if plan_result.get("sent"):
            st.success("Approved plan posted to the group.")
        elif plan_result.get("setup_required"):
            st.error(f"Approved plan could not be posted. {_discord_reason(plan_result)}")
            st.text(plan_result.get("message_preview", ""))
        elif plan_result.get("error"):
            st.error(f"Plan post failed: {_discord_reason(plan_result)}")

    with st.expander("Recent Agent Activity", expanded=False):
        if not st.session_state.agent_activity:
            st.caption("The agent has not done anything yet.")
        else:
            for line in reversed(st.session_state.agent_activity):
                st.write(f"- {line}")

    render_discussion_messages(st.session_state.discussion_messages)


@st.fragment(run_every=f"{AGENT_LOOP_INTERVAL_SECONDS}s")
def render_agent_monitor(profile: dict, api_key: str, model: str) -> None:
    if st.session_state.agent_monitoring_active:
        run_cycle(profile, api_key, model)


def main() -> None:
    init_state()
    render_header()
    api_key, model = runtime_settings()

    with st.sidebar:
        st.header("Profile")
        profile = render_profile_setup()
        render_publish_status()

    render_agent_console(profile, api_key, model)

    render_agent_monitor(profile, api_key, model)
    render_posts(st.session_state.visible_agent_posts)


if __name__ == "__main__":
    main()
