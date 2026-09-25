# Stage 4 — World State

## Purpose

Maintain the durable, current picture of the active crisis. World State is the single source of truth for what the system currently believes to be true, plus an immutable history of everything it has ever seen.

World State has two layers:
- **RawTree** — append-only history of every validated claim, never modified
- **Dashboard** — the current best understanding of each tracked fact, updated as new claims arrive

---

## Tool: Tinybird

Tinybird is a real-time analytics platform (ClickHouse-backed) used for:
- High-throughput claim ingestion (append to RawTree)
- Real-time queries over current World State (Dashboard)
- Contradiction and staleness queries by Health Monitor
- Dashboard API endpoints consumed by the UI

---

## Data Model

### RawTree (append-only)
Every validated claim is written here exactly once and never modified.

```
rawtree {
  claim_id: string
  raw_document_id: string
  source_url: string
  source_type: LowCardinality(String)
  crawled_at: DateTime
  published_at: Nullable(DateTime)
  entity: string
  entity_type: LowCardinality(String)
  claim_type: string
  value: string
  confidence: Float32
  raw_text: string
  validated_at: DateTime
  ingested_at: DateTime          // when it entered Tinybird
}
ENGINE = MergeTree()
ORDER BY (entity, claim_type, ingested_at)
```

### Dashboard (current truth)
One row per (entity, claim_type) pair. Updated when a new claim supersedes the current best.

```
dashboard {
  entity: string
  entity_type: LowCardinality(String)
  claim_type: string
  current_value: string
  confidence: Float32
  status: LowCardinality(String)    // confirmed | unresolved | low_confidence | conflicted
  last_claim_id: string
  last_updated: DateTime
  conflicting_claim_id: Nullable(String)
}
ENGINE = ReplacingMergeTree(last_updated)
ORDER BY (entity, claim_type)
```

---

## Merge Logic

When a new validated claim arrives, the merge logic decides how it updates the Dashboard:

```
1. Look up existing Dashboard entry for (entity, claim_type)

2. If no existing entry:
      → INSERT new row with status = confirmed (if confidence >= HIGH_CONFIDENCE_THRESHOLD)
        or status = low_confidence (if below threshold)

3. If existing entry found:
      a. Same value as current:
            → Update last_updated, boost confidence (average of old + new)
            → Status remains confirmed / low_confidence

      b. Different value, new confidence > existing confidence:
            → Update to new value
            → If confidence delta > CONFLICT_THRESHOLD: set status = conflicted,
              store old claim_id in conflicting_claim_id
            → Else: set status = confirmed (soft update)

      c. Different value, new confidence <= existing confidence:
            → Do not update current_value
            → If confidence is close (within CONFLICT_TOLERANCE): set status = conflicted
            → Else: discard new claim (existing is more credible)

4. Conflicted entries are never displayed as confirmed on the dashboard
      → Displayed as "unresolved" until Healing Loop resolves them
```

---

## Status Definitions

| Status | Meaning |
|---|---|
| `confirmed` | One or more consistent, sufficiently confident claims support this fact |
| `low_confidence` | Claims exist but none meet the confidence threshold for confirmed |
| `unresolved` | Two or more claims conflict and no resolution has been reached |
| `conflicted` | Active conflict detected, Healing Loop has been notified |
| `stale` | No new claims for this fact within the staleness window (set by Health Monitor) |

---

## Tinybird API Endpoints

The following Pipe endpoints are exposed for the Dashboard UI and Health Monitor:

| Endpoint | Description |
|---|---|
| `GET /dashboard` | Full current World State — all entities, current values, statuses |
| `GET /dashboard/:entity` | Current state for a single entity |
| `GET /dashboard/conflicted` | All entries in `conflicted` or `unresolved` status |
| `GET /dashboard/stale` | All entries not updated within staleness window |
| `GET /rawtree/:entity` | Full claim history for an entity |
| `GET /health/rejection_rate` | Rejection rate per source over last N hours |

---

## Conflict Handling

Conflicts are not resolved in World State — that is the Healing Loop's job. World State only:
1. Detects that a conflict exists (two claims with different values for the same fact)
2. Records both the current and conflicting claim IDs
3. Sets status to `conflicted`
4. Does not pick a winner

The dashboard displays conflicted entries as "unresolved" rather than choosing one value. This is intentional — a wrong confident answer is worse than an honest "unconfirmed."

---

## Configuration

```
TINYBIRD_API_KEY: string
TINYBIRD_HOST: string
HIGH_CONFIDENCE_THRESHOLD: float     // default: 0.7
CONFLICT_THRESHOLD: float            // confidence delta to trigger conflict (default: 0.2)
CONFLICT_TOLERANCE: float            // within this delta, claims are considered tied (default: 0.1)
STALENESS_WINDOW_HOURS: int          // how long before an entry is marked stale (default: 6)
```

---

## Design Notes

- RawTree is immutable. It is the audit log and the source for all historical analysis.
- Dashboard rows are replaced (not mutated) using ClickHouse ReplacingMergeTree — always keyed on (entity, claim_type).
- World State never deletes entries. Stale entries stay in the Dashboard marked `stale` — absence of evidence is itself evidence.
- Tinybird's real-time ingest means Health Monitor can query the Dashboard seconds after a new claim arrives.
