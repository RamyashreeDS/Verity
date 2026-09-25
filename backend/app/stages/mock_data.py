"""
DEMO SCENARIO: San Francisco — Busy Saturday
=============================================

A typical high-activity Saturday in San Francisco with multiple concurrent events:

  - SF Pride Parade (Market St closure, crowds, first aid)
  - Bay Bridge weekend lane restrictions (Caltrans construction)
  - BART Civic Center closure (maintenance)
  - 3.2 magnitude earthquake near Hayward Fault (minor, no damage)
  - Mission District water main break (flooding, road closure)
  - Dense fog advisory (Golden Gate / Embarcadero)
  - Warriors playoff game at Chase Center (traffic, road congestion)

CONFLICT:  Market St road_status — SFMTA official says "closed", local
           blog says "partial open near Van Ness". Healing loop resolves
           to "closed" (official source wins).

STALENESS: Golden Gate fog entry is 9 hours old → triggers staleness alert.
"""

import hashlib
from datetime import datetime, timezone, timedelta

from app.models import RawDocument, Claim, SourceType, EntityType


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(text: str) -> str:
    return hashlib.sha256(text.lower().encode()).hexdigest()


QUERY_ID = "demo-query-sf-saturday"

# ── Raw Documents ──────────────────────────────────────────────────────────────

MOCK_DOCUMENTS: list[RawDocument] = [

    RawDocument(
        id="doc-sfmta-001",
        source_url="https://www.sfmta.com/press-releases/sf-pride-2024-street-closures",
        source_type=SourceType.official,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=1),
        title="SFMTA — SF Pride 2024 Street Closure Advisory",
        content=(
            "STREET CLOSURE ADVISORY — SF Pride Parade 2024. "
            "Market Street is CLOSED in both directions from Beale Street to 8th Street "
            "from 10:30 AM through approximately 6:00 PM on Saturday. "
            "Embarcadero is closed from Howard to Washington Street. "
            "Muni Metro routes F, J, K, L, M, N are on surface street detours. "
            "BART Civic Center/UN Plaza Station closed for maintenance this weekend — "
            "use Powell St or 16th St Mission as alternates. "
            "A Pride First Aid and Cooling Station is operational at UN Plaza "
            "with capacity for 150 people, currently 62 attendees being assisted. "
            "Expect crowds of 500,000 to 700,000 along the parade route."
        ),
        content_hash=_hash("sfmta-pride-closures-001"),
        crisis_query_id=QUERY_ID,
    ),

    RawDocument(
        id="doc-caltrans-002",
        source_url="https://dot.ca.gov/news/bay-bridge-weekend-work-2024",
        source_type=SourceType.official,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=3),
        title="Caltrans — Bay Bridge Weekend Lane Restrictions",
        content=(
            "TRAFFIC ADVISORY: The Bay Bridge (I-80) westbound will have two right lanes "
            "closed from the toll plaza to the Fremont Street off-ramp through Sunday 5 AM "
            "for seismic retrofit bolt replacement on the SAS span. "
            "Expect 25 to 40 minute delays during peak hours. "
            "Drivers are encouraged to use BART, the Bay Bridge express lanes, "
            "or consider the San Mateo-Hayward Bridge as an alternate crossing."
        ),
        content_hash=_hash("caltrans-bay-bridge-002"),
        crisis_query_id=QUERY_ID,
    ),

    RawDocument(
        id="doc-bart-003",
        source_url="https://www.bart.gov/alerts/civic-center-closure-weekend",
        source_type=SourceType.official,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=5),
        title="BART — Civic Center/UN Plaza Station Closed This Weekend",
        content=(
            "Civic Center/UN Plaza Station is CLOSED Saturday and Sunday for "
            "platform safety inspection and ADA elevator modernization work. "
            "All lines serving Civic Center will bypass the station without stopping. "
            "Customers should use Powell Street Station (0.4 miles east) or "
            "16th Street Mission Station (0.7 miles south) as alternatives. "
            "Free shuttle buses are operating between Powell St BART and Civic Center "
            "every 8 minutes."
        ),
        content_hash=_hash("bart-civic-center-closure-003"),
        crisis_query_id=QUERY_ID,
    ),

    RawDocument(
        id="doc-usgs-004",
        source_url="https://earthquake.usgs.gov/earthquakes/eventpage/nc75014082",
        source_type=SourceType.official,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=2),
        title="USGS — M3.2 Earthquake, Hayward Fault",
        content=(
            "A magnitude 3.2 earthquake occurred at 8:47 AM local time "
            "3.1 km northeast of Fremont, CA on the Hayward Fault. "
            "Depth: 8.2 km. Maximum reported shaking: Weak (MMI III). "
            "No damage reports. No tsunami warning issued. "
            "Felt by residents in Fremont, Oakland, and parts of San Francisco. "
            "This is consistent with routine seismic activity along the Hayward Fault."
        ),
        content_hash=_hash("usgs-hayward-m32-004"),
        crisis_query_id=QUERY_ID,
    ),

    RawDocument(
        id="doc-sfpuc-005",
        source_url="https://sfwater.org/index.aspx?page=640&eid=10842",
        source_type=SourceType.official,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=2),
        title="SFPUC — Water Main Break, Mission District",
        content=(
            "SFPUC crews are responding to a 12-inch water main break at the "
            "intersection of 24th Street and Valencia Street in the Mission District. "
            "Water service is interrupted for approximately 340 addresses between "
            "22nd and 26th Streets from Guerrero to Mission Street. "
            "24th Street is closed between Valencia and Mission Street for repairs. "
            "Street flooding of 2 to 4 inches reported on Valencia between 23rd and 25th. "
            "Estimated restoration time: 6–8 hours. Crews are on site."
        ),
        content_hash=_hash("sfpuc-watermain-mission-005"),
        crisis_query_id=QUERY_ID,
    ),

    RawDocument(
        id="doc-nws-006",
        source_url="https://api.weather.gov/alerts/active?zone=CAZ006",
        source_type=SourceType.official,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=9),   # intentionally stale
        title="NWS Bay Area — Dense Fog Advisory",
        content=(
            "DENSE FOG ADVISORY in effect until 11 AM PDT for San Francisco Bay shoreline. "
            "Visibility one quarter mile or less in dense fog. "
            "Visibility at Golden Gate Bridge: 0.2 miles. "
            "Ferry services operating with reduced speed. "
            "Bay Bridge approach visibility: 0.6 miles. "
            "Fog expected to lift by late morning."
        ),
        content_hash=_hash("nws-sf-fog-advisory-006"),
        crisis_query_id=QUERY_ID,
    ),

    RawDocument(
        id="doc-sfgate-007",
        source_url="https://www.sfgate.com/sports/article/warriors-playoff-traffic-chase-center",
        source_type=SourceType.news,
        crawled_at=_now(),
        published_at=_now() - timedelta(hours=1),
        title="SFGate — Warriors playoff game tonight: Chase Center traffic guide",
        content=(
            "The Golden State Warriors host Game 4 of the Western Conference Semifinals "
            "tonight at Chase Center, tipoff at 7:30 PM. "
            "3rd Street and 16th Street are expected to be heavily congested from 5 PM onward. "
            "The King Street Caltrain station will have extended service post-game. "
            "Uber and Lyft surges expected in the Mission Bay and SoMa neighborhoods. "
            "Limited parking available — UCSF Mission Bay garage at $35 flat rate."
        ),
        content_hash=_hash("sfgate-warriors-game-007"),
        crisis_query_id=QUERY_ID,
    ),

    # ── Conflicting document ───────────────────────────────────────────────────
    # A local neighborhood blog claims the western section of Market St is open.
    # This contradicts the official SFMTA full closure. Healing loop resolves it.
    RawDocument(
        id="doc-haightlocal-008",
        source_url="https://haightashburylocal.blogspot.com/2024/06/pride-day-market-open",
        source_type=SourceType.social,
        crawled_at=_now(),
        published_at=_now() - timedelta(minutes=30),
        title="Haight Ashbury Local — Market St near Van Ness seems open?",
        content=(
            "Walked up to Market and Van Ness this morning and traffic was moving westbound. "
            "Looks like they kept the western section open past Church Street? "
            "Not sure if this is official or if they just haven't put up barriers yet. "
            "Update: someone in comments says it's only open until noon then they close it."
        ),
        content_hash=_hash("haight-market-open-blog-008"),
        crisis_query_id=QUERY_ID,
    ),

]


# ── Claims ─────────────────────────────────────────────────────────────────────

MOCK_CLAIMS: list[Claim] = [

    # ── Pride Parade — Roads ───────────────────────────────────────────────────
    Claim(
        id="claim-001",
        raw_document_id="doc-sfmta-001",
        source_url="https://www.sfmta.com/press-releases/sf-pride-2024-street-closures",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="Market Street",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="closed",
        confidence=0.99,
        raw_text="Market Street is CLOSED in both directions from Beale Street to 8th Street.",
    ),
    Claim(
        id="claim-002",
        raw_document_id="doc-sfmta-001",
        source_url="https://www.sfmta.com/press-releases/sf-pride-2024-street-closures",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="Market Street",
        entity_type=EntityType.road,
        claim_type="closure_reason",
        value="SF Pride Parade 2024",
        confidence=0.99,
        raw_text="SF Pride Parade 2024.",
    ),
    Claim(
        id="claim-003",
        raw_document_id="doc-sfmta-001",
        source_url="https://www.sfmta.com/press-releases/sf-pride-2024-street-closures",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="Embarcadero",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="closed",
        confidence=0.99,
        raw_text="Embarcadero is closed from Howard to Washington Street.",
    ),

    # CONFLICTING CLAIM — blog says Market St near Van Ness is open
    Claim(
        id="claim-004",
        raw_document_id="doc-haightlocal-008",
        source_url="https://haightashburylocal.blogspot.com/2024/06/pride-day-market-open",
        source_type=SourceType.social,
        crawled_at=_now(), published_at=_now() - timedelta(minutes=30),
        entity="Market Street",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="partial open",
        confidence=0.52,
        raw_text="traffic was moving westbound... Looks like they kept the western section open past Church Street?",
    ),

    # ── Pride Parade — Shelter / First Aid ────────────────────────────────────
    Claim(
        id="claim-005",
        raw_document_id="doc-sfmta-001",
        source_url="https://www.sfmta.com/press-releases/sf-pride-2024-street-closures",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="UN Plaza First Aid Station",
        entity_type=EntityType.shelter,
        claim_type="shelter_status",
        value="open",
        confidence=0.97,
        raw_text="A Pride First Aid and Cooling Station is operational at UN Plaza.",
    ),
    Claim(
        id="claim-006",
        raw_document_id="doc-sfmta-001",
        source_url="https://www.sfmta.com/press-releases/sf-pride-2024-street-closures",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="UN Plaza First Aid Station",
        entity_type=EntityType.shelter,
        claim_type="shelter_occupancy",
        value="62",
        confidence=0.91,
        raw_text="currently 62 attendees being assisted",
    ),

    # ── Bay Bridge ─────────────────────────────────────────────────────────────
    Claim(
        id="claim-007",
        raw_document_id="doc-caltrans-002",
        source_url="https://dot.ca.gov/news/bay-bridge-weekend-work-2024",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=3),
        entity="Bay Bridge (I-80)",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="2 lanes closed westbound",
        confidence=0.97,
        raw_text="westbound will have two right lanes closed from the toll plaza to Fremont Street off-ramp.",
    ),
    Claim(
        id="claim-008",
        raw_document_id="doc-caltrans-002",
        source_url="https://dot.ca.gov/news/bay-bridge-weekend-work-2024",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=3),
        entity="Bay Bridge (I-80)",
        entity_type=EntityType.road,
        claim_type="closure_reason",
        value="seismic retrofit construction",
        confidence=0.97,
        raw_text="seismic retrofit bolt replacement on the SAS span",
    ),

    # ── BART ───────────────────────────────────────────────────────────────────
    Claim(
        id="claim-009",
        raw_document_id="doc-bart-003",
        source_url="https://www.bart.gov/alerts/civic-center-closure-weekend",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=5),
        entity="Civic Center/UN Plaza BART",
        entity_type=EntityType.road,
        claim_type="transit_status",
        value="closed — use Powell St or 16th St Mission",
        confidence=0.99,
        raw_text="Civic Center/UN Plaza Station is CLOSED Saturday and Sunday for platform safety inspection.",
    ),

    # ── Earthquake ─────────────────────────────────────────────────────────────
    Claim(
        id="claim-010",
        raw_document_id="doc-usgs-004",
        source_url="https://earthquake.usgs.gov/earthquakes/eventpage/nc75014082",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=2),
        entity="Hayward Fault — Fremont",
        entity_type=EntityType.evacuation_zone,
        claim_type="seismic_activity",
        value="M3.2 — no damage reported",
        confidence=0.99,
        raw_text="A magnitude 3.2 earthquake occurred... Maximum reported shaking: Weak (MMI III). No damage reports.",
    ),
    Claim(
        id="claim-011",
        raw_document_id="doc-usgs-004",
        source_url="https://earthquake.usgs.gov/earthquakes/eventpage/nc75014082",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=2),
        entity="Hayward Fault — Fremont",
        entity_type=EntityType.evacuation_zone,
        claim_type="evacuation_order",
        value="none",
        confidence=0.99,
        raw_text="No damage reports. No tsunami warning issued.",
    ),

    # ── Water Main Break ───────────────────────────────────────────────────────
    Claim(
        id="claim-012",
        raw_document_id="doc-sfpuc-005",
        source_url="https://sfwater.org/index.aspx?page=640&eid=10842",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=2),
        entity="Valencia & 24th St",
        entity_type=EntityType.flood,
        claim_type="flood_status",
        value="street flooding 2–4 inches",
        confidence=0.95,
        raw_text="Street flooding of 2 to 4 inches reported on Valencia between 23rd and 25th.",
    ),
    Claim(
        id="claim-013",
        raw_document_id="doc-sfpuc-005",
        source_url="https://sfwater.org/index.aspx?page=640&eid=10842",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=2),
        entity="24th Street (Mission)",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="closed — water main repair",
        confidence=0.95,
        raw_text="24th Street is closed between Valencia and Mission Street for repairs.",
    ),
    Claim(
        id="claim-014",
        raw_document_id="doc-sfpuc-005",
        source_url="https://sfwater.org/index.aspx?page=640&eid=10842",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=2),
        entity="SFPUC Mission District Water",
        entity_type=EntityType.utility,
        claim_type="utility_status",
        value="outage — 340 addresses affected",
        confidence=0.97,
        raw_text="Water service is interrupted for approximately 340 addresses between 22nd and 26th Streets.",
    ),

    # ── Weather — intentionally stale (9h old) ────────────────────────────────
    Claim(
        id="claim-015",
        raw_document_id="doc-nws-006",
        source_url="https://api.weather.gov/alerts/active?zone=CAZ006",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=9),
        entity="San Francisco Bay",
        entity_type=EntityType.weather,
        claim_type="fog_advisory",
        value="Dense Fog Advisory — visibility 0.2 miles",
        confidence=0.98,
        raw_text="DENSE FOG ADVISORY in effect. Visibility at Golden Gate Bridge: 0.2 miles.",
    ),
    Claim(
        id="claim-016",
        raw_document_id="doc-nws-006",
        source_url="https://api.weather.gov/alerts/active?zone=CAZ006",
        source_type=SourceType.official,
        crawled_at=_now(), published_at=_now() - timedelta(hours=9),
        entity="San Francisco Bay",
        entity_type=EntityType.weather,
        claim_type="ferry_status",
        value="operating — reduced speed",
        confidence=0.90,
        raw_text="Ferry services operating with reduced speed.",
    ),

    # ── Warriors Game — Traffic ────────────────────────────────────────────────
    Claim(
        id="claim-017",
        raw_document_id="doc-sfgate-007",
        source_url="https://www.sfgate.com/sports/article/warriors-playoff-traffic-chase-center",
        source_type=SourceType.news,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="Chase Center — 3rd St",
        entity_type=EntityType.road,
        claim_type="road_status",
        value="heavy congestion expected from 5 PM",
        confidence=0.82,
        raw_text="3rd Street and 16th Street are expected to be heavily congested from 5 PM onward.",
    ),
    Claim(
        id="claim-018",
        raw_document_id="doc-sfgate-007",
        source_url="https://www.sfgate.com/sports/article/warriors-playoff-traffic-chase-center",
        source_type=SourceType.news,
        crawled_at=_now(), published_at=_now() - timedelta(hours=1),
        entity="Chase Center",
        entity_type=EntityType.shelter,
        claim_type="event_status",
        value="Warriors vs Timberwolves — Game 4, 7:30 PM tipoff",
        confidence=0.95,
        raw_text="The Golden State Warriors host Game 4 of the Western Conference Semifinals tonight at Chase Center, tipoff at 7:30 PM.",
    ),

]


# ── Mock Healing Loop diagnosis for Market Street contradiction ────────────────

MOCK_DIAGNOSIS = {
    "root_cause": (
        "Official SFMTA street closure advisory (confidence: 0.99) contradicts an "
        "unverified neighborhood blog post (confidence: 0.52) about Market Street status. "
        "The blog post is hedged ('looks like', 'not sure if this is official', 'Update: "
        "someone in comments says') and describes a partial, temporary situation."
    ),
    "cause_type": "source_conflict",
    "affected_claims": ["claim-004"],
    "proposed_action_type": "update_value",
    "proposed_value": "closed",
    "proposed_status": None,
    "reasoning": (
        "SFMTA is the authoritative source for San Francisco street closures. "
        "Their advisory explicitly states Market Street is closed in both directions. "
        "The blog observation may describe a brief pre-closure window or a misread of "
        "the situation. Official source outranks unverified social observation on "
        "road closure status. Confirm Market Street as closed."
    ),
    "confidence": 0.96,
}
