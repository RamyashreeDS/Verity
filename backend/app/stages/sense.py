import hashlib
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.models import CrisisQuery, RawDocument, SourceType, EventType
from app.stages import mock_data

NIMBLE_BASE_URL = "https://api.webit.live/api/v1"

SOURCE_APIS: dict[EventType, list[dict]] = {
    EventType.earthquake: [
        {
            "url": "https://earthquake.usgs.gov/fdsnws/event/1/query",
            "params": {"format": "geojson", "limit": 20, "minmagnitude": 2.5},
            "source_type": SourceType.official,
        }
    ],
    EventType.wildfire: [
        {
            "url": "https://firms.modaps.eosdis.nasa.gov/api/area/csv",
            "params": {"source": "VIIRS_SNPP_NRT", "day_range": 1, "area": "world"},
            "source_type": SourceType.official,
        }
    ],
    EventType.flood: [
        {
            "url": "https://api.weather.gov/alerts/active",
            "params": {"event": "Flood Warning,Flash Flood Warning"},
            "source_type": SourceType.official,
        }
    ],
    EventType.hurricane: [
        {
            "url": "https://api.weather.gov/alerts/active",
            "params": {"event": "Hurricane Warning,Hurricane Watch,Tropical Storm Warning"},
            "source_type": SourceType.official,
        }
    ],
}

SOCIAL_SEARCH_DOMAINS = [
    "reddit.com",
    "bsky.app",
]


def _content_hash(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def _build_search_queries(query: CrisisQuery) -> list[str]:
    base = f"{query.event_type.value} {query.location}"
    queries = [base]
    if query.keywords:
        queries.append(f"{base} {' '.join(query.keywords)}")
    queries.append(f"{query.event_type.value} {query.location} evacuation shelter road")
    return queries


async def _nimble_search(client: httpx.AsyncClient, query: str) -> list[str]:
    if not settings.nimble_api_key:
        return []
    try:
        resp = await client.post(
            f"{NIMBLE_BASE_URL}/realtime/web",
            headers={"Authorization": f"Bearer {settings.nimble_api_key}"},
            json={"query": query, "search_engine": "google", "num_results": settings.max_urls_per_query},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return [r["url"] for r in data.get("results", []) if "url" in r]
    except Exception:
        return []


async def _nimble_crawl(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    if not settings.nimble_api_key:
        return None
    try:
        resp = await client.post(
            f"{NIMBLE_BASE_URL}/realtime/web",
            headers={"Authorization": f"Bearer {settings.nimble_api_key}"},
            json={"url": url, "render": True},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "") or data.get("text", "")
        if not content:
            return None
        return {
            "title": data.get("title", ""),
            "content": content,
            "published_at": data.get("published_at"),
        }
    except Exception:
        return None


async def _fetch_structured_api(
    client: httpx.AsyncClient,
    source: dict,
    crisis_query_id: str,
) -> list[RawDocument]:
    try:
        resp = await client.get(source["url"], params=source.get("params", {}), timeout=10)
        resp.raise_for_status()
        content = resp.text
        return [
            RawDocument(
                source_url=str(resp.url),
                source_type=source["source_type"],
                content=content,
                content_hash=_content_hash(content),
                crisis_query_id=crisis_query_id,
                crawled_at=datetime.now(timezone.utc),
            )
        ]
    except Exception:
        return []


def _infer_source_type(url: str) -> SourceType:
    lower = url.lower()
    official_domains = [".gov", ".noaa.gov", "usgs.gov", "fema.gov", "calfire", "gdacs.org"]
    if any(d in lower for d in official_domains):
        return SourceType.official
    social_domains = ["reddit.com", "bsky.app", "twitter.com", "x.com"]
    if any(d in lower for d in social_domains):
        return SourceType.social
    news_domains = ["reuters.com", "apnews.com", "bbc.com", "cnn.com", "theguardian.com"]
    if any(d in lower for d in news_domains):
        return SourceType.news
    return SourceType.crawled


async def run(query: CrisisQuery) -> list[RawDocument]:
    # ── DEMO MODE ────────────────────────────────────────────────────────────
    if settings.demo_mode:
        return mock_data.MOCK_DOCUMENTS
    # ── END DEMO MODE ─────────────────────────────────────────────────────────

    documents: list[RawDocument] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()

    async with httpx.AsyncClient() as client:
        # 1. Fetch structured government APIs first
        api_tasks = [
            _fetch_structured_api(client, source, query.id)
            for source in SOURCE_APIS.get(query.event_type, [])
        ]
        for result in await asyncio.gather(*api_tasks):
            for doc in result:
                if doc.content_hash not in seen_hashes:
                    seen_hashes.add(doc.content_hash)
                    seen_urls.add(doc.source_url)
                    documents.append(doc)

        # 2. Nimble search for additional URLs
        search_queries = _build_search_queries(query)
        url_sets = await asyncio.gather(*[_nimble_search(client, q) for q in search_queries])
        candidate_urls = [u for urls in url_sets for u in urls if u not in seen_urls]
        candidate_urls = list(dict.fromkeys(candidate_urls))  # dedup preserving order

        # 3. Crawl candidates with concurrency limit
        sem = asyncio.Semaphore(settings.max_concurrent_crawls)

        async def crawl_one(url: str) -> Optional[RawDocument]:
            async with sem:
                result = await _nimble_crawl(client, url)
            if not result or not result["content"]:
                return None
            content_hash = _content_hash(result["content"])
            if content_hash in seen_hashes:
                return None
            seen_hashes.add(content_hash)
            published_at = None
            if result.get("published_at"):
                try:
                    published_at = datetime.fromisoformat(result["published_at"])
                except Exception:
                    pass
            return RawDocument(
                source_url=url,
                source_type=_infer_source_type(url),
                crawled_at=datetime.now(timezone.utc),
                published_at=published_at,
                title=result["title"],
                content=result["content"],
                content_hash=content_hash,
                crisis_query_id=query.id,
            )

        crawl_results = await asyncio.gather(*[crawl_one(u) for u in candidate_urls])
        documents.extend(doc for doc in crawl_results if doc is not None)

    return documents
