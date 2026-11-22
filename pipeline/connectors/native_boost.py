import base64, json, re, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pipeline.connectors.v19_common import detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def _get(url, headers=None, timeout=14):
    h = {"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "en-IN,en;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def fetch_makaan_rent(pages=8):
    out = []
    urls = [
        f"https://www.makaan.com/mumbai-property/flats-for-rent-in-mumbai-city?page={p}" for p in range(1, pages + 1)
    ] + [
        "https://www.makaan.com/mumbai-property/bandra-west-flats-for-rent-50165",
        "https://www.makaan.com/mumbai-property/andheri-west-flats-for-rent-50154",
        "https://www.makaan.com/mumbai-property/powai-flats-for-rent-50234",
        "https://www.makaan.com/mumbai-property/worli-flats-for-rent-50279",
        "https://www.makaan.com/thane-property/flats-for-rent-in-thane-city",
        "https://www.makaan.com/navi-mumbai-property/flats-for-rent-in-navi-mumbai-city",
    ]
    seen = set()
    for url in urls:
        try:
            html = _get(url, timeout=12)
        except Exception:
            continue
        for m in re.finditer(r'<script[^>]+type=["\']text/x-config["\'][^>]*>([\s\S]*?)</script>', html):
            try:
                cfg = json.loads(m.group(1))
            except Exception:
                continue
            if not isinstance(cfg, dict) or not cfg.get("price"):
                continue
            full_u = cfg.get("fullUrl") or cfg.get("listingUrl") or ""
            if full_u.startswith("/"):
                full_u = "https://www.makaan.com" + full_u
            if not full_u.startswith("http") or full_u in seen:
                continue
            loc_raw = cfg.get("localityName") or cfg.get("suburbName") or ""
            det = detect_locality(f"{loc_raw} {full_u}")
            if not det:
                continue
            price = parse_price(cfg.get("price"), mode="rent")
            if not price:
                continue
            seen.add(full_u)
            seller_t = str(cfg.get("sellerType") or cfg.get("companyType") or "").lower()
            is_owner = "owner" in seller_t
            img = cfg.get("mainImageURL") or cfg.get("imageUrl")
            if isinstance(img, str) and img.startswith("//"):
                img = "https:" + img
            sq_m = re.search(r"(\d{3,4})", str(cfg.get("size") or cfg.get("squareFeet") or ""))
            out.append({
                "name": clean_soc_name(cfg.get("projectName") or cfg.get("fullName") or f"{det[0]} Flat", det[0]),
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(cfg.get("bedrooms") or cfg.get("propertyType")),
                "sq": int(sq_m.group(1)) if sq_m else None,
                "s": "makaan", "u": full_u, "zb": is_owner,
                "lt": "owner" if is_owner else "broker",
                "f": norm_furnishing(cfg.get("furnished") or cfg.get("furnishing")),
                "img": img if (isinstance(img, str) and img.startswith("http")) else None,
                "lat": cfg.get("latitude"), "lng": cfg.get("longitude"),
            })
    return out

def fetch_squareyards_rent():
    out = []
    slugs = [
        "https://www.squareyards.com/rent/property-for-rent-in-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-bandra-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-andheri-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-powai-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-worli-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-lower-parel-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-goregaon-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-malad-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-thane-west-thane",
        "https://www.squareyards.com/rent/property-for-rent-in-navi-mumbai",
    ]
    seen = set()
    for url in slugs:
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
                u = obj.get("url") or ""
                if not u.startswith("http") or u in seen:
                    continue
                txt = json.dumps(obj, ensure_ascii=False)
                det = detect_locality(txt + " " + url)
                if not det:
                    continue
                offers = obj.get("offers") if isinstance(obj.get("offers"), dict) else {}
                price = parse_price(offers.get("price") or txt, mode="rent")
                if not price:
                    continue
                seen.add(u)
                img = obj.get("image")
                if isinstance(img, list):
                    img = img[0] if img else None
                sq_m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", txt, re.I)
                out.append({
                    "name": clean_soc_name(obj.get("name") or f"{det[0]} Flat", det[0]),
                    "locality": det[0], "mode": "rent", "p": price,
                    "b": parse_bhk(txt), "sq": int(sq_m.group(1)) if sq_m else None,
                    "s": "squareyards", "u": u, "zb": False, "lt": "broker",
                    "f": norm_furnishing(txt),
                    "img": img if (isinstance(img, str) and img.startswith("http")) else None,
                })
        for am in re.finditer(r'href="(https://www\.squareyards\.com/[^"]*(?:for-rent|rental)[^"]+)"', html):
            u = am.group(1).split("?")[0]
            if u in seen:
                continue
            ctx = html[max(0, am.start() - 350):min(len(html), am.end() + 900)]
            plain = re.sub(r"<[^>]+>", " ", ctx)
            det = detect_locality(plain + " " + u + " " + url)
            price = parse_price(plain, mode="rent")
            if not det or not price:
                continue
            seen.add(u)
            im = re.search(r'https://img\.squareyards\.com/[^"\'\s>]+?\.(?:jpg|jpeg|webp|png)', ctx, re.I)
            sq_m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", plain, re.I)
            nm = re.search(r"(?:in|at)\s+([A-Z][A-Za-z0-9\s&'-]{3,36})", plain)
            out.append({
                "name": clean_soc_name(nm.group(1) if nm else f"{det[0]} Flat", det[0]),
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(plain + " " + u), "sq": int(sq_m.group(1)) if sq_m else None,
                "s": "squareyards", "u": u, "zb": False, "lt": "broker",
                "f": norm_furnishing(plain),
                "img": im.group(0) if im else None,
            })
    return out

def _extract_nb_img(prop):
    photos = prop.get("photos") or []
    pid = prop.get("id") or ""
    for ph in photos:
        if not isinstance(ph, dict):
            continue
        im = ph.get("imagesMap") or {}
        for k in ("large", "original", "medium", "thumbnail"):
            fn = im.get(k)
            if fn:
                if str(fn).startswith("http"):
                    return fn
                return f"https://images.nobroker.in/images/{pid}/{fn}"
    return None

def fetch_nobroker_with_photos():
    out = []
    pockets = [
        ("Bandra West", 19.0596, 72.8295),
        ("Andheri West", 19.1364, 72.8296),
        ("Powai", 19.1197, 72.9051),
        ("Worli", 19.0176, 72.8162),
        ("Goregaon West", 19.1663, 72.8426),
        ("Malad West", 19.1864, 72.8358),
        ("Thane West", 19.2183, 72.9781),
        ("Vashi", 19.0771, 72.9986),
    ]
    seen = set()
    for api_type, lt_val in (("RENT", "owner"), ("SHARED_ACCOMMODATION", "shared")):
        for loc_name, lat, lng in pockets:
            sp = json.dumps([{"type": "place", "placeId": "", "lat": lat, "lon": lng, "placeName": loc_name, "showMap": False}])
            sp_b64 = base64.b64encode(sp.encode()).decode()
            url = f"https://www.nobroker.in/api/v3/multi/property/{api_type}/filter?searchParam={urllib.parse.quote(sp_b64)}&radius=3.5&city=mumbai&pageNo=1"
            try:
                raw = _get(url, headers={"Accept": "application/json", "Referer": "https://www.nobroker.in/"}, timeout=12)
                d = json.loads(raw)
            except Exception:
                continue
            for prop in (d.get("data") or []):
                if not isinstance(prop, dict):
                    continue
                detail = prop.get("detailUrl") or ""
                if detail.startswith("/"):
                    detail = "https://www.nobroker.in" + detail
                if not detail.startswith("http") or detail in seen:
                    continue
                price = parse_price(prop.get("rent") or prop.get("price"), mode="rent")
                if not price:
                    continue
                det = detect_locality(f"{prop.get('locality', '')} {prop.get('street', '')} {loc_name}")
                if not det:
                    continue
                seen.add(detail)
                bhk_str = str(prop.get("typeDesc") or prop.get("type") or "")
                out.append({
                    "name": clean_soc_name(prop.get("society") or prop.get("propertyTitle") or f"{det[0]} Flat", det[0]),
                    "locality": det[0], "mode": "rent", "p": price,
                    "b": parse_bhk(bhk_str), "sq": prop.get("propertySize"),
                    "s": "nobroker", "u": detail, "zb": True, "lt": lt_val,
                    "f": norm_furnishing(prop.get("furnishingDesc") or prop.get("furnishing")),
                    "img": _extract_nb_img(prop),
                    "lat": prop.get("latitude"), "lng": prop.get("longitude"),
                })
    return out

def backfill_nobroker_photos(socs, max_fetch=55):
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

    def _grab_og(pair):
        s, u = pair
        try:
            html = _get(u["u"], timeout=8)
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html, re.I)
            if m and "logo" not in m.group(1).lower():
                return s, u, m.group(1)
            m2 = re.search(r'https://images\.nobroker\.in/images/[^"\'\s>]+?\.(?:jpg|jpeg|webp|png)', html, re.I)
            if m2:
                return s, u, m2.group(0)
        except Exception:
            pass
        return s, u, None

    fetched = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_grab_og, t) for t in targets]):
            s, u, img = fut.result()
            if img:
                u["img"] = img
                if not s.get("thumb"):
                    s["thumb"] = img
                fetched += 1
    return filled_local + fetched

def fetch_dwelo_clean():
    out = []
    seen = set()
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
            im = re.search(r'https?://[^"\'\s>]+?\.(?:jpg|jpeg|webp|png)', m.group(2), re.I)
            out.append({
                "name": f"{'Shared Room' if is_shared else 'Direct Flat'} in {det[0]}",
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(ctx) or 1, "sq": None,
                "s": "dwelo", "u": u, "zb": True,
                "lt": "shared" if is_shared else "owner",
                "f": norm_furnishing(ctx),
                "img": im.group(0) if im else None,
            })
    return out[:120]

def fetch_playwright_coliving():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    out = []
    targets = [
        ("nextflat", "https://nextflat.in/flatmates/flatmates-in-mumbai", "shared"),
        ("nestaway", "https://www.nestaway.com/mumbai", "shared"),
    ]
    seen = set()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            for src, url, lt in targets:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=18000)
                    page.wait_for_timeout(2800)
                    cards = page.evaluate('''() => {
                        const out = [];
                        for (const a of document.querySelectorAll('a[href]')) {
                            const txt = (a.innerText || '').replace(/\\s+/g, ' ').trim();
                            if (txt.length < 20 || txt.length > 600) continue;
                            if (!/(?:\u20b9|Rs|k\\b|000)/i.test(txt)) continue;
                            const img = a.querySelector('img')?.src || '';
                            out.push({ href: a.href, txt, img });
                        }
                        return out.slice(0, 80);
                    }''')
                    for c in cards:
                        u = (c.get("href") or "").split("?")[0]
                        if not u.startswith("http") or u in seen:
                            continue
                        det = detect_locality(c["txt"] + " " + u)
                        price = parse_price(c["txt"], mode="rent")
                        if not det or not price:
                            continue
                        seen.add(u)
                        img = c.get("img") if str(c.get("img", "")).startswith("http") else None
                        out.append({
                            "name": f"{src.title()} {det[0]}",
                            "locality": det[0], "mode": "rent", "p": price,
                            "b": parse_bhk(c["txt"]) or 1, "sq": None,
                            "s": src, "u": u, "zb": True, "lt": lt,
                            "f": norm_furnishing(c["txt"]), "img": img,
                        })
                except Exception:
                    continue
            browser.close()
    except Exception:
        return out
    return out

def run_native_boost():
    all_recs = []
    for name, fn in (
        ("makaan_rent", fetch_makaan_rent),
        ("squareyards_rent", fetch_squareyards_rent),
        ("nobroker_api", fetch_nobroker_with_photos),
        ("dwelo", fetch_dwelo_clean),
        ("playwright_coliving", fetch_playwright_coliving),
    ):
        try:
            res = fn()
            print(f"  [native_boost] {name}: {len(res)} Mumbai listings")
            all_recs.extend(res)
        except Exception as e:
            print(f"  [native_boost] {name} skipped: {e}")
    return all_recs
