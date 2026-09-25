from datetime import timedelta
from app.models import WorldStateStatus, HealthEventType, HealthSeverity, EntityType
from app.stages import health_monitor as hm
from app.stages import world_state as ws
from conftest import make_world_state_entry, now


async def test_stale_entity_detected():
    stale_entry = make_world_state_entry(
        last_updated=now() - timedelta(hours=10),
        entity_type=EntityType.road,
    )
    events = await hm.check_staleness([stale_entry])
    assert len(events) == 1
    assert events[0].type == HealthEventType.stale
    assert events[0].entity == "US-101"


async def test_fresh_entity_not_flagged():
    fresh_entry = make_world_state_entry(last_updated=now() - timedelta(minutes=30))
    events = await hm.check_staleness([fresh_entry])
    assert len(events) == 0


async def test_evacuation_zone_has_tighter_staleness_threshold():
    entry = make_world_state_entry(
        entity_type=EntityType.evacuation_zone,
        entity="Zone A",
        last_updated=now() - timedelta(hours=3),
    )
    events = await hm.check_staleness([entry])
    assert len(events) == 1
    assert events[0].severity == HealthSeverity.high


async def test_utility_has_looser_staleness_threshold():
    entry = make_world_state_entry(
        entity_type=EntityType.utility,
        entity="PG&E Grid",
        claim_type="utility_status",
        last_updated=now() - timedelta(hours=5),
    )
    events = await hm.check_staleness([entry])
    assert len(events) == 0


async def test_contradiction_detected_after_grace_period():
    conflicted_entry = make_world_state_entry(
        status=WorldStateStatus.conflicted,
        last_updated=now() - timedelta(minutes=20),
        conflicting_claim_id="claim-other",
    )
    events = await hm.check_contradictions([conflicted_entry])
    assert len(events) == 1
    assert events[0].type == HealthEventType.contradiction
    assert events[0].severity == HealthSeverity.high


async def test_contradiction_suppressed_within_grace_period():
    conflicted_entry = make_world_state_entry(
        status=WorldStateStatus.conflicted,
        last_updated=now() - timedelta(minutes=5),
        conflicting_claim_id="claim-other",
    )
    events = await hm.check_contradictions([conflicted_entry])
    assert len(events) == 0


async def test_non_conflicted_entry_not_flagged():
    entry = make_world_state_entry(status=WorldStateStatus.confirmed)
    events = await hm.check_contradictions([entry])
    assert len(events) == 0


async def test_missing_entity_type_detected_for_wildfire():
    road_entry = make_world_state_entry(entity_type=EntityType.road)
    events = await hm.check_missing_data([road_entry], "wildfire")
    missing_types = {e.entity_type for e in events}
    assert "fire" in missing_types
    assert "evacuation_zone" in missing_types


async def test_no_missing_data_when_all_present():
    entries = [
        make_world_state_entry(entity_type=EntityType.fire, entity="North Fire"),
        make_world_state_entry(entity_type=EntityType.evacuation_zone, entity="Zone A"),
        make_world_state_entry(entity_type=EntityType.road, entity="US-101"),
    ]
    events = await hm.check_missing_data(entries, "wildfire")
    assert len(events) == 0


async def test_event_deduplication_prevents_double_emit():
    entry = make_world_state_entry(last_updated=now() - timedelta(hours=10))
    events1 = await hm.check_staleness([entry])
    events2 = await hm.check_staleness([entry])
    assert len(events1) == 1
    assert len(events2) == 0


async def test_resolve_event_marks_as_resolved():
    entry = make_world_state_entry(last_updated=now() - timedelta(hours=10))
    events = await hm.check_staleness([entry])
    assert len(events) == 1
    hm.resolve_event(events[0].type, events[0].entity, events[0].claim_type)
    open_events = hm.get_open_events()
    assert len(open_events) == 0


async def test_get_open_events_excludes_resolved():
    entry = make_world_state_entry(last_updated=now() - timedelta(hours=10))
    events = await hm.check_staleness([entry])
    hm.resolve_event(events[0].type, events[0].entity, events[0].claim_type)
    assert len(hm.get_open_events()) == 0
    assert len(hm.get_all_events()) == 1


async def test_run_aggregates_all_check_types():
    entries = [
        make_world_state_entry(
            last_updated=now() - timedelta(hours=10),
        ),
        make_world_state_entry(
            entity="I-5",
            status=WorldStateStatus.conflicted,
            last_updated=now() - timedelta(minutes=20),
            conflicting_claim_id="old-claim",
        ),
    ]
    events = await hm.run(entries, "wildfire")
    types = {e.type for e in events}
    assert HealthEventType.stale in types
    assert HealthEventType.contradiction in types
    assert HealthEventType.missing in types
