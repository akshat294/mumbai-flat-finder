import argparse, json, os, re, sys, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.v19_common import detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name

CACHE_PATH = ROOT / "data/apify_cache.json"

def _api_get(url, timeout=45):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))

def _call_apify_actor(actor_id, payload, token, timeout=240):
    url = f"https://api.apify.com/v2/actors/{actor_id}/run-sync-get-dataset-items?token={urllib.parse.quote(token)}&format=json&clean=true"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))

def _first_str(obj, keys):
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _find_first_url(obj):
    u = _first_str(obj, ("url", "propertyUrl", "listingUrl", "detailUrl", "canonicalUrl", "link", "href", "pageUrl"))
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        blob = json.dumps(obj, ensure_ascii=False).lower()
        if "99acres" in blob:
            return "https://www.99acres.com" + u
        if "housing" in blob:
            return "https://housing.com" + u
    return ""

def _find_img(obj):
    for k in ("coverImage", "mainImage", "imageUrl", "thumbnail", "image", "photo"):
        v = obj.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, dict):
            u = _first_str(v, ("url", "src", "large", "original"))
            if u.startswith("http"):
                return u
    for k in ("images", "photos", "gallery", "media"):
        arr = obj.get(k)
        if isinstance(arr, list) and arr:
            first = arr[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                u = _first_str(first, ("url", "src", "large", "original", "imageUrl"))
                if u.startswith("http"):
                    return u
    return None

def _norm_any_item(it, source_hint="", mode_hint="rent"):
    if not isinstance(it, dict):
        return None
    u = _find_first_url(it)
    blob = json.dumps(it, ensure_ascii=False)
    low_u = u.lower()
    src = source_hint
    if "99acres" in low_u or "99acres" in blob.lower():
        src = "99acres"
    elif "housing.com" in low_u or "housing" in src:
        src = "housing"
    if not u.startswith("http") or src not in ("housing", "99acres"):
        return None

    loc_parts = [
        it.get("locality"), it.get("localityName"), it.get("subLocality"),
        it.get("location"), it.get("address"), it.get("suburb"),
        it.get("neighbourhood"), it.get("title"), it.get("name"), u
    ]
    det = detect_locality(" ".join(str(x or "") for x in loc_parts))
    if not det:
        return None

    mode = mode_hint
    if "/buy/" in low_u or "for-sale" in low_u or str(it.get("listingType") or it.get("category") or "").lower() in ("buy", "sale", "resale"):
        mode = "buy"
    elif "/rent/" in low_u or "for-rent" in low_u or str(it.get("listingType") or it.get("category") or "").lower() == "rent":
        mode = "rent"

    raw_p = None
    for pk in ("priceInr", "price", "rent", "monthlyRent", "displayPrice", "formattedPrice", "minPrice", "priceMinInr", "priceText"):
        if it.get(pk) not in (None, "", 0):
            raw_p = it.get(pk)
            break
    if isinstance(raw_p, dict):
        raw_p = raw_p.get("value") or raw_p.get("minValue") or raw_p.get("displayValue") or raw_p.get("range")
    price = parse_price(raw_p, mode=mode)
    if not price:
        alt = "buy" if mode == "rent" else "rent"
        price = parse_price(raw_p, mode=alt)
        if price:
            mode = alt
    if not price:
        return None

    title_raw = _first_str(it, ("society", "societyName", "projectName", "buildingName", "title", "name", "heading"))
    seller = str(it.get("sellerType") or it.get("postedBy") or it.get("agentType") or it.get("ownerType") or "").lower()
    is_owner = "owner" in seller
    coords = it.get("coords") or it.get("coordinates") or it.get("geo") or {}
    lat = it.get("latitude") or it.get("lat") or (coords.get("lat") or coords.get("latitude") if isinstance(coords, dict) else None)
    lng = it.get("longitude") or it.get("lng") or it.get("lon") or (coords.get("lng") or coords.get("lon") or coords.get("longitude") if isinstance(coords, dict) else None)
    sq_raw = it.get("carpetAreaSqft") or it.get("carpetArea") or it.get("areaSqft") or it.get("builtUpArea") or it.get("area") or it.get("size")
    sq_m = re.search(r"(\d{3,4})", str(sq_raw or ""))
    rera = it.get("reraId") or it.get("rera") or it.get("reraIds")
    rera_list = rera if isinstance(rera, list) else ([rera] if isinstance(rera, str) and rera else [])

    return {
        "name": clean_soc_name(title_raw or f"{det[0]} Flat", det[0]),
        "locality": det[0], "mode": mode, "p": price,
        "b": parse_bhk(it.get("bhk") or it.get("bedrooms") or it.get("config") or it.get("configurations") or title_raw),
        "sq": int(sq_m.group(1)) if sq_m else None,
        "s": src, "u": u.split("?")[0], "zb": is_owner,
        "lt": "owner" if is_owner else "broker",
        "f": norm_furnishing(it.get("furnishing") or it.get("furnishingType") or it.get("furnished")),
        "img": _find_img(it),
        "lat": lat, "lng": lng,
        "rera_ids": rera_list,
    }

def load_cached_apify():
    if not CACHE_PATH.exists():
        return []
    try:
        blob = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        cutoff = time.time() - 28 * 86400
        return [x for x in (blob.get("records") or []) if (x.get("_ts") or 0) >= cutoff]
    except Exception:
        return []

def _save_merged_cache(fresh):
    existing = load_cached_apify()
    now_ts = int(time.time())
    by_url = {r["u"]: r for r in existing if r.get("u")}
    for r in fresh:
        r["_ts"] = now_ts
        by_url[r["u"]] = r
    merged = list(by_url.values())
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({"last_sync": now_ts, "records": merged}, ensure_ascii=False), encoding="utf-8")
    return merged

def recover_recent_runs():
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        print("  [apify] Set $env:APIFY_TOKEN first.")
        return []
    runs_resp = _api_get(f"https://api.apify.com/v2/actor-runs?token={urllib.parse.quote(token)}&desc=true&limit=10")
    runs = (runs_resp.get("data") or {}).get("items") or []
    print(f"  [apify recover] Found {len(runs)} recent run(s) in your Apify account (0 credits used).")
    fresh = []
    for r in runs:
        rid, aid, status, ds_id = r.get("id"), r.get("actId"), r.get("status"), r.get("defaultDatasetId")
        print(f"    Run {rid} | act={aid} | status={status} | dataset={ds_id}")
        if not ds_id:
            continue
        try:
            items = _api_get(f"https://api.apify.com/v2/datasets/{ds_id}/items?token={urllib.parse.quote(token)}&clean=true&limit=600")
        except Exception as e:
            print(f"      -> dataset read error: {e}")
            continue
        if not isinstance(items, list):
            continue
        print(f"      -> raw items in dataset: {len(items)}")
        if items and isinstance(items[0], dict):
            sample = {k: str(v)[:80] for k, v in list(items[0].items())[:14]}
            print(f"      -> sample item[0]: {sample}")
            ok = 0
            for it in items:
                rec = _norm_any_item(it)
                if rec:
                    fresh.append(rec)
                    ok += 1
            print(f"      -> normalized clean Mumbai records: {ok}")
        elif len(items) == 0 and aid:
            try:
                act_info = _api_get(f"https://api.apify.com/v2/acts/{aid}?token={urllib.parse.quote(token)}")
                d = act_info.get("data") or {}
                print(f"      -> actor: {d.get('username')}/{d.get('name')}")
                bid = ((d.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
                if bid:
                    binfo = _api_get(f"https://api.apify.com/v2/actor-builds/{bid}?token={urllib.parse.quote(token)}")
                    in_schema = (binfo.get("data") or {}).get("inputSchema")
                    if isinstance(in_schema, str):
                        in_schema = json.loads(in_schema)
                    props = (in_schema or {}).get("properties") or {}
                    print(f"      -> expected input keys: {list(props.keys())[:15]}")
            except Exception as e:
                print(f"      -> schema inspect skipped: {e}")
    if fresh:
        merged = _save_merged_cache(fresh)
        print(f"  [apify recover] Recovered {len(fresh)} records -> cache now has {len(merged)} records!")
        return merged
    return load_cached_apify()

def sync_apify(rent_limit=300, buy_limit=200, sources=("housing", "99acres"), force=False):
    token = os.environ.get("APIFY_TOKEN", "").strip()
    existing = load_cached_apify()
    if not token:
        print(f"  [apify] APIFY_TOKEN not set -> using {len(existing)} cached records")
        return existing

    last_ts = 0
    if CACHE_PATH.exists():
        try: last_ts = json.loads(CACHE_PATH.read_text(encoding="utf-8")).get("last_sync", 0)
        except Exception: pass
    if not force and existing and (time.time() - last_ts) < 6 * 86400:
        print(f"  [apify] Cache fresh (<6d) -> reusing {len(existing)} records")
        return existing

    fresh = []
    if "housing" in sources:
        for mode, lim in (("rent", rent_limit), ("buy", buy_limit)):
            if lim <= 0: continue
            try:
                rows = _call_apify_actor(
                    "themineworks~housing-com-scraper",
                    {"city": "Mumbai", "listingType": mode, "maxResults": lim, "proxyConfiguration": {"useApifyProxy": True}},
                    token,
                )
                n_ok = 0
                for r in (rows or []):
                    rec = _norm_any_item(r, source_hint="housing", mode_hint=mode)
                    if rec:
                        fresh.append(rec)
                        n_ok += 1
                print(f"  [apify] Housing.com ({mode}): kept {n_ok}/{len(rows or [])} clean Mumbai listings")
            except Exception as e:
                print(f"  [apify] Housing.com ({mode}) error: {e}")

    if "99acres" in sources:
        for mode, lim in (("rent", rent_limit), ("buy", buy_limit)):
            if lim <= 0: continue
            try:
                rows = _call_apify_actor(
                    "datascrapers~99acres-scraper",
                    {"searchQueries": ["Mumbai"], "category": mode, "segment": "residential", "maxItems": lim},
                    token,
                )
                n_ok = 0
                for r in (rows or []):
                    rec = _norm_any_item(r, source_hint="99acres", mode_hint=mode)
                    if rec:
                        fresh.append(rec)
                        n_ok += 1
                print(f"  [apify] 99acres ({mode}): kept {n_ok}/{len(rows or [])} clean Mumbai listings")
            except Exception as e:
                print(f"  [apify] 99acres ({mode}) error: {e}")

    return _save_merged_cache(fresh)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rent", type=int, default=300)
    ap.add_argument("--buy", type=int, default=200)
    ap.add_argument("--sources", default="housing,99acres")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--recover-runs", action="store_true")
    args = ap.parse_args()
    if args.recover_runs:
        recs = recover_recent_runs()
    else:
        recs = sync_apify(args.rent, args.buy, tuple(args.sources.split(",")), force=args.force)
    if recs and not args.recover_runs:
        from pipeline.post_build_v18 import run as run_post_build
        run_post_build()
