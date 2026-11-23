import argparse, gzip, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.connectors.v19_common import (
    detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name, merge_records_into_societies
)
from pipeline.index_io import load_index, save_sharded_index
from pipeline.quality_filter import filter_and_track_societies, REGISTRY_PATH
from pipeline.mumbai_transit import enrich_transit_context

API_BASE = "https://api.api.sh/99acres/v1/search"
CACHE_PATH = ROOT / "data/apish_99acres_cache.json"
QUEUE_PATH = ROOT / "data/apish_99acres_queue.json"
RAW_DIR = ROOT / "data/raw_99acres"

# 46 Priority-ordered Mumbai MMR slices: (slice_id, label, params, max_pages)
SLICE_SPECS = [
    ("mumbai_rent_owner", "Mumbai Rent (Owner)", {"city": "mumbai", "purpose": "rent", "posted_by": "owner", "type": "apartment,studio,builder_floor,independent_house"}, 8),
    ("mumbai_sale_owner", "Mumbai Buy (Owner)", {"city": "mumbai", "purpose": "sale", "posted_by": "owner", "type": "apartment,studio,builder_floor,independent_house"}, 6),
    ("thane_rent_owner", "Thane Rent (Owner)", {"city": "thane", "purpose": "rent", "posted_by": "owner", "type": "apartment,studio,builder_floor,independent_house"}, 4),
    ("mumbai_rent_all", "Mumbai Rent (All)", {"city": "mumbai", "purpose": "rent", "type": "apartment,studio"}, 12),
    ("mumbai_sale_all", "Mumbai Buy (All)", {"city": "mumbai", "purpose": "sale", "type": "apartment,studio"}, 10),
    ("thane_rent_all", "Thane Rent (All)", {"city": "thane", "purpose": "rent", "type": "apartment,studio"}, 5),
    ("thane_sale_all", "Thane Buy (All)", {"city": "thane", "purpose": "sale", "type": "apartment,studio"}, 4),
    ("loc_bandra_west_rent", "Bandra West Rent", {"location": "bandra-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 4),
    ("loc_bandra_west_sale", "Bandra West Buy", {"location": "bandra-west-mumbai", "purpose": "sale", "type": "apartment,studio"}, 3),
    ("loc_khar_west_rent", "Khar West Rent", {"location": "khar-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_khar_west_sale", "Khar West Buy", {"location": "khar-west-mumbai", "purpose": "sale", "type": "apartment,studio"}, 2),
    ("loc_santacruz_west_rent", "Santacruz West Rent", {"location": "santacruz-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_juhu_rent", "Juhu Rent", {"location": "juhu-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_andheri_west_rent", "Andheri West Rent", {"location": "andheri-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 5),
    ("loc_andheri_west_sale", "Andheri West Buy", {"location": "andheri-west-mumbai", "purpose": "sale", "type": "apartment,studio"}, 4),
    ("loc_andheri_east_rent", "Andheri East Rent", {"location": "andheri-east-mumbai", "purpose": "rent", "type": "apartment,studio"}, 4),
    ("loc_versova_rent", "Versova Rent", {"location": "versova-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_worli_rent", "Worli Rent", {"location": "worli-mumbai", "purpose": "rent", "type": "apartment,studio"}, 4),
    ("loc_worli_sale", "Worli Buy", {"location": "worli-mumbai", "purpose": "sale", "type": "apartment,studio"}, 3),
    ("loc_lower_parel_rent", "Lower Parel Rent", {"location": "lower-parel-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_prabhadevi_rent", "Prabhadevi Rent", {"location": "prabhadevi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_dadar_west_rent", "Dadar West Rent", {"location": "dadar-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_matunga_rent", "Matunga Rent", {"location": "matunga-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
    ("loc_colaba_rent", "Colaba Rent", {"location": "colaba-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
    ("loc_byculla_rent", "Byculla Rent", {"location": "byculla-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
    ("loc_wadala_rent", "Wadala Rent", {"location": "wadala-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_powai_rent", "Powai Rent", {"location": "powai-mumbai", "purpose": "rent", "type": "apartment,studio"}, 4),
    ("loc_powai_sale", "Powai Buy", {"location": "powai-mumbai", "purpose": "sale", "type": "apartment,studio"}, 3),
    ("loc_chembur_rent", "Chembur Rent", {"location": "chembur-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_goregaon_west_rent", "Goregaon West Rent", {"location": "goregaon-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_goregaon_east_rent", "Goregaon East Rent", {"location": "goregaon-east-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_malad_west_rent", "Malad West Rent", {"location": "malad-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 4),
    ("loc_malad_east_rent", "Malad East Rent", {"location": "malad-east-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_kandivali_west_rent", "Kandivali West Rent", {"location": "kandivali-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_kandivali_east_rent", "Kandivali East Rent", {"location": "kandivali-east-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_borivali_west_rent", "Borivali West Rent", {"location": "borivali-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_ghatkopar_west_rent", "Ghatkopar West Rent", {"location": "ghatkopar-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_vikhroli_rent", "Vikhroli Rent", {"location": "vikhroli-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
    ("loc_mulund_west_rent", "Mulund West Rent", {"location": "mulund-west-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_mira_road_rent", "Mira Road Rent", {"location": "mira-road-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_vashi_rent", "Vashi Rent", {"location": "vashi-navi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_nerul_rent", "Nerul Rent", {"location": "nerul-navi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_seawoods_rent", "Seawoods Rent", {"location": "seawoods-navi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
    ("loc_kharghar_rent", "Kharghar Rent", {"location": "kharghar-navi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 3),
    ("loc_airoli_rent", "Airoli Rent", {"location": "airoli-navi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
    ("loc_panvel_rent", "Panvel Rent", {"location": "panvel-navi-mumbai", "purpose": "rent", "type": "apartment,studio"}, 2),
]

def _load_json(p, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default

def _save_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

def _extract_property_imgs(item):
    imgs = []
    def _add(u):
        if not isinstance(u, str):
            return
        u = u.strip()
        if not u.startswith("http"):
            return
        low = u.lower()
        if any(bad in low for bad in ("logo", "icon", "avatar", "placeholder", "no-image", "not-available", "badge", ".svg")):
            return
        if u not in imgs:
            imgs.append(u)

    for k in ("image", "cover_image", "thumbnail", "photo", "main_image", "photo_url", "image_url"):
        v = item.get(k)
        if isinstance(v, str):
            _add(v)
        elif isinstance(v, dict):
            _add(v.get("url") or v.get("src") or v.get("large") or v.get("original"))

    for k in ("photos", "images", "media", "gallery", "photo_urls", "image_urls"):
        arr = item.get(k)
        if isinstance(arr, list):
            for el in arr[:8]:
                if isinstance(el, str):
                    _add(el)
                elif isinstance(el, dict):
                    _add(el.get("url") or el.get("src") or el.get("large") or el.get("original") or el.get("photoUrl"))
    return imgs[:5]

def normalize_apish_item(item, fallback_mode="rent", fallback_label=""):
    if not isinstance(item, dict):
        return None
    u = str(item.get("url") or "").strip().split("?")[0].rstrip("/")
    if not u.startswith("http"):
        return None

    purpose_raw = str(item.get("purpose") or fallback_mode).lower().strip()
    mode = "buy" if purpose_raw in ("sale", "buy", "resale") else "rent"

    loc_blob = " ".join(str(x or "") for x in (
        item.get("locality"), item.get("title"), item.get("city"), fallback_label, u
    ))
    det = detect_locality(loc_blob)
    if not det:
        return None

    raw_p = item.get("price") or item.get("price_max") or item.get("price_text")
    price = parse_price(raw_p, mode=mode)
    if not price:
        return None

    lat, lng = item.get("latitude"), item.get("longitude")
    try:
        lat_f, lng_f = float(lat), float(lng)
        if not (18.85 <= lat_f <= 19.42 and 72.75 <= lng_f <= 73.25):
            lat_f, lng_f = None, None
    except Exception:
        lat_f, lng_f = None, None

    soc_raw = str(item.get("society") or "").strip()
    title_raw = str(item.get("title") or "").strip()
    if soc_raw and soc_raw.lower() not in ("none", "null", "na", "n/a", det[0].lower()):
        name = clean_soc_name(soc_raw, det[0])
    elif title_raw:
        name = clean_soc_name(title_raw, det[0])
    else:
        name = f"{det[0]} Flat"

    sq = None
    for ak in ("carpet_sqft", "builtup_sqft", "super_builtup_sqft"):
        av = item.get(ak)
        if av not in (None, "", 0):
            try:
                sq_i = int(float(av))
                if 120 <= sq_i <= 15000:
                    sq = sq_i
                    break
            except Exception:
                pass
    if sq is None and item.get("area_text"):
        m_sq = re.search(r"(\d{3,5})", str(item.get("area_text")))
        if m_sq:
            sq_i = int(m_sq.group(1))
            if 120 <= sq_i <= 15000:
                sq = sq_i

    bhk = item.get("bedrooms")
    if bhk not in (None, ""):
        try:
            bhk = int(float(bhk))
        except Exception:
            bhk = parse_bhk(title_raw)
    else:
        bhk = parse_bhk(title_raw)

    adv = item.get("advertiser") if isinstance(item.get("advertiser"), dict) else {}
    adv_type = str(adv.get("type") or "").lower().strip()
    is_owner = ("owner" in adv_type)

    rera_raw = item.get("rera_id")
    rera_ids = [str(rera_raw).strip()] if isinstance(rera_raw, str) and rera_raw.strip() else (
        [str(x).strip() for x in rera_raw if x] if isinstance(rera_raw, list) else []
    )

    imgs = _extract_property_imgs(item)
    rec = {
        "name": name,
        "locality": det[0],
        "mode": mode,
        "p": price,
        "b": bhk if bhk is not None else 1,
        "sq": sq,
        "s": "99acres",
        "u": u,
        "zb": is_owner,
        "lt": "owner" if is_owner else ("builder" if "builder" in adv_type else "broker"),
        "f": norm_furnishing(item.get("furnishing") or ""),
        "img": imgs[0] if imgs else None,
        "imgs": imgs,
    }
    if lat_f is not None and lng_f is not None:
        rec["lat"] = round(lat_f, 6)
        rec["lng"] = round(lng_f, 6)
    if rera_ids:
        rec["rera_ids"] = rera_ids[:3]
    return rec

def _call_apish_search(params, api_key, timeout=90):
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and v != ""})
    url = f"{API_BASE}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": "BombayHomes/v30",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="ignore")
            return r.status, json.loads(body)
    except urllib.error.HTTPError as he:
        err_body = ""
        try:
            err_body = he.read().decode("utf-8", errors="ignore")[:300]
        except Exception:
            pass
        return he.code, {"success": False, "error": err_body or str(he)}

def _save_raw_gz(slice_id, page_no, payload):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_p = RAW_DIR / f"{slice_id}_p{page_no}.json.gz"
    with gzip.open(out_p, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)

def load_cached_apish_99acres():
    return _load_json(CACHE_PATH, {}).get("records") or []

def reparse_raw_archive():
    if not RAW_DIR.exists():
        print("[APISH 99] No raw archive directory yet.")
        return []
    by_u = {r["u"]: r for r in load_cached_apish_99acres() if isinstance(r, dict) and r.get("u")}
    files = sorted(RAW_DIR.glob("*.json.gz"))
    parsed = 0
    for fp in files:
        try:
            with gzip.open(fp, "rt", encoding="utf-8") as f:
                blob = json.load(f)
            purpose = blob.get("purpose") or ("sale" if "_sale" in fp.name else "rent")
            label = blob.get("heading") or fp.stem
            for it in (blob.get("results") or []):
                rec = normalize_apish_item(it, fallback_mode=purpose, fallback_label=label)
                if rec:
                    by_u[rec["u"]] = rec
                    parsed += 1
        except Exception as e:
            print(f"  [APISH RAW WARN] {fp.name}: {e}")
    recs = list(by_u.values())
    _save_json(CACHE_PATH, {"updated": int(time.time()), "count": len(recs), "records": recs})
    print(f"[APISH 99 REPARSE] Parsed {parsed:,} items from {len(files)} .json.gz files -> {len(recs):,} unique cached listings (0 credits)")
    return recs

def sync_apish_99acres(max_calls=28, incremental=True, reset_queue=False, fresh=False):
    api_key = (os.environ.get("APISH_KEY") or "").strip()
    if not api_key:
        cached = load_cached_apish_99acres()
        print(f"[APISH 99] APISH_KEY not set; returning {len(cached):,} cached listings (0 calls).")
        return cached

    by_u = {r["u"]: r for r in load_cached_apish_99acres() if isinstance(r, dict) and r.get("u")}
    reg = _load_json(REGISTRY_PATH, {})
    qstate = {"cursor": 0, "dead_slices": [], "total_credits": 0} if reset_queue else _load_json(
        QUEUE_PATH, {"cursor": 0, "dead_slices": [], "total_credits": 0}
    )
    dead_slices = set(qstate.get("dead_slices") or [])
    cursor = int(qstate.get("cursor") or 0) % len(SLICE_SPECS)

    calls_made, credits_spent, new_cnt, upd_cnt, early_stops, slices_visited = 0, 0, 0, 0, 0, 0

    while calls_made < max_calls and slices_visited < len(SLICE_SPECS):
        slice_id, label, base_params, max_pages = SLICE_SPECS[cursor]
        cursor = (cursor + 1) % len(SLICE_SPECS)
        slices_visited += 1

        if slice_id in dead_slices:
            continue

        fallback_mode = "buy" if base_params.get("purpose") == "sale" else "rent"
        for pg_no in range(1, max_pages + 1):
            if calls_made >= max_calls:
                break
            params = dict(base_params)
            params["page"] = pg_no
            if fresh:
                params["fresh"] = "true"

            status, payload = _call_apish_search(params, api_key)
            calls_made += 1

            if status in (401, 402, 429):
                print(f"  [APISH 99 STOP] HTTP {status} ({str(payload.get('error', ''))[:120]}). Stopping cleanly.")
                calls_made = max_calls
                break
            if status == 404:
                print(f"  [APISH 99 404] {label} ({slice_id}) p{pg_no} returned 404; marking slice dead.")
                if pg_no == 1:
                    dead_slices.add(slice_id)
                break
            if status != 200 or not isinstance(payload, dict):
                print(f"  [APISH 99 WARN] {label} p{pg_no} HTTP {status}: {str(payload)[:120]}")
                break

            c_used = int(payload.get("credits_used") or 0)
            credits_spent += c_used
            _save_raw_gz(slice_id, pg_no, payload)

            results = payload.get("results") or []
            if not results:
                break

            pg_valid, pg_unchanged, pg_new = 0, 0, 0
            for it in results:
                rec = normalize_apish_item(it, fallback_mode=fallback_mode, fallback_label=label)
                if not rec:
                    continue
                pg_valid += 1
                u = rec["u"]
                prev_rec = by_u.get(u)
                prev_reg = reg.get(u)
                known_p = prev_rec.get("p") if prev_rec else (
                    prev_reg[2] if isinstance(prev_reg, list) and len(prev_reg) >= 3 else None
                )
                if known_p is not None and int(known_p) == int(rec["p"]):
                    pg_unchanged += 1
                else:
                    if prev_rec:
                        upd_cnt += 1
                    else:
                        new_cnt += 1
                        pg_new += 1
                by_u[u] = rec

            print(
                f"  [APISH 99] {label} p{pg_no}/{payload.get('total_pages') or '?'} | "
                f"raw={len(results)} valid={pg_valid} new={pg_new} unchanged={pg_unchanged} | credits={c_used}"
            )

            if incremental and pg_valid >= 10 and (pg_unchanged / pg_valid) >= 0.85:
                early_stops += 1
                print(f"    -> EARLY STOP on {label} (85%+ already known & unchanged)")
                break
            if not payload.get("next_page"):
                break
            time.sleep(0.35)

        recs_now = list(by_u.values())
        _save_json(CACHE_PATH, {"updated": int(time.time()), "count": len(recs_now), "records": recs_now})
        _save_json(QUEUE_PATH, {
            "updated": int(time.time()),
            "cursor": cursor,
            "dead_slices": sorted(dead_slices),
            "total_credits": int(qstate.get("total_credits") or 0) + credits_spent,
        })

    recs = list(by_u.values())
    print(
        f"[APISH 99 SUMMARY] Calls={calls_made} | Credits={credits_spent} | "
        f"NEW={new_cnt:,} | Price-Updated={upd_cnt:,} | Early-Stops={early_stops} | "
        f"Next cursor={cursor}/{len(SLICE_SPECS)} | Total Cached={len(recs):,}"
    )
    return recs

def publish_cached_to_shards():
    recs = load_cached_apish_99acres()
    if not recs:
        print("[APISH 99 PUBLISH] Cache empty.")
        return {}
    data = load_index()
    socs = data.get("societies") or []
    au, asoc = merge_records_into_societies(socs, recs)
    enrich_transit_context(socs)
    cleaned_socs, _ = filter_and_track_societies(socs)
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["societies"] = cleaned_socs
    data["count"] = len(cleaned_socs)
    sh = save_sharded_index(data, max_shard_bytes=3_800_000)
    print(f"[APISH 99 PUBLISH] +{au:,} units (+{asoc:,} bldgs) | Shards: {sh['rent_shards']}R+{sh['buy_shards']}B ({sh['total_mb']} MB)")
    return sh

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=28, help="Max API calls (default 28/day fits 1k/mo free tier)")
    ap.add_argument("--full", action="store_true", help="Disable incremental 85% early-stop")
    ap.add_argument("--reset-queue", action="store_true", help="Reset slice cursor to 0")
    ap.add_argument("--fresh", action="store_true", help="Bypass api.sh cache")
    ap.add_argument("--reparse-raw", action="store_true", help="Re-parse saved data/raw_99acres/*.json.gz offline (0 credits)")
    ap.add_argument("--publish", action="store_true", help="Also merge cache into sharded index immediately")
    args = ap.parse_args()

    if args.reparse_raw:
        reparse_raw_archive()
    else:
        sync_apish_99acres(
            max_calls=args.max_calls,
            incremental=not args.full,
            reset_queue=args.reset_queue,
            fresh=args.fresh,
        )
    if args.publish:
        publish_cached_to_shards()
