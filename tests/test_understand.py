from unittest.mock import AsyncMock, patch, MagicMock
from datetime import timezone
from app.models import RawDocument, SourceType, EntityType
from app.stages.understand import (
    _apply_confidence_multiplier,
    _canonicalize_entity,
    _chunk_text,
    _parse_raw_claims,
    run,
)
from conftest import now


def make_raw_doc(**overrides) -> RawDocument:
    import hashlib
    content = overrides.get("content", "US-101 is closed due to wildfire.")
    base = dict(
        source_url="https://example-news.com/article",
        source_type=SourceType.news,
        crawled_at=now(),
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        crisis_query_id="query-1",
    )
    base.update(overrides)
    return RawDocument(**base)


# ── Confidence multipliers ─────────────────────────────────────────────────────

def test_official_source_multiplier_is_one():
    result = _apply_confidence_multiplier(0.8, SourceType.official)
    assert result == 0.8


def test_social_source_multiplier_reduces_confidence():
    result = _apply_confidence_multiplier(0.8, SourceType.social)
    assert result < 0.8


def test_news_source_multiplier_slightly_reduces_confidence():
    result = _apply_confidence_multiplier(1.0, SourceType.news)
    assert result == 0.9


def test_confidence_capped_at_one_after_multiplier():
    result = _apply_confidence_multiplier(1.0, SourceType.official)
    assert result <= 1.0


def test_social_multiplier_exact_value():
    result = _apply_confidence_multiplier(1.0, SourceType.social)
    assert result == 0.7


# ── Entity canonicalization ────────────────────────────────────────────────────

def test_highway_101_variants_canonicalized():
    assert _canonicalize_entity("the 101", EntityType.road) == "US-101"
    assert _canonicalize_entity("Highway 101", EntityType.road) == "US-101"
    assert _canonicalize_entity("hwy 101", EntityType.road) == "US-101"


def test_interstate_5_variants_canonicalized():
    assert _canonicalize_entity("the 5", EntityType.road) == "I-5"
    assert _canonicalize_entity("interstate 5", EntityType.road) == "I-5"
    assert _canonicalize_entity("i5", EntityType.road) == "I-5"


def test_unknown_road_returned_as_is():
    assert _canonicalize_entity("Route 66", EntityType.road) == "Route 66"


def test_non_road_entity_returned_as_is():
    result = _canonicalize_entity("Riverside Shelter", EntityType.shelter)
    assert result == "Riverside Shelter"


# ── Text chunking ──────────────────────────────────────────────────────────────

def test_short_text_not_chunked():
    text = "Short text."
    chunks = _chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_long_text_split_into_chunks():
    text = ". ".join(["Sentence number " + str(i) + " contains enough words to make it long" for i in range(300)])
    chunks = _chunk_text(text)
    assert len(chunks) > 1


def test_chunks_capped_at_max():
    text = ". ".join(["Long sentence " + str(i) for i in range(500)])
    chunks = _chunk_text(text)
    assert len(chunks) <= 5


# ── Claim parsing ──────────────────────────────────────────────────────────────

def test_valid_raw_claim_parsed_correctly():
    doc = make_raw_doc()
    raw = [{
        "entity": "US-101",
        "entity_type": "road",
        "claim_type": "road_status",
        "value": "closed",
        "confidence": 0.9,
        "raw_text": "US-101 is closed due to wildfire.",
    }]
    claims = _parse_raw_claims(raw, doc)
    assert len(claims) == 1
    assert claims[0].entity == "US-101"
    assert claims[0].claim_type == "road_status"
    assert claims[0].value == "closed"


def test_unknown_entity_type_skipped():
    doc = make_raw_doc()
    raw = [{"entity": "US-101", "entity_type": "spaceship", "claim_type": "status", "value": "ok", "confidence": 0.8, "raw_text": ""}]
    claims = _parse_raw_claims(raw, doc)
    assert len(claims) == 0


def test_missing_entity_skipped():
    doc = make_raw_doc()
    raw = [{"entity": "", "entity_type": "road", "claim_type": "road_status", "value": "closed", "confidence": 0.8, "raw_text": ""}]
    claims = _parse_raw_claims(raw, doc)
    assert len(claims) == 0


def test_duplicate_within_document_deduped():
    doc = make_raw_doc()
    raw = [
        {"entity": "US-101", "entity_type": "road", "claim_type": "road_status", "value": "closed", "confidence": 0.9, "raw_text": "text"},
        {"entity": "US-101", "entity_type": "road", "claim_type": "road_status", "value": "closed", "confidence": 0.7, "raw_text": "text"},
    ]
    claims = _parse_raw_claims(raw, doc)
    assert len(claims) == 1


def test_different_entities_not_deduped():
    doc = make_raw_doc()
    raw = [
        {"entity": "US-101", "entity_type": "road", "claim_type": "road_status", "value": "closed", "confidence": 0.9, "raw_text": "text"},
        {"entity": "I-5", "entity_type": "road", "claim_type": "road_status", "value": "open", "confidence": 0.8, "raw_text": "text"},
    ]
    claims = _parse_raw_claims(raw, doc)
    assert len(claims) == 2


def test_confidence_multiplier_applied_in_parse():
    doc = make_raw_doc(source_type=SourceType.social)
    raw = [{"entity": "US-101", "entity_type": "road", "claim_type": "road_status", "value": "closed", "confidence": 1.0, "raw_text": "text"}]
    claims = _parse_raw_claims(raw, doc)
    assert claims[0].confidence == 0.7


# ── Run without API key ────────────────────────────────────────────────────────

async def test_run_returns_empty_without_api_key():
    doc = make_raw_doc()
    claims = await run([doc], "wildfire in Los Angeles, CA")
    assert isinstance(claims, list)
