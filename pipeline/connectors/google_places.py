from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any, Dict, List
import httpx
from pipeline.core.checkpoint import CheckpointDB

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.rating,places.userRatingCount,places.googleMapsUri,places.location,places.reviews"
JSON_CACHE = Path("data/google_places_cache.json")

def enrich_with_google_places(db: CheckpointDB, societies: List[Dict[str, Any]], max_calls: int = 25) -> int:
    cache: Dict[str, Any] = {}
    if JSON_CACHE.exists():
        try: cache = json.loads(JSON_CACHE.read_text(encoding="utf-8-sig"))
        except Exception: cache = {}
    with db.connection() as conn:
        for cid, place in cache.items():
            conn.execute("INSERT OR IGNORE INTO google_places_cache (canonical_id, place_id, payload_json, fetched_at) VALUES (?, ?, ?, ?)", (cid, place.get("id"), json.dumps(place, ensure_ascii=False), time.time()))
        for row in conn.execute("SELECT canonical_id, payload_json FROM google_places_cache").fetchall():
            cache.setdefault(row["canonical_id"], json.loads(row["payload_json"]))

    key = os.getenv("GOOGLE_PLACES_API_KEY")
    calls = 0
    if key and max_calls > 0:
        ordered = sorted(societies, key=lambda s: (0 if not s.get("lat") else 1, -len(s.get("sources") or {})))
        with httpx.Client(timeout=12.0) as client:
            for soc in ordered:
                if calls >= max_calls: break
                cid = soc["id"]
                if cid in cache: continue
                try:
                    resp = client.post(PLACES_URL, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK, "Content-Type": "application/json"}, json={"textQuery": f"{soc['name']} {soc.get('locality', '')} Mumbai", "maxResultCount": 1})
                    calls += 1
                    if resp.status_code != 200: continue
                    places = resp.json().get("places") or []
                    if not places: continue
                    cache[cid] = places[0]
                    with db.connection() as conn:
                        conn.execute("INSERT OR REPLACE INTO google_places_cache (canonical_id, place_id, payload_json, fetched_at) VALUES (?, ?, ?, ?)", (cid, places[0].get("id"), json.dumps(places[0], ensure_ascii=False), time.time()))
                except Exception:
                    continue
    JSON_CACHE.parent.mkdir(parents=True, exist_ok=True)
    JSON_CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return calls
