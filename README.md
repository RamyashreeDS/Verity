# RoadWatch SF

A long-running agent that keeps a live map of which San Francisco roads are blocked, and stays small because it **forgets what no longer matters**.

Built at the [Long Horizon Agents Hack](https://tokensand.com/horizonagentshack), Sep 25 2026.

## What it does

- **Collects** permitted closures from [DataSF Temporary Street Closures](https://data.sf.gov/resource/8x25-yybr.json), live web news via **Nimble Search**, and free-text reports typed in by users.
- **Extracts** road events from free text with **Liquid AI LFM2.5-2.6B running locally** (about 3 s per report on a MacBook, with reasoning skipped).
- **Geocodes** "Market St at 5th St" to real street segments using the DataSF street-centerline dataset (OSM Nominatim as a fallback).
- **Resolves**: a new report on a street that already has an active event is merged, and confidence is combined. A "reopened" report clears the event.
- **Verifies** a low-trust social report with a Nimble search. Confidence rises if matching pages are found.
- **Forgets** with explicit rules:
  - Scheduled closures retire 30 minutes after their end time.
  - An unconfirmed social report (trust 0.3) loses 0.15 confidence per hour and is dropped below 0.2.
  - If the working state exceeds 4K tokens, the lowest-value events are folded into a digest.
- **Publishes** a shareable alert card for confirmed blocked streets: a **FLUX** (Black Forest Labs, `flux-pro-1.1`) flat-poster illustration of the event type, with the street, time window, confidence and sources overlaid. Cards are labeled "AI illustration" and are never photoreal.
- **Remembers** in **RawTree** (schemaless JSON ingest, SQL over HTTP): raw observations (deduplicated by content hash), an event ledger with every version of every event, one-line digests, and per-cycle agent metrics (`roadwatch_agent_runs`). Recall is a SQL query, not context. Falls back to SQLite if `RAWTREE_API_KEY` is not set.

The chart shows the proof: the compact working state (one line per active event) stays flat, while a naive agent that appends every observation grows without bound.

## Run

```bash
# model weights in ./LFM2.5-2.6B (Hugging Face format); NIMBLE_API_KEY, RAWTREE_API_KEY, BLACK_FORTRESS_API_KEY in .env
uv pip install fastapi uvicorn requests python-dotenv torch transformers pillow
python -m uvicorn server:app --port 8000
# open http://localhost:8000
```

- **Memory & tokens** (`/memory`) shows token utilization against the 4K cap, the per-event cost of the working state, what has been forgotten and by which rule, and what lives in RawTree instead of context.
- **Replay last week** plays back real DataSF permits at 1 simulated hour per second.
- **Live (now)** runs in real time.
- **Send report** or **Scan web news (Nimble)** adds events via LFM2.5. **Verify via Nimble** corroborates a report. The **"Reopened" example** clears it.

## Files

- `agent.py`: sources, geocoding, working state, forgetting rules, metrics
- `store.py`: long-term memory on RawTree (SQLite fallback)
- `cards.py`: FLUX alert cards
- `llm.py`: local LFM2.5 extraction
- `server.py`: FastAPI with the agent loop in a background thread
- `static/index.html`: Leaflet map, token chart, agent log, recall
