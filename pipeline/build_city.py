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
from pipeline.mumbai_features import (
    compute_commutes, extract_outdoor_features, is_outer_city_mismatch,
    classify_lister_type, load_vision_cache, parse_bhk_value, update_price_history,
)
from pipeline.osm_buildings import load_osm_buildings, OSMBuildingIndex
from pipeline.pricing_engine import summarize_portal_prices

IST = timezone(timedelta(hours=5, minutes=30))
RK_RE = re.compile(r"\b1[\s\-]*rk\b|\bstudio\b", re.I)
HARD_JUNK = re.compile(r"(^s\s+for\s+(rent|sale)|\bnear\s+me\b|^property\s+in\b|^flats?,?\s*apartments?$|^properties\s+for\s+(rent|sale)$)", re.I)
UNNAMED_RES = re.compile(r"(\bfor\s+(rent|sale)\s+in\b|^\d+\s*(bhk|rk)\s*(flat|apartment|house|independent)?$|\bindependent\s*house\b|\bstandalone\b|\bbuilder\s*floor\b|^residential\s+|houses?\s+for\s+(rent|sale)|flats?,?\s*apartments?)", re.I)
IND_HOUSE_RE = re.compile(r"\b(independent\s*house|villa|bungalow|row\s*house)\b", re.I)
COMM_DROP = re.compile(r"\b(office|commercial|shop|showroom|warehouse|business\s*park|corporate|chambers|trade\s*star|trade\s*center|town\s*center|it\s*park|coworking|the\s*summit|industrial\s*estate|mindspace|tech\s*park|infotech|cyber\s*park|knowledge\s*park|business\s*bay|corporate\s*park|sez)\b", re.I)

def _valid_src_url(k: str, u: Any) -> bool:
    if not u or not isinstance(u, str) or not u.startswith("http"): return False
    if "findghosla.com/" in u: return False
    if k == "magicbricks": return ("propertyDetails" in u or "-pdpid-" in u or "project-" in u)
    if k == "nobroker": return ("/property/" in u or "nobroker.in/" in u)
    if k == "99acres": return ("99acres.com/" in u and ("-spid-" in u or "-npxid-" in u or "property-in-" not in u))
    return k in ("reddit","community","squareyards","commonfloor","makaan","nobrokerage","housing")

def _build_units(raw_by_source: Dict[str, List[Dict[str, Any]]], loc: str):
    units_r, units_b, seen_r, seen_b = [], [], set(), set()
    sources_rent, sources_buy, clean_sources = {}, {}, {}
    thumb = None
    for src_k, grp in raw_by_source.items():
        for r in grp:
            chk_txt = f"{r.get('name') or ''} {r.get('title') or ''} {r.get('url') or ''} {r.get('address') or ''}"
            if is_outer_city_mismatch(chk_txt, loc):
                continue
            u = r.get("url")
            valid_u = u if _valid_src_url(src_k, u) else None
            u_img = r.get("image") if isinstance(r.get("image"), str) and r["image"].startswith("http") else None
            if not thumb and u_img: thumb = u_img
            low_u = (valid_u or "").lower()
            hint_all = f"{r.get('name') or ''} {r.get('title') or ''} {r.get('description') or ''} {r.get('url') or ''}"
            bhk = parse_bhk_value(r.get("bhk_exact") if r.get("bhk_exact") is not None else r.get("bhk"), hint_all)
            ltype = classify_lister_type(src_k, r, hint_all)
            sqft = r.get("carpet_sqft")
            try: sqft = int(round(float(sqft))) if sqft and 140 <= float(sqft) <= 8000 else None
            except Exception: sqft = None
            zb = bool(r.get("zero_brokerage") or src_k in ("nobroker","nobrokerage","community","reddit"))
            furn = r.get("furnishing")

            rv = r.get("rent_inr")
            if rv and 6_000 <= int(rv) <= 550_000:
                pv = int(rv)
                if (bhk == 0 and pv > 85_000) or (bhk is not None and 0 < bhk <= 1.5 and pv > 210_000) or (bhk is not None and 1.5 < bhk <= 2.5 and pv > 380_000): continue
                if low_u.endswith("/project") or "/project/" in low_u or "/sale/" in low_u or "for-sale" in low_u: continue
                if valid_u: sources_rent.setdefault(src_k, valid_u); clean_sources.setdefault(src_k, valid_u)
                ded = (src_k, bhk, pv, (sqft // 50) if sqft else 0)
                if ded not in seen_r and valid_u:
                    seen_r.add(ded)
                    units_r.append({"p": pv, "b": bhk, "sq": sqft, "s": src_k, "u": valid_u, "zb": (zb or ltype == "owner"), "lt": ltype, "f": furn, "img": u_img})

            bv = r.get("buy_inr")
            if bv and 2_000_000 <= int(bv) <= 600_000_000:
                pv = int(bv)
                if "for-rent" in low_u or "/rent/" in low_u: continue
                if valid_u: sources_buy.setdefault(src_k, valid_u); clean_sources.setdefault(src_k, valid_u)
                ded = (src_k, bhk, pv, (sqft // 50) if sqft else 0)
                if ded not in seen_b and valid_u:
                    seen_b.add(ded)
                    units_b.append({"p": pv, "b": bhk, "sq": sqft, "s": src_k, "u": valid_u, "zb": (zb or ltype == "owner"), "lt": ltype, "f": furn, "img": u_img})

    if len(units_r) >= 2:
        med_r = sorted(x["p"] for x in units_r)[len(units_r) // 2]
        units_r = [x for x in units_r if x["p"] <= max(med_r * 2.4, med_r + 120_000)]

    units_r.sort(key=lambda x: (x["p"], 0 if x.get("img") else 1, 0 if x["zb"] else 1))
    units_b.sort(key=lambda x: (x["p"], 0 if x.get("img") else 1))
    return units_r[:16], units_b[:16], sources_rent, sources_buy, clean_sources, thumb

def _strict_pricing(pricing: Dict[str, Any], units_r: List[Dict], units_b: List[Dict]) -> Dict[str, Any]:
    if units_r:
        ps = sorted(x["p"] for x in units_r); med = ps[len(ps) // 2]
        pricing["rent_monthly_inr"] = {"min": ps[0], "median": med, "max": ps[-1], "is_estimate": False}
    else:
        pricing["rent_monthly_inr"] = {"min": None, "median": None, "max": None, "is_estimate": False}
    if units_b:
        ps = sorted(x["p"] for x in units_b); med = ps[len(ps) // 2]
        pricing["buy_inr"] = {"min": ps[0], "median": med, "max": ps[-1], "is_estimate": False}
    else:
        pricing["buy_inr"] = {"min": None, "median": None, "max": None, "is_estimate": False}
    pricing["has_zero_brokerage"] = any(x.get("zb") for x in (units_r + units_b))
    by_p = {}
    for u in units_r:
        ent = by_p.setdefault(u["s"], {"count": 0, "rent_median": u["p"], "buy_median": None})
        ent["count"] += 1
    for u in units_b:
        ent = by_p.setdefault(u["s"], {"count": 0, "rent_median": None, "buy_median": u["p"]})
        ent["count"] += 1
        if not ent.get("buy_median"): ent["buy_median"] = u["p"]
    pricing["by_portal"] = by_p
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
            cur[uf].sort(key=lambda x: (x["p"], 0 if x.get("img") else 1))
            cur[uf] = cur[uf][:24 if cur.get("is_unnamed") else 16]
        for sf in ("sources","sources_rent","sources_buy"): cur[sf].update(s[sf])
        cur["pricing"] = _strict_pricing(cur["pricing"], cur["units_rent"], cur["units_buy"])
        if cur.get("features") and s.get("features"):
            cur["features"]["tags"] = sorted(set(cur["features"].get("tags") or []) | set(s["features"].get("tags") or []))
            cur["features"]["vision_tags"] = sorted(set(cur["features"].get("vision_tags") or []) | set(s["features"].get("vision_tags") or []))
            cur["features"]["bright"] = bool(cur["features"].get("bright") or s["features"].get("bright"))
    return list(by_key.values())

def _merge_with_previous_index(compiled: List[Dict[str, Any]], vision_cache: Dict[str, Any], prev_path: Path, hist_path: Path = Path("data/price_history.json"), max_days: int = 28) -> List[Dict[str, Any]]:
    import time as _t
    if not prev_path.exists(): return compiled
    try: prev_socs = json.loads(prev_path.read_text(encoding="utf-8")).get("societies") or []
    except Exception: return compiled
    hist = {}
    if hist_path.exists():
        try: hist = json.loads(hist_path.read_text(encoding="utf-8"))
        except Exception: hist = {}
    cutoff = int(_t.time()) - max_days * 86400
    cur_keys = {(re.sub(r"[^a-z0-9]+", "", s["name"].lower()), s["locality"].lower()) for s in compiled}
    preserved = 0
    for ps in prev_socs:
        if not (ps.get("units_rent") or ps.get("units_buy")): continue
        if any("findghosla.com" in str(u.get("u") or "") for u in (ps.get("units_rent") or []) + (ps.get("units_buy") or [])): continue
        k = (re.sub(r"[^a-z0-9]+", "", (ps.get("name") or "").lower()), (ps.get("locality") or "").lower())
        if k in cur_keys: continue
        hrec = hist.get(ps.get("id"))
        if hrec and int(hrec.get("last_seen", cutoff + 1)) < cutoff: continue
        for _uk in ("units_rent", "units_buy"):
            for _u in (ps.get(_uk) or []):
                if not _u.get("lt"):
                    _u["lt"] = "shared" if _u.get("s") in ("community", "reddit") else ("owner" if _u.get("zb") or _u.get("s") in ("nobroker", "owner") else "broker")
        if ps.get("thumb") and ps.get("lat") and ps.get("lng"):
            ps["features"] = extract_outdoor_features(ps.get("name") or "", [], float(ps["lat"]), float(ps["lng"]), ps.get("thumb"), vision_cache)
            if not ps.get("commutes"): ps["commutes"] = compute_commutes(float(ps["lat"]), float(ps["lng"]))
        compiled.append(ps); cur_keys.add(k); preserved += 1
    if preserved:
        print(f"[build] Rolling 28-day merge preserved {preserved:,} active societies from previous index.", flush=True)
    return compiled

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

def build_mumbai(db_path: str | Path = "pipeline/staging/mumbai_raw.db", max_google_calls: int = 25, max_osm_calls: int = 40, max_record_age_days: float = 28.0) -> Dict[str, Any]:
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
    vision_cache = load_vision_cache()

    gcache = {}
    with db.connection() as conn:
        for row in conn.execute("SELECT canonical_id, payload_json FROM google_places_cache").fetchall():
            gcache[row["canonical_id"]] = json.loads(row["payload_json"])

    now_ist = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    compiled = []

    for can in canonicals:
        src_keys = set(can["raw_by_source"].keys())
        is_comm = bool(src_keys & {"community", "reddit"})
        raw_cname = (can["name"] or "").strip()
        if COMM_DROP.search(raw_cname): continue
        if not is_comm and HARD_JUNK.search(raw_cname): continue
        is_unnamed = (not is_comm) and (len(raw_cname) < 4 or bool(UNNAMED_RES.search(raw_cname)))

        recs = [r for grp in can["raw_by_source"].values() for r in grp]
        hint_text = raw_cname + " " + " ".join(str(r.get("url") or "") for r in recs[:4])
        loc = infer_true_locality(hint_text, can["locality"])
        loc_reassigned = (loc != can["locality"])
        if is_outer_city_mismatch(hint_text, loc):
            continue

        ur, ub, sr, sb, cs, thumb = _build_units(can["raw_by_source"], loc)
        if not ur and not ub:
            continue

        gplace = gcache.get(can["id"])
        gloc = (gplace or {}).get("location") or {}
        osm_pt = osm_cache.get(can["id"]) or []
        bldg_pt = osm_bldg_idx.lookup(raw_cname, loc) if not is_unnamed else None

        rec_pts = [(float(r["lat"]), float(r["lng"])) for r in recs if r.get("lat") is not None and r.get("lng") is not None and is_valid_mmr_land(r["lat"], r["lng"], loc)]
        rec_med = (sorted(p[0] for p in rec_pts)[len(rec_pts)//2], sorted(p[1] for p in rec_pts)[len(rec_pts)//2]) if rec_pts else (None, None)
        rec_any = [(float(r["lat"]), float(r["lng"])) for r in recs if r.get("lat") is not None and r.get("lng") is not None and is_valid_mmr_land(r["lat"], r["lng"], None)]
        rec_any_med = (sorted(p[0] for p in rec_any)[len(rec_any)//2], sorted(p[1] for p in rec_any)[len(rec_any)//2]) if rec_any else (None, None)

        lat = lng = None
        coords_approx = False
        for cla, cln in ((gloc.get("latitude"), gloc.get("longitude")), (bldg_pt[0], bldg_pt[1]) if bldg_pt else (None, None), (osm_pt[0], osm_pt[1]) if len(osm_pt) == 2 else (None, None), rec_med, (can.get("lat"), can.get("lng"))):
            if is_valid_mmr_land(cla, cln, loc):
                lat, lng = round(float(cla), 6), round(float(cln), 6); break
        if lat is None:
            for cla, cln in ((gloc.get("latitude"), gloc.get("longitude")), rec_any_med, (can.get("lat"), can.get("lng"))):
                if is_valid_mmr_land(cla, cln, None):
                    lat, lng = round(float(cla), 6), round(float(cln), 6)
                    sl, sk = nearest_locality(lat, lng)
                    if sk <= 6.0: loc, loc_reassigned = sl, True
                    break
        if lat is None:
            lat, lng = safe_approx_coords(can["id"], loc); coords_approx = True

        bhk_set = {u["b"] for u in (ur + ub) if u.get("b") is not None}
        carpets = [float(u["sq"]) for u in (ur + ub) if u.get("sq")]
        med_c = round(sorted(carpets)[len(carpets)//2], 0) if carpets else None
        pricing = _strict_pricing(summarize_portal_prices(can["raw_by_source"], carpet_sqft=med_c), ur, ub)

        gblock = None
        if gplace:
            gblock = {"rating": gplace.get("rating"), "review_count": gplace.get("userRatingCount"), "url": gplace.get("googleMapsUri"), "reviews": [{"rating": r.get("rating"), "text": (r.get("text") or {}).get("text","")[:220]} for r in (gplace.get("reviews") or [])[:3] if (r.get("text") or {}).get("text")]}

        disp_name = (f"Independent Houses — {loc}" if IND_HOUSE_RE.search(raw_cname) else f"Standalone Flats — {loc}") if is_unnamed else raw_cname
        compiled.append({
            "id": can["id"], "name": disp_name, "locality": loc, "is_unnamed": is_unnamed,
            "zone": loc_to_zone.get((loc or "").lower(), can.get("zone") or "Mumbai") if loc_reassigned else (can.get("zone") or loc_to_zone.get((loc or "").lower(), "Mumbai")),
            "lat": lat, "lng": lng, "coords_approx": coords_approx, "bhks": sorted(bhk_set),
            "furnishing": sorted({u["f"] for u in (ur + ub) if u.get("f")}),
            "tenant": sorted({r["tenant"] for r in recs if r.get("tenant")}),
            "rera_ids": can["rera_ids"], "rera_carpet_sqft": int(med_c) if med_c else None,
            "pricing": pricing, "units_rent": ur, "units_buy": ub, "thumb": thumb,
            "mumbai_context": enrich_mumbai(lat, lng, transit),
            "features": extract_outdoor_features(raw_cname, recs, lat, lng, thumb, vision_cache),
            "commutes": compute_commutes(lat, lng),
            "civic": enrich_civic(lat, lng, civic_pois),
            "google": gblock, "sources": cs, "sources_rent": sr, "sources_buy": sb,
        })

    compiled = _merge_duplicates(compiled)
    compiled = _merge_with_previous_index(compiled, vision_cache, Path("web/public/data/mumbai-index.json"))
    exact_hits = sum(1 for s in compiled if not s["coords_approx"])
    great = _attach_deals(compiled)
    drops, new_cnt = update_price_history(compiled)
    with_photos = sum(1 for s in compiled if s.get("thumb"))

    out = Path("web/public/data"); out.mkdir(parents=True, exist_ok=True)
    (out / "mumbai-index.json").write_text(json.dumps({"city":"Mumbai MMR","generated_at":now_ist,"count":len(compiled),"societies":compiled}, ensure_ascii=False, separators=(",",":")), encoding="utf-8")
    with (out / "mumbai-societies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id","name","zone","locality","bhks","carpet_sqft","rent_inr","buy_inr","exact_pin","zero_brok","google","metro","walk_min","flood","features","sources"])
        for s in compiled:
            w.writerow([s["id"],s["name"],s["zone"],s["locality"],"/".join("1 RK" if b==0 else f"{b} BHK" for b in s["bhks"]),s["rera_carpet_sqft"] or "",(s["units_rent"][0]["p"] if s["units_rent"] else ""),(s["units_buy"][0]["p"] if s["units_buy"] else ""),not s["coords_approx"],s["pricing"]["has_zero_brokerage"],(s["google"] or {}).get("rating",""),(s["mumbai_context"]["nearest_metro"] or {}).get("name",""),(s["mumbai_context"]["nearest_metro"] or {}).get("walk_min",""),s["mumbai_context"]["monsoon_flood_risk"],",".join(s["features"]["tags"]),",".join(sorted(s["sources"].keys()))])
    return {
        "compiled": len(compiled), "exact_pins": exact_hits, "with_photos": with_photos,
        "great_value_deals": great, "price_drops": drops,
        "balcony_hits": sum(1 for s in compiled if "balcony" in s["features"]["tags"]),
        "terrace_garden_hits": sum(1 for s in compiled if set(s["features"]["tags"]) & {"terrace","garden"}),
        "sea_view_hits": sum(1 for s in compiled if "sea_view" in s["features"]["tags"]),
        "updated_at": now_ist,
    }
