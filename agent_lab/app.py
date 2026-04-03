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
    "the conference, stay under $50, and keep it within walking distance."
)


def init_state() -> None:
    if "goal" not in st.session_state:
        st.session_state.goal = DEFAULT_GOAL
    if "selected_tools" not in st.session_state:
        st.session_state.selected_tools = [
            "restaurant_finder",
            "weather_tool",
            "attendee_lookup",
            "conversation_starter",
        ]
    if "mode" not in st.session_state:
        st.session_state.mode = "Demo Mode"
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


def render_sidebar() -> tuple[list[str], str, str, str, str]:
    st.sidebar.header("Run Mode")
    mode = st.sidebar.radio(
        "Choose how the app should run.",
        options=["Demo Mode", "LLM Mode"],
        key="mode",
        help="Demo Mode is deterministic. LLM Mode uses your OpenAI API key to plan steps and write the final response.",
    )

    api_key = ""
    model = ""
    if mode == "LLM Mode":
        st.sidebar.subheader("OpenAI Settings")
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
            st.sidebar.warning("LLM Mode needs an OpenAI API key from the sidebar or OPENAI_API_KEY.")

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
    return selected_tools, mode, api_key, model, hotel_location


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


def render_activity(history: list[dict]) -> None:
    st.subheader("Agent Activity")
    if not history:
        st.caption("Run the agent to see the plan -> act -> observe loop.")
        return

    for item in history:
        with st.container(border=True):
            st.markdown(f"**Step {item['step']}**  ")
            st.write(item["reason"])
            st.caption(f"Tool used: {item['tool_label']}")
            st.json(item["result"])


def render_final_answer(final_answer: str) -> None:
    st.subheader("Final Plan")
    st.markdown(final_answer)


def main() -> None:
    init_state()
    render_header()
    selected_tools, mode, api_key, model, hotel_location = render_sidebar()

    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.subheader("Goal")
        goal = st.text_area(
            "Tell the agent what you want to accomplish.",
            key="goal",
            height=140,
        )
        render_tool_summary(selected_tools)

        run_clicked = st.button("Run Agent", type="primary", use_container_width=True)

    with right:
        st.subheader("Why This Works")
        st.write(
            "A chatbot answers questions. An agent can take actions to accomplish "
            "a goal. This demo makes that visible by showing each tool choice and "
            "what the AI learned from it."
        )

    if not run_clicked:
        return

    if not selected_tools:
        st.warning("Select at least one tool so the agent has something it can use.")
        return

    if mode == "LLM Mode" and not (api_key or os.getenv("OPENAI_API_KEY")):
        st.warning("Add an OpenAI API key to use LLM Mode.")
        return

    with st.spinner("Agent is building your evening plan..."):
        if st.session_state.foursquare_api_key:
            os.environ["FOURSQUARE_API_KEY"] = st.session_state.foursquare_api_key
        result = run_agent(
            goal=goal,
            enabled_tools=selected_tools,
            mode=mode,
            api_key=api_key or None,
            model=model or None,
            context={"hotel_location": hotel_location},
        )

    if result.get("mode_used"):
        st.caption(f"Mode used: {result['mode_used']}")
    if result.get("warning"):
        st.warning(result["warning"])

    render_activity(result["history"])
    render_final_answer(result["final"])


if __name__ == "__main__":
    main()
