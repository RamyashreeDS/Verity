import pytest
from app.models import WorldStateStatus
from app.stages import world_state as ws
from conftest import make_validated_claim, make_world_state_entry


async def test_new_claim_creates_entry():
    claim = make_validated_claim(confidence=0.9)
    entries = await ws.ingest_claims([claim])
    assert len(entries) == 1
    assert entries[0].entity == "US-101"
    assert entries[0].current_value == "closed"
    assert entries[0].status == WorldStateStatus.confirmed


async def test_new_claim_below_threshold_is_low_confidence():
    claim = make_validated_claim(confidence=0.5)
    entries = await ws.ingest_claims([claim])
    assert entries[0].status == WorldStateStatus.low_confidence


async def test_same_value_boosts_confidence():
    c1 = make_validated_claim(confidence=0.7)
    c2 = make_validated_claim(confidence=0.9)
    await ws.ingest_claims([c1])
    await ws.ingest_claims([c2])
    dashboard = await ws.get_dashboard()
    entry = next(e for e in dashboard if e.entity == "US-101")
    assert entry.confidence == pytest.approx(0.8, abs=0.01)


async def test_higher_confidence_different_value_updates():
    c1 = make_validated_claim(value="closed", confidence=0.6)
    c2 = make_validated_claim(value="open", confidence=0.9)
    await ws.ingest_claims([c1])
    await ws.ingest_claims([c2])
    dashboard = await ws.get_dashboard()
    entry = next(e for e in dashboard if e.entity == "US-101")
    assert entry.current_value == "open"


async def test_lower_confidence_different_value_does_not_update():
    c1 = make_validated_claim(value="closed", confidence=0.9)
    c2 = make_validated_claim(value="open", confidence=0.5)
    await ws.ingest_claims([c1])
    await ws.ingest_claims([c2])
    dashboard = await ws.get_dashboard()
    entry = next(e for e in dashboard if e.entity == "US-101")
    assert entry.current_value == "closed"


async def test_close_confidence_different_value_triggers_conflict():
    # new claim has slightly LOWER confidence — triggers the conflict_tolerance path
    c1 = make_validated_claim(value="closed", confidence=0.8)
    c2 = make_validated_claim(value="open", confidence=0.75)
    await ws.ingest_claims([c1])
    await ws.ingest_claims([c2])
    dashboard = await ws.get_dashboard()
    entry = next(e for e in dashboard if e.entity == "US-101")
    assert entry.status == WorldStateStatus.conflicted
    assert entry.conflicting_claim_id is not None


async def test_large_confidence_delta_also_triggers_conflict():
    c1 = make_validated_claim(value="closed", confidence=0.5)
    c2 = make_validated_claim(value="open", confidence=0.95)
    await ws.ingest_claims([c1])
    await ws.ingest_claims([c2])
    dashboard = await ws.get_dashboard()
    entry = next(e for e in dashboard if e.entity == "US-101")
    assert entry.status == WorldStateStatus.conflicted


async def test_multiple_entities_tracked_independently():
    c1 = make_validated_claim(entity="US-101", claim_type="road_status", value="closed")
    c2 = make_validated_claim(entity="I-5", claim_type="road_status", value="open")
    await ws.ingest_claims([c1, c2])
    dashboard = await ws.get_dashboard()
    assert len(dashboard) == 2
    values = {e.entity: e.current_value for e in dashboard}
    assert values["US-101"] == "closed"
    assert values["I-5"] == "open"


async def test_rawtree_grows_with_each_ingest():
    c1 = make_validated_claim(entity="US-101")
    c2 = make_validated_claim(entity="I-5")
    await ws.ingest_claims([c1])
    await ws.ingest_claims([c2])
    assert len(ws._in_memory_rawtree) == 2


async def test_get_conflicted_entries_filters_correctly():
    c1 = make_validated_claim(value="closed", confidence=0.8)
    c2 = make_validated_claim(value="open", confidence=0.75)
    await ws.ingest_claims([c1, c2])
    conflicted = await ws.get_conflicted_entries()
    assert len(conflicted) == 1
    assert conflicted[0].status == WorldStateStatus.conflicted


async def test_update_entry_status_changes_status():
    claim = make_validated_claim(confidence=0.75, value="closed")
    c2 = make_validated_claim(confidence=0.8, value="open")
    await ws.ingest_claims([claim, c2])
    success = await ws.update_entry_status("US-101", "road_status", WorldStateStatus.confirmed, "open")
    assert success
    dashboard = await ws.get_dashboard()
    entry = next(e for e in dashboard if e.entity == "US-101")
    assert entry.status == WorldStateStatus.confirmed
    assert entry.current_value == "open"


async def test_update_nonexistent_entity_returns_false():
    result = await ws.update_entry_status("Nonexistent-Road", "road_status", WorldStateStatus.confirmed)
    assert result is False


async def test_get_entity_history_returns_matching_records():
    c1 = make_validated_claim(entity="US-101")
    c2 = make_validated_claim(entity="I-5")
    await ws.ingest_claims([c1, c2])
    history = await ws.get_entity_history("US-101")
    assert len(history) == 1
    assert history[0]["entity"] == "US-101"
