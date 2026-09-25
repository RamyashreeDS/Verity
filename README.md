# Verity

A self-healing information pipeline for tracking natural disasters and accidents in real time — wildfires, floods, earthquakes, and similar events.

## The problem

During a live disaster, information is scattered across many sources, frequently contradictory, and changes by the minute — evacuation status, road closures, shelter availability. Getting it wrong isn't just a bug: bad information  this layer can put people at real risk. Most monitoring tools aggregate and display; they don't know when their own picture of the world has gone stale, contradictory, or broken.

This project builds a monitor that watches its own reliabilty, not just the disaster — it detects when its understanding is compromised and heals itself before that failure reaches the dashboard.

## Architecture

```
CRISIS QUERY (wildfire / flood / earthquake / etc.)
        │
        ▼
1. SENSE          search → crawl → extract → discover new information
        │
        ▼
2. UNDERSTAND      extract claims → classify → identify entities → compare
                   output: structured evidence only
        │
        ▼
3. VALIDATE        timestamps · duplicates · schemas · source IDs
                   state rules · confidence thresholds · invariants
        │
        ▼
4. WORLD STATE     🔥 Fire  🚨 Evacuations  🛣 Roads  🏠 Shelters  🌬 Weather  ⚡ Utilities  ❓ Unknowns
        │
   ┌────┴────┐
   ▼         ▼
RawTree   Dashboard
(full     (current
history)   truth)
   │
   ▼
5. HEALTH MONITOR  stale? · contradiction? · loop? · missing? · failure?
        │
     healthy? ── yes ──▶ continue
        │
        no
        ▼
6. HEALING LOOP    detect → diagnose → propose → verify → test → commit
                                                          └──▶ reject / rollback
```

**Pipeline stages**

| Stage | Responsibility |
|---|---|
| Sense | Search and crawl for new reports relevant to the active crisis |
| Understand | Turn raw crawled text into structured claims (entities, classification) |
| Validate | Deterministic checks only — schema, timestamps, dedup, confidence thresholds, invariants |
| World State | The durable, current picture of the crisis, plus full history |
| Health Monitor | Watches the pipeline itself, not just the world, for signs of failure |
| Healing Loop | Diagnoses and repairs detected problems, with verification before any change is committed |

## Why this fits "reliable agents over long tasks"

| Requirement | How it's satisfied |
|---|---|
| **Persistent state** | World State (the dashboard) is the durable "current truth," independent of any single session or conversation. |
| **Memory** | RawTree (full history) plus validation rules built on accumulated prior evidence — the system doesn't re-decide facts it has already confirmed. |
| **Context management** | The Sense → Understand boundary compresses noisy, high-volume crawled text into compact structured evidence before anything downstream reasons over it. |
| **Reliability over time** | The system runs continuously, encountering new and sometimes contradictory information across hours — the Health Monitor + Healing Loop is what keeps the picture accurate rather than silently drifting stale or wrong. |

## Design principles

- **Prefer silence over confident flapping.** When sources disagree and evidence is thin, mark the fact as unresolved/low-confidence rather than picking a side and risking a flip-flop later. A wrong confident answer is worse than an honest "unconfirmed" in this domain.
- **Verify before committing.** Every healing action goes through Verify → Test before Commit, with Reject/Rollback as the default if a proposed fix doesn't hold up — a fix that merely looks plausible is not good enough.
- **Deterministic checks first, judgment second.** Validate is schema/timestamp/dedup logic, not an LLM call — cheap, fast, and consistent. LLM reasoning is reserved for genuine judgment calls (Understand, Diagnose, Propose).

## Known limitations

- **Validate checks consistency, not truth.** A well-formed, timely, deduplicated claim can still be factually wrong — there's no ground-truth oracle for "is this shelter actually open."
- **Misinformation risk.** Crisis events draw the highest volume of unverified and sometimes deliberately false reports right when the crawl surface is widest. Structural validation alone won't catch a well-formed false claim; a source-credibility signal is a needed next step.
- **Novel contradiction shapes.** The Health Monitor reliably detects *that* something contradicts; the Healing Loop's Diagnose/Propose steps reason out *how* to resolve conflict shapes it hasn't seen before, which can be slower and less consistent on first occurrence.
- **Memory generalization.** Any memory of past healing decisions must store *reasoning patterns* (e.g. "official feeds outrank uncorroborated social posts on the same claim, absent corroboration"), not per-source trust scores — a source that was wrong once elsewhere shouldn't be discounted everywhere.

## Demo scenario

1. Seed two sources with a genuine conflict (e.g. conflicting road-closure status).
2. Show Health Monitor detecting the contradiction and the Healing Loop reasoning about it.
3. Show the system choosing unresolved/low-confidence display over a confident guess.
4. Feed in corroborating evidence and show the conflict resolving and committing to World State.

## Status

Early build — architecture and design scoped, implementation in progress.

---

## Implementation — Verity (code name: RoadWatch SF)

The working build from hack day: a long-running agent for San Francisco road status, with the slides in `slides/` and the speaker script in `slides/speech_script.md`.

A long-running agent that keeps a live map of which San Francisco roads are blocked, and stays small because it **forgets what no longer matters**.

Built at the [Long Horizon Agents Hack](https://tokensand.com/horizonagentshack), Sep 25 2026.

### What it does

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

### Run

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

### Files

- `agent.py`: sources, geocoding, working state, forgetting rules, metrics
- `store.py`: long-term memory on RawTree (SQLite fallback)
- `cards.py`: FLUX alert cards
- `llm.py`: local LFM2.5 extraction
- `server.py`: FastAPI with the agent loop in a background thread
- `static/index.html`: Leaflet map, token chart, agent log, recall
