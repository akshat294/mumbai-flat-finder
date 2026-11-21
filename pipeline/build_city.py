from __future__ import annotations
import csv, json, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from pipeline.civic_osm import load_civic_pois, enrich_civic
from pipeline.connectors.google_places import enrich_with_google_places
from pipeline.core.checkpoint import CheckpointDB
from pipeline.entity_resolver import resolve_entities
from pipeline.geo_guard import is_valid_mmr_land, safe_approx_coords, enrich_with_osm_photon, infer_true_locality, nearest_locality
from pipeline.mumbai_enricher import enrich_mumbai, load_transit
from pipeline.osm_buildings import load_osm_buildings, OSMBuildingIndex
from pipeline.pricing_engine import summarize_portal_prices

IST = timezone(timedelta(hours=5, minutes=30))
RK_RE = re.compile(r"\b1[\s\-]*rk\b|\bstudio\b", re.I)
JUNK_NAME = re.compile(r"(^s\s+for\s+(rent|sale)|\bfor\s+(rent|sale)\s+in\b|flats?,?\s*apartments?|houses?\s+for\s+(rent|sale)|properties\s+for\s+(rent|sale)|\bnear\s+me\b|^\d+\s*(bhk|rk)\s*(flat|apartment|house)?$|^property\s+in\b|^residential\s+)", re.I)
COMM_DROP = re.compile(r"\b(office|commercial|shop|showroom|warehouse|business\s*park|corporate|chambers|trade\s*star|trade\s*center|town\s*center|it\s*park|coworking|the\s*summit|industrial\s*estate|mindspace|tech\s*park|infotech|cyber\s*park|knowledge\s*park|business\s*bay|corporate\s*park|sez)\b", re.I)

def _valid_src_url(k: str, u: Any) -> bool:
    if not u or not isinstance(u, str) or not u.startswith("http"): return False
    if k == "magicbricks": return ("propertyDetails" in u or "-pdpid-" in u or "project-" in u)
    if k == "nobroker": return "/property/" in u
    if k == "99acres": return ("99acres.com/" in u and ("-spid-" in u or "-npxid-" in u or "property-in-" not in u))
    return k in ("reddit","community","squareyards","commonfloor","makaan","nobrokerage")

def _build_units(raw_by_source: Dict[str, List[Dict[str, Any]]]):
    units_r, units_b, seen_r, seen_b = [], [], set(), set()
    sources_rent, sources_buy, clean_sources = {}, {}, {}
    thumb = None
    for src_k, grp in raw_by_source.items():
        for r in grp:
            u = r.get("url")
            valid_u = u if _valid_src_url(src_k, u) else None
            if not thumb and isinstance(r.get("image"), str) and r["image"].startswith("http"): thumb = r["image"]
            low_u = (valid_u or "").lower()
            bhk = r.get("bhk")
            if RK_RE.search(str(r.get("url") or "") + " " + str(r.get("name") or "")): bhk = 0
            elif bhk is not None:
                try: bhk = int(bhk)
                except Exception: bhk = None
                if bhk is not None and not (0 <= bhk <= 6): bhk = None
            sqft = r.get("carpet_sqft")
            try: sqft = int(round(float(sqft))) if sqft and 140 <= float(sqft) <= 8000 else None
            except Exception: sqft = None
            zb = bool(r.get("zero_brokerage") or src_k in ("nobroker","nobrokerage","community","reddit"))
            furn = r.get("furnishing")

            rv = r.get("rent_inr")
            if rv and 6_000 <= int(rv) <= 550_000:
                pv = int(rv)
                if (bhk == 0 and pv > 85_000) or (bhk == 1 and pv > 165_000) or (bhk == 2 and pv > 320_000): continue
                if low_u.endswith("/project") or "/project/" in low_u or "/sale/" in low_u or "for-sale" in low_u: continue
                ur = valid_u
                if ur: sources_rent.setdefault(src_k, ur); clean_sources.setdefault(src_k, ur)
                ded = (src_k, bhk, pv, (sqft // 50) if sqft else 0)
                if ded not in seen_r:
                    seen_r.add(ded)
                    units_r.append({"p": pv, "b": bhk, "sq": sqft, "s": src_k, "u": ur, "zb": zb, "f": furn})

            bv = r.get("buy_inr")
            if bv and 2_000_000 <= int(bv) <= 600_000_000:
                pv = int(bv)
                ub = valid_u if ("for-rent" not in low_u) else None
                if ub: sources_buy.setdefault(src_k, ub); clean_sources.setdefault(src_k, ub)
                ded = (src_k, bhk, pv, (sqft // 50) if sqft else 0)
                if ded not in seen_b:
                    seen_b.add(ded)
                    units_b.append({"p": pv, "b": bhk, "sq": sqft, "s": src_k, "u": ub, "zb": zb, "f": furn})

    if len(units_r) >= 2:
        med_r = sorted(x["p"] for x in units_r)[len(units_r) // 2]
        units_r = [x for x in units_r if x["p"] <= max(med_r * 2.4, med_r + 120_000)]

    units_r.sort(key=lambda x: (x["p"], 0 if x["u"] else 1, 0 if x["zb"] else 1))
    units_b.sort(key=lambda x: (x["p"], 0 if x["u"] else 1))
    return units_r[:8], units_b[:8], sources_rent, sources_buy, clean_sources, thumb

def _ensure_pricing(pricing: Dict[str, Any], units_r: List[Dict], units_b: List[Dict]) -> Dict[str, Any]:
    if units_r:
        ps = sorted(x["p"] for x in units_r); med = ps[len(ps) // 2]
        if not pricing["rent_monthly_inr"].get("median") or pricing["rent_monthly_inr"].get("is_estimate"):
            pricing["rent_monthly_inr"] = {"min": ps[0], "median": med, "max": ps[-1], "is_estimate": False}
        elif pricing["rent_monthly_inr"]["median"] > med * 2.2:
            pricing["rent_monthly_inr"]["median"] = med
        if any(x.get("zb") for x in units_r): pricing["has_zero_brokerage"] = True
    if units_b:
        ps = sorted(x["p"] for x in units_b); med = ps[len(ps) // 2]
        if not pricing["buy_inr"].get("median") or pricing["buy_inr"].get("is_estimate"):
            pricing["buy_inr"] = {"min": ps[0], "median": med, "max": ps[-1], "is_estimate": False}
    by_p = pricing.setdefault("by_portal", {})
    for u in units_r:
        ent = by_p.setdefault(u["s"], {"count": 0, "rent_median": u["p"], "buy_median": None})
        ent["count"] = max(ent.get("count", 0), 1)
        if not ent.get("rent_median"): ent["rent_median"] = u["p"]
    for u in units_b:
        ent = by_p.setdefault(u["s"], {"count": 0, "rent_median": None, "buy_median": u["p"]})
        ent["count"] = max(ent.get("count", 0), 1)
        if not ent.get("buy_median"): ent["buy_median"] = u["p"]
    return pricing

def _merge_duplicates(compiled: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for s in compiled:
        key = (re.sub(r"[^a-z0-9]+", "", s["name"].lower()), s["locality"].lower())
        if key not in by_key: by_key[key] = s; continue
        cur = by_key[key]
        if cur["coords_approx"] and not s["coords_approx"]:
            cur["lat"], cur["lng"], cur["coords_approx"] = s["lat"], s["lng"], False
        for lf in ("bhks","furnishing","tenant","rera_ids"): cur[lf] = sorted(set(cur[lf]) | set(s[lf]))
        for ff in ("thumb","google","rera_carpet_sqft"):
            if not cur.get(ff) and s.get(ff): cur[ff] = s[ff]
        for uf in ("units_rent","units_buy"):
            seen_u = {(x["s"], x["b"], x["p"]) for x in cur[uf]}
            for u in s[uf]:
                if (u["s"], u["b"], u["p"]) not in seen_u:
                    seen_u.add((u["s"], u["b"], u["p"])); cur[uf].append(u)
            cur[uf].sort(key=lambda x: (x["p"], 0 if x["u"] else 1)); cur[uf] = cur[uf][:8]
        for sf in ("sources","sources_rent","sources_buy"): cur[sf].update(s[sf])
        cur["pricing"] = _ensure_pricing(cur["pricing"], cur["units_rent"], cur["units_buy"])
    return list(by_key.values())

def _attach_deals(compiled: List[Dict[str, Any]]) -> int:
    by_r, by_b = {}, {}
    for s in compiled:
        loc = s["locality"]
        if s["units_rent"]: by_r.setdefault(loc, []).append(float(s["units_rent"][0]["p"]))
        if s["units_buy"]: by_b.setdefault(loc, []).append(float(s["units_buy"][0]["p"]))
    med = lambda a: sorted(a)[len(a)//2] if len(a) >= 4 else None
    rmeds, bmeds = {k: med(v) for k, v in by_r.items()}, {k: med(v) for k, v in by_b.items()}
    great = 0
    for s in compiled:
        loc, deal = s["locality"], {}
        for key, units, meds in (("rent", s["units_rent"], rmeds), ("buy", s["units_buy"], bmeds)):
            mv = meds.get(loc)
            if mv and units:
                pct = round(((float(units[0]["p"]) - mv) / mv) * 100)
                if -65 <= pct <= 180:
                    lbl = "Great Value" if pct <= -12 else ("Premium" if pct >= 20 else "Fair Price")
                    if lbl == "Great Value": great += 1
                    deal[key] = {"pct": pct, "label": lbl, "loc_median": int(mv)}
        s["deal"] = deal or None
    return great

def build_mumbai(db_path: str | Path = "pipeline/staging/mumbai_raw.db", max_google_calls: int = 25, max_osm_calls: int = 40, max_record_age_days: float = 7.0) -> Dict[str, Any]:
    db = CheckpointDB(db_path)
    if hasattr(db, "prune_stale_records"): db.prune_stale_records(max_age_days=max_record_age_days)
    raw = db.fetch_all_raw()

    cfg = json.loads(Path("data/cities.json").read_text(encoding="utf-8-sig"))["mumbai"]
    loc_to_zone = {"pali hill": "Bandra-Santacruz"}
    for zn, zi in cfg["zones"].items():
        for l in zi["localities"]: loc_to_zone[l.lower()] = zn

    print(f"[build] Resolving {len(raw):,} raw records...", flush=True)
    canonicals, _ = resolve_entities(raw)
    print(f"[build] Deduplicated to {len(canonicals):,} societies. Enriching...", flush=True)
    enrich_with_google_places(db, canonicals, max_calls=max_google_calls)
    osm_cache = enrich_with_osm_photon(canonicals, max_calls=max_osm_calls)
    civic_pois = load_civic_pois(allow_fetch=True)
    osm_bldg_idx = OSMBuildingIndex(load_osm_buildings(allow_fetch=True))
    transit = load_transit()

    gcache = {}
    with db.connection() as conn:
        for row in conn.execute("SELECT canonical_id, payload_json FROM google_places_cache").fetchall():
            gcache[row["canonical_id"]] = json.loads(row["payload_json"])

    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    compiled = []

    for can in canonicals:
        src_keys = set(can["raw_by_source"].keys())
        is_comm = bool(src_keys & {"community", "reddit"})
        if COMM_DROP.search(can["name"]): continue
        if not is_comm and (len(can["name"].strip()) < 4 or JUNK_NAME.search(can["name"])): continue

        recs = [r for grp in can["raw_by_source"].values() for r in grp]
        hint_text = can["name"] + " " + " ".join(str(r.get("url") or "") for r in recs[:4])
        loc = infer_true_locality(hint_text, can["locality"])
        loc_reassigned = (loc != can["locality"])

        gplace = gcache.get(can["id"])
        gloc = (gplace or {}).get("location") or {}
        osm_pt = osm_cache.get(can["id"]) or []
        bldg_pt = osm_bldg_idx.lookup(can["name"], loc)

        lat = lng = None
        coords_approx = False
        for cla, cln in ((gloc.get("latitude"), gloc.get("longitude")), (bldg_pt[0], bldg_pt[1]) if bldg_pt else (None, None), (osm_pt[0], osm_pt[1]) if len(osm_pt) == 2 else (None, None), (can.get("lat"), can.get("lng"))):
            if is_valid_mmr_land(cla, cln, loc):
                lat, lng = round(float(cla), 6), round(float(cln), 6); break
        if lat is None:
            for cla, cln in ((gloc.get("latitude"), gloc.get("longitude")), (can.get("lat"), can.get("lng"))):
                if is_valid_mmr_land(cla, cln, None):
                    lat, lng = round(float(cla), 6), round(float(cln), 6)
                    sl, sk = nearest_locality(lat, lng)
                    if sk <= 6.0: loc, loc_reassigned = sl, True
                    break
        if lat is None:
            lat, lng = safe_approx_coords(can["id"], loc); coords_approx = True

        bhk_set = set()
        for r in recs:
            ut = str(r.get("url") or "") + " " + str(r.get("name") or "")
            if RK_RE.search(ut): bhk_set.add(0)
            elif r.get("bhk") is not None and 0 <= int(r["bhk"]) <= 6: bhk_set.add(int(r["bhk"]))
        carpets = [float(r["carpet_sqft"]) for r in recs if r.get("carpet_sqft") and 140 <= float(r["carpet_sqft"]) <= 8000]
        med_c = round(sorted(carpets)[len(carpets)//2], 0) if carpets else None

        ur, ub, sr, sb, cs, thumb = _build_units(can["raw_by_source"])
        pricing = _ensure_pricing(summarize_portal_prices(can["raw_by_source"], carpet_sqft=med_c), ur, ub)
        if not ur and not ub and not pricing["rent_monthly_inr"].get("median") and not pricing["buy_inr"].get("median"):
            continue

        gblock = None
        if gplace:
            gblock = {"rating": gplace.get("rating"), "review_count": gplace.get("userRatingCount"), "url": gplace.get("googleMapsUri"), "reviews": [{"rating": r.get("rating"), "text": (r.get("text") or {}).get("text","")[:220]} for r in (gplace.get("reviews") or [])[:3] if (r.get("text") or {}).get("text")]}

        compiled.append({
            "id": can["id"], "name": can["name"], "locality": loc,
            "zone": loc_to_zone.get((loc or "").lower(), can.get("zone") or "Mumbai") if loc_reassigned else (can.get("zone") or loc_to_zone.get((loc or "").lower(), "Mumbai")),
            "lat": lat, "lng": lng, "coords_approx": coords_approx, "bhks": sorted(bhk_set),
            "furnishing": sorted({r["furnishing"] for r in recs if r.get("furnishing")}),
            "tenant": sorted({r["tenant"] for r in recs if r.get("tenant")}),
            "rera_ids": can["rera_ids"], "rera_carpet_sqft": int(med_c) if med_c else None,
            "pricing": pricing, "units_rent": ur, "units_buy": ub, "thumb": thumb,
            "mumbai_context": enrich_mumbai(lat, lng, transit), "civic": enrich_civic(lat, lng, civic_pois),
            "google": gblock, "sources": cs, "sources_rent": sr, "sources_buy": sb,
        })

    compiled = _merge_duplicates(compiled)
    exact_hits = sum(1 for s in compiled if not s["coords_approx"])
    great = _attach_deals(compiled)

    out = Path("web/public/data"); out.mkdir(parents=True, exist_ok=True)
    (out / "mumbai-index.json").write_text(json.dumps({"city":"Mumbai MMR","generated_at":now_ist,"count":len(compiled),"societies":compiled}, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    with (out / "mumbai-societies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id","name","zone","locality","bhks","carpet_sqft","rent_inr","buy_inr","exact_pin","zero_brok","google","metro","walk_min","flood","sources"])
        for s in compiled:
            w.writerow([s["id"],s["name"],s["zone"],s["locality"],"/".join("1 RK" if b==0 else f"{b} BHK" for b in s["bhks"]),s["rera_carpet_sqft"] or "",(s["units_rent"][0]["p"] if s["units_rent"] else s["pricing"]["rent_monthly_inr"].get("median") or ""),(s["units_buy"][0]["p"] if s["units_buy"] else s["pricing"]["buy_inr"].get("median") or ""),not s["coords_approx"],s["pricing"]["has_zero_brokerage"],(s["google"] or {}).get("rating",""),(s["mumbai_context"]["nearest_metro"] or {}).get("name",""),(s["mumbai_context"]["nearest_metro"] or {}).get("walk_min",""),s["mumbai_context"]["monsoon_flood_risk"],",".join(sorted(s["sources"].keys()))])
    return {"compiled": len(compiled), "exact_pins": exact_hits, "great_value_deals": great, "updated_at": now_ist}
