# Stage 2 — Understand

## Purpose

Transform raw crawled documents into structured, machine-readable claims. This is the compression boundary of the pipeline — noisy, high-volume text becomes compact structured evidence before anything downstream reasons over it.

The Understand stage is the primary LLM stage. Liquid AI LFM handles all extraction and classification here. No LLM calls happen in Validate, World State, or Health Monitor.

---

## Tool: Liquid AI (LFM)

Liquid Foundation Models are used for:
- Named entity recognition and canonicalization
- Claim extraction (what is being asserted about which entity)
- Classification (claim type, event type, source reliability signal)
- Confidence estimation

LFMs are well-suited here because they handle sequential, time-ordered text efficiently and are leaner than GPT-class models — important for a pipeline that runs continuously.

---

## Inputs

```
RawDocument {
  id: string
  source_url: string
  source_type: enum(official | news | social | crawled)
  crawled_at: timestamp
  published_at: timestamp
  title: string
  content: string
  content_hash: string
  crisis_query_id: string
}
```

---

## Process

```
1. Chunk long documents
      → split content into overlapping chunks if > MAX_CHUNK_TOKENS
      → preserve sentence boundaries

2. For each chunk, call Liquid AI LFM with extraction prompt
      → extract all discrete claims in the chunk
      → for each claim: identify entity, claim type, value, confidence

3. Canonicalize entities
      → map surface forms to canonical names
         e.g. "the 101", "US-101", "Highway 101" → "US-101"
      → use location context from CrisisQuery to disambiguate

4. Deduplicate claims within document
      → same entity + claim_type from same source = keep highest confidence

5. Emit one Claim per extracted assertion
```

---

## Outputs

```
Claim {
  id: string                // uuid
  raw_document_id: string   // back-reference
  source_url: string
  source_type: enum(official | news | social | crawled)
  crawled_at: timestamp
  published_at: timestamp
  entity: string            // canonical name
  entity_type: enum(road | shelter | evacuation_zone | fire | flood | utility | weather)
  claim_type: string        // e.g. "road_status", "shelter_capacity", "fire_containment_pct"
  value: string             // e.g. "closed", "open", "320 people", "45%"
  confidence: float         // 0.0 – 1.0
  raw_text: string          // source excerpt that this claim was extracted from
}
```

---

## Extraction Prompt Design

The LFM is given a structured prompt that:
1. States the active crisis context (type, location, time window)
2. Provides the document text
3. Asks for claims in a strict JSON schema
4. Instructs the model to prefer `null` / low confidence over fabricating a value
5. Instructs the model to extract multiple claims per document if multiple entities are mentioned

The model is instructed to output only structured JSON — no prose. Malformed JSON responses trigger a retry (up to 2 retries), then the document is logged as `understand_failed` and skipped.

---

## Entity Canonicalization

Entity canonicalization runs as a post-processing step after LFM extraction:

- **Roads:** Normalize to standard highway designations (e.g. "the 5" → "I-5")
- **Shelters:** Match against a known shelter registry for the active event
- **Evacuation zones:** Match against official zone names for the jurisdiction
- **Geographic areas:** Match to canonical place names (city, county, neighborhood)

Unrecognized entities are retained as-is but flagged with `entity_canonical: false`.

---

## Confidence Scoring

The LFM assigns a confidence score 0.0–1.0 based on:
- How explicitly the claim is stated (direct assertion vs. implication)
- Hedging language ("reportedly", "unconfirmed", "sources say")
- Source type (official feeds get a confidence boost via a post-processing multiplier)

| Source Type | Confidence Multiplier |
|---|---|
| official | 1.0 (no change) |
| news | 0.9 |
| social | 0.7 |
| crawled | 0.8 |

Post-multiplier confidence is capped at 1.0.

---

## Error Handling

| Error | Behavior |
|---|---|
| LFM returns malformed JSON | Retry up to 2 times. Skip document after 3 failures, log `understand_failed`. |
| LFM returns empty claims list | Log `understand_no_claims`, skip document. Not an error — some documents have no extractable claims. |
| Entity canonicalization fails | Retain raw entity name, set `entity_canonical: false`. Do not discard the claim. |
| Document too long after chunking | Process first N chunks (default: 5), log that document was truncated. |

---

## Configuration

```
LIQUID_AI_API_KEY: string
LIQUID_AI_MODEL: string              // model version to use
MAX_CHUNK_TOKENS: int                // default: 2048
MAX_CHUNKS_PER_DOCUMENT: int         // default: 5
LFM_TEMPERATURE: float               // default: 0.0 (deterministic extraction)
CONFIDENCE_FLOOR: float              // claims below this are dropped (default: 0.2)
```

---

## Performance Notes

- LFM calls are the highest-latency step per document. Batch documents where the API supports it.
- Temperature 0.0 for deterministic, reproducible extraction.
- The output volume is typically 5–20 claims per document. A run processing 50 documents produces 250–1000 claims entering Validate.
