from __future__ import annotations

import os

import streamlit as st

from agent import run_agent
from prompts import AGENT_DEFINITION, CONFERENCE_TALK_TRACK
from tools import TOOL_DEFINITIONS


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


def render_header() -> None:
    st.title("Build Your Dallas Agent")
    st.write(
        "A conference-safe demo for OC Summit breakout sessions. Participants choose "
        "tools, give the AI a goal, and watch it reason step by step."
    )


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
