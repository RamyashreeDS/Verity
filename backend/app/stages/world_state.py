import json
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.models import ValidatedClaim, WorldStateEntry, WorldStateStatus

_in_memory_rawtree: list[dict] = []
_in_memory_dashboard: dict[tuple[str, str], WorldStateEntry] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _ingest_to_tinybird(records: list[dict], datasource: str) -> bool:
    if not settings.tinybird_api_key:
        return False
    ndjson = "\n".join(json.dumps(r) for r in records)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.tinybird_host}/v0/events",
                headers={
                    "Authorization": f"Bearer {settings.tinybird_api_key}",
                    "Content-Type": "application/json",
                },
                params={"name": datasource},
                content=ndjson,
                timeout=10,
            )
            return resp.status_code == 200
    except Exception:
        return False


async def _query_tinybird(pipe: str, params: dict = {}) -> list[dict]:
    if not settings.tinybird_api_key:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.tinybird_host}/v0/pipes/{pipe}.json",
                headers={"Authorization": f"Bearer {settings.tinybird_api_key}"},
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
    except Exception:
        return []


def _determine_status(confidence: float, threshold: float) -> WorldStateStatus:
    if confidence >= threshold:
        return WorldStateStatus.confirmed
    return WorldStateStatus.low_confidence


def _merge_claim_into_dashboard(claim: ValidatedClaim) -> WorldStateEntry:
    key = (claim.entity.lower(), claim.claim_type.lower())
    existing = _in_memory_dashboard.get(key)

    if existing is None:
        status = _determine_status(claim.confidence, settings.high_confidence_threshold)
        entry = WorldStateEntry(
            entity=claim.entity,
            entity_type=claim.entity_type,
            claim_type=claim.claim_type,
            current_value=claim.value,
            confidence=claim.confidence,
            status=status,
            last_claim_id=claim.id,
            last_updated=_now(),
        )
        _in_memory_dashboard[key] = entry
        return entry

    if claim.value.lower() == existing.current_value.lower():
        avg_confidence = (existing.confidence + claim.confidence) / 2
        updated = existing.model_copy(update={
            "confidence": avg_confidence,
            "last_claim_id": claim.id,
            "last_updated": _now(),
            "status": _determine_status(avg_confidence, settings.high_confidence_threshold),
        })
        _in_memory_dashboard[key] = updated
        return updated

    delta = abs(claim.confidence - existing.confidence)
    if claim.confidence > existing.confidence:
        if delta > settings.conflict_threshold:
            updated = existing.model_copy(update={
                "current_value": claim.value,
                "confidence": claim.confidence,
                "status": WorldStateStatus.conflicted,
                "conflicting_claim_id": existing.last_claim_id,
                "last_claim_id": claim.id,
                "last_updated": _now(),
            })
        else:
            updated = existing.model_copy(update={
                "current_value": claim.value,
                "confidence": claim.confidence,
                "status": _determine_status(claim.confidence, settings.high_confidence_threshold),
                "last_claim_id": claim.id,
                "last_updated": _now(),
            })
        _in_memory_dashboard[key] = updated
        return updated

    if delta <= settings.conflict_tolerance:
        updated = existing.model_copy(update={
            "status": WorldStateStatus.conflicted,
            "conflicting_claim_id": claim.id,
            "last_updated": _now(),
        })
        _in_memory_dashboard[key] = updated
        return updated

    return existing


async def ingest_claims(claims: list[ValidatedClaim]) -> list[WorldStateEntry]:
    updated_entries: list[WorldStateEntry] = []

    rawtree_records = [
        {
            "claim_id": c.id,
            "raw_document_id": c.raw_document_id,
            "source_url": c.source_url,
            "source_type": c.source_type.value,
            "crawled_at": c.crawled_at.isoformat(),
            "published_at": c.published_at.isoformat() if c.published_at else None,
            "entity": c.entity,
            "entity_type": c.entity_type.value,
            "claim_type": c.claim_type,
            "value": c.value,
            "confidence": c.confidence,
            "raw_text": c.raw_text,
            "validated_at": c.validated_at.isoformat(),
            "ingested_at": _now().isoformat(),
        }
        for c in claims
    ]
    _in_memory_rawtree.extend(rawtree_records)
    await _ingest_to_tinybird(rawtree_records, "rawtree")

    for claim in claims:
        entry = _merge_claim_into_dashboard(claim)
        updated_entries.append(entry)

    return updated_entries


async def get_dashboard() -> list[WorldStateEntry]:
    if settings.tinybird_api_key:
        rows = await _query_tinybird("dashboard")
        if rows:
            return [WorldStateEntry(**r) for r in rows]
    return list(_in_memory_dashboard.values())


async def get_entity_history(entity: str) -> list[dict]:
    if settings.tinybird_api_key:
        rows = await _query_tinybird("rawtree_by_entity", {"entity": entity})
        if rows:
            return rows
    return [r for r in _in_memory_rawtree if r["entity"].lower() == entity.lower()]


async def get_conflicted_entries() -> list[WorldStateEntry]:
    all_entries = await get_dashboard()
    return [e for e in all_entries if e.status in (WorldStateStatus.conflicted, WorldStateStatus.unresolved)]


async def update_entry_status(entity: str, claim_type: str, new_status: WorldStateStatus, new_value: Optional[str] = None) -> bool:
    key = (entity.lower(), claim_type.lower())
    if key not in _in_memory_dashboard:
        return False
    updates: dict = {"status": new_status, "last_updated": _now()}
    if new_value is not None:
        updates["current_value"] = new_value
    _in_memory_dashboard[key] = _in_memory_dashboard[key].model_copy(update=updates)
    return True
