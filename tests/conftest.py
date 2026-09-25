from datetime import datetime, timezone, timedelta
import pytest
from app.stages import world_state as ws
from app.stages import health_monitor as hm
from app.stages import healing_loop as hl
from app.models import (
    Claim, ValidatedClaim, SourceType, EntityType,
    WorldStateEntry, WorldStateStatus, HealthEvent, HealthEventType, HealthSeverity,
)


@pytest.fixture(autouse=True)
def reset_module_state():
    ws._in_memory_dashboard.clear()
    ws._in_memory_rawtree.clear()
    hm._open_events.clear()
    hl._healing_records.clear()
    yield


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_claim(**overrides) -> Claim:
    base = dict(
        raw_document_id="doc-1",
        source_url="https://example-news.com/article",
        source_type=SourceType.news,
        crawled_at=now(),
        published_at=now() - timedelta(hours=1),
        entity="US-101",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="closed",
        confidence=0.8,
        raw_text="US-101 is closed due to wildfire activity.",
    )
    base.update(overrides)
    return Claim(**base)


def make_validated_claim(**overrides) -> ValidatedClaim:
    c = make_claim(**overrides)
    return ValidatedClaim(**c.model_dump())


def make_world_state_entry(**overrides) -> WorldStateEntry:
    base = dict(
        entity="US-101",
        entity_type=EntityType.road,
        claim_type="road_status",
        current_value="closed",
        confidence=0.8,
        status=WorldStateStatus.confirmed,
        last_claim_id="claim-1",
        last_updated=now(),
    )
    base.update(overrides)
    return WorldStateEntry(**base)


def make_health_event(**overrides) -> HealthEvent:
    base = dict(
        type=HealthEventType.stale,
        severity=HealthSeverity.medium,
        entity="US-101",
        entity_type="road",
        claim_type="road_status",
        description="US-101 road_status has not been updated in 5.0h",
        context={},
    )
    base.update(overrides)
    return HealthEvent(**base)
