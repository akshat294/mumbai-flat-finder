import json, math, sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.v19_common import haversine_km, clean_soc_name, merge_records_into_societies
from pipeline.connectors.native_boost import run_native_boost, backfill_nobroker_photos
import os
from pipeline.connectors.apify_portals import sync_apify, load_cached_apify

def run():
    idx_p = ROOT / "web/public/data/mumbai-index.json"
    data = json.loads(idx_p.read_text(encoding="utf-8"))
    socs = data.get("societies", [])

    # Drop old broken hs-* records so they re-ingest cleanly in exact schema
    socs = [s for s in socs if not str(s.get("id", "")).startswith("hs-")]

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

    nb_photos = backfill_nobroker_photos(socs, max_fetch=55)

    r_src, b_src, r_img = Counter(), Counter(), Counter()
    for s in socs:
        for u in (s.get("units_rent") or []):
            src = u.get("s") or "unknown"
            r_src[src] += 1
            if u.get("img") or s.get("thumb"): r_img[src] += 1
        for u in (s.get("units_buy") or []):
            b_src[u.get("s") or "unknown"] += 1

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["count"] = len(socs)
    data["societies"] = socs
    idx_p.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    print(f"[v19 DONE] Pins fixed: {fixed_pins} | Names cleaned: {fixed_names} | Native +{n_u} units ({n_s} new bldgs) | Apify +{a_u} units | NoBroker photos +{nb_photos}")
    print(f"[v19 RENT] {sum(r_src.values())} units | {dict(r_src.most_common())}")
    print(f"[v19 RENT+IMG] {sum(r_img.values())} units | {dict(r_img.most_common())}")
    print(f"[v19 BUY ] {sum(b_src.values())} units | {dict(b_src.most_common())}")

if __name__ == "__main__":
    run()
