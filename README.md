# OC Summit Agent Lab

This repo contains a conference-safe Streamlit demo for a "Build Your Own Agent" breakout session.

## What it does

The app lets attendees:

- describe a Dallas evening goal
- toggle agent tools on and off
- watch the agent take step-by-step actions
- review a final dinner and networking plan

The experience is intentionally local and deterministic. It uses curated Dallas and attendee demo data instead of brittle live integrations.

## Modes

- `Demo Mode` uses the built-in deterministic planner and does not require any external service.
- `LLM Mode` uses the OpenAI Responses API to choose tool steps and synthesize the final answer.

For `LLM Mode`, set `OPENAI_API_KEY` in your environment or paste the key into the sidebar at runtime. You can also set `OPENAI_MODEL` to change the default model shown in the UI.

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
