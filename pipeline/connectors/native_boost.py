import base64, json, re, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pipeline.connectors.v19_common import detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

try:
    from curl_cffi import requests as _cffi_req
except Exception:
    _cffi_req = None

def _get(url, headers=None, timeout=14):
    h = {"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "en-IN,en;q=0.9"}
    if headers:
        h.update(headers)
    if _cffi_req is not None:
        r = _cffi_req.get(url, headers=h, impersonate="chrome", timeout=timeout)
        r.raise_for_status()
        return r.text
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def _extract_nb_imgs(prop):
    photos = prop.get("photos") or []
    pid = prop.get("id") or ""
    imgs = []
    for ph in photos[:6]:
        if not isinstance(ph, dict):
            continue
        im = ph.get("imagesMap") or {}
        for k in ("large", "original", "medium", "thumbnail"):
            fn = im.get(k)
            if fn:
                url = fn if str(fn).startswith("http") else f"https://images.nobroker.in/images/{pid}/{fn}"
                if url not in imgs:
                    imgs.append(url)
                break
    return imgs[:5]

def fetch_nobroker_scaled():
    pockets = [
        ("Bandra West", 19.0596, 72.8295), ("Khar West", 19.0700, 72.8339),
        ("Santacruz West", 19.0825, 72.8350), ("Juhu", 19.1075, 72.8263),
        ("Andheri West", 19.1364, 72.8296), ("Andheri East", 19.1136, 72.8697),
        ("Powai", 19.1197, 72.9051), ("Worli", 19.0176, 72.8162),
        ("Lower Parel", 18.9977, 72.8290), ("Dadar West", 19.0213, 72.8376),
        ("Wadala", 19.0169, 72.8636), ("Chembur", 19.0522, 72.9005),
        ("Ghatkopar West", 19.0860, 72.9080), ("Vikhroli", 19.1095, 72.9275),
        ("Mulund West", 19.1726, 72.9425), ("Goregaon West", 19.1663, 72.8426),
        ("Goregaon East", 19.1653, 72.8645), ("Malad West", 19.1864, 72.8358),
        ("Kandivali West", 19.2084, 72.8364), ("Borivali West", 19.2288, 72.8415),
        ("Thane West", 19.2183, 72.9781), ("Vashi", 19.0771, 72.9986),
        ("Kharghar", 19.0473, 73.0699), ("Airoli", 19.1590, 72.9986),
    ]
    tasks = []
    for loc_name, lat, lng in pockets:
        for pg in (1, 2, 3):
            tasks.append(("RENT", "rent", "owner", loc_name, lat, lng, pg))
        for pg in (1, 2):
            tasks.append(("SHARED_ACCOMMODATION", "rent", "shared", loc_name, lat, lng, pg))
            tasks.append(("BUY", "buy", "owner", loc_name, lat, lng, pg))

    def _fetch_one(task):
        api_type, mode, lt_val, loc_name, lat, lng, pg = task
        sp = json.dumps([{"type": "place", "placeId": "", "lat": lat, "lon": lng, "placeName": loc_name, "showMap": False}])
        sp_b64 = base64.b64encode(sp.encode()).decode()
        url = f"https://www.nobroker.in/api/v3/multi/property/{api_type}/filter?searchParam={urllib.parse.quote(sp_b64)}&radius=3.5&city=mumbai&pageNo={pg}"
        rows = []
        try:
            raw = _get(url, headers={"Accept": "application/json", "Referer": "https://www.nobroker.in/"}, timeout=12)
            d = json.loads(raw)
        except Exception:
            return rows
        for prop in (d.get("data") or []):
            if not isinstance(prop, dict):
                continue
            detail = prop.get("detailUrl") or ""
            if detail.startswith("/"):
                detail = "https://www.nobroker.in" + detail
            if not detail.startswith("http"):
                continue
            raw_p = prop.get("price") if mode == "buy" else (prop.get("rent") or prop.get("price"))
            price = parse_price(raw_p, mode=mode)
            if not price:
                continue
            det = detect_locality(f"{prop.get('locality', '')} {prop.get('street', '')} {loc_name}")
            if not det:
                continue
            imgs = _extract_nb_imgs(prop)
            bhk_str = str(prop.get("typeDesc") or prop.get("type") or "")
            rows.append({
                "name": clean_soc_name(prop.get("society") or prop.get("propertyTitle") or f"{det[0]} Flat", det[0]),
                "locality": det[0], "mode": mode, "p": price,
                "b": parse_bhk(bhk_str), "sq": prop.get("propertySize"),
                "s": "nobroker", "u": detail.split("?")[0], "zb": True, "lt": lt_val,
                "f": norm_furnishing(prop.get("furnishingDesc") or prop.get("furnishing")),
                "img": imgs[0] if imgs else None, "imgs": imgs,
                "lat": prop.get("latitude"), "lng": prop.get("longitude"),
            })
        return rows

    out, seen = [], set()
    with ThreadPoolExecutor(max_workers=10) as ex:
        for fut in as_completed([ex.submit(_fetch_one, t) for t in tasks]):
            for r in fut.result():
                if r["u"] not in seen:
                    seen.add(r["u"])
                    out.append(r)
    return out

def fetch_squareyards_rent():
    base_slugs = [
        "https://www.squareyards.com/rent/property-for-rent-in-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-bandra-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-khar-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-andheri-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-andheri-east-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-powai-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-worli-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-lower-parel-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-dadar-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-chembur-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-goregaon-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-goregaon-east-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-malad-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-kandivali-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-borivali-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-mulund-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-thane-west-thane",
        "https://www.squareyards.com/rent/property-for-rent-in-navi-mumbai",
    ]
    urls = [u for base in base_slugs for u in (base, base + "?page=2")]

    def _scrape_sy(url):
        rows = []
        try:
            html = _get(url, timeout=14)
        except Exception:
            return rows
        for am in re.finditer(r'href="(https://www\.squareyards\.com/[^"]*(?:for-rent|rental)[^"]+)"', html):
            u = am.group(1).split("?")[0]
            ctx = html[max(0, am.start() - 350):min(len(html), am.end() + 900)]
            plain = re.sub(r"<[^>]+>", " ", ctx)
            det = detect_locality(plain + " " + u + " " + url)
            price = parse_price(plain, mode="rent")
            if not det or not price:
                continue
            imgs = re.findall(r'https://img\.squareyards\.com/[^"\'\s>]+?\.(?:jpg|jpeg|webp|png)', ctx, re.I)[:5]
            sq_m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", plain, re.I)
            nm = re.search(r"(?:in|at)\s+([A-Z][A-Za-z0-9\s&'-]{3,36})", plain)
            rows.append({
                "name": clean_soc_name(nm.group(1) if nm else f"{det[0]} Flat", det[0]),
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(plain + " " + u), "sq": int(sq_m.group(1)) if sq_m else None,
                "s": "squareyards", "u": u, "zb": False, "lt": "broker",
                "f": norm_furnishing(plain), "img": imgs[0] if imgs else None, "imgs": imgs,
            })
        return rows

    out, seen = [], set()
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_scrape_sy, u) for u in urls]):
            for r in fut.result():
                if r["u"] not in seen:
                    seen.add(r["u"])
                    out.append(r)
    return out

def fetch_stanza_zolo_ssr():
    out, seen = [], set()
    pages = [
        ("stanza", "https://www.stanzaliving.com/mumbai"),
        ("stanza", "https://www.stanzaliving.com/unisex-paying-guest-pg-hostel-near-mumbai"),
        ("zolostays", "https://zolostays.com/pgs-in-mumbai"),
    ]
    for src, url in pages:
        try:
            html = _get(url, timeout=14)
        except Exception:
            continue
        for jm in re.finditer(r'<script[^>]+application/ld\+json[^>]*>([\s\S]*?)</script>', html):
            try:
                blob = json.loads(jm.group(1))
            except Exception:
                continue
            items = blob if isinstance(blob, list) else (blob.get("itemListElement") or [blob])
            for it in items:
                obj = it.get("item") if isinstance(it, dict) and isinstance(it.get("item"), dict) else it
                if not isinstance(obj, dict):
                    continue
                txt = json.dumps(obj, ensure_ascii=False)
                det = detect_locality(txt)
                if not det:
                    continue
                offers = obj.get("offers") if isinstance(obj.get("offers"), dict) else {}
                price = parse_price(offers.get("price") or offers.get("lowPrice") or txt, mode="rent")
                if not price:
                    continue
                u = str(obj.get("url") or url).split("?")[0]
                if u in seen:
                    continue
                seen.add(u)
                raw_img = obj.get("image")
                imgs = [raw_img] if isinstance(raw_img, str) else (list(raw_img) if isinstance(raw_img, list) else [])
                imgs = [x for x in imgs if isinstance(x, str) and x.startswith("http")][:5]
                out.append({
                    "name": clean_soc_name(obj.get("name") or f"{src.title()} {det[0]}", det[0]),
                    "locality": det[0], "mode": "rent", "p": price,
                    "b": 0, "sq": None, "s": src, "u": u, "zb": True, "lt": "shared",
                    "f": "furnished", "img": imgs[0] if imgs else None, "imgs": imgs,
                })
    return out[:120]

def fetch_dwelo_clean():
    out, seen = [], set()
    for page_url, is_shared in (("https://dwelo.in/mumbai/flatmates", True), ("https://dwelo.in/mumbai/flats", False)):
        try:
            html = _get(page_url, timeout=12)
        except Exception:
            continue
        for m in re.finditer(r'href="(/(?:mumbai|listing|flat|room)[^"]+)"[^>]*>([\s\S]{10,700}?)</a>', html):
            u = "https://dwelo.in" + m.group(1).split("?")[0]
            if u in seen:
                continue
            ctx = re.sub(r"<[^>]+>", " ", m.group(2))
            det = detect_locality(ctx + " " + u)
            price = parse_price(ctx, mode="rent")
            if not det or not price:
                continue
            seen.add(u)
            imgs = re.findall(r'https?://[^"\'\s>]+?\.(?:jpg|jpeg|webp|png)', m.group(2), re.I)[:4]
            out.append({
                "name": f"{'Shared Room' if is_shared else 'Direct Flat'} in {det[0]}",
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(ctx) or 1, "sq": None,
                "s": "dwelo", "u": u, "zb": True,
                "lt": "shared" if is_shared else "owner",
                "f": norm_furnishing(ctx), "img": imgs[0] if imgs else None, "imgs": imgs,
            })
    return out[:120]

def fetch_playwright_coliving():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    out, seen = [], set()
    targets = [
        ("nextflat", "https://nextflat.in/flatmates/flatmates-in-mumbai", "shared", True),
        ("nextflat", "https://nextflat.in/flats/flats-for-rent-in-mumbai", "owner", True),
        ("nestaway", "https://www.nestaway.com/mumbai", "shared", True),
        ("zolostays", "https://zolostays.com/pgs-in-mumbai", "shared", True),
        ("stanza", "https://www.stanzaliving.com/mumbai", "shared", True),
        ("makaan", "https://www.makaan.com/mumbai-property/flats-for-rent-in-mumbai-city", "broker", False),
    ]
    eval_js = (
        "() => {"
        "  const out = [];"
        "  for (const a of document.querySelectorAll('a[href]')) {"
        "    const txt = (a.innerText || '').replace(/\\s+/g, ' ').trim();"
        "    if (txt.length < 18 || txt.length > 650) continue;"
        "    if (!/(?:\\u20b9|Rs|k\\b|000|lac|lakh)/i.test(txt)) continue;"
        "    const imgs = [...a.querySelectorAll('img')].map(i => i.src || (i.dataset && i.dataset.src) || '').filter(u => u.startsWith('http'));"
        "    out.push({ href: a.href, txt, imgs: imgs.slice(0, 4) });"
        "  }"
        "  return out.slice(0, 100);"
        "}"
    )
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            for src, url, lt, is_zb in targets:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=18000)
                    page.wait_for_timeout(3200)
                    page.evaluate("window.scrollTo(0, 1400)")
                    page.wait_for_timeout(1000)
                    cards = page.evaluate(eval_js)
                    for c in cards:
                        u = (c.get("href") or "").split("?")[0]
                        if not u.startswith("http") or u in seen:
                            continue
                        det = detect_locality(c["txt"] + " " + u)
                        price = parse_price(c["txt"], mode="rent")
                        if not det or not price:
                            continue
                        seen.add(u)
                        imgs = c.get("imgs") or []
                        out.append({
                            "name": f"{src.title()} {det[0]}",
                            "locality": det[0], "mode": "rent", "p": price,
                            "b": parse_bhk(c["txt"]) or (0 if src in ("zolostays", "stanza") else 1),
                            "sq": None, "s": src, "u": u, "zb": is_zb, "lt": lt,
                            "f": norm_furnishing(c["txt"]) or ("furnished" if src in ("zolostays", "stanza") else None),
                            "img": imgs[0] if imgs else None, "imgs": imgs,
                        })
                except Exception:
                    continue
            browser.close()
    except Exception:
        return out
    return out

def backfill_nobroker_photos(socs, max_fetch=220):
    filled_local = 0
    for s in socs:
        thumb = s.get("thumb")
        us = s.get("units_rent") or []
        if not thumb:
            thumb = next((u.get("img") for u in us if u.get("img")), None)
            if thumb:
                s["thumb"] = thumb
        if thumb:
            for u in us:
                if u.get("s") == "nobroker" and not u.get("img"):
                    u["img"] = thumb
                    filled_local += 1

    targets = []
    for s in socs:
        if s.get("thumb"):
            continue
        nb_u = next((u for u in (s.get("units_rent") or []) if u.get("s") == "nobroker" and u.get("u")), None)
        if nb_u:
            targets.append((s, nb_u))
    targets = targets[:max_fetch]
    if not targets:
        return filled_local

    def _grab_imgs(pair):
        s, u = pair
        try:
            html = _get(u["u"], timeout=8)
            imgs = []
            for m in re.finditer(r'https://images\.nobroker\.in/images/[^"\'\s>]+?_(?:large|medium|original)\.(?:jpg|jpeg|webp|png)', html, re.I):
                iu = m.group(0)
                if iu not in imgs:
                    imgs.append(iu)
                if len(imgs) >= 5:
                    break
            if not imgs:
                m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html, re.I)
                if m and "logo" not in m.group(1).lower():
                    imgs.append(m.group(1))
            return s, u, imgs
        except Exception:
            return s, u, []

    fetched = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for fut in as_completed([ex.submit(_grab_imgs, t) for t in targets]):
            s, u, imgs = fut.result()
            if imgs:
                u["img"] = imgs[0]
                if len(imgs) > 1:
                    u["imgs"] = imgs
                if not s.get("thumb"):
                    s["thumb"] = imgs[0]
                fetched += 1
    return filled_local + fetched

def run_native_boost():
    all_recs = []
    for name, fn in (
        ("nobroker_24hubs_rent_shared_buy", fetch_nobroker_scaled),
        ("squareyards_18hubs_rent", fetch_squareyards_rent),
        ("stanza_zolo_ssr", fetch_stanza_zolo_ssr),
        ("dwelo", fetch_dwelo_clean),
        ("playwright_coliving_makaan", fetch_playwright_coliving),
    ):
        try:
            res = fn()
            print(f"  [native_boost] {name}: {len(res)} Mumbai listings")
            all_recs.extend(res)
        except Exception as e:
            print(f"  [native_boost] {name} skipped: {e}")
    return all_recs
