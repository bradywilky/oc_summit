from __future__ import annotations

import os
import time
import uuid

import streamlit as st

from agent import run_agent
from prompts import AGENT_DEFINITION, CONFERENCE_TALK_TRACK
from tools import (
    TOOL_DEFINITIONS,
    listen_for_agent_posts,
    post_collaboration_reply,
    publish_agent_post,
    synthesize_agent_collaboration,
)


st.set_page_config(
    page_title="Build Your Dallas Agent",
    page_icon=":robot_face:",
    layout="wide",
)


DEFAULT_GOAL = (
    "Plan a fun Dallas dinner tonight where I can meet interesting people from "
    "the conference, stay under $50, and keep it within walking distance. "
    "I am meeting with people from Philly and do not remember their BCBS Plan."
)


def init_state() -> None:
    if "goal" not in st.session_state:
        st.session_state.goal = DEFAULT_GOAL
    if "conversation" not in st.session_state:
        st.session_state.conversation = []
    if "agent_runs" not in st.session_state:
        st.session_state.agent_runs = []
    if "selected_tools" not in st.session_state:
        st.session_state.selected_tools = [
            "restaurant_finder",
            "weather_tool",
            "conversation_starter",
            "discord_message_sender",
        ]
    if "openai_model" not in st.session_state:
        st.session_state.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    if "openai_api_key" not in st.session_state:
        st.session_state.openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if "hotel_location" not in st.session_state:
        st.session_state.hotel_location = os.getenv(
            "HOTEL_LOCATION",
            "Dallas Marriott Downtown, 650 N Pearl St, Dallas, TX 75201",
        )
    if "foursquare_api_key" not in st.session_state:
        st.session_state.foursquare_api_key = os.getenv("FOURSQUARE_API_KEY", "")
    if "participant_id" not in st.session_state:
        st.session_state.participant_id = str(uuid.uuid4())
    if "participant_name" not in st.session_state:
        st.session_state.participant_name = ""
    if "bcbs_plan" not in st.session_state:
        st.session_state.bcbs_plan = ""
    if "job_title" not in st.session_state:
        st.session_state.job_title = ""
    if "restaurant_preferences" not in st.session_state:
        st.session_state.restaurant_preferences = ""
    if "agent_intent" not in st.session_state:
        st.session_state.agent_intent = (
            "Find a dinner group near the conference where I can meet useful peers, "
            "compare AI agent ideas, and land on a restaurant that works for the group."
        )
    if "visible_agent_posts" not in st.session_state:
        st.session_state.visible_agent_posts = []
    if "collaboration_result" not in st.session_state:
        st.session_state.collaboration_result = None
    if "last_publish_result" not in st.session_state:
        st.session_state.last_publish_result = None


def render_sidebar() -> tuple[list[str], str, str, str]:
    st.sidebar.header("OpenAI Settings")
    api_key = st.sidebar.text_input(
        "OpenAI API key",
        key="openai_api_key",
        type="password",
        help="Leave this blank if OPENAI_API_KEY is already set in your environment.",
    )
    model = st.sidebar.text_input(
        "Model",
        key="openai_model",
        help="You can override the default model if your account uses a different one.",
    )
    if not (api_key or os.getenv("OPENAI_API_KEY")):
        st.sidebar.warning("This app now runs only in LLM Mode and needs an OpenAI API key.")

    st.sidebar.divider()
    st.sidebar.header("Live Foursquare Search")
    hotel_location = st.sidebar.text_input(
        "Hotel or search center",
        key="hotel_location",
        help="Nearby restaurant and after-dinner venue search is centered on this location.",
    )
    foursquare_api_key = st.sidebar.text_input(
        "Foursquare API key",
        key="foursquare_api_key",
        type="password",
        help="Leave this blank if FOURSQUARE_API_KEY is already set in your environment.",
    )
    if not (foursquare_api_key or os.getenv("FOURSQUARE_API_KEY")):
        st.sidebar.caption("Without a Foursquare key, the app falls back to the built-in restaurant and event lists.")

    st.sidebar.divider()
    st.sidebar.header("Agent Tools")
    st.sidebar.caption("Give the AI a few powers, then watch how the plan improves.")

    selected_tools: list[str] = []
    for tool_name, tool in TOOL_DEFINITIONS.items():
        checked = tool_name in st.session_state.selected_tools
        enabled = st.sidebar.checkbox(
            tool["label"],
            value=checked,
            help=tool["description"],
        )
        if enabled:
            selected_tools.append(tool_name)

    st.sidebar.divider()
    st.sidebar.subheader("How To Explain It")
    st.sidebar.info(AGENT_DEFINITION)
    st.sidebar.caption(CONFERENCE_TALK_TRACK)
    return selected_tools, api_key, model, hotel_location


def current_profile() -> dict:
    return {
        "participant_id": st.session_state.participant_id,
        "name": st.session_state.participant_name.strip() or "Anonymous",
        "bcbs_plan": st.session_state.bcbs_plan.strip() or "Unknown BCBS Plan",
        "job_title": st.session_state.job_title.strip() or "Conference participant",
        "restaurant_preferences": st.session_state.restaurant_preferences.strip(),
        "goal": st.session_state.agent_intent.strip(),
    }


def render_header() -> None:
    st.title("Build Your Dallas Agent")
    st.write(
        "A conference-safe demo for OC Summit breakout sessions. Ten participants can "
        "set up their agents, publish dinner intents to Discord, listen for other "
        "agents, and coordinate a shared plan."
    )


def render_profile_setup() -> dict:
    st.subheader("1. Set Up Your Agent")
    st.text_input("Your name", key="participant_name", placeholder="Alex Lee")
    st.text_input("BCBS Plan", key="bcbs_plan", placeholder="Independence Blue Cross")
    st.text_input("Job title", key="job_title", placeholder="Director, Product Operations")
    st.text_area(
        "Restaurant preferences",
        key="restaurant_preferences",
        height=90,
        placeholder="Vegetarian-friendly, under $50, easy walk, good for conversation",
    )
    st.text_area(
        "What do you want to do tonight?",
        key="agent_intent",
        height=120,
    )
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
        st.caption(f"Still useful, but richer if you add: {', '.join(missing)}.")
    return profile


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
        st.caption("No other agent posts are visible yet. Ask a few participants to publish, then listen again.")
        return

    for post in posts:
        with st.container(border=True):
            st.markdown(f"**{post.get('name', 'Anonymous')}**")
            st.write(f"{post.get('bcbs_plan', 'Unknown BCBS Plan')} | {post.get('job_title', 'Conference participant')}")
            if post.get("restaurant_preferences"):
                st.caption(f"Food: {post['restaurant_preferences']}")
            st.write(post.get("goal", "Looking for dinner collaborators."))


def wait_for_other_posts(profile: dict, seconds: int = 30) -> dict:
    deadline = time.time() + seconds
    result = listen_for_agent_posts(profile["participant_id"])
    while time.time() < deadline and not result["posts"]:
        time.sleep(5)
        result = listen_for_agent_posts(profile["participant_id"])
    return result


def render_agent_network(api_key: str, model: str) -> None:
    left, right = st.columns([1, 1], gap="large")

    with left:
        profile = render_profile_setup()
        can_publish = bool(st.session_state.participant_name.strip() and st.session_state.agent_intent.strip())
        if st.button("Publish Agent Post", type="primary", use_container_width=True, disabled=not can_publish):
            st.session_state.last_publish_result = publish_agent_post(profile, st.session_state.agent_intent)
            st.success("Your agent posted its intent. If Discord is configured, it went to the channel too.")

        if st.session_state.last_publish_result:
            discord_result = st.session_state.last_publish_result.get("discord", {})
            if discord_result.get("sent"):
                st.caption(f"Discord message sent: {discord_result.get('message_id')}")
            elif discord_result.get("setup_required"):
                st.info("Discord is not configured, so this lab is using local demo posts.")
            elif discord_result.get("error"):
                st.warning(f"Discord send failed: {discord_result['error']}")
            with st.expander("Post Preview"):
                st.text(st.session_state.last_publish_result.get("message_preview", ""))

    with right:
        st.subheader("2. Listen And Collaborate")
        listen_now = st.button("Listen Now", use_container_width=True)
        wait_now = st.button("Wait Up To 30 Seconds", use_container_width=True)
        if listen_now or wait_now:
            with st.spinner("Listening for other agents..."):
                listen_result = wait_for_other_posts(profile) if wait_now else listen_for_agent_posts(profile["participant_id"])
            st.session_state.visible_agent_posts = listen_result["posts"]
            discord_result = listen_result.get("discord", {})
            if discord_result.get("setup_required"):
                st.info("Using local demo posts because Discord credentials are not set.")
            elif discord_result.get("error"):
                st.warning(f"Discord listen failed: {discord_result['error']}")

        if st.button("Build Collaboration Plan", use_container_width=True):
            with st.spinner("Your agent is comparing posts and looking for a group..."):
                st.session_state.collaboration_result = synthesize_agent_collaboration(
                    profile,
                    st.session_state.visible_agent_posts,
                    context={"openai_api_key": api_key or None, "openai_model": model or None},
                )

        collaboration = st.session_state.collaboration_result
        if collaboration:
            st.markdown(f"**Recommendation:** {collaboration['summary']}")
            for step in collaboration.get("next_steps", []):
                st.write(f"- {step}")
            if st.button("Post Collaboration Reply To Discord", use_container_width=True):
                reply_result = post_collaboration_reply(profile, collaboration)
                if reply_result.get("sent"):
                    st.success("Collaboration reply posted to Discord.")
                elif reply_result.get("setup_required"):
                    st.info("Discord is not configured, so the reply is only a preview.")
                    st.text(reply_result.get("message_preview", ""))
                else:
                    st.warning(f"Discord reply failed: {reply_result.get('error', 'Unknown error')}")

    render_participant_slots(st.session_state.visible_agent_posts, current_profile())
    render_posts(st.session_state.visible_agent_posts)


def render_tool_summary(selected_tools: list[str]) -> None:
    cols = st.columns(len(TOOL_DEFINITIONS))
    for col, (tool_name, tool) in zip(cols, TOOL_DEFINITIONS.items()):
        active = "Enabled" if tool_name in selected_tools else "Off"
        col.metric(tool["label"], active)


def render_activity(runs: list[dict]) -> None:
    st.subheader("Agent Activity")
    if not runs:
        st.caption("Run the agent to see the plan -> act -> observe loop.")
        return

    for run_number, run in enumerate(reversed(runs), start=1):
        label = run["user_message"]
        with st.expander(f"Turn {len(runs) - run_number + 1}: {label}", expanded=(run_number == 1)):
            for item in run["history"]:
                with st.container(border=True):
                    st.markdown(f"**Step {item['step']}**  ")
                    st.write(item["reason"])
                    st.caption(f"Tool used: {item['tool_label']}")
                    if item["tool"] == "restaurant_finder":
                        render_restaurant_results(item["result"])
                    else:
                        st.json(item["result"])


def render_restaurant_results(result: dict) -> None:
    source = result.get("source", "Unknown source")
    search_center = result.get("search_center", "Unknown search center")
    st.caption(f"Source: {source} | Search center: {search_center}")

    for restaurant in result.get("restaurants", []):
        with st.container(border=True):
            st.markdown(f"**{restaurant['name']}**")
            details = (
                f"{restaurant.get('cuisine', 'Restaurant')} | "
                f"{restaurant.get('estimated_cost', 'N/A')} | "
                f"{restaurant.get('walk_minutes', '?')} min walk"
            )
            st.write(details)

            address = restaurant.get("address")
            if address:
                st.caption(address)

            cols = st.columns(3)
            cols[0].link_button("Book", restaurant["booking_url"], use_container_width=True)
            cols[1].link_button("Website", restaurant["website_url"], use_container_width=True)
            cols[2].link_button("Map", restaurant["maps_url"], use_container_width=True)

    if result.get("error"):
        st.caption(f"Live search fallback reason: {result['error']}")


def render_final_answer(final_answer: str) -> None:
    st.subheader("Final Plan")
    st.markdown(final_answer)


def render_conversation(conversation: list[dict]) -> None:
    st.subheader("Conversation")
    if not conversation:
        st.caption("Start with a goal, then use follow-ups to refine the plan.")
        return

    for message in conversation:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def run_turn(
    user_message: str,
    selected_tools: list[str],
    api_key: str,
    model: str,
    hotel_location: str,
) -> None:
    conversation_history = list(st.session_state.conversation)
    with st.spinner("Agent is building your evening plan..."):
        if st.session_state.foursquare_api_key:
            os.environ["FOURSQUARE_API_KEY"] = st.session_state.foursquare_api_key
        result = run_agent(
            goal=user_message,
            enabled_tools=selected_tools,
            api_key=api_key or None,
            model=model or None,
            context={"hotel_location": hotel_location},
            conversation_history=conversation_history,
        )

    st.session_state.conversation.append({"role": "user", "content": user_message})
    st.session_state.conversation.append({"role": "assistant", "content": result["final"]})
    st.session_state.agent_runs.append(
        {
            "user_message": user_message,
            "history": result["history"],
            "final": result["final"],
            "mode_used": result.get("mode_used"),
            "warning": result.get("warning"),
        }
    )


def main() -> None:
    init_state()
    render_header()
    selected_tools, api_key, model, hotel_location = render_sidebar()

    render_agent_network(api_key, model)
    st.divider()
    st.subheader("Optional: Inspect One Agent's Planning Loop")

    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.subheader("Goal")
        goal = st.text_area(
            "Tell the agent what you want to accomplish.",
            key="goal",
            height=140,
        )
        render_tool_summary(selected_tools)

        run_clicked = st.button("Start Agent", type="primary", use_container_width=True)

    with right:
        st.subheader("Why This Works")
        st.write(
            "A chatbot answers questions. An agent can take actions to accomplish "
            "a goal. This demo makes that visible by showing each tool choice and "
            "what the AI learned from it. Once it answers, you can keep the conversation going with follow-up requests."
        )

    if run_clicked:
        if not selected_tools:
            st.warning("Select at least one tool so the agent has something it can use.")
            return
        if not (api_key or os.getenv("OPENAI_API_KEY")):
            st.warning("Add an OpenAI API key to run the agent.")
            return
        run_turn(goal, selected_tools, api_key, model, hotel_location)

    latest_run = st.session_state.agent_runs[-1] if st.session_state.agent_runs else None
    if latest_run:
        if latest_run.get("mode_used"):
            st.caption(f"Mode used: {latest_run['mode_used']}")
        if latest_run.get("warning"):
            st.warning(latest_run["warning"])

    render_conversation(st.session_state.conversation)

    follow_up = st.chat_input("Ask a follow-up to refine the plan")
    if follow_up:
        if not selected_tools:
            st.warning("Select at least one tool so the agent has something it can use.")
            return
        if not (api_key or os.getenv("OPENAI_API_KEY")):
            st.warning("Add an OpenAI API key to run the agent.")
            return
        run_turn(follow_up, selected_tools, api_key, model, hotel_location)
        st.rerun()

    render_activity(st.session_state.agent_runs)
    if latest_run:
        render_final_answer(latest_run["final"])


if __name__ == "__main__":
    main()
