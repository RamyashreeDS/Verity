from __future__ import annotations
from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


# ── Enums ──────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    wildfire = "wildfire"
    flood = "flood"
    earthquake = "earthquake"
    hurricane = "hurricane"
    accident = "accident"


class SourceType(str, Enum):
    official = "official"
    news = "news"
    social = "social"
    crawled = "crawled"


class EntityType(str, Enum):
    road = "road"
    shelter = "shelter"
    evacuation_zone = "evacuation_zone"
    fire = "fire"
    flood = "flood"
    utility = "utility"
    weather = "weather"


class WorldStateStatus(str, Enum):
    confirmed = "confirmed"
    low_confidence = "low_confidence"
    unresolved = "unresolved"
    conflicted = "conflicted"
    stale = "stale"


class HealthEventType(str, Enum):
    stale = "stale"
    contradiction = "contradiction"
    missing = "missing"
    loop = "loop"
    source_failure = "source_failure"
    source_degraded = "source_degraded"


class HealthSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class HealingAction(str, Enum):
    update_value = "update_value"
    update_status = "update_status"
    evict_claims = "evict_claims"
    mark_unresolvable = "mark_unresolvable"
    request_resense = "request_resense"
    suppress_source = "suppress_source"


class RejectionReason(str, Enum):
    schema = "schema"
    stale = "stale"
    low_confidence = "low_confidence"
    duplicate = "duplicate"
    invariant = "invariant"


class PipelineRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


# ── Core models ────────────────────────────────────────────────────────────────

class CrisisQuery(BaseModel):
    id: str = Field(default_factory=new_id)
    event_type: EventType
    location: str
    radius_km: int = 50
    time_window_hours: int = 24
    keywords: list[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RawDocument(BaseModel):
    id: str = Field(default_factory=new_id)
    source_url: str
    source_type: SourceType
    crawled_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None
    title: str = ""
    content: str
    content_hash: str
    crisis_query_id: str


class Claim(BaseModel):
    id: str = Field(default_factory=new_id)
    raw_document_id: str
    source_url: str
    source_type: SourceType
    crawled_at: datetime
    published_at: Optional[datetime] = None
    entity: str
    entity_type: EntityType
    claim_type: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    raw_text: str
    entity_canonical: bool = True


class ValidatedClaim(Claim):
    validated_at: datetime = Field(default_factory=datetime.utcnow)
    corrections: list[str] = []


class RejectedClaim(Claim):
    rejection_reason: RejectionReason
    rejection_detail: str
    rejected_at: datetime = Field(default_factory=datetime.utcnow)


class WorldStateEntry(BaseModel):
    entity: str
    entity_type: EntityType
    claim_type: str
    current_value: str
    confidence: float
    status: WorldStateStatus
    last_claim_id: str
    last_updated: datetime
    conflicting_claim_id: Optional[str] = None


class HealthEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    type: HealthEventType
    severity: HealthSeverity
    entity: Optional[str] = None
    entity_type: Optional[str] = None
    claim_type: Optional[str] = None
    description: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    context: dict = {}
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class HealingProposal(BaseModel):
    action: HealingAction
    target_entity: str
    target_claim_type: str
    new_value: Optional[str] = None
    new_status: Optional[str] = None
    evicted_claim_ids: list[str] = []
    reasoning: str
    confidence: float


class HealingRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    health_event_id: str
    diagnosed_cause_type: str
    proposed_action: str
    action_detail: dict
    lfm_reasoning: str
    verify_passed: bool
    test_passed: bool
    committed: bool
    committed_at: Optional[datetime] = None
    rolled_back: bool = False
    rolled_back_reason: Optional[str] = None


# ── Pipeline run tracking ──────────────────────────────────────────────────────

class PipelineStageResult(BaseModel):
    stage: str
    status: str
    count: int = 0
    detail: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PipelineRun(BaseModel):
    id: str = Field(default_factory=new_id)
    query: CrisisQuery
    status: PipelineRunStatus = PipelineRunStatus.pending
    stages: list[PipelineStageResult] = []
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


# ── API request/response models ────────────────────────────────────────────────

class StartPipelineRequest(BaseModel):
    event_type: EventType
    location: str
    radius_km: int = 50
    time_window_hours: int = 24
    keywords: list[str] = []


class DashboardResponse(BaseModel):
    entries: list[WorldStateEntry]
    last_updated: Optional[datetime]
    active_run_id: Optional[str] = None


class VisualRequest(BaseModel):
    crisis_query_id: str
    world_state: list[WorldStateEntry]
