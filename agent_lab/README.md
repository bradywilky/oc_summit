# OC Summit Agent Lab

This repo contains a conference-safe Streamlit demo for a "Build Your Own Agent" breakout session.

## What it does

The app lets attendees:

- set up an agent profile with their name, BCBS Plan, job title, and restaurant preferences
- add when they expect to be done for the day so the agent can time suggestions appropriately
- publish a structured agent intent post to the shared Discord channel
- listen for other participant agents in the channel
- synthesize a collaboration plan from visible agent posts
- post a collaboration reply back to Discord
- describe a Dallas evening goal
- say "I don't know" in the profile and get concrete follow-up questions grounded in nearby options and other participants' plans
- toggle agent tools on and off
- watch the agent take step-by-step actions
- review a final dinner and networking plan
- ask follow-up questions to refine the plan without starting over

The app now runs in LLM-only mode. It uses the OpenAI Responses API to choose tool steps and synthesize the final answer, with live weather and optional live Foursquare lookup layered on top.

The weather tool calls the live Open-Meteo forecast API for Dallas and falls back to a static summary if the request fails.

The restaurant finder and event finder can call the live Foursquare Places API near your hotel or conference location using the current `places-api.foursquare.com` endpoint with Bearer auth and an explicit Places API version header. The event finder uses Foursquare to suggest nearby after-dinner venues such as live music spots, rooftops, comedy clubs, and cocktail bars. If `FOURSQUARE_API_KEY` is missing or the request fails, both tools fall back to the built-in demo datasets.

The Discord message sender posts a short summary to a Discord channel using a bot token. If Discord is not configured or the API call fails, the app now surfaces the exact reason in the UI instead of silently falling back.

The multi-agent lab flow uses structured Discord messages marked with `[AGENT_LAB_POST]`, so every running Streamlit session can poll the same channel and identify other participants. Discord is now the required source of truth for agent coordination. If credentials are missing, the bot lacks channel access, or the API returns an error, agent coordination stops and the UI shows the failure reason.

## OpenAI setup

Set `OPENAI_API_KEY` in your environment or paste the key into the sidebar at runtime. You can also set `OPENAI_MODEL` to change the default model shown in the UI.

For live Foursquare search, set `FOURSQUARE_API_KEY` in your environment or paste it into the sidebar at runtime. The sidebar also lets you change the hotel/search center used for nearby restaurant and venue results.

For Discord messages, set these environment variables:

- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNEL_ID`

The bot needs permission to read channel history and send messages in the configured channel.

## Run it

1. Create a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Start the app:

```powershell
streamlit run app.py
```

4. Start the separate developer console when you want to control shared dev-only settings:

```powershell
streamlit run dev_console.py
```

## Project structure

- `app.py` - Streamlit UI
- `dev_console.py` - separate Streamlit controls for dev-only settings
- `agent.py` - controlled agent loop
- `tools.py` - demo tools and local data loading
- `prompts.py` - presentation framing and response templates
- `data/` - curated demo datasets

## Streaming agent updates

`agent.py` now exposes both:

- `run_agent(...)` for the original one-shot behavior
- `run_agent_stream(...)` for incremental UI updates

If you want Streamlit to render intermediate status messages as they happen, iterate the stream in `app.py` and update the UI on each event instead of waiting for `run_agent(...)` to return.

```python
from agent import run_agent_stream

status_box = st.empty()
chat_box = st.container()

for event in run_agent_stream(goal, enabled_tools, api_key=api_key, model=model):
    if event["type"] == "status":
        status_box.info(event["message"])
    elif event["type"] == "step_started":
        with chat_box:
            st.chat_message("assistant").write(
                f"Running {event['tool_label']}..."
            )
    elif event["type"] == "step_completed":
        with chat_box:
            st.chat_message("assistant").write(
                f"Finished {event['tool_label']}."
            )
    elif event["type"] == "final":
        with chat_box:
            st.chat_message("assistant").write(event["final"])
```
