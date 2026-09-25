import json
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.models import (
    HealthEvent,
    # noqa — mock_data imported below
    HealthEventType,
    HealingAction,
    HealingProposal,
    HealingRecord,
    WorldStateStatus,
)
from app.stages import world_state, health_monitor, mock_data

_healing_records: list[HealingRecord] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


DIAGNOSE_SYSTEM_PROMPT = """You are a crisis data pipeline healing system.
Given a health event and the current world state for the affected entity, diagnose the root cause and propose a fix.
Return ONLY valid JSON. No prose.

Output format:
{
  "root_cause": "<human-readable explanation>",
  "cause_type": "<source_conflict|source_stale|data_gap|clock_skew|propagation_loop|source_degraded|unknown>",
  "affected_claims": ["<claim_id>", ...],
  "proposed_action_type": "<update_value|update_status|evict_claims|mark_unresolvable|request_resense|suppress_source>",
  "proposed_value": "<new value if action is update_value, else null>",
  "proposed_status": "<new status if action is update_status, else null>",
  "reasoning": "<why this fix is correct>",
  "confidence": <0.0-1.0>
}
"""


def _sync_liquid_diagnose(messages: list[dict], model: str, api_key: str, base_url: str) -> str:
    from liquidai import Client
    liq = Client(base_url=base_url, api_key=api_key)
    response = liq.complete(messages, model=model, temperature=0.0, max_new_tokens=512)
    return response["message"]["content"]


async def _call_liquid_ai_diagnose(
    event: HealthEvent,
    entity_history: list[dict],
) -> Optional[dict]:
    # ── DEMO MODE ────────────────────────────────────────────────────────────
    if settings.demo_mode:
        return mock_data.MOCK_DIAGNOSIS
    # ── END DEMO MODE ─────────────────────────────────────────────────────────

    if not settings.liquid_ai_api_key or not settings.liquid_url:
        return None

    context = {
        "health_event": event.model_dump(),
        "entity_history": entity_history[-20:],
    }

    messages = [
        {"role": "system", "content": DIAGNOSE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(context, default=str)},
    ]

    for attempt in range(3):
        try:
            text = await asyncio.to_thread(
                _sync_liquid_diagnose,
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
                return None
            await asyncio.sleep(1)
        except Exception:
            return None
    return None


def _build_proposal(diagnosis: dict, event: HealthEvent) -> Optional[HealingProposal]:
    try:
        action_str = diagnosis.get("proposed_action_type", "")
        try:
            action = HealingAction(action_str)
        except ValueError:
            action = HealingAction.mark_unresolvable

        return HealingProposal(
            action=action,
            target_entity=event.entity or "",
            target_claim_type=event.claim_type or "",
            new_value=diagnosis.get("proposed_value"),
            new_status=diagnosis.get("proposed_status"),
            evicted_claim_ids=diagnosis.get("affected_claims", []),
            reasoning=diagnosis.get("reasoning", ""),
            confidence=float(diagnosis.get("confidence", 0.0)),
        )
    except Exception:
        return None


def _verify_proposal(proposal: HealingProposal) -> tuple[bool, str]:
    if proposal.confidence < settings.healing_confidence_floor:
        return False, f"proposal confidence {proposal.confidence:.2f} below floor {settings.healing_confidence_floor}"

    if not proposal.target_entity:
        return False, "proposal has no target entity"

    if proposal.action == HealingAction.update_value and not proposal.new_value:
        return False, "update_value action requires new_value"

    if proposal.action == HealingAction.update_status and not proposal.new_status:
        return False, "update_status action requires new_status"

    return True, "ok"


async def _test_proposal(proposal: HealingProposal, event: HealthEvent) -> tuple[bool, str]:
    if proposal.action == HealingAction.request_resense:
        return True, "resense request always passes test"

    if proposal.action == HealingAction.mark_unresolvable:
        return True, "mark unresolvable always passes test"

    if proposal.action in (HealingAction.update_value, HealingAction.update_status):
        new_status = None
        if proposal.new_status:
            try:
                new_status = WorldStateStatus(proposal.new_status)
            except ValueError:
                return False, f"invalid status value '{proposal.new_status}'"

        if new_status == WorldStateStatus.conflicted:
            return False, "heal action must not result in conflicted status"

    return True, "ok"


async def _commit_proposal(proposal: HealingProposal) -> bool:
    if proposal.action == HealingAction.update_value:
        return await world_state.update_entry_status(
            proposal.target_entity,
            proposal.target_claim_type,
            WorldStateStatus.confirmed,
            proposal.new_value,
        )

    if proposal.action == HealingAction.update_status:
        try:
            new_status = WorldStateStatus(proposal.new_status)
        except ValueError:
            return False
        return await world_state.update_entry_status(
            proposal.target_entity,
            proposal.target_claim_type,
            new_status,
        )

    if proposal.action == HealingAction.mark_unresolvable:
        return await world_state.update_entry_status(
            proposal.target_entity,
            proposal.target_claim_type,
            WorldStateStatus.unresolved,
        )

    if proposal.action == HealingAction.request_resense:
        return True

    return True


async def heal(event: HealthEvent) -> HealingRecord:
    entity_history = []
    if event.entity:
        entity_history = await world_state.get_entity_history(event.entity)

    diagnosis = await _call_liquid_ai_diagnose(event, entity_history)

    if not diagnosis:
        record = HealingRecord(
            health_event_id=event.id,
            diagnosed_cause_type="unknown",
            proposed_action="none",
            action_detail={},
            lfm_reasoning="LFM call failed or returned no diagnosis",
            verify_passed=False,
            test_passed=False,
            committed=False,
            rolled_back=True,
            rolled_back_reason="diagnosis failed",
        )
        _healing_records.append(record)
        return record

    proposal = _build_proposal(diagnosis, event)
    if not proposal:
        record = HealingRecord(
            health_event_id=event.id,
            diagnosed_cause_type=diagnosis.get("cause_type", "unknown"),
            proposed_action="none",
            action_detail=diagnosis,
            lfm_reasoning=diagnosis.get("reasoning", ""),
            verify_passed=False,
            test_passed=False,
            committed=False,
            rolled_back=True,
            rolled_back_reason="could not build proposal from diagnosis",
        )
        _healing_records.append(record)
        return record

    verify_ok, verify_reason = _verify_proposal(proposal)
    if not verify_ok:
        record = HealingRecord(
            health_event_id=event.id,
            diagnosed_cause_type=diagnosis.get("cause_type", "unknown"),
            proposed_action=proposal.action.value,
            action_detail=proposal.model_dump(),
            lfm_reasoning=proposal.reasoning,
            verify_passed=False,
            test_passed=False,
            committed=False,
            rolled_back=True,
            rolled_back_reason=f"verify failed: {verify_reason}",
        )
        _healing_records.append(record)
        return record

    test_ok, test_reason = await _test_proposal(proposal, event)
    if not test_ok:
        record = HealingRecord(
            health_event_id=event.id,
            diagnosed_cause_type=diagnosis.get("cause_type", "unknown"),
            proposed_action=proposal.action.value,
            action_detail=proposal.model_dump(),
            lfm_reasoning=proposal.reasoning,
            verify_passed=True,
            test_passed=False,
            committed=False,
            rolled_back=True,
            rolled_back_reason=f"test failed: {test_reason}",
        )
        _healing_records.append(record)
        return record

    committed = await _commit_proposal(proposal)
    if committed and event.entity:
        health_monitor.resolve_event(event.type, event.entity, event.claim_type)

    record = HealingRecord(
        health_event_id=event.id,
        diagnosed_cause_type=diagnosis.get("cause_type", "unknown"),
        proposed_action=proposal.action.value,
        action_detail=proposal.model_dump(),
        lfm_reasoning=proposal.reasoning,
        verify_passed=True,
        test_passed=True,
        committed=committed,
        committed_at=_now() if committed else None,
        rolled_back=not committed,
        rolled_back_reason=None if committed else "commit failed",
    )
    _healing_records.append(record)
    return record


async def run(events: list[HealthEvent]) -> list[HealingRecord]:
    records = []
    for event in events:
        record = await heal(event)
        records.append(record)
    return records


def get_records() -> list[HealingRecord]:
    return list(_healing_records)
