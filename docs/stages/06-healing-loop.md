# Stage 6 — Healing Loop

## Purpose

Diagnose and repair problems detected by the Health Monitor. The Healing Loop is the system's self-repair mechanism — it takes a health event, reasons about its cause, proposes a fix, verifies the fix holds, and commits it to World State. If verification fails, it rolls back.

Commit and Rollback is the only binary outcome. There is no partial healing.

---

## Tool: Liquid AI (LFM)

Liquid AI LFMs handle the two judgment-heavy steps:
- **Diagnose** — reason about why the health event occurred
- **Propose** — suggest a specific resolution action

All other steps (Detect, Verify, Test, Commit, Rollback) are deterministic code.

---

## Inputs

```
HealthEvent {
  id, type, severity, entity, entity_type, claim_type,
  description, detected_at, context, resolved
}
```

Plus read access to:
- World State Dashboard (current truth for the affected entity)
- RawTree (full claim history for the affected entity)
- Rejection log (recent rejections related to the entity/source)

---

## Process

```
DETECT
  HealthEvent received from queue
  Fetch current Dashboard entry and RawTree history for affected entity
  Fetch related HealthEvents (same entity, unresolved)
        │
        ▼
DIAGNOSE  [Liquid AI LFM]
  Given: health event type, current world state, claim history, related events
  Output: diagnosis struct {
    root_cause: string         // human-readable explanation
    cause_type: enum           // see below
    affected_claims: list[id]  // which claims are involved
    proposed_action_type: enum // what class of fix to propose
  }
        │
        ▼
PROPOSE  [Liquid AI LFM]
  Given: diagnosis, claim history, world state
  Output: HealingProposal {
    action: enum               // see actions below
    target_entity: string
    target_claim_type: string
    new_value: string          // if action = update_value
    new_status: string         // if action = update_status
    evicted_claim_ids: list    // if action = evict_claims
    reasoning: string          // why this fix is correct
    confidence: float
  }
        │
        ▼
VERIFY  [deterministic]
  Check that the proposal is internally consistent and doesn't violate invariants
  Re-run the Validate invariant checks against the proposed new state
  Check that the proposal would actually resolve the health event
  Check that the proposal doesn't create new conflicts in World State
        │
      pass?
     /     \
   yes      no
    │        │
    ▼        ▼
  TEST     REJECT → log, mark HealthEvent unresolvable, alert
  [deterministic]
  Simulate applying the proposal to a snapshot of World State
  Re-run Health Monitor checks against the simulated state
  Confirm the original health event would not re-trigger
        │
      pass?
     /     \
   yes      no
    │        │
    ▼        ▼
 COMMIT   ROLLBACK → discard simulation, log, mark HealthEvent as retry
  Apply the proposal to the live Dashboard in Tinybird
  Mark the HealthEvent as resolved
  Write a HealingRecord to the audit log
```

---

## Cause Types

| Cause Type | Description |
|---|---|
| `source_conflict` | Two sources disagree on the same fact |
| `source_stale` | A source has stopped providing updates |
| `data_gap` | Expected data is missing entirely |
| `clock_skew` | Timestamps from a source are unreliable |
| `propagation_loop` | Same claim recycling without effect |
| `source_degraded` | A source is consistently producing bad data |
| `unknown` | Cause cannot be determined |

---

## Healing Actions

| Action | Description |
|---|---|
| `update_value` | Replace current_value in Dashboard with a new value |
| `update_status` | Change status (e.g. `conflicted` → `unresolved`, `stale` → `low_confidence`) |
| `evict_claims` | Mark specific claims as unreliable; remove their contribution to Dashboard |
| `mark_unresolvable` | Mark the fact as unresolvable with current evidence; display as unknown |
| `request_resense` | Trigger a new Sense run targeting the affected entity/source |
| `suppress_source` | Temporarily stop accepting claims from a degraded source |

---

## Healing Record (Audit Log)

Every committed healing action writes an immutable record:

```
HealingRecord {
  id: string
  health_event_id: string
  diagnosed_cause_type: string
  proposed_action: string
  action_detail: dict
  lfm_reasoning: string
  verify_passed: bool
  test_passed: bool
  committed: bool
  committed_at: Nullable(timestamp)
  rolled_back: bool
  rolled_back_reason: Nullable(string)
}
```

This audit log is used to:
- Build a library of reasoning patterns for future healing
- Identify recurring failure modes
- Support human review of automated decisions

---

## Reasoning Pattern Memory

After each successful commit, the Healing Loop extracts and stores the reasoning pattern:

```
ReasoningPattern {
  cause_type: string
  context_signature: string      // hash of the key features of the situation
  successful_action: string
  reasoning_summary: string
}
```

On future diagnoses, the LFM is given matching reasoning patterns as context. This improves consistency on repeated failure shapes without hard-coding source-specific trust scores.

Patterns store the *logic*, not the *source* — e.g. "official feeds outrank uncorroborated social posts on the same claim" rather than "trust Reuters more than Twitter."

---

## Failure Modes

| Scenario | Behavior |
|---|---|
| Verify fails | Reject proposal. Log. Mark HealthEvent as `retry` (up to MAX_RETRIES). |
| Test fails | Rollback simulation. Log. Mark as `retry`. |
| Max retries exceeded | Mark HealthEvent as `unresolvable`. Alert operator. |
| LFM returns malformed proposal | Retry LFM call up to 2 times, then mark as `retry`. |
| Proposal would create new conflict | Verify catches this — treated as verify failure. |

---

## Configuration

```
LIQUID_AI_API_KEY: string
LIQUID_AI_MODEL: string
MAX_RETRIES: int                    // default: 3
HEALING_CONFIDENCE_FLOOR: float     // proposals below this are rejected (default: 0.6)
PATTERN_MEMORY_MAX: int             // max reasoning patterns to include in LFM context (default: 5)
COMMIT_TIMEOUT_SECONDS: int         // default: 30
```

---

## Design Notes

- Rollback is the default. A proposal that merely looks plausible is not good enough — it must pass both Verify (logical consistency) and Test (simulated outcome).
- The LFM is never given write access to World State directly. It only produces proposals; deterministic code decides whether to apply them.
- Healing Records are append-only. No healing decision is ever deleted, even if superseded.
- `request_resense` is the lightest action — it triggers upstream rather than modifying state. Prefer it for staleness over making assumptions about what the current value should be.
