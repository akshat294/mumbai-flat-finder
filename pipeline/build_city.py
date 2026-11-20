from __future__ import annotations
import csv, hashlib, json, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from pipeline.connectors.google_places import enrich_with_google_places
from pipeline.core.checkpoint import CheckpointDB
from pipeline.entity_resolver import resolve_entities
from pipeline.mumbai_enricher import enrich_mumbai, load_transit
from pipeline.pricing_engine import summarize_portal_prices

IST = timezone(timedelta(hours=5, minutes=30))

def _approx_coords(soc_id: str, locality: str, centroids: Dict[str, List[float]]):
    base = centroids.get(locality) or [19.0760, 72.8777]
    h = int(hashlib.md5(soc_id.encode("utf-8")).hexdigest()[:8], 16)
    ang = (h % 360) * (math.pi / 180.0)
    rad = 0.0012 + ((h >> 8) % 100) * 0.00003
    return round(base[0] + math.sin(ang) * rad, 6), round(base[1] + math.cos(ang) * rad, 6)

def build_mumbai(db_path: str | Path = "pipeline/staging/mumbai_raw.db", max_google_calls: int = 25, max_record_age_days: float = 7.0) -> Dict[str, Any]:
    db = CheckpointDB(db_path)
    pruned = db.prune_stale_records(max_age_days=max_record_age_days) if hasattr(db, "prune_stale_records") else 0
    raw = db.fetch_all_raw()

    cfg = json.loads(Path("data/cities.json").read_text(encoding="utf-8-sig"))["mumbai"]
    centroids = cfg.get("centroids") or {}
    loc_to_zone = {"pali hill": "Bandra-Santacruz"}
    for zname, zinfo in cfg["zones"].items():
        for l in zinfo["localities"]:
            loc_to_zone[l.lower()] = zname

    canonicals, _ = resolve_entities(raw)
    google_calls = enrich_with_google_places(db, canonicals, max_calls=max_google_calls)
    transit = load_transit()

    gcache = {}
    with db.connection() as conn:
        for row in conn.execute("SELECT canonical_id, payload_json FROM google_places_cache").fetchall():
            gcache[row["canonical_id"]] = json.loads(row["payload_json"])

    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    compiled: List[Dict[str, Any]] = []
    for can in canonicals:
        gplace = gcache.get(can["id"])
        gloc = (gplace or {}).get("location") or {}
        lat, lng = can.get("lat") or gloc.get("latitude"), can.get("lng") or gloc.get("longitude")
        coords_approx = False
        if not lat or not lng:
            lat, lng = _approx_coords(can["id"], can["locality"], centroids)
            coords_approx = True
        else:
            lat, lng = round(float(lat), 6), round(float(lng), 6)

        recs = [r for grp in can["raw_by_source"].values() for r in grp]
        bhks = sorted({int(r["bhk"]) for r in recs if r.get("bhk") and 1 <= int(r["bhk"]) <= 6})
        carpets = [float(r["carpet_sqft"]) for r in recs if r.get("carpet_sqft") and 200 <= float(r["carpet_sqft"]) <= 8000]
        med_carpet = round(sorted(carpets)[len(carpets) // 2], 0) if carpets else None
        pricing = summarize_portal_prices(can["raw_by_source"], carpet_sqft=med_carpet)
        if not pricing["rent_monthly_inr"]["median"] and not pricing["buy_inr"]["median"]:
            continue

        gblock = None
        if gplace:
            gblock = {
                "rating": gplace.get("rating"), "review_count": gplace.get("userRatingCount"), "url": gplace.get("googleMapsUri"),
                "reviews": [{"rating": r.get("rating"), "text": (r.get("text") or {}).get("text", "")[:240]} for r in (gplace.get("reviews") or [])[:3] if (r.get("text") or {}).get("text")],
            }
        compiled.append({
            "id": can["id"], "name": can["name"], "locality": can["locality"],
            "zone": can.get("zone") or loc_to_zone.get((can["locality"] or "").lower(), "Mumbai"),
            "lat": lat, "lng": lng, "coords_approx": coords_approx, "bhks": bhks,
            "rera_ids": can["rera_ids"], "rera_carpet_sqft": int(med_carpet) if med_carpet else None,
            "pricing": pricing, "mumbai_context": enrich_mumbai(lat, lng, transit),
            "google": gblock, "sources": can["sources"],
        })

    out_dir = Path("web/public/data"); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mumbai-index.json").write_text(json.dumps({"city":"Mumbai MMR","generated_at":now_ist,"count":len(compiled),"societies":compiled}, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    with (out_dir / "mumbai-societies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id","name","zone","locality","bhks","carpet_sqft","rent_median_inr","buy_median_inr","has_zero_brokerage","google_rating","nearest_metro","metro_walk_min","flood_risk","portals"])
        for s in compiled:
            w.writerow([s["id"],s["name"],s["zone"],s["locality"],"/".join(map(str,s["bhks"])),s["rera_carpet_sqft"] or "",s["pricing"]["rent_monthly_inr"]["median"] or "",s["pricing"]["buy_inr"]["median"] or "",s["pricing"]["has_zero_brokerage"],(s["google"] or {}).get("rating",""),(s["mumbai_context"]["nearest_metro"] or {}).get("name",""),(s["mumbai_context"]["nearest_metro"] or {}).get("walk_min",""),s["mumbai_context"]["monsoon_flood_risk"],",".join(sorted(s["sources"].keys()))])
    return {"compiled": len(compiled), "pruned_stale": pruned, "google_new_calls": google_calls, "google_cached_total": len(gcache), "updated_at": now_ist}
