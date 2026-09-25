from unittest.mock import AsyncMock, patch
from app.models import HealingAction, HealthEventType, HealthSeverity, WorldStateStatus
from app.stages.healing_loop import (
    _verify_proposal,
    _test_proposal,
    _build_proposal,
    heal,
    get_records,
)
from app.models import HealingProposal, HealthEvent
from conftest import make_health_event, make_validated_claim
from app.stages import world_state as ws


def make_proposal(**overrides) -> HealingProposal:
    base = dict(
        action=HealingAction.update_value,
        target_entity="US-101",
        target_claim_type="road_status",
        new_value="open",
        reasoning="Official source confirms road is open.",
        confidence=0.85,
    )
    base.update(overrides)
    return HealingProposal(**base)


# ── Verify ─────────────────────────────────────────────────────────────────────

def test_verify_passes_for_valid_proposal():
    ok, reason = _verify_proposal(make_proposal())
    assert ok is True


def test_verify_fails_for_low_confidence():
    ok, reason = _verify_proposal(make_proposal(confidence=0.3))
    assert ok is False
    assert "confidence" in reason


def test_verify_fails_for_missing_target_entity():
    ok, reason = _verify_proposal(make_proposal(target_entity=""))
    assert ok is False
    assert "entity" in reason


def test_verify_fails_for_update_value_without_new_value():
    ok, reason = _verify_proposal(make_proposal(action=HealingAction.update_value, new_value=None))
    assert ok is False
    assert "new_value" in reason


def test_verify_fails_for_update_status_without_new_status():
    ok, reason = _verify_proposal(make_proposal(action=HealingAction.update_status, new_status=None))
    assert ok is False
    assert "new_status" in reason


def test_verify_passes_for_mark_unresolvable():
    ok, _ = _verify_proposal(make_proposal(action=HealingAction.mark_unresolvable, new_value=None))
    assert ok is True


def test_verify_passes_for_request_resense():
    ok, _ = _verify_proposal(make_proposal(action=HealingAction.request_resense, new_value=None))
    assert ok is True


# ── Test ──────────────────────────────────────────────────────────────────────

async def test_test_passes_for_request_resense():
    event = make_health_event()
    proposal = make_proposal(action=HealingAction.request_resense, new_value=None)
    ok, _ = await _test_proposal(proposal, event)
    assert ok is True


async def test_test_passes_for_mark_unresolvable():
    event = make_health_event()
    proposal = make_proposal(action=HealingAction.mark_unresolvable, new_value=None)
    ok, _ = await _test_proposal(proposal, event)
    assert ok is True


async def test_test_fails_if_proposed_status_is_conflicted():
    event = make_health_event()
    proposal = make_proposal(
        action=HealingAction.update_status,
        new_value=None,
        new_status="conflicted",
    )
    ok, reason = await _test_proposal(proposal, event)
    assert ok is False
    assert "conflicted" in reason


async def test_test_passes_for_valid_status_update():
    event = make_health_event()
    proposal = make_proposal(
        action=HealingAction.update_status,
        new_value=None,
        new_status="confirmed",
    )
    ok, _ = await _test_proposal(proposal, event)
    assert ok is True


async def test_test_fails_for_invalid_status_value():
    event = make_health_event()
    proposal = make_proposal(
        action=HealingAction.update_status,
        new_value=None,
        new_status="not_a_real_status",
    )
    ok, reason = await _test_proposal(proposal, event)
    assert ok is False


# ── Build proposal ─────────────────────────────────────────────────────────────

def test_build_proposal_maps_action_correctly():
    event = make_health_event()
    diagnosis = {
        "proposed_action_type": "update_value",
        "proposed_value": "open",
        "proposed_status": None,
        "reasoning": "Official source says open.",
        "confidence": 0.9,
        "affected_claims": [],
    }
    proposal = _build_proposal(diagnosis, event)
    assert proposal is not None
    assert proposal.action == HealingAction.update_value
    assert proposal.new_value == "open"


def test_build_proposal_falls_back_to_mark_unresolvable_for_unknown_action():
    event = make_health_event()
    diagnosis = {
        "proposed_action_type": "do_magic",
        "proposed_value": None,
        "proposed_status": None,
        "reasoning": "Unknown.",
        "confidence": 0.8,
        "affected_claims": [],
    }
    proposal = _build_proposal(diagnosis, event)
    assert proposal.action == HealingAction.mark_unresolvable


# ── Full heal flow (mocked LFM) ────────────────────────────────────────────────

async def test_heal_records_rollback_when_diagnosis_fails():
    event = make_health_event()
    with patch("app.stages.healing_loop._call_liquid_ai_diagnose", new=AsyncMock(return_value=None)):
        record = await heal(event)
    assert record.committed is False
    assert record.rolled_back is True
    assert "diagnosis failed" in (record.rolled_back_reason or "")


async def test_heal_records_rollback_when_verify_fails():
    event = make_health_event()
    diagnosis = {
        "cause_type": "source_conflict",
        "proposed_action_type": "update_value",
        "proposed_value": "open",
        "proposed_status": None,
        "reasoning": "Official source.",
        "confidence": 0.1,
        "affected_claims": [],
    }
    with patch("app.stages.healing_loop._call_liquid_ai_diagnose", new=AsyncMock(return_value=diagnosis)):
        record = await heal(event)
    assert record.verify_passed is False
    assert record.committed is False


async def test_heal_commits_when_all_checks_pass():
    claim = make_validated_claim(confidence=0.75, value="closed")
    claim2 = make_validated_claim(confidence=0.8, value="open")
    await ws.ingest_claims([claim, claim2])

    event = make_health_event(type=HealthEventType.contradiction)
    diagnosis = {
        "cause_type": "source_conflict",
        "proposed_action_type": "update_value",
        "proposed_value": "open",
        "proposed_status": None,
        "reasoning": "Official source confirms open.",
        "confidence": 0.9,
        "affected_claims": [],
    }
    with patch("app.stages.healing_loop._call_liquid_ai_diagnose", new=AsyncMock(return_value=diagnosis)):
        record = await heal(event)
    assert record.verify_passed is True
    assert record.test_passed is True
    assert record.committed is True
    assert record.committed_at is not None


async def test_heal_writes_to_audit_log():
    event = make_health_event()
    with patch("app.stages.healing_loop._call_liquid_ai_diagnose", new=AsyncMock(return_value=None)):
        await heal(event)
    assert len(get_records()) == 1
