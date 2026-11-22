import math, re

OUTER_CITY_RE = re.compile(
    r"\b(kalyan|dombivli|dombivali|badlapur|ambernath|ulhasnagar|vasai|virar|"
    r"nallasopara|nalasopara|naigaon|bhiwandi|boisar|karjat|khopoli|palghar|"
    r"titwala|shahad|dahanu|diva|mumbra|kalwa)\b", re.I
)

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
    ("Dahisar East", "Western Suburbs", 19.2505, 72.8650),
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
    ("Mulund East", "Powai-Central", 19.1700, 72.9560),
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

LOC_MAP = {name.lower(): (name, zone, lat, lng) for name, zone, lat, lng in MUMBAI_LOCS}

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def detect_locality(txt):
    low = (txt or "").lower()
    if OUTER_CITY_RE.search(low.replace("-", " ")):
        return None
    for name, zone, lat, lng in MUMBAI_LOCS:
        if name.lower() in low:
            return name, zone, lat, lng
    aliases = [
        ("bandra", "Bandra West"), ("khar", "Khar West"), ("santacruz", "Santacruz West"),
        ("santa cruz", "Santacruz West"), ("andheri", "Andheri West"), ("dadar", "Dadar West"),
        ("goregaon", "Goregaon West"), ("malad", "Malad West"), ("kandivali", "Kandivali West"),
        ("borivali", "Borivali West"), ("thane", "Thane West"), ("belapur", "CBD Belapur"),
        ("vile parle", "Vile Parle West"), ("ghatkopar", "Ghatkopar West"), ("mulund", "Mulund West"),
        ("matunga", "Matunga West"), ("bkc", "Bandra East"), ("marol", "Andheri East"),
        ("oshiwara", "Andheri West"), ("chakala", "Andheri East"), ("hiranandani", "Powai"),
    ]
    for alias, target in aliases:
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            return LOC_MAP[target.lower()]
    return None

def parse_price(raw, mode="rent"):
    if isinstance(raw, (int, float)):
        val = int(round(raw))
    else:
        txt = str(raw or "")
        m = re.search(r"(?:\u20b9|rs\.?|inr)?\s*([\d,.]+)\s*(cr|crore|l|lac|lakh|lakhs|k)?", txt, re.I)
        if not m:
            return None
        try:
            v = float(m.group(1).replace(",", ""))
        except Exception:
            return None
        u = (m.group(2) or "").lower()
        if u.startswith("cr"): v *= 1e7
        elif u.startswith("l"): v *= 1e5
        elif u == "k": v *= 1e3
        val = int(round(v))
    if mode == "buy":
        return val if 1800000 <= val <= 500000000 else None
    return val if 5000 <= val <= 600000 else None

def parse_bhk(raw):
    if isinstance(raw, (int, float)):
        v = float(raw)
        return round(v * 2) / 2 if 0 <= v <= 6.5 else None
    txt = str(raw or "").lower()
    if "rk" in txt or "studio" in txt:
        return 0
    m = re.search(r"\b([1-6](?:\.5)?)\s*[-]?\s*(?:bhk|bed|room)", txt)
    if m:
        v = float(m.group(1))
        return int(v) if v.is_integer() else v
    m2 = re.search(r"^\s*([1-6](?:\.5)?)\s*$", txt)
    if m2:
        v = float(m2.group(1))
        return int(v) if v.is_integer() else v
    return None

def norm_furnishing(raw):
    low = str(raw or "").lower()
    if "unfurn" in low: return "unfurnished"
    if "semi" in low: return "semi"
    if "furn" in low: return "furnished"
    return None

def clean_soc_name(name, locality=""):
    raw = re.sub(r"\s+", " ", str(name or "")).strip()
    if not raw:
        return f"{locality} Residence" if locality else "Mumbai Residence"
    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        loc_l = locality.lower()
        keep, seen = [], set()
        for p in parts:
            pl = p.lower()
            if pl in seen or pl in ("mumbai", "navi mumbai", "thane", loc_l):
                continue
            if keep and ((loc_l and loc_l in pl) or "mumbai" in pl):
                continue
            seen.add(pl)
            keep.append(p)
        raw = keep[0] if keep else parts[0]
    raw = re.sub(r"\bfor\s+(?:rent|sale)\s+in\b.*$", "", raw, flags=re.I).strip(" -|,")
    return raw[:72] if raw else f"{locality} Flat"

def norm_key(name, locality):
    n = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    l = re.sub(r"[^a-z0-9]+", "", (locality or "").lower())
    return f"{n}::{l}"

def build_unit(p, b, sq, src, url, zb=False, lt="broker", furn=None, img=None):
    return {
        "p": int(p),
        "b": b if b is not None else 1,
        "sq": int(sq) if (sq and 150 <= int(sq) <= 15000) else None,
        "s": str(src).lower(),
        "u": str(url).strip(),
        "zb": bool(zb),
        "lt": lt if lt in ("owner", "broker", "shared") else ("owner" if zb else "broker"),
        "f": norm_furnishing(furn),
        "img": img if (isinstance(img, str) and img.startswith("http")) else None,
    }

def _add_source_entry(soc, field, src_name, url, template_val):
    cur = soc.get(field)
    if cur is None:
        if isinstance(template_val, dict):
            soc[field] = {src_name: url if any(isinstance(v, str) for v in template_val.values()) else 1}
        else:
            soc[field] = [src_name]
        return
    if isinstance(cur, list):
        if src_name not in cur:
            cur.append(src_name)
    elif isinstance(cur, dict):
        sample_v = next(iter(cur.values()), None)
        if isinstance(sample_v, (int, float)):
            cur[src_name] = int(cur.get(src_name, 0)) + 1
        else:
            cur.setdefault(src_name, url)

def merge_records_into_societies(socs, records):
    tmpl = next((s for s in socs if s.get("sources") is not None), {})
    soc_by_key = {}
    seen_urls = set()
    for s in socs:
        k = norm_key(s.get("name"), s.get("locality"))
        soc_by_key.setdefault(k, s)
        for uk in ("units_rent", "units_buy"):
            for u in (s.get(uk) or []):
                uu = u.get("u") or u.get("url")
                if uu: seen_urls.add(uu)

    added_units, added_socs = 0, 0
    for idx, rec in enumerate(records):
        u_url = rec.get("u")
        if not u_url or u_url in seen_urls:
            continue
        mode = "buy" if rec.get("mode") == "buy" else "rent"
        loc = rec.get("locality")
        if not loc or loc.lower() not in LOC_MAP:
            det = detect_locality(f"{loc or ''} {rec.get('name', '')} {u_url}")
            if not det:
                continue
            loc, zone, mlat, mlng = det
        else:
            loc, zone, mlat, mlng = LOC_MAP[loc.lower()]

        if OUTER_CITY_RE.search(f"{rec.get('name', '')} {u_url}".replace("-", " ")):
            continue

        p = parse_price(rec.get("p"), mode=mode)
        if not p:
            continue
        name = clean_soc_name(rec.get("name"), loc)
        unit = build_unit(
            p=p, b=parse_bhk(rec.get("b")), sq=rec.get("sq"), src=rec.get("s"),
            url=u_url, zb=rec.get("zb", False), lt=rec.get("lt", "broker"),
            furn=rec.get("f"), img=rec.get("img")
        )
        seen_urls.add(u_url)

        rlat, rlng = rec.get("lat"), rec.get("lng")
        coords_approx = True
        if rlat and rlng:
            try:
                rlat, rlng = float(rlat), float(rlng)
                if haversine_km(rlat, rlng, mlat, mlng) <= 3.8:
                    coords_approx = False
                else:
                    rlat, rlng = None, None
            except Exception:
                rlat, rlng = None, None
        if not rlat or not rlng:
            ang = ((abs(hash(name + loc)) + idx * 37) % 360) * math.pi / 180.0
            rad = 0.0012 + ((idx % 7) * 0.00035)
            rlat = round(mlat + rad * math.cos(ang), 6)
            rlng = round(mlng + rad * math.sin(ang), 6)
            coords_approx = True

        list_k = "units_buy" if mode == "buy" else "units_rent"
        src_list_k = "sources_buy" if mode == "buy" else "sources_rent"
        key = norm_key(name, loc)
        if key in soc_by_key:
            s = soc_by_key[key]
            s.setdefault(list_k, []).append(unit)
            if unit["img"] and not s.get("thumb"):
                s["thumb"] = unit["img"]
            for sk in ("sources", src_list_k):
                _add_source_entry(s, sk, unit["s"], unit["u"], tmpl.get(sk))
            if unit["b"] is not None:
                bhks = s.setdefault("bhks", [])
                if unit["b"] not in bhks:
                    bhks.append(unit["b"])
            if unit["f"] and not s.get("furnishing"):
                s["furnishing"] = unit["f"]
            added_units += 1
        else:
            sid = f"bh-{unit['s'][:4]}-{abs(hash(u_url)) % 10000000}"
            pricing = {"rent_min": p, "rent_max": p, "rent_med": p} if mode == "rent" else {"buy_min": p, "buy_max": p, "buy_med": p}
            new_soc = {
                "id": sid, "name": name, "locality": loc, "is_unnamed": False,
                "zone": zone, "lat": round(rlat, 6), "lng": round(rlng, 6),
                "coords_approx": coords_approx,
                "bhks": [unit["b"]] if unit["b"] is not None else [],
                "furnishing": unit["f"] or "", "tenant": "",
                "rera_ids": rec.get("rera_ids") or [],
                "rera_carpet_sqft": unit["sq"], "pricing": pricing,
                "units_rent": [unit] if mode == "rent" else [],
                "units_buy": [unit] if mode == "buy" else [],
                "thumb": unit["img"], "mumbai_context": {}, "features": [],
                "commutes": {}, "civic": {}, "google": {},
                "sources": {} if isinstance(tmpl.get("sources"), dict) else [],
                "sources_rent": {} if isinstance(tmpl.get("sources_rent"), dict) else [],
                "sources_buy": {} if isinstance(tmpl.get("sources_buy"), dict) else [],
                "deal": None, "is_new": True,
            }
            _add_source_entry(new_soc, "sources", unit["s"], unit["u"], tmpl.get("sources"))
            _add_source_entry(new_soc, src_list_k, unit["s"], unit["u"], tmpl.get(src_list_k))
            socs.append(new_soc)
            soc_by_key[key] = new_soc
            added_socs += 1
            added_units += 1
    return added_units, added_socs
