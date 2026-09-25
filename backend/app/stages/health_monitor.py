from datetime import datetime, timezone, timedelta

from app.config import settings
from app.models import (
    WorldStateEntry,
    WorldStateStatus,
    HealthEvent,
    HealthEventType,
    HealthSeverity,
    EntityType,
)
from app.stages import world_state

STALENESS_HOURS: dict[EntityType, int] = {
    EntityType.evacuation_zone: 2,
    EntityType.road: 3,
    EntityType.shelter: 4,
    EntityType.fire: 4,
    EntityType.flood: 4,
    EntityType.weather: 6,
    EntityType.utility: 8,
}

STALENESS_SEVERITY: dict[EntityType, HealthSeverity] = {
    EntityType.evacuation_zone: HealthSeverity.high,
    EntityType.road: HealthSeverity.high,
    EntityType.shelter: HealthSeverity.medium,
    EntityType.fire: HealthSeverity.medium,
    EntityType.flood: HealthSeverity.medium,
    EntityType.weather: HealthSeverity.low,
    EntityType.utility: HealthSeverity.low,
}

REQUIRED_ENTITY_TYPES: dict[str, list[EntityType]] = {
    "wildfire": [EntityType.fire, EntityType.evacuation_zone, EntityType.road],
    "flood": [EntityType.flood, EntityType.road, EntityType.shelter],
    "earthquake": [EntityType.road, EntityType.utility, EntityType.shelter],
    "hurricane": [EntityType.weather, EntityType.evacuation_zone, EntityType.shelter],
    "accident": [EntityType.road],
}

_open_events: dict[str, HealthEvent] = {}
CONFLICT_GRACE_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_tz(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _event_key(type: HealthEventType, entity: str | None, claim_type: str | None) -> str:
    return f"{type.value}::{entity or ''}::{claim_type or ''}"


def _emit(event: HealthEvent) -> HealthEvent | None:
    key = _event_key(event.type, event.entity, event.claim_type)
    existing = _open_events.get(key)
    if existing and not existing.resolved:
        return None
    _open_events[key] = event
    return event


async def check_staleness(entries: list[WorldStateEntry]) -> list[HealthEvent]:
    events: list[HealthEvent] = []
    now = _now()
    for entry in entries:
        threshold_hours = STALENESS_HOURS.get(entry.entity_type, settings.staleness_window_hours)
        last = _ensure_tz(entry.last_updated)
        if now - last > timedelta(hours=threshold_hours):
            event = HealthEvent(
                type=HealthEventType.stale,
                severity=STALENESS_SEVERITY.get(entry.entity_type, HealthSeverity.low),
                entity=entry.entity,
                entity_type=entry.entity_type.value,
                claim_type=entry.claim_type,
                description=f"{entry.entity} {entry.claim_type} has not been updated in {(now - last).total_seconds() / 3600:.1f}h",
                context={"last_updated": last.isoformat(), "threshold_hours": threshold_hours},
            )
            emitted = _emit(event)
            if emitted:
                events.append(emitted)
    return events


async def check_contradictions(entries: list[WorldStateEntry]) -> list[HealthEvent]:
    events: list[HealthEvent] = []
    now = _now()
    for entry in entries:
        if entry.status != WorldStateStatus.conflicted:
            continue
        last = _ensure_tz(entry.last_updated)
        if now - last < timedelta(minutes=CONFLICT_GRACE_MINUTES):
            continue
        event = HealthEvent(
            type=HealthEventType.contradiction,
            severity=HealthSeverity.high,
            entity=entry.entity,
            entity_type=entry.entity_type.value,
            claim_type=entry.claim_type,
            description=f"Unresolved contradiction for {entry.entity} {entry.claim_type}: current='{entry.current_value}' conflicts with claim {entry.conflicting_claim_id}",
            context={
                "current_value": entry.current_value,
                "current_claim_id": entry.last_claim_id,
                "conflicting_claim_id": entry.conflicting_claim_id,
            },
        )
        emitted = _emit(event)
        if emitted:
            events.append(emitted)
    return events


async def check_missing_data(entries: list[WorldStateEntry], event_type: str) -> list[HealthEvent]:
    events: list[HealthEvent] = []
    required = REQUIRED_ENTITY_TYPES.get(event_type, [])
    present_types = {e.entity_type for e in entries}
    for required_type in required:
        if required_type not in present_types:
            event = HealthEvent(
                type=HealthEventType.missing,
                severity=HealthSeverity.medium,
                entity=required_type.value,
                entity_type=required_type.value,
                description=f"No data for entity type '{required_type.value}' — expected for {event_type}",
                context={"event_type": event_type, "missing_entity_type": required_type.value},
            )
            emitted = _emit(event)
            if emitted:
                events.append(emitted)
    return events


def resolve_event(type: HealthEventType, entity: str | None, claim_type: str | None) -> bool:
    key = _event_key(type, entity, claim_type)
    if key in _open_events:
        _open_events[key] = _open_events[key].model_copy(
            update={"resolved": True, "resolved_at": _now()}
        )
        return True
    return False


def get_open_events() -> list[HealthEvent]:
    return [e for e in _open_events.values() if not e.resolved]


def get_all_events() -> list[HealthEvent]:
    return list(_open_events.values())


async def run(entries: list[WorldStateEntry], event_type: str) -> list[HealthEvent]:
    all_events: list[HealthEvent] = []
    all_events.extend(await check_staleness(entries))
    all_events.extend(await check_contradictions(entries))
    all_events.extend(await check_missing_data(entries, event_type))
    return all_events
