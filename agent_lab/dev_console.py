from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from tools import (
    DEFAULT_LISTEN_WINDOW_MINUTES,
    get_discord_oldest_lookback_timestamp,
    listen_for_agent_posts,
    set_discord_oldest_lookback_timestamp,
)


st.set_page_config(
    page_title="Agent Lab Dev Console",
    page_icon=":wrench:",
    layout="centered",
)


def _current_lookback_label() -> str:
    timestamp = get_discord_oldest_lookback_timestamp()
    if not timestamp:
        return f"last {DEFAULT_LISTEN_WINDOW_MINUTES} minutes"

    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return "a custom memory boundary"

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    local_timestamp = parsed.astimezone()
    return f"messages since {local_timestamp.strftime('%Y-%m-%d %I:%M:%S %p %Z')}"


def render_room_view() -> None:
    st.subheader("Room View")
    room_result = listen_for_agent_posts(
        current_participant_id=None,
        limit=10,
        oldest_lookback_timestamp=get_discord_oldest_lookback_timestamp(),
    )
    discord_result = room_result.get("discord", {})
    if not discord_result.get("fetched"):
        st.error(discord_result.get("reason") or "Could not fetch Discord room state.")
        return

    posts = room_result.get("posts", [])
    slots = st.columns(5)
    for index in range(10):
        post = posts[index] if index < len(posts) else None
        with slots[index % 5]:
            if post:
                st.metric(f"Agent {index + 1}", post.get("name", "Anonymous"))
                st.caption(post.get("bcbs_plan", "Unknown Plan"))
            else:
                st.metric(f"Agent {index + 1}", "Waiting")
                st.caption("No post yet")


def main() -> None:
    st.title("Agent Lab Dev Console")
    st.write(
        "This console controls shared developer settings for the user-facing app. "
        "Changes here are picked up by `app.py` on its next refresh cycle."
    )

    st.subheader("Discord Memory")
    st.caption(f"Current lookback: {_current_lookback_label()}.")

    left, right = st.columns(2)
    with left:
        if st.button("Clear Memory", type="primary", use_container_width=True):
            cleared_at = datetime.now(timezone.utc).isoformat()
            set_discord_oldest_lookback_timestamp(cleared_at)
            st.success("Discord memory cleared. The user app will now ignore earlier messages.")
            st.rerun()
    with right:
        if st.button("Use Rolling Window", use_container_width=True):
            set_discord_oldest_lookback_timestamp(None)
            st.success(f"Restored the default rolling window of {DEFAULT_LISTEN_WINDOW_MINUTES} minutes.")
            st.rerun()

    current_timestamp = get_discord_oldest_lookback_timestamp()
    if current_timestamp:
        st.code(current_timestamp, language="text")

    render_room_view()


if __name__ == "__main__":
    main()
