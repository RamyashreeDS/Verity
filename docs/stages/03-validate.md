# Stage 3 — Validate

## Purpose

Apply deterministic checks to structured claims before they enter World State. Validate is the gatekeeper — it catches malformed, stale, duplicate, and logically impossible claims using pure code rules with no LLM involvement.

Fast, cheap, and consistent. If a check can be expressed as a rule, it lives here. Judgment calls do not.

---

## Inputs

```
Claim {
  id, raw_document_id, source_url, source_type,
  crawled_at, published_at, entity, entity_type,
  claim_type, value, confidence, raw_text
}
```

---

## Checks (in order)

### 1. Schema Conformance
Verify all required fields are present and typed correctly.

| Field | Rule |
|---|---|
| `id` | Non-empty string |
| `entity` | Non-empty string |
| `entity_type` | Must be a known enum value |
| `claim_type` | Non-empty string |
| `value` | Non-empty string |
| `confidence` | Float in [0.0, 1.0] |
| `crawled_at` | Valid ISO timestamp, not in the future |
| `source_url` | Valid URL format |

Failure → `REJECTED: schema`

### 2. Timestamp Freshness
Reject claims that are too old to be relevant to the current crisis.

- If `published_at` is present: reject if older than `MAX_CLAIM_AGE_HOURS` (default: 48h)
- If `published_at` is null: use `crawled_at` as a proxy. Apply a wider tolerance (default: 72h) since crawl time ≠ publish time.
- Reject claims with `published_at` in the future (clock skew / bad source data)

Failure → `REJECTED: stale`

### 3. Confidence Threshold
Reject claims below the minimum confidence floor.

- Default floor: `0.3`
- Floor is lower for official source types: `0.2` for `source_type = official`

Failure → `REJECTED: low_confidence`

### 4. Duplicate Detection
Reject claims that are functionally identical to a claim already in World State.

Two claims are duplicates if they share:
- Same `entity` (canonicalized)
- Same `claim_type`
- Same `value` (normalized)
- Same `source_url`
- `published_at` within 1 hour of each other (or both null)

Failure → `REJECTED: duplicate`

### 5. Invariant Checks
Reject claims that violate known logical constraints.

| Invariant | Rule |
|---|---|
| Road status mutex | A road cannot be both `open` and `closed` in the same claim |
| Containment range | Fire containment percentage must be in [0, 100] |
| Shelter capacity | Shelter capacity/occupancy must be non-negative integers |
| Evacuation zone mutex | A zone cannot be both under mandatory evacuation and under no evacuation order |
| No self-contradiction | A single claim cannot assert two mutually exclusive values |

Failure → `REJECTED: invariant`

### 6. Source ID Consistency
Verify that the `source_url` domain is consistent with the declared `source_type`.

Examples:
- `source_type = official` but domain is a social media site → flag as suspicious, downgrade `source_type` to `crawled`
- `source_type = news` but domain is a known official government domain → upgrade to `official`

This is not a rejection — it is a correction applied before the claim proceeds.

---

## Outputs

### Validated Claim
All checks pass. Claim proceeds to World State.
```
ValidatedClaim {
  ...all Claim fields...
  validated_at: timestamp
  corrections: list[string]    // any field corrections applied (e.g. source_type upgrade)
}
```

### Rejected Claim
At least one check fails. Claim is discarded and logged.
```
RejectedClaim {
  ...all Claim fields...
  rejection_reason: enum(schema | stale | low_confidence | duplicate | invariant)
  rejection_detail: string     // human-readable explanation
  rejected_at: timestamp
}
```

---

## Rejection Log

All rejected claims are written to a rejection log (Tinybird) for:
- Monitoring the health of upstream stages
- Diagnosing recurring patterns (e.g. a source consistently producing stale claims)
- Health Monitor ingestion (high rejection rates from a source = source failure signal)

---

## Configuration

```
MAX_CLAIM_AGE_HOURS: int              // default: 48
MAX_CLAIM_AGE_NULL_DATE_HOURS: int    // default: 72
CONFIDENCE_FLOOR: float               // default: 0.3
CONFIDENCE_FLOOR_OFFICIAL: float      // default: 0.2
DEDUP_TIME_WINDOW_HOURS: int          // default: 1
```

---

## Design Notes

- Validate never calls an LLM. Every check is a deterministic function.
- Checks run in the order listed above — a claim that fails schema is not run through invariant checks.
- Corrections (source type upgrades/downgrades) are applied in-place before further checks proceed.
- The rejection log is the Health Monitor's primary signal for upstream stage degradation.
