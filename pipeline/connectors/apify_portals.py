import argparse, json, os, re, sys, time, urllib.error, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.v19_common import detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name

CACHE_PATH = ROOT / "data/apify_cache.json"
_APIFY_EXHAUSTED = set()

def _get_apify_tokens():
    out = []
    for env_k in ("APIFY_TOKEN_1", "APIFY_TOKEN_2", "APIFY_TOKEN_3", "APIFY_TOKEN_4", "APIFY_TOKEN_5", "APIFY_TOKEN"):
        val = (os.environ.get(env_k) or "").strip()
        if val and val not in out:
            out.append(val)
    return out

def _api_get(url, timeout=45):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))

def _call_apify_actor(actor_id, payload, token, timeout=900):
    if (os.environ.get("APISH_KEY") or os.environ.get("SKIP_APIFY_99ACRES")) and ("99acres" in str(actor_id).lower() or "99acres" in json.dumps(payload, ensure_ascii=False).lower()):
        print(f"  [apify] Skipping 99acres actor ({actor_id}) - api.sh owns 99acres; saving Apify credits for Housing.com")
        return []
    cands = [t for t in _get_apify_tokens() if t not in _APIFY_EXHAUSTED]
    if token and token not in cands and token not in _APIFY_EXHAUSTED:
        cands.append(token)
    if not cands:
        raise RuntimeError("All configured Apify tokens are exhausted or missing")
    apify_base = "https:" + "//api.apify.com/v2"
    body = json.dumps(payload).encode("utf-8")
    last_err = None
    for tok in cands:
        tok_tag = tok[:8] + "..."
        try:
            start_url = f"{apify_base}/actors/{actor_id}/runs?token={urllib.parse.quote(tok)}"
            req = urllib.request.Request(start_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=45) as r:
                run_data = json.loads(r.read().decode("utf-8", errors="ignore")).get("data") or {}
            rid = run_data.get("id")
            ds_id = run_data.get("defaultDatasetId")
            if not rid or not ds_id:
                raise RuntimeError(f"Apify run did not start cleanly: {run_data}")
            t0 = time.time()
            while time.time() - t0 < timeout:
                time.sleep(6)
                st_data = _api_get(f"{apify_base}/actor-runs/{rid}?token={urllib.parse.quote(tok)}", timeout=30).get("data") or {}
                status = st_data.get("status")
                if status == "SUCCEEDED":
                    items = _api_get(f"{apify_base}/datasets/{ds_id}/items?token={urllib.parse.quote(tok)}&clean=true&limit=5000", timeout=90)
                    try:
                        import gzip as _gz
                        _rdir = ROOT / "data/raw_housing"
                        _rdir.mkdir(parents=True, exist_ok=True)
                        with _gz.open(_rdir / f"apify_{rid}.json.gz", "wt", encoding="utf-8") as _gf:
                            json.dump(items, _gf, separators=(",", ":"), ensure_ascii=False)
                    except Exception:
                        pass
                    return items
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    msg = str(st_data.get("statusMessage") or "")
                    if any(w in msg.lower() for w in ("limit", "usage", "credit", "payment", "quota")):
                        _APIFY_EXHAUSTED.add(tok)
                        print(f"  [apify] Token {tok_tag} hit usage limit ({status}: {msg[:80]}) -> failing over to next key...")
                        last_err = RuntimeError(f"Token exhausted: {msg}")
                        break
                    raise RuntimeError(f"Apify run {rid} ended with status={status} {msg}")
            else:
                raise TimeoutError(f"Apify run {rid} timed out after {timeout}s")
        except urllib.error.HTTPError as he:
            err_txt = ""
            try:
                err_txt = he.read().decode("utf-8", errors="ignore")[:160]
            except Exception:
                pass
            if he.code in (401, 402, 403, 429):
                _APIFY_EXHAUSTED.add(tok)
                print(f"  [apify] Token {tok_tag} returned HTTP {he.code} ({err_txt}) -> failing over to next key...")
                last_err = he
                continue
            raise
    raise RuntimeError(f"All Apify tokens failed: {last_err}")

def _first_str(obj, keys):
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _find_first_url(obj):
    u = _first_str(obj, (
        "url", "listing_url", "property_url", "detail_url", "page_url", "source_url", "canonical_url",
        "propertyUrl", "listingUrl", "detailUrl", "canonicalUrl", "link", "href", "pageUrl"
    ))
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        blob = json.dumps(obj, ensure_ascii=False).lower()
        return ("https://www.99acres.com" if "99acres" in blob else "https://housing.com") + u
    for v in obj.values():
        if isinstance(v, str) and (v.startswith("https://housing.com") or v.startswith("https://www.99acres.com")):
            return v.strip()
    lid = obj.get("listing_id")
    if lid:
        lt = str(obj.get("listing_type") or "").lower()
        pt = str(obj.get("property_type") or "").lower()
        if lt == "buy":
            return f"https://housing.com/in/buy/projects/page/{lid}" if "project" in pt else f"https://housing.com/in/buy/resale/page/{lid}"
        return f"https://housing.com/in/rent/page/{lid}"
    return ""

def _find_imgs(obj):
    out = []
    def _add(u):
        if isinstance(u, str) and "housingcdn.com" in u and "/version/" in u: u = u.replace("/version/", "/fs/")
        if isinstance(u, str) and u.startswith("http") and "logo" not in u.lower() and u not in out:
            out.append(u)
    for k in ("coverImage", "cover_image", "mainImage", "main_image", "imageUrl", "image_url", "photo_url", "thumbnail", "thumbnail_url", "image", "photo"):
        v = obj.get(k)
        if isinstance(v, str): _add(v)
        elif isinstance(v, dict): _add(_first_str(v, ("url", "src", "large", "original")))
    for k in ("images", "photos", "image_urls", "photo_urls", "gallery", "media"):
        arr = obj.get(k)
        if isinstance(arr, list):
            for item in arr[:8]:
                if isinstance(item, str): _add(item)
                elif isinstance(item, dict): _add(_first_str(item, ("url", "src", "large", "original", "imageUrl")))
    if not out:
        for v in obj.values():
            if isinstance(v, str):
                m = re.search(r"https?://[^\"'\s]+?\.(?:jpg|jpeg|webp|png)", v, re.I)
                if m: _add(m.group(0))
    return out[:5]

def _find_img(obj):
    for k in ("coverImage", "cover_image", "mainImage", "main_image", "imageUrl", "image_url", "photo_url", "thumbnail", "thumbnail_url", "image", "photo"):
        v = obj.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, dict):
            u = _first_str(v, ("url", "src", "large", "original"))
            if u.startswith("http"):
                return u
    for k in ("images", "photos", "image_urls", "photo_urls", "gallery", "media"):
        arr = obj.get(k)
        if isinstance(arr, list) and arr:
            first = arr[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                u = _first_str(first, ("url", "src", "large", "original", "imageUrl"))
                if u.startswith("http"):
                    return u
    for v in obj.values():
        if isinstance(v, str):
            m = re.search(r"https?://[^\"'\s]+?\.(?:jpg|jpeg|webp|png)", v, re.I)
            if m and "logo" not in m.group(0).lower():
                return m.group(0)
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
    elif "housing.com" in low_u or "housing" in src or it.get("listing_id"):
        src = "housing"
    if not u.startswith("http") or src not in ("housing", "99acres"):
        return None

    loc_parts = [
        it.get("locality"), it.get("locality_name"), it.get("localityName"), it.get("subLocality"),
        it.get("location"), it.get("address"), it.get("suburb"),
        it.get("neighbourhood"), it.get("title"), it.get("subtitle"), it.get("name"), u
    ]
    det = detect_locality(" ".join(str(x or "") for x in loc_parts))
    if not det:
        return None

    mode = mode_hint
    lt_raw = str(it.get("listing_type") or it.get("listingType") or it.get("category") or "").lower()
    if "/buy/" in low_u or "for-sale" in low_u or lt_raw in ("buy", "sale", "resale"):
        mode = "buy"
    elif "/rent/" in low_u or "for-rent" in low_u or lt_raw == "rent":
        mode = "rent"

    raw_p = None
    for pk in ("priceInr", "price", "rent", "monthly_rent", "monthlyRent", "price_label", "displayPrice", "formattedPrice", "minPrice", "priceMinInr", "priceText"):
        if it.get(pk) not in (None, "", 0, "None"):
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

    title_raw = _first_str(it, ("society", "society_name", "societyName", "project_name", "projectName", "building_name", "buildingName", "title", "name", "heading"))
    seller = str(it.get("seller_type") or it.get("posted_by") or it.get("sellerType") or it.get("postedBy") or it.get("agentType") or it.get("ownerType") or "").lower()
    is_owner = "owner" in seller
    coords = it.get("coords") or it.get("coordinates") or it.get("geo") or {}
    lat = it.get("latitude") or it.get("lat") or (coords.get("lat") or coords.get("latitude") if isinstance(coords, dict) else None)
    lng = it.get("longitude") or it.get("lng") or it.get("lon") or (coords.get("lng") or coords.get("lon") or coords.get("longitude") if isinstance(coords, dict) else None)
    sq_raw = it.get("area_sqft") or it.get("carpet_area") or it.get("carpetAreaSqft") or it.get("carpetArea") or it.get("areaSqft") or it.get("builtUpArea") or it.get("area") or it.get("size")
    sq_m = re.search(r"(\d{3,4})", str(sq_raw or ""))
    rera = it.get("rera_id") or it.get("reraId") or it.get("rera") or it.get("reraIds")
    rera_list = rera if isinstance(rera, list) else ([rera] if isinstance(rera, str) and rera else [])

    bhk_raw = it.get("bhk") or it.get("bedrooms") or it.get("config") or it.get("configurations") or it.get("subtitle") or it.get("amenities") or title_raw

    return {
        "name": clean_soc_name(title_raw or f"{det[0]} Flat", det[0]),
        "locality": det[0], "mode": mode, "p": price,
        "b": parse_bhk(bhk_raw),
        "sq": int(sq_m.group(1)) if sq_m else None,
        "s": src, "u": u.split("?")[0], "zb": is_owner,
        "lt": "owner" if is_owner else "broker",
        "f": norm_furnishing(it.get("furnishing") or it.get("furnishing_type") or it.get("furnishingType") or it.get("furnished")),
        "img": (_find_imgs(it)[0] if _find_imgs(it) else None), "imgs": _find_imgs(it),
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
    print(f"  [apify recover] Found {len(runs)} recent run(s) (0 credits used).")
    fresh = []
    for r in runs:
        rid, ds_id = r.get("id"), r.get("defaultDatasetId")
        if not ds_id:
            continue
        try:
            items = _api_get(f"https://api.apify.com/v2/datasets/{ds_id}/items?token={urllib.parse.quote(token)}&clean=true&limit=5000")
        except Exception as e:
            print(f"    Run {rid} read error: {e}")
            continue
        if not isinstance(items, list):
            continue
        ok = 0
        for it in items:
            rec = _norm_any_item(it)
            if rec:
                fresh.append(rec)
                ok += 1
        keys_str = list(items[0].keys()) if (items and isinstance(items[0], dict)) else []
        print(f"    Run {rid} | raw={len(items)} -> clean Mumbai={ok} | keys={keys_str}")
    if fresh:
        merged = _save_merged_cache(fresh)
        print(f"  [apify recover] Cache now has {len(merged)} total clean Mumbai records!")
        return merged
    return load_cached_apify()

def sync_apify(rent_limit=250, buy_limit=125, sources=("housing", "99acres"), force=False):
    tokens = _get_apify_tokens()
    token = tokens[0] if tokens else ""
    existing = load_cached_apify()
    if not token:
        print(f"  [apify] No APIFY_TOKEN(_1/2/3) set -> using {len(existing)} cached records")
        return existing
    print(f"  [apify] Loaded {len(tokens)} Apify token(s) in failover pool")

    last_ts = 0
    if CACHE_PATH.exists():
        try: last_ts = json.loads(CACHE_PATH.read_text(encoding="utf-8")).get("last_sync", 0)
        except Exception: pass
    if os.environ.get("FORCE_APIFY_REFRESH") == "1":
        force = True
    if os.environ.get("APIFY_RENT_LIMIT"):
        rent_limit = int(os.environ["APIFY_RENT_LIMIT"])
    if os.environ.get("APIFY_BUY_LIMIT"):
        buy_limit = int(os.environ["APIFY_BUY_LIMIT"])
    if not force and existing and (time.time() - last_ts) < 6 * 86400:
        print(f"  [apify] Cache fresh (<6d) -> reusing {len(existing)} records")
        return existing

    fresh = []
    if "housing" in sources:
        h_cities = [c.strip() for c in (os.environ.get("APIFY_HOUSING_CITIES") or "Mumbai").split(",") if c.strip()]
        for h_city in h_cities:
            city_div = 1 if h_city.lower() == "mumbai" else 2
            for mode, lim in (("rent", rent_limit // city_div), ("buy", buy_limit // city_div)):
                if lim <= 0: continue
                try:
                    rows = _call_apify_actor(
                        "themineworks~housing-com-scraper",
                        {"city": h_city, "listingType": mode, "maxResults": lim, "proxyConfiguration": {"useApifyProxy": True}},
                        token,
                    )
                    n_ok = 0
                    for r in (rows or []):
                        rec = _norm_any_item(r, source_hint="housing", mode_hint=mode)
                        if rec:
                            fresh.append(rec)
                            n_ok += 1
                    print(f"  [apify] Housing.com {h_city} ({mode}, lim={lim}): kept {n_ok}/{len(rows or [])} clean listings")
                    if fresh:
                        _save_merged_cache(fresh)
                except Exception as e:
                    print(f"  [apify] Housing.com {h_city} ({mode}) error: {e}")

    if "99acres" in sources:
        for mode, lim in (("rent", rent_limit), ("buy", buy_limit)):
            if lim <= 0: continue
            try:
                rows = _call_apify_actor(
                    "datascrapers~99acres-scraper",
                    {"searchQueries": ["Bandra West Mumbai", "Khar West Mumbai", "Andheri West Mumbai", "Powai Mumbai", "Worli Mumbai", "Lower Parel Mumbai", "Goregaon West Mumbai", "Malad West Mumbai", "Chembur Mumbai", "Dadar West Mumbai", "Thane West", "Navi Mumbai"], "category": mode, "segment": "residential", "maxItems": lim},
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
