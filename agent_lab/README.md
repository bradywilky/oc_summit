# OC Summit Agent Lab

This repo contains a conference-safe Streamlit demo for a "Build Your Own Agent" breakout session.

## What it does

The app lets attendees:

- describe a Dallas evening goal
- toggle agent tools on and off
- watch the agent take step-by-step actions
- review a final dinner and networking plan
- ask follow-up questions to refine the plan without starting over

The app now runs in LLM-only mode. It uses the OpenAI Responses API to choose tool steps and synthesize the final answer, with live weather and optional live Foursquare lookup layered on top.

The weather tool calls the live Open-Meteo forecast API for Dallas and falls back to a static summary if the request fails.

The restaurant finder and event finder can call the live Foursquare Places API near your hotel or conference location using the current `places-api.foursquare.com` endpoint with Bearer auth and an explicit Places API version header. The event finder uses Foursquare to suggest nearby after-dinner venues such as live music spots, rooftops, comedy clubs, and cocktail bars. If `FOURSQUARE_API_KEY` is missing or the request fails, both tools fall back to the built-in demo datasets.

The text message sender uses Twilio to send a short SMS summary. Until you create a Twilio account, the tool safely returns a preview and reports which environment variables are still missing. The current destination number defaults to the static placeholder `+15555550123`.

## OpenAI setup

Set `OPENAI_API_KEY` in your environment or paste the key into the sidebar at runtime. You can also set `OPENAI_MODEL` to change the default model shown in the UI.

For live Foursquare search, set `FOURSQUARE_API_KEY` in your environment or paste it into the sidebar at runtime. The sidebar also lets you change the hotel/search center used for nearby restaurant and venue results.

For Twilio SMS, set these environment variables after signup:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_PHONE_NUMBER`
- `TWILIO_TO_PHONE_NUMBER` (optional; the app uses a static placeholder if you leave this unset)

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
