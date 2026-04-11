from __future__ import annotations

import os
import uuid

import streamlit as st

from tools import (
    DEFAULT_LISTEN_WINDOW_MINUTES,
    post_collaboration_reply,
    publish_agent_post,
    run_agent_negotiation_cycle,
)


AGENT_LOOP_INTERVAL_SECONDS = 10


st.set_page_config(
    page_title="Build Your Dallas Agent",
    page_icon=":robot_face:",
    layout="wide",
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
        "agent_intent": (
            "Find a dinner group near the conference where I can meet useful peers, "
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
        "last_publish_result": None,
        "last_plan_result": None,
        "negotiation_state": {},
        "last_cycle_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def runtime_settings() -> tuple[str, str]:
    return st.session_state.openai_api_key, st.session_state.openai_model


def current_profile() -> dict:
    return {
        "participant_id": st.session_state.participant_id,
        "name": st.session_state.participant_name.strip() or "Anonymous",
        "bcbs_plan": st.session_state.bcbs_plan.strip() or "Unknown BCBS Plan",
        "job_title": st.session_state.job_title.strip() or "Conference participant",
        "restaurant_preferences": st.session_state.restaurant_preferences.strip(),
        "goal": st.session_state.agent_intent.strip(),
    }


def append_activity(lines: list[str]) -> None:
    for line in lines:
        if line:
            st.session_state.agent_activity.append(line)
    st.session_state.agent_activity = st.session_state.agent_activity[-12:]


def run_cycle(profile: dict, api_key: str, model: str) -> None:
    result = run_agent_negotiation_cycle(
        profile,
        context={"openai_api_key": api_key or None, "openai_model": model or None},
        state=st.session_state.negotiation_state,
    )
    st.session_state.last_cycle_result = result
    st.session_state.visible_agent_posts = result.get("visible_agent_posts", [])
    st.session_state.discussion_messages = result.get("discussion_messages", [])
    st.session_state.follow_up_questions = result.get("follow_up_questions", [])
    st.session_state.agent_status = result.get("status", "idle")
    st.session_state.agent_summary = result.get("summary", "")
    st.session_state.negotiation_state = result.get("state", {})

    candidate_plan = result.get("candidate_plan")
    if candidate_plan:
        st.session_state.candidate_plan = candidate_plan
    elif result.get("status") != "proposal_ready":
        st.session_state.candidate_plan = None

    append_activity(result.get("activity", []))


def launch_agent(profile: dict, api_key: str, model: str) -> None:
    st.session_state.last_publish_result = publish_agent_post(profile, st.session_state.agent_intent)
    st.session_state.agent_monitoring_active = True
    st.session_state.agent_status = "monitoring"
    st.session_state.agent_summary = "Your agent posted its intent and started monitoring the shared chat."
    st.session_state.candidate_plan = None
    st.session_state.follow_up_questions = []
    st.session_state.negotiation_state = {}
    append_activity(["Published this human's intent and started monitoring the agent channel."])
    run_cycle(profile, api_key, model)


def send_back_to_discussion(profile: dict, api_key: str, model: str) -> None:
    st.session_state.last_publish_result = publish_agent_post(profile, st.session_state.agent_intent)
    st.session_state.agent_monitoring_active = True
    st.session_state.agent_status = "monitoring"
    st.session_state.agent_summary = "Your agent is back in the discussion with your latest preferences."
    st.session_state.candidate_plan = None
    st.session_state.negotiation_state = {"force_new_round": True}
    append_activity(["Republished your latest profile and sent the agent back to negotiate."])
    run_cycle(profile, api_key, model)


def accept_plan(profile: dict) -> None:
    plan = st.session_state.candidate_plan
    if not plan:
        return
    st.session_state.last_plan_result = post_collaboration_reply(profile, plan)
    st.session_state.agent_monitoring_active = False
    st.session_state.agent_status = "approved"
    st.session_state.agent_summary = "You approved the draft, and your agent sent the plan back to the group."
    append_activity(["Human approved the draft plan and the agent posted it to the group channel."])


def render_header() -> None:
    st.title("Build Your Dallas Agent")
    st.write(
        "Each participant gets a personal agent that can watch the shared chat, talk to other agents, "
        "check back with its human when needed, and surface a draft dinner plan for approval."
    )


def render_profile_setup() -> dict:
    st.subheader("1. Human Profile")
    st.text_input("Your name", key="participant_name", placeholder="Alex Lee")
    st.text_input("BCBS Plan", key="bcbs_plan", placeholder="Independence Blue Cross")
    st.text_input("Job title", key="job_title", placeholder="Director, Product Operations")
    st.text_area(
        "Restaurant preferences",
        key="restaurant_preferences",
        height=90,
        placeholder="Vegetarian-friendly, under $50, easy walk, good for conversation",
    )
    st.text_area("What do you want to do tonight?", key="agent_intent", height=120)
    profile = current_profile()
    missing = [
        label
        for label, value in (
            ("name", st.session_state.participant_name.strip()),
            ("BCBS Plan", st.session_state.bcbs_plan.strip()),
            ("job title", st.session_state.job_title.strip()),
            ("restaurant preferences", st.session_state.restaurant_preferences.strip()),
        )
        if not value
    ]
    if missing:
        st.caption(f"The agent can still run, but it negotiates better with: {', '.join(missing)}.")
    return profile


def render_publish_status() -> None:
    publish_result = st.session_state.last_publish_result
    if not publish_result:
        return

    discord_result = publish_result.get("discord", {})
    if discord_result.get("sent"):
        st.caption(f"Latest agent post sent to Discord as message `{discord_result.get('message_id')}`.")
    elif discord_result.get("setup_required"):
        st.info("Discord is not configured, so this lab is using the local demo message store.")
    elif discord_result.get("error"):
        st.warning(f"Discord send failed: {discord_result['error']}")

    with st.expander("Latest Intent Message"):
        st.text(publish_result.get("message_preview", ""))


def render_collaboration_options(collaboration: dict) -> None:
    restaurants = collaboration.get("restaurants") or []
    events = collaboration.get("events") or []

    if restaurants:
        st.markdown("**Dinner options**")
        for restaurant in restaurants:
            details = (
                f"{restaurant.get('cuisine', 'Restaurant')} | "
                f"{restaurant.get('estimated_cost', 'cost TBD')} | "
                f"{restaurant.get('walk_minutes', '?')} min walk"
            )
            st.write(f"- **{restaurant.get('name', 'Dinner option')}** - {details}")
        st.caption(
            f"Restaurant source: {collaboration.get('restaurant_source', 'Unknown source')} "
            f"near {collaboration.get('restaurant_search_center', 'the conference area')}"
        )

    if events:
        st.markdown("**After-dinner options**")
        for event in events:
            details = [event.get("time"), event.get("venue_type") or event.get("type"), event.get("address")]
            detail_text = " | ".join(str(item) for item in details if item)
            suffix = f" - {detail_text}" if detail_text else ""
            st.write(f"- **{event.get('name', 'After-dinner option')}**{suffix}")
        st.caption(
            f"Event source: {collaboration.get('event_source', 'Unknown source')} "
            f"near {collaboration.get('event_search_center', 'the conference area')}"
        )

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


def render_participant_slots(posts: list[dict], profile: dict) -> None:
    st.subheader("Room View")
    known_posts = [profile] + posts
    slots = st.columns(5)
    for index in range(10):
        post = known_posts[index] if index < len(known_posts) else None
        with slots[index % 5]:
            if post:
                st.metric(f"Agent {index + 1}", post.get("name", "Anonymous"))
                st.caption(post.get("bcbs_plan", "Unknown Plan"))
            else:
                st.metric(f"Agent {index + 1}", "Waiting")
                st.caption("No post yet")


def render_posts(posts: list[dict]) -> None:
    st.subheader("Other Agent Posts")
    if not posts:
        st.caption("No other active agent posts are visible yet.")
        return

    for post in posts:
        with st.container(border=True):
            st.markdown(f"**{post.get('name', 'Anonymous')}**")
            st.write(f"{post.get('bcbs_plan', 'Unknown BCBS Plan')} | {post.get('job_title', 'Conference participant')}")
            if post.get("restaurant_preferences"):
                st.caption(f"Food: {post['restaurant_preferences']}")
            st.write(post.get("goal", "Looking for dinner collaborators."))


def render_agent_console(profile: dict, api_key: str, model: str) -> None:
    st.subheader("2. Agent Console")
    st.caption(
        f"The agent watches the last {DEFAULT_LISTEN_WINDOW_MINUTES} minutes of the shared chat and "
        f"refreshes every {AGENT_LOOP_INTERVAL_SECONDS} seconds while monitoring is active."
    )

    can_launch = bool(st.session_state.participant_name.strip() and st.session_state.agent_intent.strip())
    left, middle, right = st.columns(3)
    with left:
        if st.button("Launch Agent", type="primary", use_container_width=True, disabled=not can_launch):
            launch_agent(profile, api_key, model)
    with middle:
        if st.button("Refresh Now", use_container_width=True, disabled=not st.session_state.agent_monitoring_active):
            run_cycle(profile, api_key, model)
    with right:
        if st.button("Pause Monitoring", use_container_width=True, disabled=not st.session_state.agent_monitoring_active):
            st.session_state.agent_monitoring_active = False
            st.session_state.agent_status = "paused"
            st.session_state.agent_summary = "Monitoring is paused until you relaunch or refresh the agent."

    status = st.session_state.agent_status
    if status == "proposal_ready":
        st.success(st.session_state.agent_summary)
    elif status == "needs_human_input":
        st.warning(st.session_state.agent_summary)
    else:
        st.info(st.session_state.agent_summary)

    if st.session_state.follow_up_questions:
        st.markdown("**Questions for you**")
        for question in st.session_state.follow_up_questions:
            st.write(f"- {question}")

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
                send_back_to_discussion(profile, api_key, model)
    elif st.session_state.follow_up_questions:
        if st.button("Update Profile And Return To Discussion", use_container_width=True):
            send_back_to_discussion(profile, api_key, model)

    if st.session_state.last_plan_result:
        plan_result = st.session_state.last_plan_result
        if plan_result.get("sent"):
            st.success("Approved plan posted to the group.")
        elif plan_result.get("setup_required"):
            st.info("Discord is not configured, so the approved group message is only shown as a preview.")
            st.text(plan_result.get("message_preview", ""))
        elif plan_result.get("error"):
            st.warning(f"Plan post failed: {plan_result['error']}")

    with st.expander("Recent Agent Activity", expanded=True):
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

    left, right = st.columns([1, 1], gap="large")
    with left:
        profile = render_profile_setup()
        render_publish_status()
    with right:
        render_agent_console(profile, api_key, model)

    render_agent_monitor(profile, api_key, model)
    render_participant_slots(st.session_state.visible_agent_posts, current_profile())
    render_posts(st.session_state.visible_agent_posts)


if __name__ == "__main__":
    main()
