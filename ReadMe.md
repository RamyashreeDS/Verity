# Emergency Crisis Monitor

A self-healing information pipeline for tracking natural disasters and accidents in real time — wildfires, floods, earthquakes, and similar events.

## The problem

During a live disaster, information is scattered across many sources, frequently contradictory, and changes by the minute — evacuation status, road closures, shelter availability. Getting it wrong isn't just a bug: bad information at this layer can put people at real risk. Most monitoring tools aggregate and display; they don't know when their own picture of the world has gone stale, contradictory, or broken.

This project builds a monitor that watches its own reliability, not just the disaster — it detects when its understanding is compromised and heals itself before that failure reaches the dashboard.

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
