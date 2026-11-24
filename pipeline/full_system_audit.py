import gzip, json, math, random, re, time, traceback, urllib.parse, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(".")
out = []
def log(s=""):
    print(s)
    out.append(str(s))

def hav_km(a1, o1, a2, o2):
    r = 6371.0
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, dl = math.radians(a2 - a1), math.radians(o2 - o1)
    return 2 * r * math.asin(math.sqrt(math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))

def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, round((time.time() - t0) * 1000), json.loads(body)
    except Exception as e:
        return -1, round((time.time() - t0) * 1000), {"error": str(e)[:120]}

def http_probe_url(url, timeout=10):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-IN,en;q=0.9",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(160000)
            return r.status, len(data), round((time.time() - t0) * 1000), r.headers.get("Content-Type", "")
    except Exception as e:
        return -1, 0, round((time.time() - t0) * 1000), str(e)[:80]

try:
    man = json.loads((ROOT / "web/public/data/manifest.json").read_text(encoding="utf-8-sig"))
    rent_socs, buy_socs = [], []
    for sf in (man.get("rent_shards") or []):
        p = ROOT / "web/public/data" / sf
        if p.exists():
            b = json.loads(p.read_text(encoding="utf-8-sig"))
            rent_socs.extend(b if isinstance(b, list) else (b.get("societies") or []))
    for sf in (man.get("buy_shards") or []):
        p = ROOT / "web/public/data" / sf
        if p.exists():
            b = json.loads(p.read_text(encoding="utf-8-sig"))
            buy_socs.extend(b if isinstance(b, list) else (b.get("societies") or []))

    all_socs = rent_socs + buy_socs
    log("====================================================================")
    log("BOMBAY HOMES - FULL ARCHITECTURE DIAGNOSTIC AUDIT")
    log(f"Rent entries: {len(rent_socs):,} | Buy entries: {len(buy_socs):,} | Total: {len(all_socs):,}")
    log("====================================================================")

    # --- LAYER 1: MEDIA, RESOLUTION, CLUTTER & MULTI-UNIT MIXING ---
    log("\n=== LAYER 1: MEDIA, RESOLUTION, CLUTTER & MULTI-UNIT MIXING ===")
    by_src_photos = defaultdict(Counter)
    lowres_counts = Counter()
    multi_unit_socs = 0
    multi_unit_units_with_own_imgs = 0
    multi_unit_total_units = 0
    sample_portal_urls = {}
    sample_img_urls = defaultdict(list)

    for s in rent_socs:
        us = s.get("units_rent") or []
        if not us:
            continue
        src = us[0].get("s") or "?"
        imgs = []
        if s.get("thumb"):
            imgs.append(s["thumb"])
        for p in (s.get("photos") or []):
            if p and p not in imgs:
                imgs.append(p)
        n = len(imgs)
        by_src_photos[src]["0" if n == 0 else ("1" if n == 1 else ("2-3" if n <= 3 else "4+"))] += 1
        if src not in sample_portal_urls:
            u0 = next((u.get("u") for u in us if u.get("u")), None)
            if u0:
                sample_portal_urls[src] = (s.get("name"), u0, n)
        if src == "99acres" and n == 0 and "99acres_0photo" not in sample_portal_urls:
            u0 = next((u.get("u") for u in us if u.get("u")), None)
            if u0:
                sample_portal_urls["99acres_0photo"] = (s.get("name"), u0, 0)

        for im in imgs:
            if not isinstance(im, str):
                continue
            if len(sample_img_urls[src]) < 4 and im not in sample_img_urls[src]:
                sample_img_urls[src].append(im)
            if "Photo_h180_w240" in im or "_180_240." in im:
                lowres_counts["mb_180x240_tiny"] += 1
            elif "Photo_h310_w462" in im:
                lowres_counts["mb_310x462_small"] += 1
            if "imagecdn.99acres.com" in im and re.search(r"/\d+T-\d+\.", im):
                lowres_counts["99acres_T_thumb_only"] += 1
            if "images.nobroker.in" in im and "_medium." in im:
                lowres_counts["nb_medium_only"] += 1
            if "housingcdn.com" in im and "/version/" in im:
                lowres_counts["housing_version_unupgraded"] += 1

        if len(us) >= 2:
            multi_unit_socs += 1
            multi_unit_total_units += len(us)
            multi_unit_units_with_own_imgs += sum(1 for u in us if u.get("img") or u.get("imgs"))

    for src, cnts in sorted(by_src_photos.items()):
        tot = sum(cnts.values())
        log(f"  [{src:11s}] total={tot:5d} | 0={cnts['0']:4d} | 1={cnts['1']:4d} | 2-3={cnts['2-3']:4d} | 4+={cnts['4+']:4d}")
    log(f"  Low-res image URLs still in Rent shards: {dict(lowres_counts)}")
    log(f"  Multi-unit Rent societies: {multi_unit_socs:,} ({multi_unit_total_units:,} units; {multi_unit_units_with_own_imgs:,} have unit-level img)")

    # --- LAYER 2: PRICING, DEAL-BADGE MATH & MISSING SPECS ---
    log("\n=== LAYER 2: PRICING, DEAL-BADGE MATH & MISSING SPECS ===")
    price_issues = Counter()
    missing_specs = defaultdict(Counter)
    deal_skew_examples = []
    loc_bhk_prices = defaultdict(list)
    for s in rent_socs:
        loc = s.get("locality") or ""
        for u in (s.get("units_rent") or []):
            p, b = u.get("p") or 0, u.get("b")
            if p > 0 and b is not None:
                loc_bhk_prices[(loc, int(float(b)))].append(p)
    med_bhk = {k: sorted(v)[len(v)//2] for k, v in loc_bhk_prices.items() if len(v) >= 5}

    for s in rent_socs:
        us = s.get("units_rent") or []
        pr = s.get("pricing") or {}
        ps = [u.get("p") for u in us if u.get("p")]
        if ps and pr.get("rent_min") and pr["rent_min"] != min(ps):
            price_issues["rent_min_mismatch_units"] += 1
        deal = s.get("deal")
        if isinstance(deal, dict) and deal.get("label") == "Great Value" and us:
            u_min = min(us, key=lambda x: x.get("p") or 9e12)
            b_min, p_min, loc = u_min.get("b"), u_min.get("p") or 0, s.get("locality") or ""
            mb = med_bhk.get((loc, int(float(b_min)))) if b_min is not None else None
            if mb and p_min > 0:
                true_pct = round((1 - p_min / mb) * 100)
                if true_pct < 10 and (deal.get("pct") or 0) <= -20:
                    price_issues["false_great_value_bhk_skew"] += 1
                    if len(deal_skew_examples) < 5:
                        deal_skew_examples.append(f"{s.get('name')} ({loc}): {b_min}BHK Rs {p_min:,} marked {deal.get('pct')}% vs true {b_min}BHK med Rs {mb:,} ({-true_pct}%)")
        for u in us:
            src = u.get("s") or "?"
            p, b, sq, f = u.get("p") or 0, u.get("b"), u.get("sq"), u.get("f")
            if b is None: missing_specs[src]["no_bhk"] += 1
            if not sq: missing_specs[src]["no_sqft"] += 1
            if not f: missing_specs[src]["no_furn"] += 1
            if p < 8000 and u.get("lt") != "shared": price_issues["rent_under_8k_nonshared"] += 1
            if p > 1500000: price_issues["rent_over_15L"] += 1
            if sq and (sq < 120 or sq > 10000): price_issues["absurd_sqft"] += 1
            if sq and p and (p / sq < 12 or p / sq > 450): price_issues["absurd_psf"] += 1

    log(f"  Price & Deal issues: {dict(price_issues)}")
    for ex in deal_skew_examples:
        log(f"    Skew ex: {ex}")
    log(f"  Missing unit specs (Rent) by source: { {k: dict(v) for k, v in sorted(missing_specs.items())} }")

    # --- LAYER 3: GEO, PIN COLLISIONS, TRANSIT & GOOGLE REVIEWS ---
    log("\n=== LAYER 3: GEO, PIN COLLISIONS, TRANSIT & GOOGLE REVIEWS ===")
    geo_issues = Counter()
    coord_buckets = Counter()
    loc_pts = defaultdict(list)
    for s in rent_socs:
        if s.get("lat") and s.get("lng") and s.get("locality"):
            loc_pts[s["locality"]].append((float(s["lat"]), float(s["lng"])))
    loc_med = {k: (sorted(p[0] for p in v)[len(v)//2], sorted(p[1] for p in v)[len(v)//2]) for k, v in loc_pts.items() if len(v) >= 3}

    bad_reviews = []
    blue_empire = None
    for s in rent_socs:
        lat, lng = s.get("lat"), s.get("lng")
        if not lat or not lng:
            geo_issues["missing_coords"] += 1
        else:
            lat, lng = float(lat), float(lng)
            if not (18.85 <= lat <= 19.45 and 72.75 <= lng <= 73.25):
                geo_issues["outside_mmr_bbox"] += 1
            coord_buckets[(round(lat, 5), round(lng, 5))] += 1
            loc = s.get("locality")
            if loc in loc_med and hav_km(lat, lng, loc_med[loc][0], loc_med[loc][1]) > 3.0:
                geo_issues["pin_over_3km_from_loc_median"] += 1
        ctx = s.get("mumbai_context") or {}
        if not ctx.get("nearest_metro"): geo_issues["no_metro"] += 1
        if not ctx.get("nearest_local"): geo_issues["no_local_train"] += 1
        if not (ctx.get("commute_hubs_min") or {}).get("bkc"): geo_issues["no_bkc_commute"] += 1
        if ctx.get("nearest_local") and (ctx["nearest_local"].get("walk_min") or 0) > 45:
            geo_issues["local_train_over_45m_walk"] += 1

        g = s.get("google") or {}
        g_name = str(g.get("name") or "").lower()
        s_name = str(s.get("name") or "").lower()
        if g.get("reviews") and g_name and s_name:
            sw = {w for w in re.findall(r"[a-z]{3,}", s_name) if w not in ("chs", "society", "tower", "heights", "apartment", "residency", "west", "east", "mumbai")}
            gw = set(re.findall(r"[a-z]{3,}", g_name))
            if sw and not (sw & gw):
                geo_issues["google_place_name_mismatch"] += 1
                if len(bad_reviews) < 5:
                    bad_reviews.append(f"soc='{s.get('name')}' ({s.get('locality')}) vs google='{g.get('name')}'")
        if "blue empire" in s_name and not blue_empire:
            blue_empire = {
                "name": s.get("name"), "loc": s.get("locality"), "lat": s.get("lat"), "lng": s.get("lng"),
                "approx": s.get("coords_approx"), "ctx": ctx, "deal": s.get("deal"),
                "photos": s.get("photos"), "units": s.get("units_rent"),
            }

    stacked = sum(1 for v in coord_buckets.values() if v >= 3)
    log(f"  Geo & Transit issues: {dict(geo_issues)} | Stacked coord spots (>=3 bldgs same pin): {stacked}")
    for br in bad_reviews:
        log(f"    Google mismatch ex: {br}")
    if blue_empire:
        log(f"  [CASE STUDY: Blue Empire Complex] loc={blue_empire['loc']} lat={blue_empire['lat']} lng={blue_empire['lng']} approx={blue_empire['approx']}")
        log(f"    deal={blue_empire['deal']} | local={blue_empire['ctx'].get('nearest_local')} | metro={blue_empire['ctx'].get('nearest_metro')}")
        log(f"    photos={blue_empire['photos']}")

    # --- LAYER 4: NAMING & DUPLICATE FLATS ---
    log("\n=== LAYER 4: NAMING & DUPLICATE FLATS ===")
    name_issues = Counter()
    dup_units_same_soc = 0
    cross_portal_dups = Counter()
    for s in rent_socs:
        nm = str(s.get("name") or "").strip()
        loc = str(s.get("locality") or "").strip()
        if nm and nm == nm.lower(): name_issues["all_lowercase_name"] += 1
        if nm and len(nm) > 4 and nm == nm.upper(): name_issues["all_caps_name"] += 1
        if re.search(r"^(?:\d\s*(?:bhk|rk)|on request|independent house|flat|apartment)\b", nm, re.I): name_issues["generic_name"] += 1
        if nm.lower() == loc.lower(): name_issues["name_equals_locality"] += 1
        if re.search(r"\b(?:for rent|for sale|sq\.?\s*ft|looking for)\b", nm, re.I): name_issues["ad_sentence_as_name"] += 1
        us = s.get("units_rent") or []
        seen_sig = set()
        for u in us:
            sig = (u.get("b"), u.get("p"), round((u.get("sq") or 0) / 50))
            if sig in seen_sig:
                dup_units_same_soc += 1
            seen_sig.add(sig)
            cross_portal_dups[(loc, nm.lower(), u.get("b"), u.get("p"))] += 1
    log(f"  Name issues: {dict(name_issues)}")
    log(f"  Duplicate units inside same society: {dup_units_same_soc} | Cross-entry exact (loc,name,bhk,price) dups: {sum(v-1 for v in cross_portal_dups.values() if v > 1)}")

    # --- LAYER 5: FRONTEND MOJIBAKE / ENCODING CHECK ---
    log("\n=== LAYER 5: FRONTEND MOJIBAKE / ENCODING CHECK ===")
    mojibake_re = re.compile(r"(?:\u00e2\u201a\u00b9|\u00c2\u00b7|\u00e2\u20ac\u201d|\u00e2\u20ac\u201c|\u00e2\u2020\u2014|\u00e2\u0153\u2022|\u00e2\u02dc\u2026|\u00e2\u20ac\u2039|\u00e2\u20ac\u00ba|\u00e2\u20ac\u00a6)")
    for rel in ("web/index.html", "web/app.js", "web/styles.css", "web/js/enhancements.js", "web/css/enhancements.css"):
        p = ROOT / rel
        if p.exists():
            txt = p.read_text(encoding="utf-8-sig")
            hits = mojibake_re.findall(txt)
            log(f"  {rel:28s}: {len(hits)} mojibake sequences")

    # --- LAYER 6: LIVE EDGE API PROBES VS DIRECT PORTAL FETCHES ---
    log("\n=== LAYER 6: LIVE EDGE API PROBES (WORKER VS DIRECT PORTAL) ===")
    base_api = "https:" + "//bombayhomes.pages.dev"
    for src, (nm, u, stored_n) in sorted(sample_portal_urls.items()):
        if src in ("community", "nextflat"):
            continue
        q = urllib.parse.quote(u, safe="")
        st, ms, j = http_get_json(f"{base_api}/api/photos?url={q}")
        ph = j.get("photos") or []
        vd = j.get("videos") or []
        err = j.get("error") or j.get("status") or ""
        log(f"  /api/photos [{src:14s}] stored={stored_n} -> HTTP {st} ({ms}ms) | returned photos={len(ph)} videos={len(vd)} {('err=' + str(err)) if err else ''}")
        if ph:
            log(f"    sample returned photo[0]: {ph[0][:110]}")
        try:
            from curl_cffi import requests as _cr
            _r = _cr.get(u, impersonate="chrome124", timeout=12)
            _t = _r.text or ""
            _n_cdn = len(re.findall(r"(?:imagecdn\.99acres|img\.staticmb|images\.nobroker|housingcdn\.com|n7net\.in)", _t, re.I))
            _n_vid = len(re.findall(r"\.(?:mp4|m3u8|webm)", _t, re.I))
            log(f"    direct curl_cffi -> HTTP {_r.status_code} | html={len(_t):,} B | cdn_refs={_n_cdn} | vid_refs={_n_vid}")
        except Exception:
            _dst, _dlen, _dms, _dct = http_probe_url(u, timeout=10)
            log(f"    direct urllib -> HTTP {_dst} | bytes={_dlen:,} | {_dct[:60]}")

    ask_req = urllib.request.Request(
        f"{base_api}/api/ask",
        data=json.dumps({"action": "parse", "query": "Sunlit 2BHK under 85k Bandra West zero brokerage", "currentMode": "rent", "knownLocalities": ["Bandra West", "Khar West"]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": base_api, "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(ask_req, timeout=15) as r:
            aj = json.loads(r.read().decode("utf-8", "replace"))
            log(f"  /api/ask [parse] -> HTTP {r.status} ({round((time.time()-t0)*1000)}ms) | ok={aj.get('ok')} | filters={aj.get('filters')} | err={aj.get('error')}")
    except Exception as e:
        log(f"  /api/ask [parse] -> ERR: {e}")

    # --- LAYER 7: LIVE IMAGE BYTE-SIZE & 404 PROBE ---
    log("\n=== LAYER 7: LIVE IMAGE BYTE-SIZE & 404 PROBE ===")
    for src in ("99acres", "magicbricks", "nobroker", "housing"):
        for im in sample_img_urls[src][:2]:
            st, nb, ms, ct = http_probe_url(im, timeout=8)
            log(f"  IMG [{src:11s}] HTTP {st} | {nb:7,d} B | {ms:4d}ms | {im[:95]}")

except Exception:
    log("[AUDIT ERR]\n" + traceback.format_exc())
finally:
    (ROOT / "bombayhomes_full_audit.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\nSaved bombayhomes_full_audit.txt")
