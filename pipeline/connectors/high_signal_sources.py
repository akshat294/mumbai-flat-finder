import json, re, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

MUMBAI_LOCS = [
    ("Bandra West", "Bandra-Santacruz", 19.0596, 72.8295),
    ("Bandra East", "Bandra-Santacruz", 19.0658, 72.8482),
    ("Pali Hill", "Bandra-Santacruz", 19.0608, 72.8256),
    ("Khar West", "Bandra-Santacruz", 19.0700, 72.8339),
    ("Khar East", "Bandra-Santacruz", 19.0714, 72.8453),
    ("Santacruz West", "Bandra-Santacruz", 19.0825, 72.8350),
    ("Santacruz East", "Bandra-Santacruz", 19.0815, 72.8510),
    ("Vile Parle West", "Bandra-Santacruz", 19.1005, 72.8380),
    ("Vile Parle East", "Bandra-Santacruz", 19.0989, 72.8512),
    ("Juhu", "Andheri-Juhu", 19.1075, 72.8263),
    ("Versova", "Andheri-Juhu", 19.1314, 72.8152),
    ("Lokhandwala", "Andheri-Juhu", 19.1415, 72.8255),
    ("Andheri West", "Andheri-Juhu", 19.1364, 72.8296),
    ("Andheri East", "Andheri-Juhu", 19.1136, 72.8697),
    ("Jogeshwari West", "Andheri-Juhu", 19.1367, 72.8427),
    ("Jogeshwari East", "Andheri-Juhu", 19.1380, 72.8565),
    ("Goregaon West", "Western Suburbs", 19.1663, 72.8426),
    ("Goregaon East", "Western Suburbs", 19.1653, 72.8645),
    ("Malad West", "Western Suburbs", 19.1864, 72.8358),
    ("Malad East", "Western Suburbs", 19.1872, 72.8582),
    ("Kandivali West", "Western Suburbs", 19.2084, 72.8364),
    ("Kandivali East", "Western Suburbs", 19.2054, 72.8687),
    ("Borivali West", "Western Suburbs", 19.2288, 72.8415),
    ("Borivali East", "Western Suburbs", 19.2307, 72.8645),
    ("Dahisar West", "Western Suburbs", 19.2502, 72.8520),
    ("Colaba", "South Bombay", 18.9067, 72.8147),
    ("Cuffe Parade", "South Bombay", 18.9128, 72.8214),
    ("Malabar Hill", "South Bombay", 18.9548, 72.8017),
    ("Tardeo", "South Bombay", 18.9718, 72.8147),
    ("Worli", "South Bombay", 19.0176, 72.8162),
    ("Lower Parel", "South Bombay", 18.9977, 72.8290),
    ("Prabhadevi", "South Bombay", 19.0168, 72.8290),
    ("Parel", "South Bombay", 19.0033, 72.8421),
    ("Byculla", "South Bombay", 18.9750, 72.8330),
    ("Dadar West", "South Bombay", 19.0213, 72.8376),
    ("Dadar East", "South Bombay", 19.0178, 72.8478),
    ("Mahim", "South Bombay", 19.0354, 72.8407),
    ("Matunga West", "South Bombay", 19.0269, 72.8442),
    ("Matunga East", "South Bombay", 19.0277, 72.8553),
    ("Wadala", "South Bombay", 19.0169, 72.8636),
    ("Sion", "South Bombay", 19.0434, 72.8633),
    ("Powai", "Powai-Central", 19.1197, 72.9051),
    ("Chandivali", "Powai-Central", 19.1107, 72.8982),
    ("Kurla West", "Powai-Central", 19.0726, 72.8793),
    ("Chembur", "Powai-Central", 19.0522, 72.9005),
    ("Ghatkopar West", "Powai-Central", 19.0860, 72.9080),
    ("Ghatkopar East", "Powai-Central", 19.0815, 72.9145),
    ("Vikhroli", "Powai-Central", 19.1095, 72.9275),
    ("Kanjurmarg", "Powai-Central", 19.1288, 72.9315),
    ("Bhandup West", "Powai-Central", 19.1497, 72.9335),
    ("Mulund West", "Powai-Central", 19.1726, 72.9425),
    ("Thane West", "Thane", 19.2183, 72.9781),
    ("Ghodbunder Road", "Thane", 19.2598, 72.9685),
    ("Vashi", "Navi Mumbai", 19.0771, 72.9986),
    ("Nerul", "Navi Mumbai", 19.0330, 73.0297),
    ("Seawoods", "Navi Mumbai", 19.0218, 73.0185),
    ("Kharghar", "Navi Mumbai", 19.0473, 73.0699),
    ("CBD Belapur", "Navi Mumbai", 19.0183, 73.0389),
    ("Airoli", "Navi Mumbai", 19.1590, 72.9986),
    ("Panvel", "Navi Mumbai", 18.9894, 73.1175),
]

def _fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def _detect_loc(txt):
    low = (txt or "").lower()
    for name, zone, lat, lng in MUMBAI_LOCS:
        if name.lower() in low:
            return name, zone, lat, lng
    for alias, target in [("bandra", "Bandra West"), ("khar", "Khar West"), ("santacruz", "Santacruz West"),
                          ("andheri", "Andheri West"), ("dadar", "Dadar West"), ("goregaon", "Goregaon West"),
                          ("malad", "Malad West"), ("kandivali", "Kandivali West"), ("borivali", "Borivali West"),
                          ("thane", "Thane West"), ("belapur", "CBD Belapur")]:
        if re.search(r"\b" + alias + r"\b", low):
            for name, zone, lat, lng in MUMBAI_LOCS:
                if name == target:
                    return name, zone, lat, lng
    return None

def _parse_price(txt):
    m = re.search(r"(?:\u20b9|rs\.?|inr|rent[:\s]+)\s*([\d,.]+)\s*(cr|crore|l|lac|lakh|k)?", txt, re.I)
    if not m:
        m = re.search(r"\b(\d{2,3})\s*k\b", txt, re.I)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    u = (m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else ("k" if "k" in m.group(0).lower() else "")).lower()
    if u.startswith("cr"): val *= 1e7
    elif u.startswith("l"): val *= 1e5
    elif u == "k": val *= 1e3
    val = int(round(val))
    return val if 5000 <= val <= 550000 else None

def _parse_bhk(txt):
    if re.search(r"\b1\s*rk\b|\bstudio\b", txt, re.I):
        return 0
    m = re.search(r"\b([1-5](?:\.5)?)\s*[-]?\s*bhk\b", txt, re.I)
    return float(m.group(1)) if m else 1

def fetch_nextflat():
    out = []
    for page_url in ("https://nextflat.in/flatmates/flatmates-in-mumbai", "https://nextflat.in/flats/flats-for-rent-in-mumbai"):
        try: html = _fetch(page_url)
        except Exception: continue
        m_nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', html)
        if m_nd:
            try:
                nd = json.loads(m_nd.group(1))
                blobs = []
                def walk(obj):
                    if isinstance(obj, dict):
                        if any(k in obj for k in ("rent", "price", "monthlyRent")) and any(k in obj for k in ("locality", "address", "title", "society")):
                            blobs.append(obj)
                        for v in obj.values(): walk(v)
                    elif isinstance(obj, list):
                        for x in obj: walk(x)
                walk(nd)
                for b in blobs[:80]:
                    raw_txt = json.dumps(b, ensure_ascii=False)
                    loc = _detect_loc(raw_txt)
                    if not loc: continue
                    p = int(float(b.get("rent") or b.get("price") or b.get("monthlyRent") or 0))
                    if not (5000 <= p <= 450000): continue
                    title = str(b.get("society") or b.get("title") or b.get("name") or f"Shared Flat in {loc[0]}")[:72]
                    slug = b.get("slug") or b.get("url") or ""
                    u_url = slug if str(slug).startswith("http") else page_url
                    img = None
                    imgs = b.get("images") or b.get("photos") or []
                    if isinstance(imgs, list) and imgs:
                        first = imgs[0]
                        img = first if isinstance(first, str) else (first.get("url") if isinstance(first, dict) else None)
                    out.append({
                        "name": title, "locality": loc[0], "zone": loc[1], "lat": loc[2], "lng": loc[3],
                        "p": p, "bhk": _parse_bhk(raw_txt), "src": "nextflat", "url": u_url,
                        "img": img, "lister": "shared" if "flatmate" in page_url else "owner", "zb": True
                    })
            except Exception:
                pass
        if not out:
            for m in re.finditer(r'href="(/(?:flatmates|flat|room)[^"]+)"[^>]*>([\s\S]{15,600}?)</a>', html):
                ctx = re.sub(r"<[^>]+>", " ", m.group(2))
                loc = _detect_loc(ctx + " " + m.group(1))
                p = _parse_price(ctx)
                if not loc or not p: continue
                out.append({
                    "name": f"Shared Room - {loc[0]}", "locality": loc[0], "zone": loc[1],
                    "lat": loc[2], "lng": loc[3], "p": p, "bhk": _parse_bhk(ctx),
                    "src": "nextflat", "url": "https://nextflat.in" + m.group(1),
                    "img": None, "lister": "shared", "zb": True
                })
    return out[:120]

def fetch_dwelo():
    out = []
    for page_url in ("https://dwelo.in/mumbai/flatmates", "https://dwelo.in/mumbai/flats"):
        try: html = _fetch(page_url)
        except Exception: continue
        is_shared = "flatmates" in page_url
        for m in re.finditer(r'href="(/(?:mumbai|listing|flat|room)[^"]+)"[^>]*>([\s\S]{10,700}?)</a>', html):
            ctx = re.sub(r"<[^>]+>", " ", m.group(2))
            loc = _detect_loc(ctx + " " + m.group(1))
            p = _parse_price(ctx)
            if not loc or not p: continue
            out.append({
                "name": f"{'Shared Room' if is_shared else 'Direct Flat'} in {loc[0]}",
                "locality": loc[0], "zone": loc[1], "lat": loc[2], "lng": loc[3],
                "p": p, "bhk": _parse_bhk(ctx), "src": "dwelo",
                "url": "https://dwelo.in" + m.group(1), "img": None,
                "lister": "shared" if is_shared else "owner", "zb": True
            })
    return out[:120]

def fetch_coliving():
    out = []
    for src_name, url in (("nestaway", "https://www.nestaway.com/mumbai"), ("zolostays", "https://zolostays.com/pgs-in-mumbai")):
        try: html = _fetch(url)
        except Exception: continue
        for jm in re.finditer(r'<script[^>]+application/ld\+json[^>]*>([\s\S]*?)</script>', html):
            try:
                blob = json.loads(jm.group(1))
                items = blob if isinstance(blob, list) else (blob.get("itemListElement") or [blob])
                for it in items:
                    obj = it.get("item") if isinstance(it, dict) and isinstance(it.get("item"), dict) else it
                    if not isinstance(obj, dict): continue
                    txt = json.dumps(obj, ensure_ascii=False)
                    loc = _detect_loc(txt)
                    if not loc: continue
                    offers = obj.get("offers") or {}
                    p = int(float(offers.get("price") or offers.get("lowPrice") or 0)) if isinstance(offers, dict) else (_parse_price(txt) or 0)
                    if not (5000 <= p <= 350000): continue
                    name = str(obj.get("name") or f"{src_name.title()} {loc[0]}")[:72]
                    u_url = obj.get("url") or url
                    img = obj.get("image")
                    if isinstance(img, list): img = img[0] if img else None
                    out.append({
                        "name": name, "locality": loc[0], "zone": loc[1], "lat": loc[2], "lng": loc[3],
                        "p": p, "bhk": _parse_bhk(txt), "src": src_name, "url": u_url,
                        "img": img if isinstance(img, str) and img.startswith("http") else None,
                        "lister": "shared", "zb": True
                    })
            except Exception:
                continue
    return out[:120]

def fetch_reddit_direct():
    out = []
    for sub in ("FlatmatesinMumbai", "MumbaiRealEstate"):
        try:
            d = json.loads(_fetch(f"https://www.reddit.com/r/{sub}/new.json?limit=40"))
        except Exception:
            continue
        for ch in d.get("data", {}).get("children", []):
            p_obj = ch.get("data") or {}
            title = str(p_obj.get("title") or "")
            body = str(p_obj.get("selftext") or "")
            full = f"{title} {body}"
            if re.search(r"\b(looking for a flat|need a flat|searching for a|want a room|anyone know)\b", title, re.I):
                continue
            loc = _detect_loc(full)
            price = _parse_price(full)
            if not loc or not price: continue
            is_shared = bool(re.search(r"\b(flatmate|roommate|sharing|occupancy|replacement|single room)\b", full, re.I))
            img = None
            prev = p_obj.get("preview", {}).get("images", [])
            if prev:
                img = prev[0].get("source", {}).get("url", "").replace("&", "&")
            out.append({
                "name": re.sub(r"\s+", " ", title)[:72],
                "locality": loc[0], "zone": loc[1], "lat": loc[2], "lng": loc[3],
                "p": price, "bhk": _parse_bhk(full), "src": "community",
                "url": "https://www.reddit.com" + str(p_obj.get("permalink") or ""),
                "img": img, "lister": "shared" if is_shared else "owner", "zb": True
            })
    return out[:80]

def fetch_all_high_signal():
    items = []
    for fn in (fetch_nextflat, fetch_dwelo, fetch_coliving, fetch_reddit_direct):
        try:
            res = fn()
            items.extend(res)
            print(f"  [high_signal] {fn.__name__}: {len(res)} Mumbai listings")
        except Exception as e:
            print(f"  [high_signal] {fn.__name__} skipped: {e}")
    return items
