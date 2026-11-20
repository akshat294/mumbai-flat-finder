from __future__ import annotations
import hashlib, json, random, time
from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.core.checkpoint import CheckpointDB

def walk_dicts(obj: Any, max_depth: int = 6) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    if max_depth <= 0:
        return found
    if isinstance(obj, dict):
        found.append(obj)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found.extend(walk_dicts(v, max_depth - 1))
    elif isinstance(obj, list):
        for item in obj[:120]:
            if isinstance(item, (dict, list)):
                found.extend(walk_dicts(item, max_depth - 1))
    return found

def to_float(v: Any):
    try:
        return float(v) if v not in (None, "") else None
    except Exception:
        return None

def to_int(v: Any):
    try:
        if isinstance(v, str):
            v = v.replace(",", "").strip()
        return int(float(v)) if v not in (None, "") else None
    except Exception:
        return None

class BaseConnector:
    source_name: str = "base"

    def __init__(self, db: CheckpointDB, cache_dir: str | Path = "pipeline/cache"):
        self.db = db
        self.cache_dir = Path(cache_dir) / self.source_name / "mumbai"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_file(self, key: str) -> Path:
        return self.cache_dir / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}.json"

    def read_cache(self, key: str, max_age_hours: float = 168.0) -> Optional[Any]:
        p = self._cache_file(key)
        if not p.exists() or ((time.time() - p.stat().st_mtime) / 3600.0) > max_age_hours:
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            return None

    def write_cache(self, key: str, data: Any) -> None:
        self._cache_file(key).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def polite_sleep(self, low: float = 1.2, high: float = 2.4) -> None:
        time.sleep(random.uniform(low, high))
