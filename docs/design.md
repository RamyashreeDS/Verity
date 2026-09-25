# Verity — Design Document

## Overview

Verity is a self-healing information pipeline for tracking natural disasters and accidents in real time. It monitors wildfires, floods, earthquakes, and similar events — and crucially, monitors its own reliability, detecting when its picture of the world has gone stale, contradictory, or broken, and healing before that failure reaches the dashboard.

---

## Problem Statement

During a live disaster, information is scattered, frequently contradictory, and changes by the minute — evacuation status, road closures, shelter availability. Most monitoring tools aggregate and display; they don't know when their own understanding has drifted wrong. Bad information in this domain is not just a bug — it can put people at real risk.

Verity builds a monitor that watches itself, not just the disaster.

---

## Tech Stack

| Layer | Tool | Role |
|---|---|---|
| Crawling | Nimble | Web scraping, JS rendering, proxy handling for news and government sites |
| AI / Reasoning | Liquid AI (LFM) | Claim extraction, classification, contradiction diagnosis, healing proposals |
| Storage & Analytics | Tinybird | Real-time data ingestion, RawTree history, World State queries, Dashboard APIs |
| Visuals | Black Forest Labs (FLUX) | Generate visual situation maps, area overlays, crisis state snapshots |

---

## Data Sources

### Government / Official (structured, free)
| Source | Data | Endpoint |
|---|---|---|
| USGS | Earthquakes, real-time | earthquake.usgs.gov/fdsnws |
| NOAA / NWS | Weather alerts, floods | api.weather.gov |
| NASA FIRMS | Active wildfires (satellite) | firms.modaps.eosdis.nasa.gov |
| FEMA | Disaster declarations | fema.gov/api/open |
| GDACS | Global disasters (UN-backed) | gdacs.org/xml |

### News & Text
| Source | Notes |
|---|---|
| GDELT Project | Free, updated every 15 min, global news events |
| NewsAPI.org | Free tier, keyword search across 80k+ sources |
| Local news RSS feeds | Crawled via Nimble, highest specificity per event |

### Social / Crowdsourced
| Source | Notes |
|---|---|
| Reddit API | Subreddits: r/wildfires, r/weather, local city subs |
| Bluesky API | Free, open, increasingly active during disasters |

### Road & Infrastructure
| Source | Notes |
|---|---|
| State 511 feeds | DOT road closure/traffic feeds |
| OpenStreetMap Overpass API | Free, queryable map and infrastructure data |

---

## Architecture

```
CRISIS QUERY (wildfire / flood / earthquake / etc.)
        │
        ▼
1. SENSE          Nimble → crawl → extract → discover new information
        │
        ▼
2. UNDERSTAND     Liquid AI → extract claims → classify → identify entities → compare
                  output: structured evidence only
        │
        ▼
3. VALIDATE       timestamps · duplicates · schemas · source IDs
                  state rules · confidence thresholds · invariants
                  (deterministic code only — no LLM)
        │
        ▼
4. WORLD STATE    🔥 Fire  🚨 Evacuations  🛣 Roads  🏠 Shelters  🌬 Weather  ⚡ Utilities  ❓ Unknowns
                  stored in Tinybird (RawTree + Dashboard)
        │
   ┌────┴────┐
   ▼         ▼
RawTree   Dashboard ── FLUX visuals (BFL)
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
6. HEALING LOOP   Liquid AI → detect → diagnose → propose → verify → test → commit
                                                             └──▶ reject / rollback
```

---

## Pipeline Stages

### Stage 1 — Sense
- **Inputs:** Crisis query (event type + location + time window)
- **Tools:** Nimble API for crawling news sites, government pages, social feeds
- **Outputs:** Raw text documents with source URL, crawl timestamp, content
- **Notes:** Deduplication at crawl level (URL + content hash). Nimble handles JS rendering and proxy rotation.

### Stage 2 — Understand
- **Inputs:** Raw crawled documents from Sense
- **Tools:** Liquid AI LFM
- **Outputs:** Structured `Claim` objects — entity, claim type, value, confidence score, source, timestamp
- **Notes:** LLM call is reserved for this stage. Output is compact structured evidence, not raw text. Compression boundary — noisy high-volume text becomes small structured records before anything downstream.

### Stage 3 — Validate
- **Inputs:** Structured claims from Understand
- **Tools:** Deterministic code only
- **Checks:**
  - Schema conformance
  - Timestamp freshness (reject claims older than threshold)
  - Duplicate detection against existing World State
  - Confidence threshold floor
  - Invariant checks (e.g. a road cannot be both open and closed from the same source)
- **Outputs:** Validated claims ready for World State, or rejected with reason

### Stage 4 — World State
- **Inputs:** Validated claims
- **Tools:** Tinybird
- **Stores:**
  - `RawTree` — append-only full history of all validated claims
  - `Dashboard` — current truth per entity/fact, updated on each new claim
- **Outputs:** Live queryable state, powering the dashboard UI and Health Monitor

### Stage 5 — Health Monitor
- **Inputs:** World State (Tinybird queries)
- **Checks:**
  - Staleness — last update for a tracked entity exceeds threshold
  - Contradiction — two claims conflict on the same fact for the same entity
  - Missing data — expected entities/fields absent given active crisis type
  - Loop detection — same claim cycling through pipeline repeatedly
  - Source failure — a previously active source has gone silent
- **Outputs:** Health events with type, severity, affected entity, and timestamp

### Stage 6 — Healing Loop
- **Inputs:** Health events from Health Monitor
- **Tools:** Liquid AI LFM
- **Steps:** Detect → Diagnose → Propose → Verify → Test → Commit (or Reject/Rollback)
- **Notes:**
  - Every proposed fix must pass Verify + Test before Commit
  - Rollback is the default when a proposed fix doesn't hold up
  - Reasoning patterns are stored (not per-source trust scores) to improve future healing

---

## Core Data Models

### Claim
```
{
  id: string
  source_url: string
  source_type: enum(official | news | social | crawled)
  crawled_at: timestamp
  published_at: timestamp
  entity: string              // canonical name (road, shelter, area)
  entity_type: enum(road | shelter | evacuation_zone | fire | flood | utility)
  claim_type: string          // e.g. "road_status", "shelter_capacity"
  value: string               // e.g. "closed", "open", "500 people"
  confidence: float           // 0.0 – 1.0
  raw_text: string            // source excerpt
}
```

### WorldStateEntry
```
{
  entity: string
  entity_type: enum
  fact: string
  current_value: string
  confidence: float
  last_updated: timestamp
  source_claim_id: string
  status: enum(confirmed | unresolved | low_confidence | conflicted)
}
```

### HealthEvent
```
{
  id: string
  type: enum(stale | contradiction | missing | loop | source_failure)
  severity: enum(low | medium | high | critical)
  entity: string
  description: string
  detected_at: timestamp
  resolved: boolean
}
```

---

## Design Principles

1. **Prefer silence over confident flapping.** When sources disagree and evidence is thin, mark the fact as `unresolved` or `low_confidence` rather than picking a side.
2. **Verify before committing.** Every healing action goes through Verify → Test before Commit. Reject/Rollback is the default if a fix doesn't hold up.
3. **Deterministic checks first, judgment second.** Validate is pure code — cheap, fast, consistent. Liquid AI is reserved for genuine judgment calls (Understand, Diagnose, Propose).
4. **Compression at the Sense → Understand boundary.** High-volume noisy text is compressed into compact structured claims before anything downstream reasons over it.

---

## Known Limitations

- **Validate checks consistency, not truth.** A well-formed, timely, deduplicated claim can still be factually wrong.
- **Misinformation risk.** Crisis events attract the highest volume of unverified and sometimes deliberately false reports. Source credibility scoring is a needed next step.
- **Novel contradiction shapes.** The Healing Loop handles familiar contradiction patterns well; first-occurrence novel patterns can be slower and less consistent.
- **Memory generalization.** Healing memory must store reasoning patterns, not per-source trust scores.

---

## Demo Scenario

1. Seed two sources with a genuine conflict (e.g. conflicting road-closure status for the same road).
2. Show Health Monitor detecting the contradiction and the Healing Loop reasoning about it.
3. Show the system choosing `unresolved` / `low_confidence` display over a confident guess.
4. Feed in corroborating evidence and show the conflict resolving and committing to World State.

---

## Build Order

1. Core data models (`Claim`, `WorldStateEntry`, `HealthEvent`)
2. Tinybird schema setup (RawTree + Dashboard tables)
3. Sense stage — Nimble integration + crawl deduplication
4. Understand stage — Liquid AI claim extraction pipeline
5. Validate stage — deterministic checks
6. World State — claim merging logic
7. Health Monitor — staleness + contradiction detectors
8. Healing Loop — Liquid AI diagnose/propose/verify chain
9. Dashboard UI + FLUX visual generation

---

*Status: Design complete. Implementation not started.*
