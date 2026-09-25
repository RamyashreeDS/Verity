"""Long-term memory store: RawTree (schemaless ingest + SQL over HTTP), with SQLite as an offline fallback.

Tables: observations (tier 0, append-only raw docs), ledger (tier 1, every event version), digests (tier 2).
"""
import os
import queue
import sqlite3
import threading
from pathlib import Path

import requests

RAWTREE_URL = "https://api.rawtree.com/v1"
TABLES = ("observations", "ledger", "digests", "agent_runs")


def sql_str(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


class RawTreeStore:
    """Rows are buffered and flushed by a writer thread (one POST per table per flush) so the agent loop never blocks."""

    name = "RawTree"

    def __init__(self, api_key: str, prefix: str = "roadwatch_"):
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.prefix = prefix
        self.q: queue.Queue = queue.Queue()
        self.stats = {"inserted": 0, "queries": 0, "errors": 0, "last_error": ""}
        threading.Thread(target=self._writer, daemon=True).start()

    def table(self, t: str) -> str:
        return self.prefix + t

    def insert(self, t: str, row: dict):
        self.q.put((t, row))

    def _writer(self):
        while True:
            t, row = self.q.get()
            batch = {t: [row]}
            try:
                while True:  # drain what else is waiting
                    t2, r2 = self.q.get_nowait()
                    batch.setdefault(t2, []).append(r2)
            except queue.Empty:
                pass
            for t, rows in batch.items():
                try:
                    r = requests.post(f"{RAWTREE_URL}/tables/{self.table(t)}", headers=self.headers, json=rows, timeout=30)
                    r.raise_for_status()
                    self.stats["inserted"] += r.json().get("inserted", len(rows))
                except Exception as e:
                    self.stats["errors"] += 1
                    self.stats["last_error"] = str(e)[:200]

    def flush(self, timeout: float = 5.0):
        import time
        t0 = time.time()
        while not self.q.empty() and time.time() - t0 < timeout:
            time.sleep(0.05)

    def query(self, sql: str) -> list[dict]:
        self.stats["queries"] += 1
        r = requests.post(f"{RAWTREE_URL}/query", headers=self.headers, json={"sql": sql}, timeout=30)
        body = r.json()
        if "error" in body:
            if "not found" in body.get("message", "").lower():
                return []
            raise RuntimeError(body.get("message"))
        return body.get("data", [])

    def reset(self):
        with self.q.mutex:  # drop anything still queued from the previous run
            self.q.queue.clear()
        for t in TABLES:
            requests.delete(f"{RAWTREE_URL}/tables/{self.table(t)}", headers=self.headers, timeout=30)

    def recall(self, street_like: str) -> dict:
        like = sql_str(f"%{street_like}%")
        ledger = self.query(f"SELECT ts, action, street FROM {self.table('ledger')} "
                            f"WHERE upper(street) LIKE {like} ORDER BY ts DESC LIMIT 30")
        digests = self.query(f"SELECT line FROM {self.table('digests')} WHERE upper(line) LIKE {like} ORDER BY ts DESC LIMIT 20")
        return {"ledger": [[r["ts"], r["action"], r["street"]] for r in ledger], "digests": [r["line"] for r in digests]}

    def counts(self) -> dict:
        out = {}
        for t in TABLES:
            try:
                rows = self.query(f"SELECT count() AS n FROM {self.table(t)}")
                out[t] = int(rows[0]["n"]) if rows else 0
            except Exception:
                out[t] = None
        return out


class SQLiteStore:
    name = "SQLite"

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.stats = {"inserted": 0, "queries": 0, "errors": 0, "last_error": ""}
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS observations (ts TEXT, source TEXT, hash TEXT, text TEXT, tokens INT);
            CREATE TABLE IF NOT EXISTS ledger (ts TEXT, event_id TEXT, action TEXT, street TEXT, status TEXT,
                                               confidence REAL, kind TEXT, json TEXT);
            CREATE TABLE IF NOT EXISTS digests (ts TEXT, line TEXT, event_id TEXT, why TEXT);
            CREATE TABLE IF NOT EXISTS agent_runs (ts TEXT, cycle INT, t TEXT, compact INT, naive INT, active INT,
                                                   new INT, merged INT, retired INT);
        """)

    def insert(self, t: str, row: dict):
        cols = ",".join(row)
        with self.lock:
            self.db.execute(f"INSERT INTO {t} ({cols}) VALUES ({','.join('?' * len(row))})", list(row.values()))
            self.db.commit()
        self.stats["inserted"] += 1

    def flush(self, timeout: float = 0):
        pass

    def reset(self):
        with self.lock:
            self.db.executescript("".join(f"DELETE FROM {t};" for t in TABLES))

    def recall(self, street_like: str) -> dict:
        like = f"%{street_like}%"
        with self.lock:
            ledger = self.db.execute("SELECT ts, action, street FROM ledger WHERE upper(street) LIKE ? ORDER BY ts DESC LIMIT 30",
                                     (like,)).fetchall()
            digests = self.db.execute("SELECT line FROM digests WHERE upper(line) LIKE ? ORDER BY ts DESC LIMIT 20", (like,)).fetchall()
        self.stats["queries"] += 2
        return {"ledger": [list(r) for r in ledger], "digests": [d[0] for d in digests]}

    def counts(self) -> dict:
        with self.lock:
            return {t: self.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


def make_store(data_dir: Path):
    key = os.environ.get("RAWTREE_API_KEY")
    if key:
        return RawTreeStore(key)
    return SQLiteStore(data_dir / "memory.db")
