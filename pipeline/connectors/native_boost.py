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

def fetch_telegram_public():
    channels = ["mumbaihousing", "Mumbaiflats2", "mumbairooms2", "Mumbairooms3", "Navimumbaiflatsrooms"]
    out, seen = [], set()
    for ch in channels:
        try:
            html = _get(f"https://t.me/s/{ch}", timeout=12)
        except Exception:
            continue
        for blk in html.split("tgme_widget_message_wrap")[1:]:
            pm = re.search(r'data-post="([^"]+)"', blk)
            if not pm:
                continue
            u = f"https://t.me/{pm.group(1)}"
            if u in seen:
                continue
            tm = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>([\s\S]*?)</div>', blk)
            if not tm:
                continue
            txt = re.sub(r"<br\s*/?>", "\n", tm.group(1), flags=re.I)
            txt = re.sub(r"<[^>]+>", " ", txt)
            txt = re.sub(r"\s+", " ", txt).strip()
            if len(txt) < 25:
                continue
            if re.search(r"\b(looking for|searching for|wanted|need a flat|need room|budget is)\b", txt[:120], re.I):
                continue
            det = detect_locality(txt)
            price = parse_price(txt, mode="rent")
            if not det or not price:
                continue
            seen.add(u)
            imgs = []
            for im in re.finditer(r"background-image:url\(['\"]?(https://[^'\")]+)['\"]?\)", blk):
                iu = im.group(1)
                if "emoji" not in iu and iu not in imgs:
                    imgs.append(iu)
            is_shared = bool(re.search(r"\b(flatmate|roommate|sharing|single occupancy|double occupancy|triple|pg\b|bed available|replacement)\b", txt, re.I))
            bhk = parse_bhk(txt)
            nm = re.search(r"(?:society|building|tower|complex|residency|heights|apartments?)[:\s-]+([A-Z][A-Za-z0-9\s&'-]{3,34})", txt, re.I)
            title = nm.group(1).strip() if nm else f"{'Shared Room' if is_shared else 'Direct Flat'} - {det[0]}"
            out.append({
                "name": clean_soc_name(title, det[0]),
                "locality": det[0], "mode": "rent", "p": price,
                "b": bhk if bhk is not None else 1, "sq": None,
                "s": "telegram", "u": u, "zb": True,
                "lt": "shared" if is_shared else "owner",
                "f": norm_furnishing(txt),
                "img": imgs[0] if imgs else None, "imgs": imgs[:5],
            })
    return out[:140]

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
        m_nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
        if m_nd:
            try:
                nd = json.loads(m_nd.group(1))
                found = []
                def walk(o):
                    if isinstance(o, dict):
                        if any(k in o for k in ("startingPrice", "minRent", "rent", "price")) and any(k in o for k in ("residenceName", "name", "propertyName", "title")):
                            found.append(o)
                        for v in o.values(): walk(v)
                    elif isinstance(o, list):
                        for x in o: walk(x)
                walk(nd)
                for b in found[:80]:
                    raw_s = json.dumps(b, ensure_ascii=False)
                    det = detect_locality(raw_s)
                    price = parse_price(b.get("startingPrice") or b.get("minRent") or b.get("rent") or b.get("price"), mode="rent")
                    if not det or not price:
                        continue
                    slug = b.get("slug") or b.get("seoUrl") or b.get("url") or ""
                    u = slug if str(slug).startswith("http") else (f"{url.rstrip('/')}/{str(slug).lstrip('/')}" if slug else f"{url}#{abs(hash(raw_s))%100000}")
                    if u in seen:
                        continue
                    seen.add(u)
                    imgs = []
                    for ik in ("images", "photos", "gallery", "imageUrls"):
                        arr = b.get(ik)
                        if isinstance(arr, list):
                            for it2 in arr[:5]:
                                iu = it2 if isinstance(it2, str) else (it2.get("url") or it2.get("imageUrl") if isinstance(it2, dict) else None)
                                if isinstance(iu, str) and iu.startswith("http") and iu not in imgs:
                                    imgs.append(iu)
                    name = b.get("residenceName") or b.get("propertyName") or b.get("name") or f"{src.title()} {det[0]}"
                    out.append({
                        "name": clean_soc_name(name, det[0]),
                        "locality": det[0], "mode": "rent", "p": price,
                        "b": 0, "sq": None, "s": src, "u": u, "zb": True, "lt": "shared",
                        "f": "furnished", "img": imgs[0] if imgs else None, "imgs": imgs[:5],
                        "lat": b.get("latitude") or b.get("lat"), "lng": b.get("longitude") or b.get("lng"),
                    })
            except Exception:
                pass
    return out[:120]

def fetch_squareyards_rent():
    out, seen = [], set()
    slugs = [
        "https://www.squareyards.com/rent/property-for-rent-in-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-bandra-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-andheri-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-powai-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-worli-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-lower-parel-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-goregaon-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-malad-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-chembur-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-dadar-west-mumbai",
        "https://www.squareyards.com/rent/property-for-rent-in-thane-west-thane",
        "https://www.squareyards.com/rent/property-for-rent-in-navi-mumbai",
    ]
    for url in slugs:
        try:
            html = _get(url, timeout=14)
        except Exception:
            continue
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
            imgs = re.findall(r'https://img\.squareyards\.com/[^"\'\s>]+?\.(?:jpg|jpeg|webp|png)', ctx, re.I)[:5]
            sq_m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", plain, re.I)
            nm = re.search(r"(?:in|at)\s+([A-Z][A-Za-z0-9\s&'-]{3,36})", plain)
            out.append({
                "name": clean_soc_name(nm.group(1) if nm else f"{det[0]} Flat", det[0]),
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(plain + " " + u), "sq": int(sq_m.group(1)) if sq_m else None,
                "s": "squareyards", "u": u, "zb": False, "lt": "broker",
                "f": norm_furnishing(plain), "img": imgs[0] if imgs else None, "imgs": imgs,
            })
    return out

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

def fetch_nobroker_with_photos():
    out, seen = [], set()
    pockets = [
        ("Bandra West", 19.0596, 72.8295), ("Khar West", 19.0700, 72.8339),
        ("Juhu", 19.1075, 72.8263), ("Andheri West", 19.1364, 72.8296),
        ("Powai", 19.1197, 72.9051), ("Worli", 19.0176, 72.8162),
        ("Lower Parel", 18.9977, 72.8290), ("Dadar West", 19.0213, 72.8376),
        ("Chembur", 19.0522, 72.9005), ("Goregaon West", 19.1663, 72.8426),
        ("Malad West", 19.1864, 72.8358), ("Kandivali West", 19.2084, 72.8364),
        ("Thane West", 19.2183, 72.9781), ("Vashi", 19.0771, 72.9986),
    ]
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
                imgs = _extract_nb_imgs(prop)
                bhk_str = str(prop.get("typeDesc") or prop.get("type") or "")
                out.append({
                    "name": clean_soc_name(prop.get("society") or prop.get("propertyTitle") or f"{det[0]} Flat", det[0]),
                    "locality": det[0], "mode": "rent", "p": price,
                    "b": parse_bhk(bhk_str), "sq": prop.get("propertySize"),
                    "s": "nobroker", "u": detail, "zb": True, "lt": lt_val,
                    "f": norm_furnishing(prop.get("furnishingDesc") or prop.get("furnishing")),
                    "img": imgs[0] if imgs else None, "imgs": imgs,
                    "lat": prop.get("latitude"), "lng": prop.get("longitude"),
                })
    return out

def backfill_nobroker_photos(socs, max_fetch=150):
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
    with ThreadPoolExecutor(max_workers=10) as ex:
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

def run_native_boost():
    all_recs = []
    for name, fn in (
        ("telegram_public", fetch_telegram_public),
        ("stanza_zolo_ssr", fetch_stanza_zolo_ssr),
        ("squareyards_rent", fetch_squareyards_rent),
        ("nobroker_api", fetch_nobroker_with_photos),
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
