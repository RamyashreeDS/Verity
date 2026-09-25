import json
import asyncio
from typing import Optional

from app.config import settings
from app.models import Claim, RawDocument, SourceType, EntityType
from app.stages import mock_data

SOURCE_CONFIDENCE_MULTIPLIERS = {
    SourceType.official: 1.0,
    SourceType.news: 0.9,
    SourceType.crawled: 0.8,
    SourceType.social: 0.7,
}

MAX_CHUNK_TOKENS = 2048
MAX_CHUNKS_PER_DOC = 5

ENTITY_TYPE_MAP = {
    "road": EntityType.road,
    "shelter": EntityType.shelter,
    "evacuation_zone": EntityType.evacuation_zone,
    "fire": EntityType.fire,
    "flood": EntityType.flood,
    "utility": EntityType.utility,
    "weather": EntityType.weather,
}

EXTRACTION_SYSTEM_PROMPT = """You are a crisis information extraction system.
Extract all discrete factual claims from the provided text about an active crisis.
Return ONLY a valid JSON array of claim objects. No prose, no explanation.

Each claim object must have:
- entity: canonical name of the thing being described (road name, shelter name, area name, etc.)
- entity_type: one of [road, shelter, evacuation_zone, fire, flood, utility, weather]
- claim_type: what is being asserted (e.g. road_status, shelter_capacity, fire_containment_pct, evacuation_order)
- value: the asserted value (e.g. "closed", "open", "45%", "mandatory evacuation")
- confidence: float 0.0-1.0 based on how explicitly and authoritatively the claim is stated
- raw_text: the exact excerpt from the source that supports this claim

Rules:
- Prefer null or low confidence over fabricating a value.
- If the text hedges ("reportedly", "unconfirmed"), lower confidence.
- Extract multiple claims if multiple entities are mentioned.
- If no extractable claims exist, return an empty array [].
"""


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_TOKENS * 4) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    sentences = text.replace("\n", " ").split(". ")
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
            current = sentence
        else:
            current += sentence + ". "
    if current:
        chunks.append(current.strip())
    return chunks[:MAX_CHUNKS_PER_DOC]


def _apply_confidence_multiplier(confidence: float, source_type: SourceType) -> float:
    multiplier = SOURCE_CONFIDENCE_MULTIPLIERS.get(source_type, 0.8)
    return min(confidence * multiplier, 1.0)


def _canonicalize_entity(entity: str, entity_type: EntityType) -> str:
    entity = entity.strip()
    if entity_type == EntityType.road:
        replacements = {
            "the 101": "US-101", "highway 101": "US-101", "hwy 101": "US-101",
            "the 5": "I-5", "interstate 5": "I-5", "i5": "I-5",
            "the 405": "I-405", "interstate 405": "I-405",
        }
        return replacements.get(entity.lower(), entity)
    return entity


def _sync_liquid_complete(messages: list[dict], model: str, api_key: str, base_url: str) -> str:
    from liquidai import Client
    liq = Client(base_url=base_url, api_key=api_key)
    response = liq.complete(messages, model=model, temperature=0.0, max_new_tokens=1024)
    return response["message"]["content"]


async def _call_liquid_ai(chunk: str, context: str) -> list[dict]:
    if not settings.liquid_ai_api_key or not settings.liquid_url:
        return []

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Crisis context: {context}\n\nText to analyze:\n{chunk}"},
    ]

    for attempt in range(3):
        try:
            text = await asyncio.to_thread(
                _sync_liquid_complete,
                messages,
                settings.liquid_ai_model,
                settings.liquid_ai_api_key,
                settings.liquid_url,
            )
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except (json.JSONDecodeError, KeyError):
            if attempt == 2:
                return []
            await asyncio.sleep(1)
        except Exception:
            return []

    return []


def _parse_raw_claims(
    raw_claims: list[dict],
    doc: RawDocument,
) -> list[Claim]:
    claims = []
    seen = set()

    for raw in raw_claims:
        try:
            entity_type_str = raw.get("entity_type", "").lower()
            entity_type = ENTITY_TYPE_MAP.get(entity_type_str)
            if not entity_type:
                continue

            entity = _canonicalize_entity(raw.get("entity", ""), entity_type)
            claim_type = raw.get("claim_type", "").strip()
            value = str(raw.get("value", "")).strip()
            raw_confidence = float(raw.get("confidence", 0.5))
            raw_text = raw.get("raw_text", "")[:500]

            if not entity or not claim_type or not value:
                continue

            # dedup within document
            key = (entity.lower(), claim_type.lower(), value.lower())
            if key in seen:
                continue
            seen.add(key)

            confidence = _apply_confidence_multiplier(raw_confidence, doc.source_type)

            claims.append(
                Claim(
                    raw_document_id=doc.id,
                    source_url=doc.source_url,
                    source_type=doc.source_type,
                    crawled_at=doc.crawled_at,
                    published_at=doc.published_at,
                    entity=entity,
                    entity_type=entity_type,
                    claim_type=claim_type,
                    value=value,
                    confidence=confidence,
                    raw_text=raw_text,
                    entity_canonical=entity != raw.get("entity", ""),
                )
            )
        except Exception:
            continue

    return claims


async def process_document(doc: RawDocument, crisis_context: str) -> list[Claim]:
    chunks = _chunk_text(doc.content)
    results = await asyncio.gather(
        *[_call_liquid_ai(chunk, crisis_context) for chunk in chunks]
    )
    all_raw = [claim for chunk_claims in results for claim in chunk_claims]
    return _parse_raw_claims(all_raw, doc)


async def run(documents: list[RawDocument], crisis_context: str) -> list[Claim]:
    # ── DEMO MODE ────────────────────────────────────────────────────────────
    if settings.demo_mode:
        return mock_data.MOCK_CLAIMS
    # ── END DEMO MODE ─────────────────────────────────────────────────────────

    all_claims: list[Claim] = []
    for doc in documents:
        claims = await process_document(doc, crisis_context)
        all_claims.extend(claims)
    return all_claims
