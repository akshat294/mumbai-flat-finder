import json, math, os, re, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.v19_common import haversine_km, clean_soc_name, merge_records_into_societies, extract_rera_ids
from pipeline.connectors.native_boost import run_native_boost, backfill_nobroker_photos
from pipeline.connectors.apify_portals import sync_apify, load_cached_apify
from pipeline.compact_index import save_compacted_index
from pipeline.mumbai_transit import enrich_transit_context
from pipeline.connectors.maharera_enricher import enrich_societies as enrich_maharera

SEEN_PATH = ROOT / "data/seen_timestamps.json"

def _load_first_seen():
    seen = {}
    for ph_cand in (ROOT / "data/price_history.json", ROOT / "web/public/data/price_history.json"):
        if ph_cand.exists():
            try:
                ph = json.loads(ph_cand.read_text(encoding="utf-8"))
                if isinstance(ph, dict):
                    for sid, hist in ph.items():
                        if isinstance(hist, list) and hist and isinstance(hist[0], dict):
                            ts = hist[0].get("ts") or hist[0].get("t")
                            if isinstance(ts, (int, float)) and ts > 1600000000:
                                seen[sid] = int(ts)
            except Exception:
                pass
    if SEEN_PATH.exists():
        try:
            saved = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if isinstance(v, (int, float)):
                        seen[k] = min(seen.get(k, int(v)), int(v))
        except Exception:
            pass
    return seen

def _enrich_maharera_local(socs):
    rera_lookup = {}
    if (ROOT / "data").exists():
        for cand in (ROOT / "data").glob("*rera*.json"):
            try:
                blob = json.loads(cand.read_text(encoding="utf-8"))
                rows = blob if isinstance(blob, list) else (blob.get("projects") or blob.get("records") or list(blob.values()))
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    nm = re.sub(r"[^a-z0-9]+", "", str(r.get("name") or r.get("project_name") or "").lower())
                    if len(nm) >= 4:
                        rera_lookup[nm] = r
            except Exception:
                continue

    matched = 0
    for s in socs:
        rids = list(s.get("rera_ids") or [])
        for rid in extract_rera_ids(f"{s.get('name', '')} {json.dumps(s.get('units_buy') or [])[:600]}"):
            if rid not in rids:
                rids.append(rid)
        if rera_lookup:
            k = re.sub(r"[^a-z0-9]+", "", str(s.get("name") or "").lower())
            hit = rera_lookup.get(k)
            if hit:
                rid = hit.get("rera_id") or hit.get("registration_no") or hit.get("id")
                if isinstance(rid, str) and rid and rid not in rids:
                    rids.append(rid)
                if hit.get("developer") or hit.get("promoter"):
                    s["rera_developer"] = str(hit.get("developer") or hit.get("promoter"))[:64]
                if hit.get("possession") or hit.get("completion_date"):
                    s["rera_possession"] = str(hit.get("possession") or hit.get("completion_date"))[:32]
                matched += 1
        if rids:
            s["rera_ids"] = rids[:4]
    return matched

def run():
    idx_p = ROOT / "web/public/data/mumbai-index.json"
    data = json.loads(idx_p.read_text(encoding="utf-8"))
    socs = [s for s in data.get("societies", []) if not str(s.get("id", "")).startswith("hs-")]

    loc_pts = {}
    for s in socs:
        loc, lat, lng = s.get("locality"), s.get("lat"), s.get("lng")
        if loc and lat and lng:
            loc_pts.setdefault(loc, []).append((float(lat), float(lng)))
    loc_med = {
        loc: (sorted(p[0] for p in pts)[len(pts) // 2], sorted(p[1] for p in pts)[len(pts) // 2])
        for loc, pts in loc_pts.items()
    }

    fixed_pins, fixed_names = 0, 0
    for i, s in enumerate(socs):
        raw_name = str(s.get("name") or "")
        clean_n = clean_soc_name(raw_name, str(s.get("locality") or ""))
        if clean_n and clean_n != raw_name:
            s["name"] = clean_n
            fixed_names += 1
        loc, lat, lng = s.get("locality"), s.get("lat"), s.get("lng")
        if loc in loc_med and lat and lng:
            mlat, mlng = loc_med[loc]
            if haversine_km(float(lat), float(lng), mlat, mlng) > 3.8:
                ang = (hash(s.get("id") or s.get("name") or str(i)) % 360) * math.pi / 180.0
                rad = 0.0012 + ((i % 7) * 0.0003)
                s["lat"] = round(mlat + rad * math.cos(ang), 6)
                s["lng"] = round(mlng + rad * math.sin(ang), 6)
                s["coords_approx"] = True
                ctx = s.get("mumbai_context")
                if isinstance(ctx, dict):
                    if isinstance(ctx.get("nearest_metro"), dict) and (ctx["nearest_metro"].get("walk_min") or 0) > 60:
                        ctx.pop("nearest_metro", None)
                    if isinstance(ctx.get("nearest_train"), dict) and (ctx["nearest_train"].get("walk_min") or 0) > 60:
                        ctx.pop("nearest_train", None)
                fixed_pins += 1

    native_recs = run_native_boost()
    n_u, n_s = merge_records_into_societies(socs, native_recs)

    apify_recs = sync_apify() if os.environ.get("GITHUB_ACTIONS") == "true" else load_cached_apify()
    a_u, a_s = merge_records_into_societies(socs, apify_recs)

    nb_photos = backfill_nobroker_photos(socs, max_fetch=150)
    multi_photo_socs = 0
    for s in socs:
        gal = []
        def _addp(u):
            if isinstance(u, str) and u.startswith("http") and u not in gal:
                gal.append(u)
        _addp(s.get("thumb"))
        for u in (s.get("units_rent") or []) + (s.get("units_buy") or []):
            _addp(u.get("img"))
            for x in (u.get("imgs") or []):
                _addp(x)
        if len(gal) > 1:
            s["photos"] = gal[:6]
            multi_photo_socs += 1
        elif gal and not s.get("thumb"):
            s["thumb"] = gal[0]

    rera_hits = _enrich_maharera_local(socs)
    rera_total = enrich_maharera(socs, max_fetch=200)

    now_ts = int(time.time())
    first_seen = _load_first_seen()
    for s in socs:
        sid = s.get("id")
        if not sid:
            continue
        if sid not in first_seen:
            first_seen[sid] = now_ts if s.get("is_new") else (now_ts - 86400)
        age_d = max(0, int((now_ts - first_seen[sid]) // 86400))
        s["age_days"] = age_d
        s["is_new"] = (age_d == 0)
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(first_seen, separators=(",", ":")), encoding="utf-8")

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["count"] = len(socs)
    data["societies"] = socs
    enrich_transit_context(socs)
    save_compacted_index(idx_p, data)
    try:
        from pipeline.vision_vibe import score_societies
        score_societies()
    except Exception as _ve:
        print(f'[v25 VIBE WARN] {_ve}')

    print(f"[v20 DONE] Pins fixed: {fixed_pins} | Names cleaned: {fixed_names} | Native +{n_u} ({n_s} bldgs) | Apify +{a_u} | NB photos +{nb_photos} | Multi-photo bldgs: {multi_photo_socs} | RERA bldgs: {rera_total} (+{rera_hits} matched)")

if __name__ == "__main__":
    run()
