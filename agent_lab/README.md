# OC Summit Agent Lab

This repo contains a conference-safe Streamlit demo for a "Build Your Own Agent" breakout session.

## What it does

The app lets attendees:

- set up an agent profile with their name, BCBS Plan, job title, and restaurant preferences
- publish a structured agent intent post to the shared Discord channel
- listen for other participant agents in the channel
- synthesize a collaboration plan from visible agent posts
- post a collaboration reply back to Discord
- describe a Dallas evening goal
- toggle agent tools on and off
- watch the agent take step-by-step actions
- review a final dinner and networking plan
- ask follow-up questions to refine the plan without starting over

The app now runs in LLM-only mode. It uses the OpenAI Responses API to choose tool steps and synthesize the final answer, with live weather and optional live Foursquare lookup layered on top.

The weather tool calls the live Open-Meteo forecast API for Dallas and falls back to a static summary if the request fails.

The restaurant finder and event finder can call the live Foursquare Places API near your hotel or conference location using the current `places-api.foursquare.com` endpoint with Bearer auth and an explicit Places API version header. The event finder uses Foursquare to suggest nearby after-dinner venues such as live music spots, rooftops, comedy clubs, and cocktail bars. If `FOURSQUARE_API_KEY` is missing or the request fails, both tools fall back to the built-in demo datasets.

The Discord message sender posts a short summary to a Discord channel using a bot token. Until you configure Discord credentials, the tool safely returns a preview and reports which environment variables are still missing.

The multi-agent lab flow uses structured Discord messages marked with `[AGENT_LAB_POST]`, so every running Streamlit session can poll the same channel and identify other participants. If Discord credentials are missing or the channel fetch fails, the app falls back to `data/agent_posts.json` so facilitators can still demo the 10-person collaboration loop locally.

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

## Project structure

- `app.py` - Streamlit UI
- `agent.py` - controlled agent loop
- `tools.py` - demo tools and local data loading
- `prompts.py` - presentation framing and response templates
- `data/` - curated demo datasets
