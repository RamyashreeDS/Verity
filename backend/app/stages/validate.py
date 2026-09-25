from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from app.config import settings
from app.models import (
    Claim,
    ValidatedClaim,
    RejectedClaim,
    RejectionReason,
    SourceType,
    EntityType,
)

OFFICIAL_DOMAINS = {
    ".gov", "usgs.gov", "noaa.gov", "weather.gov", "fema.gov",
    "calfire.ca.gov", "gdacs.org", "firms.modaps.eosdis.nasa.gov",
}

SOCIAL_DOMAINS = {
    "reddit.com", "bsky.app", "twitter.com", "x.com",
}

# Mutual exclusion rules: (entity_type, claim_type) -> list of mutually exclusive value pairs
MUTEX_VALUES: dict[tuple, list[tuple[str, str]]] = {
    (EntityType.road, "road_status"): [("open", "closed")],
    (EntityType.evacuation_zone, "evacuation_order"): [
        ("mandatory evacuation", "no evacuation"),
        ("mandatory evacuation", "lifted"),
    ],
    (EntityType.shelter, "shelter_status"): [("open", "closed")],
}

NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "fire_containment_pct": (0.0, 100.0),
    "flood_level_ft": (0.0, 9999.0),
    "shelter_capacity": (0.0, 999999.0),
    "shelter_occupancy": (0.0, 999999.0),
    "wind_speed_mph": (0.0, 999.0),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _check_schema(claim: Claim) -> str | None:
    if not claim.id:
        return "missing id"
    if not claim.entity or not claim.entity.strip():
        return "missing entity"
    if not claim.claim_type or not claim.claim_type.strip():
        return "missing claim_type"
    if not claim.value or not claim.value.strip():
        return "missing value"
    if not (0.0 <= claim.confidence <= 1.0):
        return f"confidence {claim.confidence} out of range"
    if claim.crawled_at > _now() + timedelta(minutes=5):
        return "crawled_at is in the future"
    try:
        urlparse(claim.source_url)
    except Exception:
        return "invalid source_url"
    return None


def _check_freshness(claim: Claim) -> str | None:
    now = _now()
    ref_time = _ensure_tz(claim.published_at) if claim.published_at else _ensure_tz(claim.crawled_at)
    max_age = timedelta(hours=settings.max_claim_age_hours)
    if claim.published_at is None:
        max_age = timedelta(hours=settings.max_claim_age_hours + 24)
    if now - ref_time > max_age:
        return f"claim is {(now - ref_time).total_seconds() / 3600:.1f}h old (max {max_age.total_seconds() / 3600}h)"
    if claim.published_at and _ensure_tz(claim.published_at) > now + timedelta(hours=1):
        return "published_at is in the future"
    return None


def _check_confidence(claim: Claim) -> str | None:
    floor = (
        settings.confidence_floor_official
        if claim.source_type == SourceType.official
        else settings.confidence_floor
    )
    if claim.confidence < floor:
        return f"confidence {claim.confidence:.2f} below floor {floor}"
    return None


def _check_invariants(claim: Claim) -> str | None:
    key = (claim.entity_type, claim.claim_type)
    pairs = MUTEX_VALUES.get(key, [])
    value_lower = claim.value.lower()
    for a, b in pairs:
        if a in value_lower and b in value_lower:
            return f"claim simultaneously asserts '{a}' and '{b}' for {claim.claim_type}"

    if claim.claim_type in NUMERIC_RANGES:
        lo, hi = NUMERIC_RANGES[claim.claim_type]
        try:
            num = float("".join(c for c in claim.value if c.isdigit() or c == "."))
            if not (lo <= num <= hi):
                return f"{claim.claim_type} value {num} out of expected range [{lo}, {hi}]"
        except ValueError:
            pass

    return None


def _correct_source_type(claim: Claim) -> tuple[Claim, list[str]]:
    corrections: list[str] = []
    domain = urlparse(claim.source_url).netloc.lower()

    if any(d in domain for d in OFFICIAL_DOMAINS) and claim.source_type != SourceType.official:
        claim = claim.model_copy(update={"source_type": SourceType.official})
        corrections.append(f"upgraded source_type to official (domain: {domain})")
    elif any(d in domain for d in SOCIAL_DOMAINS) and claim.source_type == SourceType.official:
        claim = claim.model_copy(update={"source_type": SourceType.social})
        corrections.append(f"downgraded source_type to social (domain: {domain})")

    return claim, corrections


def validate(claim: Claim, existing_claim_keys: set[tuple]) -> ValidatedClaim | RejectedClaim:
    # Schema
    err = _check_schema(claim)
    if err:
        return RejectedClaim(**claim.model_dump(), rejection_reason=RejectionReason.schema, rejection_detail=err)

    # Source type correction (mutates claim copy)
    claim, corrections = _correct_source_type(claim)

    # Freshness
    err = _check_freshness(claim)
    if err:
        return RejectedClaim(**claim.model_dump(), rejection_reason=RejectionReason.stale, rejection_detail=err)

    # Confidence
    err = _check_confidence(claim)
    if err:
        return RejectedClaim(**claim.model_dump(), rejection_reason=RejectionReason.low_confidence, rejection_detail=err)

    # Duplicate
    dedup_key = (
        claim.entity.lower(),
        claim.claim_type.lower(),
        claim.value.lower().strip(),
        claim.source_url,
    )
    if dedup_key in existing_claim_keys:
        return RejectedClaim(
            **claim.model_dump(),
            rejection_reason=RejectionReason.duplicate,
            rejection_detail="identical claim already processed in this run",
        )

    # Invariants
    err = _check_invariants(claim)
    if err:
        return RejectedClaim(**claim.model_dump(), rejection_reason=RejectionReason.invariant, rejection_detail=err)

    return ValidatedClaim(**claim.model_dump(), corrections=corrections)


def run(claims: list[Claim]) -> tuple[list[ValidatedClaim], list[RejectedClaim]]:
    validated: list[ValidatedClaim] = []
    rejected: list[RejectedClaim] = []
    seen_keys: set[tuple] = set()

    for claim in claims:
        result = validate(claim, seen_keys)
        if isinstance(result, ValidatedClaim):
            key = (
                claim.entity.lower(),
                claim.claim_type.lower(),
                claim.value.lower().strip(),
                claim.source_url,
            )
            seen_keys.add(key)
            validated.append(result)
        else:
            rejected.append(result)

    return validated, rejected
