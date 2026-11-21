from __future__ import annotations
import csv, json, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from pipeline.civic_osm import load_civic_pois, enrich_civic
from pipeline.connectors.google_places import enrich_with_google_places
from pipeline.core.checkpoint import CheckpointDB
from pipeline.entity_resolver import resolve_entities
from pipeline.geo_guard import is_valid_mmr_land, safe_approx_coords, enrich_with_osm_photon
from pipeline.mumbai_enricher import enrich_mumbai, load_transit
from pipeline.pricing_engine import summarize_portal_prices

IST = timezone(timedelta(hours=5, minutes=30))
RK_RE = re.compile(r"\b1[\s\-]*rk\b|\bstudio\b", re.I)
JUNK_NAME = re.compile(r"(flats?,?\s*apartments?|houses?\s+for\s+(rent|sale)|properties\s+for\s+(rent|sale)|\bfor\s+(rent|sale)\s+in\b|\bnear\s+me\b|^\d+\s*(bhk|rk)\s*(flat|apartment|house)?$)", re.I)
COMM_DROP = re.compile(
    r"\b(office|commercial|shop|showroom|warehouse|business\s*park|corporate|chambers|"
    r"trade\s*star|trade\s*center|town\s*center|it\s*park|coworking|the\s*summit|industrial\s*estate|"
    r"mindspace|tech\s*park|infotech|cyber\s*park|knowledge\s*park|business\s*bay|corporate\s*park|sez)\b",
    re.I,
)

def _attach_fair_price_deals(compiled: List[Dict[str, Any]]) -> int:
    by_loc_rent: Dict[str, List[float]] = {}
    by_loc_buy: Dict[str, List[float]] = {}
    for s in compiled:
        loc = s["locality"]
        rm, bm = s["pricing"]["rent_monthly_inr"], s["pricing"]["buy_inr"]
        if rm.get("median") and not rm.get("is_estimate"):
            by_loc_rent.setdefault(loc, []).append(float(rm["median"]))
        if bm.get("median") and not bm.get("is_estimate"):
            by_loc_buy.setdefault(loc, []).append(float(bm["median"]))
    med = lambda arr: sorted(arr)[len(arr) // 2] if len(arr) >= 4 else None
    rent_meds = {k: med(v) for k, v in by_loc_rent.items()}
    buy_meds = {k: med(v) for k, v in by_loc_buy.items()}

    great = 0
    for s in compiled:
        loc, deal = s["locality"], {}
        for key, field, meds in (("rent", "rent_monthly_inr", rent_meds), ("buy", "buy_inr", buy_meds)):
            mval, pinfo = meds.get(loc), s["pricing"][field]
            if mval and pinfo.get("median") and not pinfo.get("is_estimate"):
                pct = round(((float(pinfo["median"]) - mval) / mval) * 100)
                if -65 <= pct <= 180:
                    label = "Great Value" if pct <= -12 else ("Premium" if pct >= 20 else "Fair Price")
                    if label == "Great Value": great += 1
                    deal[key] = {"pct": pct, "label": label, "loc_median": int(mval)}
        s["deal"] = deal or None
    return great

def build_mumbai(db_path: str | Path = "pipeline/staging/mumbai_raw.db", max_google_calls: int = 25, max_osm_calls: int = 40, max_record_age_days: float = 7.0) -> Dict[str, Any]:
    db = CheckpointDB(db_path)
    pruned = db.prune_stale_records(max_age_days=max_record_age_days) if hasattr(db, "prune_stale_records") else 0
    raw = db.fetch_all_raw()

    cfg = json.loads(Path("data/cities.json").read_text(encoding="utf-8-sig"))["mumbai"]
    loc_to_zone = {"pali hill": "Bandra-Santacruz"}
    for zname, zinfo in cfg["zones"].items():
        for l in zinfo["localities"]:
            loc_to_zone[l.lower()] = zname

    print(f"[build] Resolving {len(raw)} raw records...", flush=True)
    canonicals, _ = resolve_entities(raw)
    print(f"[build] Deduplicated to {len(canonicals)} societies. Running Google Places...", flush=True)
    google_calls = enrich_with_google_places(db, canonicals, max_calls=max_google_calls)
    print(f"[build] Google Places done ({google_calls} calls). Running OSM Photon & Civic POIs...", flush=True)
    osm_cache = enrich_with_osm_photon(canonicals, max_calls=max_osm_calls)
    civic_pois = load_civic_pois(allow_fetch=True)
    transit = load_transit()
    print(f"[build] Civic POIs ready ({sum(len(v) for v in civic_pois.values())} anchors). Writing bundle...", flush=True)

    gcache = {}
    with db.connection() as conn:
        for row in conn.execute("SELECT canonical_id, payload_json FROM google_places_cache").fetchall():
            gcache[row["canonical_id"]] = json.loads(row["payload_json"])

    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    compiled: List[Dict[str, Any]] = []
    fixed_bad = 0

    for can in canonicals:
        if COMM_DROP.search(can["name"]) or JUNK_NAME.search(can["name"]): continue
        loc = can["locality"]
        gplace = gcache.get(can["id"])
        gloc = (gplace or {}).get("location") or {}
        osm_pt = osm_cache.get(can["id"]) or []

        lat = lng = None
        coords_approx = False
        for cla, cln in ((gloc.get("latitude"), gloc.get("longitude")), (osm_pt[0], osm_pt[1]) if len(osm_pt) == 2 else (None, None), (can.get("lat"), can.get("lng"))):
            if is_valid_mmr_land(cla, cln, loc):
                lat, lng = round(float(cla), 6), round(float(cln), 6)
                break
        if lat is None:
            if can.get("lat") is not None: fixed_bad += 1
            lat, lng = safe_approx_coords(can["id"], loc)
            coords_approx = True

        recs = [r for grp in can["raw_by_source"].values() for r in grp]
        bhk_set = set()
        for r in recs:
            u_txt = str(r.get("url") or "") + " " + str(r.get("name") or "")
            if RK_RE.search(u_txt): bhk_set.add(0)
            elif r.get("bhk") is not None and 0 <= int(r["bhk"]) <= 6: bhk_set.add(int(r["bhk"]))
        bhks = sorted(bhk_set)

        carpets = [float(r["carpet_sqft"]) for r in recs if r.get("carpet_sqft") and 140 <= float(r["carpet_sqft"]) <= 8000]
        med_carpet = round(sorted(carpets)[len(carpets) // 2], 0) if carpets else None
        furns = sorted({r["furnishing"] for r in recs if r.get("furnishing")})
        tenants = sorted({r["tenant"] for r in recs if r.get("tenant")})

        pricing = summarize_portal_prices(can["raw_by_source"], carpet_sqft=med_carpet)
        if not pricing["rent_monthly_inr"]["median"] and not pricing["buy_inr"]["median"]: continue

        clean_sources = {}
        for k, u in (can.get("sources") or {}).items():
            if not u: continue
            if k == "magicbricks" and ("propertyDetails" in u or "-pdpid-" in u or "project-" in u): clean_sources[k] = u
            elif k == "nobroker" and "/property/" in u: clean_sources[k] = u
            elif k == "99acres" and ("-spid-" in u or "-npxid-" in u or "99acres.com/" in u): clean_sources[k] = u
            elif k in ("reddit", "community", "squareyards", "commonfloor", "makaan", "nobrokerage") and u.startswith("http"): clean_sources[k] = u

        gblock = None
        if gplace:
            gblock = {
                "rating": gplace.get("rating"), "review_count": gplace.get("userRatingCount"), "url": gplace.get("googleMapsUri"),
                "reviews": [{"rating": r.get("rating"), "text": (r.get("text") or {}).get("text", "")[:240]} for r in (gplace.get("reviews") or [])[:3] if (r.get("text") or {}).get("text")],
            }
        compiled.append({
            "id": can["id"], "name": can["name"], "locality": loc,
            "zone": can.get("zone") or loc_to_zone.get((loc or "").lower(), "Mumbai"),
            "lat": lat, "lng": lng, "coords_approx": coords_approx, "bhks": bhks,
            "furnishing": furns, "tenant": tenants,
            "rera_ids": can["rera_ids"], "rera_carpet_sqft": int(med_carpet) if med_carpet else None,
            "pricing": pricing, "mumbai_context": enrich_mumbai(lat, lng, transit),
            "civic": enrich_civic(lat, lng, civic_pois),
            "google": gblock, "sources": clean_sources,
        })

    great_deals = _attach_fair_price_deals(compiled)

    out_dir = Path("web/public/data"); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mumbai-index.json").write_text(json.dumps({"city":"Mumbai MMR","generated_at":now_ist,"count":len(compiled),"societies":compiled}, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    with (out_dir / "mumbai-societies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id","name","zone","locality","bhks","carpet_sqft","rent_median_inr","buy_median_inr","rent_deal_pct","has_zero_brokerage","google_rating","nearest_metro","metro_walk_min","nearest_hospital","flood_risk","exact_links"])
        for s in compiled:
            bhk_str = "/".join("1 RK" if b == 0 else f"{b} BHK" for b in s["bhks"])
            w.writerow([s["id"],s["name"],s["zone"],s["locality"],bhk_str,s["rera_carpet_sqft"] or "",s["pricing"]["rent_monthly_inr"]["median"] or "",s["pricing"]["buy_inr"]["median"] or "",((s.get("deal") or {}).get("rent") or {}).get("pct",""),s["pricing"]["has_zero_brokerage"],(s["google"] or {}).get("rating",""),(s["mumbai_context"]["nearest_metro"] or {}).get("name",""),(s["mumbai_context"]["nearest_metro"] or {}).get("walk_min",""),((s.get("civic") or {}).get("hospital") or {}).get("name",""),s["mumbai_context"]["monsoon_flood_risk"],",".join(sorted(s["sources"].keys()))])
    return {"compiled": len(compiled), "great_value_deals": great_deals, "bad_coords_clamped": fixed_bad, "rk_tagged": sum(1 for s in compiled if 0 in s["bhks"]), "civic_anchors": sum(len(v) for v in civic_pois.values()), "updated_at": now_ist}
