"""RoadWatch SF agent: compact working state + explicit forgetting rules + SQLite long-term memory."""
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

from store import make_store

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")

CLOSURES_URL = "https://data.sf.gov/resource/8x25-yybr.json"
CENTERLINES_URL = "https://data.sf.gov/resource/3psu-pn9h.json"
NIMBLE_SEARCH_URL = "https://sdk.nimbleway.com/v2/search"

REPLAY_START = datetime(2026, 9, 19, 6, 0)
REPLAY_END = datetime(2026, 10, 3, 0, 0)

TRUST = {"gov": 0.95, "news": 0.8, "social": 0.3}
CONFIRM_THRESHOLD = 0.7
RETIRE_BUFFER = timedelta(minutes=30)
DECAY_PER_HOUR = 0.15
DROP_BELOW = 0.2
CONTEXT_CAP_TOKENS = 4000


def approx_tokens(text: str) -> int:
    return len(text) // 4


# ---------- sources ----------

def fetch_datasf() -> list[dict]:
    cache = DATA / "datasf_closures.json"
    if cache.exists():
        return json.loads(cache.read_text())
    where = f"start_dt <= '{REPLAY_END:%Y-%m-%dT%H:%M:%S}' AND end_dt >= '{REPLAY_START:%Y-%m-%dT%H:%M:%S}'"
    rows = requests.get(CLOSURES_URL, params={"$where": where, "$limit": 5000}, timeout=60).json()
    cache.write_text(json.dumps(rows))
    return rows


def datasf_events(rows: list[dict]) -> list[dict]:
    """One event per permit (case + time window); each street segment becomes one line of the geometry."""
    grouped: dict[tuple, dict] = {}
    for r in rows:
        if "shape" not in r or "start_dt" not in r or "end_dt" not in r:
            continue
        key = (r.get("case_num"), r["start_dt"], r["end_dt"])
        ev = grouped.get(key)
        if ev is None:
            blocked = r.get("veh_imp") == "all-lanes-closed"
            ev = grouped[key] = {
                "id": "dsf_" + hashlib.md5(repr(key).encode()).hexdigest()[:8],
                "title": r.get("case_name", "Permit"),
                "streets": [],
                "type": (r.get("type") or "other").lower(),
                "status": "blocked" if blocked else "partial",
                "starts_at": r["start_dt"][:19],
                "ends_at": r["end_dt"][:19],
                "confidence": TRUST["gov"],
                "sources": [{"kind": "gov", "name": "DataSF Temporary Street Closures", "url": CLOSURES_URL}],
                "geometry": {"type": "MultiLineString", "coordinates": []},
                "summary": (r.get("info") or r.get("loc_desc", ""))[:160],
                "raw": r,
            }
        ev["streets"].append(r.get("loc_desc", r.get("street", "")))
        ev["geometry"]["coordinates"].append(r["shape"]["coordinates"])
    for ev in grouped.values():
        ev["streets"] = sorted(set(ev["streets"]))
    return sorted(grouped.values(), key=lambda e: e["starts_at"])


def nimble_search(query: str, max_results: int = 5) -> list[dict]:
    key = os.environ.get("NIMBLE_API_KEY")
    if not key:
        return []
    resp = requests.post(
        NIMBLE_SEARCH_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query, "max_results": max_results},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


# ---------- geocoding ----------

SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "PLACE": "PL",
          "LANE": "LN", "COURT": "CT", "TERRACE": "TER", "WAY": "WAY", "HIGHWAY": "HWY"}


def norm_street(name: str) -> str:
    s = re.sub(r"[.,]", "", (name or "").upper()).strip()
    parts = s.split()
    if parts and parts[-1] in SUFFIX:
        parts[-1] = SUFFIX[parts[-1]]
    parts = [("0" + p) if re.fullmatch(r"\d(ST|ND|RD|TH)", p) else p for p in parts]
    return " ".join(parts)


def street_key(name: str) -> str:
    """Street name without suffix, used to match events on the same street."""
    parts = norm_street(name).split()
    if len(parts) > 1 and parts[-1] in SUFFIX.values():
        parts = parts[:-1]
    return " ".join(parts)


def forget_rule(why: str) -> str:
    if why.startswith("ended"):
        return "expired"
    if "decayed" in why:
        return "decayed"
    if "reopened" in why:
        return "cleared"
    if "compacted" in why:
        return "compacted"
    return "other"


def base_street(label: str) -> str:
    """'North Point St between Powell and Stockton' / 'Market St at 5th St' -> 'NORTH POINT' / 'MARKET'."""
    return street_key(re.split(r"\s+(?:between|at|from|near)\s+", label, maxsplit=1, flags=re.I)[0])


def label_crosses(label: str) -> list[str]:
    """'Market St between 5th St and 8th St' -> ['05TH', '08TH']; 'Market St at 5th St' -> ['05TH']."""
    parts = re.split(r"\s+(?:between|at|from|near)\s+", label, maxsplit=1, flags=re.I)
    return split_crosses(parts[1]) if len(parts) > 1 else []


def split_crosses(*names: str | None) -> list[str]:
    """'Powell and Stockton' / 'Powell & Stockton' / ['Powell', 'Stockton'] -> ['POWELL', 'STOCKTON']."""
    out = []
    for n in names:
        for part in re.split(r"\s+(?:and|&|to)\s+|/|,", n or "", flags=re.I):
            k = street_key(part)
            if k and k not in out:
                out.append(k)
    return out


def _centerlines(where: str, limit: int = 40) -> list:
    try:
        rows = requests.get(CENTERLINES_URL, params={"$select": "line", "$where": where, "$limit": limit}, timeout=30).json()
        return [r["line"]["coordinates"] for r in rows if isinstance(r, dict) and "line" in r]
    except Exception:
        return []


def geocode(street: str, cross: str | None, from_st: str | None = None, to_st: str | None = None) -> dict | None:
    s = norm_street(street)
    if not s.endswith(tuple(" " + v for v in SUFFIX.values())):
        s_where = f"streetname like '{s} %'"
    else:
        s_where = f"streetname = '{s}'"
    crosses = split_crosses(cross, from_st, to_st)

    lines = []
    if len(crosses) >= 2:  # "between A and B": the segment(s) bounded by both
        a, b = crosses[0], crosses[1]
        lines = _centerlines(f"{s_where} AND ((f_st like '{a}%' AND t_st like '{b}%') OR (f_st like '{b}%' AND t_st like '{a}%'))")
    if not lines and crosses:  # segments touching any named cross street
        touch = " OR ".join(f"f_st like '{c}%' OR t_st like '{c}%'" for c in crosses)
        lines = _centerlines(f"{s_where} AND ({touch})")
    if not lines and not crosses:  # whole street
        lines = _centerlines(s_where)
    if lines:
        return {"type": "MultiLineString", "coordinates": lines}

    q = f"{street} and {crosses[0].title()}, San Francisco" if crosses else f"{street}, San Francisco"
    try:
        hits = requests.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "json", "limit": 1},
                            headers={"User-Agent": "roadwatch-sf-hackathon"}, timeout=20).json()
        if hits:
            return {"type": "Point", "coordinates": [float(hits[0]["lon"]), float(hits[0]["lat"])]}
    except Exception:
        pass
    return None


# ---------- the agent ----------

class RoadWatch:
    def __init__(self):
        self.lock = threading.RLock()
        self.store = make_store(DATA)
        self.scheduled = datasf_events(fetch_datasf())
        self.busy: list[str] = []
        self.reset(REPLAY_START, speed=3600)

    # --- control ---
    def reset(self, start: datetime, speed: float):
        with self.lock:
            self.store.reset()
            self.seen_hashes: set[str] = set()
            self.recent_digests: list[str] = []
            self.recent_cards: list[dict] = []
            self.forgotten: list[dict] = []
            self.now = start
            self.speed = speed  # simulated seconds per real second
            self.paused = False
            self.active: dict[str, dict] = {}
            self.pending = list(self.scheduled)
            self.metrics: list[dict] = []
            self.log: list[str] = []
            self.naive_tokens = 0
            self.cycle = 0
            self.counts = {"new": 0, "merged": 0, "retired": 0}
            self.say(f"Agent started at {start:%a %m-%d %H:%M}, {len(self.pending)} permits in the DataSF feed window; "
                     f"long-term memory: {self.store.name}")

    def say(self, msg: str):
        self.log.append(f"[{self.now:%a %m-%d %H:%M}] {msg}")
        self.log = self.log[-200:]

    # --- memory ---
    def observe(self, source: str, text: str) -> bool:
        """Tier 0: append-only raw observations. Returns False if already seen (dedup)."""
        h = hashlib.sha1(text.encode()).hexdigest()
        if h in self.seen_hashes:
            return False
        self.seen_hashes.add(h)
        self.store.insert("observations", {"ts": self.now.isoformat(), "source": source, "hash": h,
                                           "text": text, "tokens": approx_tokens(text)})
        self.naive_tokens += approx_tokens(text)
        return True

    def ledger(self, ev: dict, action: str):
        slim = {k: v for k, v in ev.items() if k not in ("raw", "geometry")}
        self.store.insert("ledger", {"ts": self.now.isoformat(), "event_id": ev["id"], "action": action,
                                     "street": " | ".join(ev["streets"]), "status": ev["status"],
                                     "confidence": ev["confidence"], "kind": ev["kind"], "json": json.dumps(slim)})

    def retire(self, ev: dict, why: str):
        self.active.pop(ev["id"], None)
        line = f"{self.now:%m-%d %H:%M} retired {ev['title']} on {'; '.join(ev['streets'])[:80]} ({why})"
        self.store.insert("digests", {"ts": self.now.isoformat(), "line": line, "event_id": ev["id"], "why": why})
        self.recent_digests = ([line] + self.recent_digests)[:15]
        self.forgotten.append({
            "ts": self.now.strftime("%m-%d %H:%M"), "title": ev["title"], "street": ev["streets"][0][:60] if ev["streets"] else "",
            "kind": ev["kind"], "why": why, "rule": forget_rule(why),
            "tokens_freed": approx_tokens(self.context_line(ev)), "digest_tokens": approx_tokens(line),
        })
        self.forgotten = self.forgotten[-1000:]
        self.ledger(ev, "retired:" + why)
        self.counts["retired"] += 1
        self.say(f"− FORGET {ev['title']} — {why}")

    def add_or_merge(self, ev: dict):
        """Resolve step: same street as an active event -> merge sources and raise confidence."""
        # Only free-text reports get merged; each permit from the official feed is its own event.
        key = base_street(ev["streets"][0]) if ev["streets"] and ev["kind"] != "gov" else ""
        my_crosses = set(label_crosses(ev["streets"][0])) if ev["streets"] else set()
        for other in self.active.values():
            if not key:
                break
            same_street = [s for s in other["streets"] if base_street(s) == key]
            if not same_street:
                continue
            # Long streets (Market St) carry many unrelated permits: for official permits require a shared cross street.
            if other["kind"] == "gov" and my_crosses and not any(my_crosses & set(label_crosses(s)) for s in same_street):
                continue
            if ev["status"] == "open" and other["kind"] != "gov":
                self.retire(other, f"reported reopened by {ev['sources'][0]['kind']} source")
                return
            if ev["status"] == "open":
                continue
            other["sources"] += ev["sources"]
            other["confidence"] = round(1 - (1 - other["confidence"]) * (1 - ev["confidence"]), 2)
            other["last_seen"] = self.now.isoformat()
            self.counts["merged"] += 1
            self.ledger(other, "merged")
            self.say(f"≈ MERGE new {ev['sources'][0]['kind']} report into {other['title']} → confidence {other['confidence']}")
            return
        if ev["status"] == "open":
            self.say(f"· Report says {ev['streets'][0]} reopened; nothing active to clear")
            return
        ev.setdefault("last_seen", self.now.isoformat())
        self.active[ev["id"]] = ev
        self.counts["new"] += 1
        self.ledger(ev, "created")
        tag = "✓" if ev["confidence"] >= CONFIRM_THRESHOLD else "?"
        self.say(f"+ NEW {tag} {ev['title']} on {'; '.join(ev['streets'])[:70]} (conf {ev['confidence']})")

    # --- the loop ---
    def step(self, real_seconds: float):
        with self.lock:
            if self.paused:
                return
            prev = self.now
            self.now = self.now + timedelta(seconds=real_seconds * self.speed)
            hours = (self.now - prev).total_seconds() / 3600
            now_s = self.now.isoformat()

            # Collect: permits whose window has started
            while self.pending and self.pending[0]["starts_at"] <= now_s:
                ev = self.pending.pop(0)
                if ev["ends_at"] < now_s:
                    continue
                ev = {**ev, "kind": "gov"}
                if self.observe("datasf", json.dumps(ev["raw"])):
                    self.add_or_merge(ev)

            # Expire + decay (the forgetting rules)
            for ev in list(self.active.values()):
                ends = datetime.fromisoformat(ev["ends_at"])
                if self.now > ends + RETIRE_BUFFER:
                    self.retire(ev, f"ended {ends:%m-%d %H:%M}")
                elif ev["kind"] == "social" and ev["confidence"] < CONFIRM_THRESHOLD:
                    ev["confidence"] = round(ev["confidence"] - DECAY_PER_HOUR * hours, 3)
                    if ev["confidence"] < DROP_BELOW:
                        self.retire(ev, "unconfirmed social report decayed")

            # Cap working state: fold lowest-value events into a digest
            while approx_tokens(self.context()) > CONTEXT_CAP_TOKENS and self.active:
                worst = min(self.active.values(), key=lambda e: (e["status"] == "blocked") * 2 + e["confidence"])
                self.retire(worst, "compacted: working state over token cap")

            self.cycle += 1
            m = {
                "cycle": self.cycle, "t": self.now.strftime("%m-%d %H:%M"),
                "compact": approx_tokens(self.context()), "naive": self.naive_tokens,
                "active": len(self.active), **self.counts,
            }
            self.metrics.append(m)
            self.metrics = self.metrics[-5000:]
            self.store.insert("agent_runs", {"ts": self.now.isoformat(), **m})

    def context_line(self, ev: dict) -> str:
        street = ev["streets"][0][:60] + (f" +{len(ev['streets']) - 1}" if len(ev["streets"]) > 1 else "")
        return f"{ev['id']} | {ev['status']} | {street} | until {ev['ends_at'][5:16]} | c={ev['confidence']:.2f}"

    def context(self) -> str:
        """Tier 3: the only thing a planner model ever sees. One line per active event."""
        lines = [f"NOW {self.now:%Y-%m-%d %H:%M} | active={len(self.active)}"]
        for ev in sorted(self.active.values(), key=lambda e: e["starts_at"]):
            lines.append(self.context_line(ev))
        return "\n".join(lines)

    def memory_report(self) -> dict:
        """Everything the /memory page needs: where tokens go, what was discarded and why, what lives outside context."""
        with self.lock:
            ctx = self.context()
            ctx_tokens = approx_tokens(ctx)
            rows = []
            for ev in self.active.values():
                raw_tokens = approx_tokens(json.dumps(ev.get("raw"))) if ev.get("raw") else sum(
                    approx_tokens(s.get("text", "")) for s in ev["sources"])
                rows.append({
                    "id": ev["id"], "title": ev["title"], "street": ev["streets"][0][:60] if ev["streets"] else "",
                    "status": ev["status"], "kind": ev["kind"], "confidence": ev["confidence"], "ends_at": ev["ends_at"][5:16].replace("T", " "),
                    "context_tokens": approx_tokens(self.context_line(ev)), "raw_tokens": raw_tokens,
                    "sources": len(ev["sources"]),
                })
            rows.sort(key=lambda r: (-r["context_tokens"], r["ends_at"]))
            by_rule: dict[str, dict] = {}
            for f in self.forgotten:
                b = by_rule.setdefault(f["rule"], {"count": 0, "tokens_freed": 0, "digest_tokens": 0})
                b["count"] += 1
                b["tokens_freed"] += f["tokens_freed"]
                b["digest_tokens"] += f["digest_tokens"]
            step = max(1, len(self.metrics) // 400)
            return {
                "now": self.now.strftime("%a %Y-%m-%d %H:%M"), "cycle": self.cycle,
                "context_tokens": ctx_tokens, "cap": CONTEXT_CAP_TOKENS, "naive_tokens": self.naive_tokens,
                "observations": len(self.seen_hashes), "active": len(self.active), "pending": len(self.pending),
                "counts": dict(self.counts), "context": ctx, "events": rows,
                "forgotten": self.forgotten[-60:][::-1], "by_rule": by_rule,
                "metrics": self.metrics[::step] + self.metrics[-1:],
                "rules": [
                    {"rule": "expired", "text": f"Scheduled closures retire at ends_at + {int(RETIRE_BUFFER.total_seconds() // 60)} min"},
                    {"rule": "decayed", "text": f"Unconfirmed social reports lose {DECAY_PER_HOUR} confidence per hour; dropped below {DROP_BELOW}"},
                    {"rule": "cleared", "text": "A 'reopened' report from a trusted source clears the event"},
                    {"rule": "compacted", "text": f"Over {CONTEXT_CAP_TOKENS} tokens: lowest severity × confidence folded into a digest"},
                    {"rule": "dedup", "text": "Every observation is hashed; repeats never enter memory or context"},
                ],
                "store": {"name": self.store.name, **self.store.stats},
            }

    # --- LLM-powered inputs ---
    def ingest_text(self, text: str, kind: str, url: str | None = None):
        """Free text (a social post or news article) -> LFM2.5 extraction -> geocode -> merge."""
        import llm

        with self.lock:
            if not self.observe(kind, text):
                self.say("· Duplicate report ignored (dedup by content hash)")
                return []
            today = f"{self.now:%A %Y-%m-%d}"
        self.busy.append(f"LFM2.5 reading {kind} text")
        try:
            items, raw = llm.extract_events(text, today)
        finally:
            self.busy.pop()
        created = []
        for it in items:
            geom = geocode(it["street"], it.get("cross_street"), it.get("from_street"), it.get("to_street"))
            with self.lock:
                hrs = float(it.get("hours") or 2)
                if it.get("from_street") and it.get("to_street"):
                    street = f"{it['street']} between {it['from_street']} and {it['to_street']}"
                elif it.get("cross_street"):
                    street = f"{it['street']} at {it['cross_street']}"
                else:
                    street = it["street"]
                if geom is None:
                    self.say(f"! Could not locate '{street}' on the map; keeping it in the list only")
                ev = {
                    "id": "rep_" + hashlib.md5(f"{street}{self.now}{text}".encode()).hexdigest()[:8],
                    "title": f"{(it.get('type') or 'report').title()}: {it.get('reason', '')}"[:60],
                    "streets": [street], "type": it.get("type", "other"), "kind": kind,
                    "status": "blocked" if it.get("blocked", True) else "open",
                    "starts_at": self.now.isoformat(),
                    "ends_at": (self.now + timedelta(hours=min(max(hrs, 0.5), 48))).isoformat(),
                    "confidence": TRUST[kind],
                    "sources": [{"kind": kind, "name": url or f"{kind} report", "url": url, "text": text[:300]}],
                    "geometry": geom, "summary": it.get("reason", ""), "llm_json": it,
                }
                self.add_or_merge(ev)
                created.append(ev)
        if not items:
            with self.lock:
                self.say(f"· LFM2.5 found no road event in {kind} text")
        return created

    def scan_news(self):
        queries = ["San Francisco road closure today", "San Francisco street closed protest OR parade OR fire today"]
        self.busy.append("Nimble searching the web")
        try:
            results = [r for q in queries for r in nimble_search(q, 4)]
        finally:
            self.busy.pop()
        with self.lock:
            self.say(f"Nimble search returned {len(results)} pages")
        for r in results:
            text = f"{r.get('title', '')}\n{r.get('description', '')}"
            self.ingest_text(text, "news", r.get("url"))

    def verify(self, event_id: str):
        with self.lock:
            ev = self.active.get(event_id)
            if not ev:
                return
            street = re.split(r"\s+(?:between|at|from|near)\s+", ev["streets"][0], maxsplit=1, flags=re.I)[0]
        self.busy.append(f"Nimble verifying {street}")
        try:
            results = nimble_search(f'"{street}" San Francisco closed today', 5)
        finally:
            self.busy.pop()
        key = street_key(street).lower()
        hits = [r for r in results if key in (r.get("title", "") + r.get("description", "")).lower()
                and re.search(r"clos|block|shut", (r.get("title", "") + r.get("description", "")).lower())]
        with self.lock:
            if event_id not in self.active:
                return
            if hits:
                ev["sources"] += [{"kind": "news", "name": h.get("title"), "url": h.get("url")} for h in hits[:2]]
                ev["confidence"] = round(1 - (1 - ev["confidence"]) * (1 - TRUST["news"]), 2)
                self.ledger(ev, "verified")
                self.say(f"✓ VERIFIED {street} via Nimble ({len(hits)} matching pages) → conf {ev['confidence']}")
                if ev["confidence"] >= CONFIRM_THRESHOLD and ev["status"] == "blocked":
                    threading.Thread(target=self.make_card, args=(event_id,), daemon=True).start()
            else:
                self.say(f"✗ Nimble found no corroboration for {street}; confidence keeps decaying")

    def make_card(self, event_id: str):
        """Publish step: a FLUX alert card for a confirmed blocked event."""
        import cards

        with self.lock:
            ev = self.active.get(event_id)
            if not ev or ev.get("card"):
                return
            snapshot = {k: v for k, v in ev.items() if k not in ("raw", "geometry")}
        self.busy.append("FLUX drawing alert card")
        try:
            url = cards.make_card(snapshot)
        finally:
            self.busy.pop()
        with self.lock:
            if event_id in self.active:
                self.active[event_id]["card"] = url
                self.ledger(self.active[event_id], "card")
            self.recent_cards = ([{"url": url, "street": snapshot["streets"][0], "title": snapshot["title"]}]
                                 + self.recent_cards)[:8]
            self.say(f"🖼 FLUX alert card ready for {snapshot['streets'][0][:50]}")

    def recall(self, street: str) -> dict:
        """Long-term memory is a SQL query, not context."""
        self.store.flush()
        return {**self.store.recall(street_key(street)), "store": self.store.name}

    def snapshot(self) -> dict:
        with self.lock:
            events = [{k: v for k, v in e.items() if k != "raw"} for e in self.active.values()]
            return {
                "now": self.now.strftime("%a %Y-%m-%d %H:%M"), "speed": self.speed, "paused": self.paused,
                "events": events, "metrics": self.metrics[::max(1, len(self.metrics) // 300)] + self.metrics[-1:],
                "log": self.log[-40:][::-1], "digests": list(self.recent_digests), "cards": list(self.recent_cards),
                "context": self.context(), "busy": list(self.busy), "threshold": CONFIRM_THRESHOLD,
                "store": {"name": self.store.name, **self.store.stats},
            }
