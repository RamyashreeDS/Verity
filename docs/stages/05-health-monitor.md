# Stage 5 — Health Monitor

## Purpose

Watch the pipeline itself — not just the crisis data — for signs that the system's picture of the world is becoming unreliable. The Health Monitor runs continuously in the background and emits health events when it detects problems.

It does not fix anything. It detects, classifies, and hands off to the Healing Loop.

---

## Inputs

Health Monitor queries Tinybird on a schedule:
- Dashboard (current World State)
- RawTree (claim history)
- Rejection log (from Validate)
- Pipeline run logs (from Sense and Understand)

---

## Checks

### 1. Staleness Detection
An entity's fact is stale when no new supporting claims have arrived within the expected window.

```
For each (entity, claim_type) in Dashboard:
  if now() - last_updated > STALENESS_THRESHOLD[entity_type]:
    emit HealthEvent(type=stale, severity=based on entity_type criticality)
```

Staleness thresholds by entity type (configurable):

| Entity Type | Threshold |
|---|---|
| evacuation_zone | 2 hours |
| road | 3 hours |
| shelter | 4 hours |
| fire | 4 hours |
| flood | 4 hours |
| weather | 6 hours |
| utility | 8 hours |

Criticality tiers affect severity:
- `evacuation_zone`, `road` → high severity when stale
- `shelter`, `fire`, `flood` → medium
- `weather`, `utility` → low

### 2. Contradiction Detection
Two claims in the Dashboard conflict on the same (entity, claim_type).

```
For each Dashboard entry with status = conflicted:
  if conflict has existed for > CONFLICT_GRACE_PERIOD (default: 15 min):
    emit HealthEvent(type=contradiction, severity=high)
```

The grace period avoids noise from rapid-fire updates that self-resolve.

### 3. Missing Data Detection
Expected entities are absent from the Dashboard given the active crisis type.

```
For each active crisis:
  check that required entity types are represented:
    - wildfire: fire, evacuation_zone, road
    - flood: flood, road, shelter
    - earthquake: road, utility, shelter
  if a required entity type has zero entries:
    emit HealthEvent(type=missing, severity=medium)
```

### 4. Loop Detection
The same claim or nearly-identical claim is cycling through the pipeline repeatedly without updating World State.

```
For each entity in RawTree:
  if >N identical (entity, claim_type, value) claims have been ingested
     in the last LOOP_WINDOW_MINUTES without any Dashboard update:
    emit HealthEvent(type=loop, severity=medium)
```

### 5. Source Failure Detection
A previously active source has gone silent.

```
For each known source domain that produced claims in the last 24h:
  if no new claims from that source in SOURCE_SILENCE_THRESHOLD (default: 6h):
    emit HealthEvent(type=source_failure, severity=low)

For official sources (USGS, NOAA, CAL FIRE):
  threshold is tighter: 2h
  severity = high
```

### 6. High Rejection Rate
A source is generating claims that Validate is consistently rejecting.

```
For each source_url domain:
  compute rejection_rate = rejected_claims / total_claims in last N hours
  if rejection_rate > REJECTION_RATE_THRESHOLD (default: 0.5):
    emit HealthEvent(type=source_degraded, severity=medium)
```

---

## Outputs

```
HealthEvent {
  id: string
  type: enum(stale | contradiction | missing | loop | source_failure | source_degraded)
  severity: enum(low | medium | high | critical)
  entity: string                      // which entity is affected (null for pipeline-wide issues)
  entity_type: string
  claim_type: string                  // which fact type is affected
  description: string                 // human-readable summary
  detected_at: timestamp
  context: dict                       // additional data for Healing Loop (e.g. conflicting claim IDs)
  resolved: bool                      // updated by Healing Loop on resolution
  resolved_at: Nullable(timestamp)
}
```

---

## Run Schedule

Health Monitor runs on two cadences:

| Check | Frequency |
|---|---|
| Staleness | Every 5 minutes |
| Contradiction | Every 2 minutes |
| Missing data | Every 10 minutes |
| Loop detection | Every 5 minutes |
| Source failure | Every 10 minutes |
| High rejection rate | Every 15 minutes |

---

## Deduplication

Health Monitor deduplicates its own events — it does not re-emit a HealthEvent for a problem it already flagged and that has not yet been resolved.

```
Before emitting a new HealthEvent:
  check if an open (resolved=false) event of the same type + entity + claim_type exists
  if yes: update its context if new information is available, do not emit a duplicate
```

---

## Routing to Healing Loop

All emitted HealthEvents are written to a queue consumed by the Healing Loop. Severity determines priority:

| Severity | Queue Priority |
|---|---|
| critical | Immediate |
| high | < 1 minute |
| medium | < 5 minutes |
| low | < 15 minutes |

---

## Configuration

```
STALENESS_THRESHOLD_*: int              // per entity type, in hours
CONFLICT_GRACE_PERIOD_MINUTES: int      // default: 15
LOOP_WINDOW_MINUTES: int                // default: 30
LOOP_COUNT_THRESHOLD: int               // default: 5
SOURCE_SILENCE_THRESHOLD_HOURS: int     // default: 6
OFFICIAL_SOURCE_SILENCE_THRESHOLD_HOURS: int   // default: 2
REJECTION_RATE_THRESHOLD: float         // default: 0.5
REJECTION_RATE_WINDOW_HOURS: int        // default: 3
```
