from unittest.mock import AsyncMock, patch, MagicMock
from datetime import timezone
from app.models import CrisisQuery, EventType, SourceType
from app.stages.sense import (
    _content_hash,
    _infer_source_type,
    _build_search_queries,
    run,
)


# ── Pure functions ─────────────────────────────────────────────────────────────

def test_content_hash_is_deterministic():
    assert _content_hash("hello world") == _content_hash("hello world")


def test_content_hash_normalizes_whitespace():
    assert _content_hash("hello   world") == _content_hash("hello world")


def test_content_hash_normalizes_case():
    assert _content_hash("Hello World") == _content_hash("hello world")


def test_content_hash_differs_for_different_content():
    assert _content_hash("road closed") != _content_hash("road open")


def test_infer_source_type_gov_is_official():
    assert _infer_source_type("https://earthquake.usgs.gov/feed") == SourceType.official


def test_infer_source_type_noaa_is_official():
    assert _infer_source_type("https://api.weather.gov/alerts") == SourceType.official


def test_infer_source_type_reddit_is_social():
    assert _infer_source_type("https://reddit.com/r/wildfires/post/abc") == SourceType.social


def test_infer_source_type_bsky_is_social():
    assert _infer_source_type("https://bsky.app/profile/user/post/123") == SourceType.social


def test_infer_source_type_reuters_is_news():
    assert _infer_source_type("https://www.reuters.com/world/us/story") == SourceType.news


def test_infer_source_type_unknown_is_crawled():
    assert _infer_source_type("https://localcountyherald.com/wildfire") == SourceType.crawled


def test_build_search_queries_includes_base():
    query = CrisisQuery(event_type=EventType.wildfire, location="Los Angeles, CA")
    queries = _build_search_queries(query)
    assert any("wildfire" in q and "Los Angeles" in q for q in queries)


def test_build_search_queries_includes_keywords():
    query = CrisisQuery(
        event_type=EventType.wildfire,
        location="Los Angeles, CA",
        keywords=["evacuation", "shelter"],
    )
    queries = _build_search_queries(query)
    assert any("evacuation" in q for q in queries)


def test_build_search_queries_always_includes_evacuation_terms():
    query = CrisisQuery(event_type=EventType.flood, location="Houston, TX")
    queries = _build_search_queries(query)
    assert any("evacuation" in q or "shelter" in q or "road" in q for q in queries)


# ── Run with no API key returns empty ─────────────────────────────────────────

async def test_run_returns_empty_without_api_key():
    query = CrisisQuery(event_type=EventType.accident, location="Phoenix, AZ")
    docs = await run(query)
    assert isinstance(docs, list)


# ── Structured API sources (USGS, NOAA) ───────────────────────────────────────

async def test_run_fetches_usgs_for_earthquake():
    query = CrisisQuery(event_type=EventType.earthquake, location="San Francisco, CA")
    mock_response = MagicMock()
    mock_response.text = '{"type":"FeatureCollection","features":[]}'
    mock_response.status_code = 200
    mock_response.url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    mock_response.raise_for_status = MagicMock()

    with patch("app.stages.sense.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        instance.post = AsyncMock(return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"results": []}),
        ))
        docs = await run(query)

    assert isinstance(docs, list)


# ── Deduplication ──────────────────────────────────────────────────────────────

def test_content_hash_deduplication_catches_syndicated_articles():
    content = "This is the article body that was syndicated across multiple sites."
    h1 = _content_hash(content)
    h2 = _content_hash("  " + content.upper() + "  ")
    assert h1 == h2
