# Stage 1 — Sense

## Purpose

Discover and collect raw information about an active crisis from external sources. This stage is the entry point of the pipeline — it produces uninterpreted raw documents that the Understand stage will process.

The Sense stage knows nothing about what the text means. Its only job is: given a crisis query, find relevant pages, crawl them, extract their text, and deduplicate.

---

## Tool: Nimble API

Nimble handles all crawling and scraping. It manages:
- JavaScript-rendered pages (government dashboards, dynamic news sites)
- Proxy rotation (to avoid blocks on high-frequency crawls)
- Structured extraction (article text, headlines, publish dates)

Nimble is called in two modes:
1. **Search mode** — given a query string, returns a ranked list of relevant URLs
2. **Crawl mode** — given a URL, returns the extracted page content

---

## Inputs

```
CrisisQuery {
  event_type: enum(wildfire | flood | earthquake | hurricane | accident)
  location: string          // e.g. "Los Angeles County, CA"
  radius_km: int            // search radius around location centroid
  time_window_hours: int    // how far back to look (default: 24)
  keywords: list[string]    // optional additional search terms
}
```

---

## Process

```
1. Build search queries from CrisisQuery
      → "<event_type> <location> <keywords>"
      → site-specific queries for known high-value sources (USGS, NWS, CAL FIRE, etc.)

2. Nimble Search → list of candidate URLs (ranked by relevance)

3. Filter URLs
      → skip already-crawled URLs (URL dedup store)
      → skip known-bad domains (blocklist)

4. Nimble Crawl each URL → raw page content

5. Content deduplication
      → compute content hash (SHA-256 of normalized text)
      → skip if hash already seen in this pipeline run

6. Emit RawDocument for each unique result
```

---

## Outputs

```
RawDocument {
  id: string                // uuid
  source_url: string
  source_type: enum(official | news | social | crawled)
  crawled_at: timestamp     // when Nimble fetched it
  published_at: timestamp   // article publish date (null if unknown)
  title: string
  content: string           // extracted text body
  content_hash: string      // SHA-256 of normalized content
  crisis_query_id: string   // back-reference to triggering query
}
```

---

## Deduplication Strategy

Two-layer deduplication:
1. **URL dedup** — maintain a set of crawled URLs per pipeline run. Do not re-crawl the same URL within a run.
2. **Content hash dedup** — after extracting text, hash the normalized content. Reject documents whose hash matches an already-seen document. This catches syndicated articles that appear on multiple domains with identical text.

Normalization before hashing: lowercase, strip HTML, collapse whitespace, remove boilerplate (nav, footers, ads).

---

## Data Sources by Event Type

| Event Type | Primary Sources |
|---|---|
| Wildfire | NASA FIRMS, CAL FIRE, local news RSS, InciWeb |
| Earthquake | USGS Earthquake API, USGS ShakeMap |
| Flood | NOAA/NWS Alerts, USGS Water Resources |
| Hurricane | National Hurricane Center, NOAA |
| General | GDELT Project, NewsAPI, GDACS, FEMA |

For structured APIs (USGS, NOAA, FIRMS), Sense hits the API directly and wraps the response as a RawDocument — Nimble is not used for these.

---

## Error Handling

| Error | Behavior |
|---|---|
| Nimble API timeout | Retry up to 3 times with exponential backoff. Log and skip URL after 3 failures. |
| Nimble returns empty content | Log as `crawl_empty`, skip document. |
| Published date missing | Set `published_at = null`. Validate stage will apply staleness rules. |
| Source API (USGS, NOAA) error | Log, skip that source for this run, continue with others. |

---

## Configuration

```
NIMBLE_API_KEY: string
MAX_URLS_PER_QUERY: int          // default: 20
CRAWL_TIMEOUT_SECONDS: int       // default: 10
DEDUP_WINDOW_HOURS: int          // how long URL/content hashes are retained (default: 48)
```

---

## Performance Notes

- Nimble calls are the slowest part of this stage. Run crawls concurrently (up to `MAX_CONCURRENT_CRAWLS`, default 5).
- Structured API calls (USGS, NOAA) are fast and should run first to seed the URL list.
- A single pipeline run for an active crisis should complete Sense in under 2 minutes.
