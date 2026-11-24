import gzip, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.index_io import load_index, save_sharded_index
from pipeline.connectors.apify_portals import _norm_any_item, _save_merged_cache
from pipeline.connectors.apish_99acres import reparse_raw_archive
from pipeline.connectors.native_boost import backfill_nobroker_photos
from pipeline.connectors.v19_common import is_generic_name
from pipeline.data_hygiene import run_data_hygiene, clean_fleet_media
from pipeline.mumbai_transit import enrich_transit_context
from pipeline.quality_filter import filter_and_track_societies

def run():
    by_url = {}
    raw_h_dir = ROOT / "data/raw_housing"
    h_recs = []
    if raw_h_dir.exists():
        for fp in sorted(raw_h_dir.glob("*.json.gz")):
            try:
                with gzip.open(fp, "rt", encoding="utf-8") as f:
                    rows = json.load(f)
                for it in (rows if isinstance(rows, list) else []):
                    rec = _norm_any_item(it, source_hint="housing", mode_hint="rent")
                    if rec and rec.get("u"):
                        h_recs.append(rec)
                        by_url[rec["u"]] = rec
            except Exception:
                pass
    if h_recs:
        _save_merged_cache(h_recs)
        print(f"[v37 APPLY] Reparsed raw_housing -> {len(h_recs):,} records (0 credits)")

    recs99 = reparse_raw_archive()
    for r in recs99:
        if isinstance(r, dict) and r.get("u"):
            by_url[r["u"]] = r

    data = load_index()
    socs = data.get("societies") or []
    upgraded_names, upgraded_furn, upgraded_imgs = 0, 0, 0
    for s in socs:
        loc = str(s.get("locality") or "")
        all_u = list(s.get("units_rent") or []) + list(s.get("units_buy") or [])
        for u in all_u:
            rec = by_url.get(u.get("u") or "")
            if not rec:
                continue
            if rec.get("f") and not u.get("f"):
                u["f"] = rec["f"]
                upgraded_furn += 1
            if rec.get("img") and not u.get("img"):
                u["img"] = rec["img"]
                upgraded_imgs += 1
            if rec.get("imgs") and len(rec["imgs"]) > len(u.get("imgs") or []):
                u["imgs"] = rec["imgs"][:5]
            if len(all_u) == 1 and is_generic_name(s.get("name"), loc):
                cand = rec.get("name") or ""
                if cand and not is_generic_name(cand, loc):
                    s["name"] = cand
                    upgraded_names += 1
    print(f"[v37 APPLY] Upgraded from raw archives -> names: +{upgraded_names} | furnishing: +{upgraded_furn} | photos: +{upgraded_imgs}")

    run_data_hygiene(socs)
    nb_p = backfill_nobroker_photos(socs, max_fetch=400)
    for s in socs:
        gal = []
        def _add(p):
            if isinstance(p, str) and p.startswith("http") and p not in gal:
                gal.append(p)
        _add(s.get("thumb"))
        for p in (s.get("photos") or []):
            _add(p)
        for u in (s.get("units_rent") or []) + (s.get("units_buy") or []):
            _add(u.get("img"))
            for p in (u.get("imgs") or []):
                _add(p)
        if gal:
            s["thumb"] = gal[0]
            if len(gal) > 1:
                s["photos"] = gal[:6]

    clean_fleet_media(socs)
    enrich_transit_context(socs)
    cleaned, _ = filter_and_track_societies(socs)
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["societies"] = cleaned
    data["count"] = len(cleaned)
    sh = save_sharded_index(data, max_shard_bytes=3_800_000)
    print(f"[v37 APPLY DONE] NB photos +{nb_p} | Clean bldgs: {len(cleaned):,} | Shards: {sh['rent_shards']}R+{sh['buy_shards']}B ({sh['total_mb']} MB)")

if __name__ == "__main__":
    run()
