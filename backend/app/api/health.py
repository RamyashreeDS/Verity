from fastapi import APIRouter

from app.models import HealthSeverity, HealthEventType
from app.stages import health_monitor, healing_loop

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/events")
async def get_health_events(open_only: bool = True):
    events = health_monitor.get_open_events() if open_only else health_monitor.get_all_events()
    return {"events": events, "count": len(events)}


@router.get("/events/by-severity/{severity}")
async def get_by_severity(severity: HealthSeverity):
    events = health_monitor.get_all_events()
    matched = [e for e in events if e.severity == severity]
    return {"events": matched, "count": len(matched)}


@router.get("/events/by-type/{event_type}")
async def get_by_type(event_type: HealthEventType):
    events = health_monitor.get_all_events()
    matched = [e for e in events if e.type == event_type]
    return {"events": matched, "count": len(matched)}


@router.get("/healing/records")
async def get_healing_records():
    records = healing_loop.get_records()
    committed = [r for r in records if r.committed]
    rolled_back = [r for r in records if r.rolled_back]
    return {
        "records": records,
        "total": len(records),
        "committed": len(committed),
        "rolled_back": len(rolled_back),
    }


@router.get("/summary")
async def get_health_summary():
    open_events = health_monitor.get_open_events()
    records = healing_loop.get_records()
    severity_counts = {}
    for e in open_events:
        severity_counts[e.severity.value] = severity_counts.get(e.severity.value, 0) + 1
    type_counts = {}
    for e in open_events:
        type_counts[e.type.value] = type_counts.get(e.type.value, 0) + 1
    return {
        "open_event_count": len(open_events),
        "severity_breakdown": severity_counts,
        "type_breakdown": type_counts,
        "healing_committed": sum(1 for r in records if r.committed),
        "healing_rolled_back": sum(1 for r in records if r.rolled_back),
    }
