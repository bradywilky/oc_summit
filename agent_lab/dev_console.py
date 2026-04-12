from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from tools import (
    DEFAULT_LISTEN_WINDOW_MINUTES,
    SIMULATED_PROFILE_SOURCE,
    clear_local_agent_posts,
    create_local_agent_post,
    get_discord_oldest_lookback_timestamp,
    list_local_agent_posts,
    listen_for_agent_posts,
    seed_sample_agent_posts,
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
        st.warning(discord_result.get("reason") or "Could not fetch Discord room state. Showing local simulated profiles only.")

    posts = room_result.get("posts", [])
    slots = st.columns(5)
    for index in range(10):
        post = posts[index] if index < len(posts) else None
        with slots[index % 5]:
            if post:
                st.metric(f"Agent {index + 1}", post.get("name", "Anonymous"))
                source = "Simulated" if post.get("source") == SIMULATED_PROFILE_SOURCE else "Live"
                st.caption(f"{post.get('bcbs_plan', 'Unknown Plan')} · {source}")
            else:
                st.metric(f"Agent {index + 1}", "Waiting")
                st.caption("No post yet")


def render_simulated_humans() -> None:
    st.subheader("Simulated Humans")
    st.write(
        "Add a few fake attendee profiles here for testing. These profiles are injected through the dev console only, "
        "so `app.py` stays focused on the real participant experience."
    )

    simulated_posts = list_local_agent_posts(source=SIMULATED_PROFILE_SOURCE)
    count_label = "profile" if len(simulated_posts) == 1 else "profiles"
    st.caption(f"{len(simulated_posts)} simulated {count_label} currently active.")

    left, right = st.columns(2)
    with left:
        if st.button("Seed Sample Profiles", type="primary", use_container_width=True):
            seeded = seed_sample_agent_posts()
            st.success(f"Loaded {len(seeded)} sample profiles into the room.")
            st.rerun()
    with right:
        if st.button("Clear Simulated Profiles", use_container_width=True):
            removed = clear_local_agent_posts(source=SIMULATED_PROFILE_SOURCE)
            st.success(f"Removed {removed} simulated profiles.")
            st.rerun()

    with st.expander("Add Custom Simulated Profile"):
        with st.form("custom_simulated_profile"):
            name = st.text_input("Name", placeholder="Taylor Morgan")
            bcbs_plan = st.text_input("BCBS Plan", placeholder="Blue Cross and Blue Shield of Texas")
            job_title = st.text_input("Job Title", placeholder="Product Manager")
            restaurant_preferences = st.text_input(
                "Restaurant Preferences",
                placeholder="vegetarian-friendly, lively but not too loud",
            )
            done_for_day_time = st.text_input("Done For Day Time", placeholder="6:00 PM")
            goal = st.text_area(
                "Goal",
                placeholder="Meet a few people working on AI and find a good dinner spot nearby.",
                height=100,
            )
            submitted = st.form_submit_button("Add Simulated Profile", use_container_width=True)

        if submitted:
            trimmed_name = name.strip()
            if not trimmed_name:
                st.error("Add at least a name so the simulated profile is easy to identify.")
            else:
                profile = {
                    "participant_id": f"sim-{trimmed_name.lower().replace(' ', '-')}",
                    "name": trimmed_name,
                    "bcbs_plan": bcbs_plan.strip() or "Unknown BCBS Plan",
                    "job_title": job_title.strip() or "Conference participant",
                    "restaurant_preferences": restaurant_preferences.strip(),
                    "done_for_day_time": done_for_day_time.strip(),
                    "goal": goal.strip() or "Meet people for dinner",
                }
                create_local_agent_post(profile, source=SIMULATED_PROFILE_SOURCE)
                st.success(f"Added simulated profile for {trimmed_name}.")
                st.rerun()

    if simulated_posts:
        for post in simulated_posts[:8]:
            title = f"{post.get('name', 'Anonymous')} · {post.get('job_title', 'Conference participant')}"
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(post.get("bcbs_plan", "Unknown BCBS Plan"))
                st.write(post.get("goal", ""))
                if post.get("restaurant_preferences"):
                    st.write(f"Food: {post['restaurant_preferences']}")
                if post.get("done_for_day_time"):
                    st.write(f"Free around: {post['done_for_day_time']}")


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

    render_simulated_humans()
    render_room_view()


if __name__ == "__main__":
    main()
