from datetime import timedelta
from app.models import RejectedClaim, ValidatedClaim, SourceType, EntityType, RejectionReason
from app.stages.validate import validate, run
from conftest import make_claim, now


# ── Schema checks ──────────────────────────────────────────────────────────────

def test_valid_claim_passes():
    result = validate(make_claim(), set())
    assert isinstance(result, ValidatedClaim)


def test_missing_entity_rejected():
    result = validate(make_claim(entity=""), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.schema


def test_missing_value_rejected():
    result = validate(make_claim(value=""), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.schema


def test_confidence_above_one_rejected():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_claim(confidence=1.1)


def test_future_crawled_at_rejected():
    result = validate(make_claim(crawled_at=now() + timedelta(hours=2)), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.schema


# ── Freshness checks ───────────────────────────────────────────────────────────

def test_stale_published_at_rejected():
    result = validate(make_claim(published_at=now() - timedelta(hours=72)), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.stale


def test_future_published_at_rejected():
    result = validate(make_claim(published_at=now() + timedelta(hours=2)), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.stale


def test_recent_claim_passes_freshness():
    result = validate(make_claim(published_at=now() - timedelta(hours=12)), set())
    assert isinstance(result, ValidatedClaim)


def test_null_published_at_uses_crawled_at():
    claim = make_claim(published_at=None, crawled_at=now() - timedelta(hours=10))
    result = validate(claim, set())
    assert isinstance(result, ValidatedClaim)


# ── Confidence checks ──────────────────────────────────────────────────────────

def test_low_confidence_rejected():
    result = validate(make_claim(confidence=0.1), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.low_confidence


def test_official_source_has_lower_floor():
    claim = make_claim(
        confidence=0.22,
        source_type=SourceType.official,
        source_url="https://usgs.gov/earthquakes",
    )
    result = validate(claim, set())
    assert isinstance(result, ValidatedClaim)


def test_news_source_needs_higher_confidence():
    result = validate(make_claim(confidence=0.22, source_type=SourceType.news), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.low_confidence


# ── Duplicate checks ───────────────────────────────────────────────────────────

def test_duplicate_claim_rejected():
    claim = make_claim()
    key = (
        claim.entity.lower(),
        claim.claim_type.lower(),
        claim.value.lower().strip(),
        claim.source_url,
    )
    result = validate(claim, {key})
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.duplicate


def test_different_value_not_duplicate():
    claim = make_claim(value="open")
    key = ("us-101", "road_status", "closed", claim.source_url)
    result = validate(claim, {key})
    assert isinstance(result, ValidatedClaim)


def test_run_deduplicates_within_batch():
    c1 = make_claim()
    c2 = make_claim()
    validated, rejected = run([c1, c2])
    assert len(validated) == 1
    assert len(rejected) == 1
    assert rejected[0].rejection_reason == RejectionReason.duplicate


# ── Invariant checks ───────────────────────────────────────────────────────────

def test_road_open_and_closed_rejected():
    result = validate(make_claim(value="open and closed"), set())
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.invariant


def test_containment_over_100_rejected():
    result = validate(
        make_claim(
            entity_type=EntityType.fire,
            claim_type="fire_containment_pct",
            value="150",
        ),
        set(),
    )
    assert isinstance(result, RejectedClaim)
    assert result.rejection_reason == RejectionReason.invariant


def test_containment_within_range_passes():
    result = validate(
        make_claim(
            entity_type=EntityType.fire,
            claim_type="fire_containment_pct",
            value="45",
        ),
        set(),
    )
    assert isinstance(result, ValidatedClaim)


# ── Source type correction ─────────────────────────────────────────────────────

def test_gov_domain_upgraded_to_official():
    claim = make_claim(
        source_url="https://earthquake.usgs.gov/feeds/v1.0/summary/all_day.geojson",
        source_type=SourceType.news,
    )
    result = validate(claim, set())
    assert isinstance(result, ValidatedClaim)
    assert result.source_type == SourceType.official
    assert len(result.corrections) == 1


def test_social_domain_downgraded_from_official():
    claim = make_claim(
        source_url="https://reddit.com/r/wildfires/post/123",
        source_type=SourceType.official,
    )
    result = validate(claim, set())
    assert isinstance(result, ValidatedClaim)
    assert result.source_type == SourceType.social


# ── Batch run ─────────────────────────────────────────────────────────────────

def test_run_separates_valid_and_invalid():
    claims = [
        make_claim(),
        make_claim(entity=""),
        make_claim(confidence=0.05),
        make_claim(entity="I-5", value="open"),
    ]
    validated, rejected = run(claims)
    assert len(validated) == 2
    assert len(rejected) == 2
