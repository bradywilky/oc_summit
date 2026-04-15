from __future__ import annotations

import re
from datetime import datetime, timezone

import streamlit as st

from tools import (
    SIMULATED_PROFILE_SOURCE,
    get_discord_oldest_lookback_timestamp,
    listen_for_discord_chat,
    listen_for_agent_posts,
)


st.set_page_config(
    page_title="Dallas Evening Planner",
    page_icon=":cityscape:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def inject_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        .tv-section-title {
            font-size: 2.1rem;
            font-weight: 700;
            line-height: 1.1;
            margin-bottom: 0.75rem;
        }
        .tv-body {
            font-size: 1.15rem;
            line-height: 1.55;
        }
        .tv-step-title {
            font-size: 1.35rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .tv-step-body {
            font-size: 1.1rem;
            line-height: 1.5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_intro() -> None:
    st.title("Plan an evening in Dallas with an AI Agent")
    st.write(
        "Use this dashboard to see who is active in the room and give your agent a clear brief "
        "for what kind of Dallas evening you want to create."
    )


def render_lab_overview() -> None:
    st.markdown('<div class="tv-section-title">What Is This?</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="tv-body">
        <p>The purpose of this lab is to get hands-on experience using a simple AI agent.
        This lab demonstrates what agents do well: coming up with an action plan, using tools,
        and making decisions.</p>
        <p>The Dallas Agent has one main goal in mind: plan an evening for you and your peers based
        on your preferences. After you fill in your information, the Dallas Agent looks at it and
        decides which tools it needs to use to build a plan. It can use maps, weather, and search
        to work through the evening until it decides the plan is ready.</p>
        <p>But it does not stop there. The Dallas Agent then enters a group chat to try to make plans
        with the other Dallas Agents. Your agent may ask follow-up questions based on what it sees
        in the group chat. Once it believes it has a strong plan with other agents, it will bring
        you a final proposal that you can accept or send back with new information.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("Fun fact: this lab was built with the help of an AI coding agent.")


def render_steps() -> None:
    st.markdown('<div class="tv-section-title">How To Participate</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="tv-step-title">Step 1</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="tv-step-body">
            Click the <code>&gt;&gt;</code> at the top left of the screen and fill in the "Human Profile."
            You can also optionally customize your agent's diplomacy and autonomy level.
            This gives your agent the context it needs to create a plan around your preferences.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown('<div class="tv-step-title">Step 2</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="tv-step-body">
            Under the Agent Console, click "Launch Agent." Your agent will then join the group
            chat with the other Dallas Agents.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        st.markdown('<div class="tv-step-title">Step 3</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="tv-step-body">
            Monitor your agent as it works. It will keep you updated on how the group chat
            discussions are going and when it is ready to propose a plan.
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_room_view() -> None:
    st.subheader("Room View")
    room_result = listen_for_agent_posts(
        current_participant_id=None,
        limit=10,
        oldest_lookback_timestamp=get_discord_oldest_lookback_timestamp(),
    )
    discord_result = room_result.get("discord", {})
    if not discord_result.get("fetched"):
        st.warning(
            discord_result.get("reason")
            or "Could not fetch Discord room state. Showing local simulated profiles only."
        )

    posts = room_result.get("posts", [])
    slots = st.columns(5)
    for index in range(10):
        post = posts[index] if index < len(posts) else None
        with slots[index % 5]:
            if post:
                st.metric(f"Agent {index + 1}", post.get("name", "Anonymous"))
                source = "Simulated" if post.get("source") == SIMULATED_PROFILE_SOURCE else "Live"
                st.caption(f"{post.get('bcbs_plan', 'Unknown Plan')} | {source}")
                if post.get("job_title"):
                    st.write(post["job_title"])
            else:
                st.metric(f"Agent {index + 1}", "Waiting")
                st.caption("No post yet")


def _format_chat_timestamp(timestamp: str | None) -> str:
    if not timestamp:
        return "Time unknown"

    normalized = timestamp.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return timestamp

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone().strftime("%Y-%m-%d %I:%M %p %Z")


def _clean_chat_content(content: str) -> str:
    visible = content.split("```json", 1)[0].strip()
    lines = [line.strip() for line in visible.splitlines() if line.strip()]
    cleaned_lines: list[str] = []
    for index, line in enumerate(lines):
        if "[AGENT_LAB_" in line:
            continue
        plain_line = re.sub(r"\*\*(.*?)\*\*", r"\1", line).strip()
        if index == 0 and "oc summit" in plain_line.lower():
            continue
        cleaned_lines.append(plain_line)
    return "\n".join(cleaned_lines).strip()


def render_discord_chat_feed() -> None:
    st.subheader("Chat Feed")
    chat_result = listen_for_discord_chat(
        limit=20,
        oldest_lookback_timestamp=get_discord_oldest_lookback_timestamp(),
    )
    discord_result = chat_result.get("discord", {})
    if not discord_result.get("fetched"):
        st.warning(discord_result.get("reason") or "Could not fetch Discord chat feed.")
        return

    messages = chat_result.get("messages", [])
    if not messages:
        st.caption("No recent Discord messages are visible in the current lookback window.")
        return

    for message in messages:
        author = message.get("author", {}) if isinstance(message.get("author"), dict) else {}
        sender_name = author.get("global_name") or author.get("username") or "Unknown sender"
        content = _clean_chat_content((message.get("content") or "").strip())
        if not content:
            content = "[No text content]"

        with st.container(border=True):
            st.markdown(f"**{sender_name}**")
            st.caption(_format_chat_timestamp(message.get("timestamp")))
            st.write(content)


def main() -> None:
    inject_dashboard_styles()
    render_intro()
    overview_column, steps_column = st.columns([7, 5], gap="large")
    with overview_column:
        render_lab_overview()
    with steps_column:
        render_steps()
    st.divider()
    room_column, chat_column = st.columns([4, 8], gap="large")
    with room_column:
        render_room_view()
    with chat_column:
        render_discord_chat_feed()


if __name__ == "__main__":
    main()
