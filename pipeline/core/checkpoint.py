from __future__ import annotations
import json, sqlite3, time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 30000;
PRAGMA temp_store = MEMORY;

CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    locality TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_records (
    record_uid TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    native_id TEXT NOT NULL,
    name TEXT NOT NULL,
    locality TEXT,
    zone TEXT,
    lat REAL,
    lng REAL,
    rera_id TEXT,
    payload_json TEXT NOT NULL,
    source_url TEXT,
    fetched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS google_places_cache (
    canonical_id TEXT PRIMARY KEY,
    place_id TEXT,
    payload_json TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""

class CheckpointDB:
    def __init__(self, db_path: str | Path = "pipeline/staging/mumbai_raw.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute("UPDATE crawl_jobs SET status = 'pending', updated_at = ? WHERE status = 'in_progress'", (time.time(),))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        return conn

    @contextmanager
    def connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reset_stale_jobs(self, fresh_hours: float = 20.0) -> int:
        cutoff = time.time() - (fresh_hours * 3600.0)
        with self.connection() as conn:
            cur = conn.execute(
                "UPDATE crawl_jobs SET status = 'pending', attempts = 0, last_error = NULL, updated_at = ? WHERE status IN ('done', 'failed') AND updated_at < ?",
                (time.time(), cutoff),
            )
            return cur.rowcount

    def prune_stale_records(self, max_age_days: float = 7.0) -> int:
        cutoff = time.time() - (max_age_days * 86400.0)
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM raw_records WHERE fetched_at < ?", (cutoff,))
            return cur.rowcount

    def register_jobs(self, source: str, localities: Iterable[str]) -> int:
        now = time.time()
        rows = [(f"{source}:{loc}", source, loc, now) for loc in localities]
        with self.connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO crawl_jobs (job_key, source, locality, status, attempts, updated_at) VALUES (?, ?, ?, 'pending', 0, ?)",
                rows,
            )
            return conn.total_changes

    def next_pending_jobs(self, source: str, max_attempts: int = 3) -> List[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT * FROM crawl_jobs WHERE source = ? AND status IN ('pending', 'failed') AND attempts < ? ORDER BY attempts ASC, job_key ASC",
                (source, max_attempts),
            ).fetchall()

    def mark_job(self, job_key: str, status: str, error: Optional[str] = None) -> None:
        now = time.time()
        with self.connection() as conn:
            if status == "in_progress":
                conn.execute("UPDATE crawl_jobs SET status = ?, attempts = attempts + 1, updated_at = ? WHERE job_key = ?", (status, now, job_key))
            else:
                conn.execute("UPDATE crawl_jobs SET status = ?, last_error = ?, updated_at = ? WHERE job_key = ?", (status, error, now, job_key))

    def upsert_raw_record(self, source: str, native_id: str, name: str, payload: Dict[str, Any],
                          locality: Optional[str] = None, zone: Optional[str] = None,
                          lat: Optional[float] = None, lng: Optional[float] = None,
                          rera_id: Optional[str] = None, source_url: Optional[str] = None) -> None:
        uid = f"{source}:{native_id}"
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO raw_records (record_uid, source, native_id, name, locality, zone, lat, lng, rera_id, payload_json, source_url, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_uid) DO UPDATE SET
                    name = excluded.name,
                    locality = COALESCE(excluded.locality, raw_records.locality),
                    zone = COALESCE(excluded.zone, raw_records.zone),
                    lat = COALESCE(excluded.lat, raw_records.lat),
                    lng = COALESCE(excluded.lng, raw_records.lng),
                    rera_id = COALESCE(excluded.rera_id, raw_records.rera_id),
                    payload_json = excluded.payload_json,
                    source_url = COALESCE(excluded.source_url, raw_records.source_url),
                    fetched_at = excluded.fetched_at
                """,
                (uid, source, str(native_id), name.strip(), locality, zone, lat, lng, rera_id, json.dumps(payload, ensure_ascii=False), source_url, time.time()),
            )

    def fetch_all_raw(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM raw_records WHERE source = ?", (source,)).fetchall() if source else conn.execute("SELECT * FROM raw_records").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["payload"] = json.loads(item.pop("payload_json"))
            out.append(item)
        return out

    def stats(self) -> Dict[str, Any]:
        with self.connection() as conn:
            counts = dict(conn.execute("SELECT source, COUNT(*) FROM raw_records GROUP BY source").fetchall())
            jobs = dict(conn.execute("SELECT status, COUNT(*) FROM crawl_jobs GROUP BY status").fetchall())
        return {"raw_records_by_source": counts, "jobs_by_status": jobs}
