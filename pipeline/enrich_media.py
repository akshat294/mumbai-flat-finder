import argparse, json, math, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from curl_cffi import requests as creq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.data_hygiene import _media_key_rank
from pipeline.fleet_repair import upgrade_media_url, _dedupe_rank_urls

CACHE_PATH = ROOT / "data/media_cache.json"
BAD_CAPTION_RE = re.compile(
    r"(floor\s*plan|master\s*plan|site\s*plan|unit\s*plan|location\s*map|"
    r"layout|brochure|blueprint|3d\s*plan|3d\s*render|elevation|route\s*map|"
    r"amenity\s*map|payment\s*plan)",
    re.I,
)
BAD_URL_RE = re.compile(
    r"(floor[-_]?plan|master[-_]?plan|site[-_]?plan|unit[-_]?plan|location[-_]?map|"
    r"3d[-_]?plan|3d[-_]?render|layout|blueprint|brochure|elevation|under_screening|"
    r"fbshare|static\.99acres\.com|assets\.nobroker\.in|no[-_]?image|no[-_]?photo|"
    r"placeholder|default[-_]?img|avatar|logo|\.svg(?:\?|$)|\.gif(?:\?|$))",
    re.I,
)

DEAD_PAGE_RE = re.compile(
    r"(?:property\s+(?:is\s+)?(?:no\s+longer\s+available|has\s+been\s+(?:rented|sold|deactivated|removed)|expired)|"
    r"this\s+listing\s+is\s+(?:no\s+longer|expired|inactive)|oops!\s*page\s+not\s+found)",
    re.I,
)
GENERIC_SOC_RE = re.compile(
    r"^(?:\d(?:\.\d)?\s*(?:bhk|rk)|flat|apartment|studio|independent|house|room|pg|hostel|"
    r"on\s+request|standalone|residential|na|n/a|none|null|others?|mumbai|thane|navi\s+mumbai)$",
    re.I,
)

def _clean_soc_candidate(raw):
    if not isinstance(raw, str):
        return ""
    s = re.sub(r"\s+", " ", raw.strip(" ,.-_|")).strip()
    if len(s) < 3 or len(s) > 65:
        return ""
    if GENERIC_SOC_RE.match(s) or re.search(r"\b(?:for\s+rent|for\s+sale|sq\.?\s*ft|bhk|crore|lakh)\b", s, re.I):
        return ""
    if re.match(r"^(?:[2-9a-z]{4}\+[2-9a-z]{2,4}|(?:[a-z]{1,2}[\s\-/]*)?\d{1,4}[a-z]?)$", s, re.I):
        return ""
    return s

def _parse_inr_int(val):
    if isinstance(val, (int, float)):
        n = int(val)
        return n if 1000 <= n <= 50000000 else 0
    s = str(val or "").strip().lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lac|lakh|cr|crore|k)?", s)
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("lac", "lakh"): num *= 100000
    elif unit in ("cr", "crore"): num *= 10000000
    elif unit == "k": num *= 1000
    n = int(round(num))
    return n if 1000 <= n <= 50000000 else 0

def load_cache():
    if CACHE_PATH.exists():
        try:
            d = json.loads(CACHE_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {}

def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(CACHE_PATH)

def _extract_nobroker(html, url):
    t = html.replace("\\u002F", "/").replace("\\/", "/")
    pid_m = (
        re.search(r"/([a-f0-9]{24,32})(?:/detail|\?|$)", url, re.I)
        or re.search(r'"propertyId"\s*:\s*"([a-f0-9]{20,32})"', t, re.I)
        or re.search(r'"id"\s*:\s*"([a-f0-9]{24,32})"', t, re.I)
    )
    pid = pid_m.group(1) if pid_m else ""
    raw_imgs = []

    m_arr = re.search(r'"photos"\s*:\s*(\[\s*\{.*?\}\s*\])', t)
    if m_arr and pid:
        try:
            arr = json.loads(m_arr.group(1))
            for item in arr:
                if not isinstance(item, dict):
                    continue
                cap = f"{item.get('title') or ''} {item.get('name') or ''}"
                if BAD_CAPTION_RE.search(cap):
                    continue
                imap = item.get("imagesMap") or {}
                fn = imap.get("large") or imap.get("enhance_large") or imap.get("original") or imap.get("medium")
                if isinstance(fn, str) and fn and not BAD_URL_RE.search(fn):
                    full = fn if fn.startswith("http") else ("https:" + f"//images.nobroker.in/images/{pid}/{fn}")
                    raw_imgs.append(full)
        except Exception:
            pass

    if not raw_imgs and pid:
        for m in re.finditer(r'"(?:large|enhance_large|original|medium)"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp))"', t, re.I):
            fn = m.group(1)
            if not BAD_URL_RE.search(fn):
                full = fn if fn.startswith("http") else ("https:" + f"//images.nobroker.in/images/{pid}/{fn}")
                raw_imgs.append(full)

    if not raw_imgs:
        for m in re.finditer(r'https?:/{2}images\.nobroker\.in/images/[a-f0-9]{16,32}/[^\s"\'<>\\]+\.(?:jpg|jpeg|png|webp)', t, re.I):
            raw_imgs.append(m.group(0))

    furn = ""
    fm = re.search(r'"furnishing(?:Desc)?"\s*:\s*"([^"]{3,25})"', t, re.I)
    if fm:
        fv = fm.group(1).lower()
        if "semi" in fv: furn = "semi"
        elif "unfurn" in fv or "not" in fv: furn = "unfurnished"
        elif "full" in fv or "furn" in fv: furn = "furnished"

    soc_m = re.search(r'"(?:society|buildingName|projectName)"\s*:\s*"([^"]{3,65})"', t)
    soc_nm = _clean_soc_candidate(soc_m.group(1)) if soc_m else ""
    dep_m = re.search(r'"deposit"\s*:\s*(\d{4,8})', t)
    dep = _parse_inr_int(int(dep_m.group(1))) if dep_m else 0
    fl_m = re.search(r'"floor"\s*:\s*(\d{1,2})', t)
    tf_m = re.search(r'"totalFloor"\s*:\s*(\d{1,2})', t)
    flr = f"{fl_m.group(1)}/{tf_m.group(1)}" if (fl_m and tf_m) else (fl_m.group(1) if fl_m else "")
    fac_m = re.search(r'"facingDesc"\s*:\s*"([A-Za-z\-\s]{3,16})"', t)
    fac = fac_m.group(1).strip() if fac_m else ""
    dead = bool(DEAD_PAGE_RE.search(t[:45000]) or '"inactive":true' in t[:45000].lower())
    imgs, _ = _dedupe_rank_urls(raw_imgs, cap=10)
    return {"imgs": imgs, "vids": [], "furn": furn, "soc": soc_nm, "dep": dep, "flr": flr, "fac": fac, "dead": dead}

def _mb_hex_to_pid(url, html):
    m = re.search(r"[?&]id=([0-9a-f]{12,32})", url, re.I)
    if m:
        try:
            dec = bytes.fromhex(m.group(1)).decode("ascii", "ignore")
            dm = re.search(r"(\d{6,10})", dec)
            if dm:
                return dm.group(1)
        except Exception:
            pass
    m2 = re.search(r'"propertyId"\s*:\s*"?(\d{6,10})"?', html, re.I)
    return m2.group(1) if m2 else ""

def _extract_magicbricks(html, url):
    t = html.replace("\\u002F", "/").replace("\\/", "/")
    pid = _mb_hex_to_pid(url, t)
    raw_imgs = []
    for m in re.finditer(r'https?:/{2}img\.staticmb\.com/mbphoto/property/[^\s"\'<>\\]+\.(?:jpg|jpeg|png|webp)', t, re.I):
        u = m.group(0)
        if pid and pid not in u:
            continue
        if BAD_URL_RE.search(u):
            continue
        if "Photo_h300_w450" in u:
            u = u.replace("Photo_h300_w450", "Photo_h600_w900").replace("_300_450.", "_600_900.")
        elif "Photo_h180_w240" in u:
            u = u.replace("Photo_h180_w240", "Photo_h600_w900").replace("_180_240.", "_600_900.")
        raw_imgs.append(u)

    proj_added = 0
    for m in re.finditer(r'https?:/{2}img\.staticmb\.com/mbimages/project/[^\s"\'<>\\]+\.(?:jpg|jpeg|png|webp)', t, re.I):
        u = m.group(0)
        if BAD_URL_RE.search(u):
            continue
        if "Project-Photo" in u and proj_added < 3:
            raw_imgs.append(u)
            proj_added += 1

    soc_m = re.search(r'"(?:projectName|pName|societyName)"\s*:\s*"([^"]{3,65})"', t)
    soc_nm = _clean_soc_candidate(soc_m.group(1)) if soc_m else ""
    dep_m = re.search(r'Security\s+Deposit[^0-9]{0,40}([\d.,]+\s*(?:Lac|Lakh|Cr|K)?)', t, re.I)
    dep = _parse_inr_int(dep_m.group(1)) if dep_m else 0
    fl_m = re.search(r'"floorNo"\s*:\s*"?(\d{1,2}|Ground)"?', t, re.I)
    tf_m = re.search(r'"totalFloor"\s*:\s*"?(\d{1,2})"?', t, re.I)
    flr = f"{fl_m.group(1)}/{tf_m.group(1)}" if (fl_m and tf_m) else (fl_m.group(1) if fl_m else "")
    fac_m = re.search(r'"facing"\s*:\s*"([A-Za-z\-\s]{3,16})"', t)
    fac = fac_m.group(1).strip() if fac_m else ""
    dead = bool(DEAD_PAGE_RE.search(t[:45000]))
    imgs, _ = _dedupe_rank_urls(raw_imgs, cap=10)
    return {"imgs": imgs, "vids": [], "furn": "", "soc": soc_nm, "dep": dep, "flr": flr, "fac": fac, "dead": dead}

def _extract_99acres(html, url):
    t = html.replace("\\u002F", "/").replace("\\/", "/")
    raw_imgs, vids = [], []
    seen_v = set()

    m_pv = re.search(r'"propertyVideos"\s*:\s*\{.{0,3000}', t)
    pv_blob = m_pv.group(0) if m_pv else t
    for m in re.finditer(r'"videoLink"\s*:\s*"([^"]+)"', pv_blob, re.I):
        vu = m.group(1).strip()
        yt = re.search(r'(?:youtube\.com/embed/|youtu\.be/|watch\?v=)([A-Za-z0-9_-]{11})', vu)
        if yt:
            eu = "https:" + "//www.youtube.com/embed/" + yt.group(1)
            if eu not in seen_v:
                seen_v.add(eu)
                vids.append({"url": eu, "kind": "youtube"})
        elif re.search(r'\.(?:mp4|m3u8|webm)', vu, re.I) and vu not in seen_v:
            seen_v.add(vu)
            vids.append({"url": vu, "kind": "video"})

    m_pi = re.search(r'"(?:propertyImages|mediaDetails|photoDetails)"\s*:\s*[\[{].{0,18000}', t)
    scan_blob = m_pi.group(0) if m_pi else t[:220000]
    for m in re.finditer(r'https?:/{2}imagecdn\.99acres\.com/media\d+/[^\s"\'<>\\]+\.(?:jpg|jpeg|png|webp)', scan_blob, re.I):
        u = m.group(0)
        if not BAD_URL_RE.search(u):
            raw_imgs.append(u)

    soc_m = re.search(r'"(?:SOCIETY_NAME|BUILDING_NAME|societyName|projectName)"\s*:\s*"([^"]{3,65})"', t)
    soc_nm = _clean_soc_candidate(soc_m.group(1)) if soc_m else ""
    fl_m = re.search(r'"FLOOR_NUM"\s*:\s*"?(\d{1,2}|Ground)"?', t, re.I)
    tf_m = re.search(r'"TOTAL_FLOOR"\s*:\s*"?(\d{1,2})"?', t, re.I)
    flr = f"{fl_m.group(1)}/{tf_m.group(1)}" if (fl_m and tf_m) else (fl_m.group(1) if fl_m else "")
    dead = bool(DEAD_PAGE_RE.search(t[:45000]))
    imgs, _ = _dedupe_rank_urls(raw_imgs, cap=10)
    return {"imgs": imgs, "vids": vids[:3], "furn": "", "soc": soc_nm, "dep": 0, "flr": flr, "fac": "", "dead": dead}

HS_BAD_GROUP_RE = re.compile(r"(floor|plan|layout|map|brochure|locality|neighbourhood|neighborhood|amenity|amenities|master)", re.I)

def _norm_housing_src(src):
    if not isinstance(src, str) or not src.strip():
        return ""
    u = src.strip().replace("\\u002F", "/").replace("\\/", "/")
    if u.startswith("//"):
        u = "https:" + u
    u = u.replace("/{version}/", "/fs/").replace("/version/", "/fs/").replace("version/", "fs/").replace("/%s/", "/fs/")
    u = re.sub(r"/v(\d+)/(?:fs_medium|medium|small|thumb)/", r"/v\1/fs/", u, flags=re.I)
    return u

def _extract_housing_gql(url):
    m_rent = re.search(r"/rent/(\d+)(?:-|/|$)", url)
    m_proj = re.search(r"/projects/page/(\d+)(?:-|/|$)", url)
    m_buy = re.search(r"/(?:buy|resale)/(?:[^/]+/)*(\d+)(?:-|/|$)", url) or re.search(r"/page/(\d+)(?:-|/|$)", url)
    if m_rent:
        pid, ptype = int(m_rent.group(1)), "rent"
    elif m_proj:
        pid, ptype = int(m_proj.group(1)), "project"
    elif m_buy:
        pid, ptype = int(m_buy.group(1)), "resale"
    else:
        return {"imgs": [], "vids": [], "furn": "", "st": 400}

    gql = "https:" + "//mightyzeus.housing.com/api/gql?apiName=DETAILS&isBot=false&source=web"
    hdrs = {"Accept": "application/json", "Origin": "https:" + "//housing.com", "Referer": "https:" + "//housing.com/"}
    q = (
        f'{{ details(propertyId: {pid}, propertyType: "{ptype}") {{'
        ' furnishingType propertyVideoUrl'
        ' coverImage { src alt caption type tag }'
        ' details { images { type images { src alt caption tag category } } }'
        ' } }'
    )
    r = creq.post(gql, json={"query": q}, headers=hdrs, impersonate="chrome124", timeout=12)
    if r.status_code != 200:
        return {"imgs": [], "vids": [], "furn": "", "st": r.status_code}
    det = ((r.json() or {}).get("data") or {}).get("details")
    if not isinstance(det, dict):
        return {"imgs": [], "vids": [], "furn": "", "st": 404}

    prop_imgs, proj_imgs = [], []
    cov = det.get("coverImage") or {}
    if isinstance(cov, dict) and cov.get("src"):
        cap0 = f"{cov.get('caption') or ''} {cov.get('alt') or ''} {cov.get('tag') or ''}"
        u0 = _norm_housing_src(cov["src"])
        if u0 and not BAD_CAPTION_RE.search(cap0) and not BAD_URL_RE.search(u0):
            prop_imgs.append(u0)

    for grp in ((det.get("details") or {}).get("images") or []):
        if not isinstance(grp, dict):
            continue
        gtype = str(grp.get("type") or "")
        if HS_BAD_GROUP_RE.search(gtype):
            continue
        is_proj = "project" in gtype.lower() or "society" in gtype.lower() or "exterior" in gtype.lower()
        for item in (grp.get("images") or []):
            if not isinstance(item, dict):
                continue
            cap = f"{item.get('caption') or ''} {item.get('alt') or ''} {item.get('tag') or ''} {item.get('category') or ''}"
            if BAD_CAPTION_RE.search(cap) or ("model flat" in cap.lower() and "render" in cap.lower()):
                continue
            u = _norm_housing_src(item.get("src") or "")
            if not u or BAD_URL_RE.search(u):
                continue
            if is_proj:
                if len(proj_imgs) < 3:
                    proj_imgs.append(u)
            else:
                prop_imgs.append(u)

    raw_imgs = prop_imgs + proj_imgs
    imgs, _ = _dedupe_rank_urls(raw_imgs, cap=12)

    vids = []
    pv = str(det.get("propertyVideoUrl") or "").strip()
    if pv:
        yt = re.search(r"(?:youtube\.com/embed/|youtu\.be/|watch\?v=)([A-Za-z0-9_-]{11})", pv)
        if yt:
            vids.append({"url": "https:" + "//www.youtube.com/embed/" + yt.group(1), "kind": "youtube"})
        elif re.search(r"\.(?:mp4|m3u8|webm)", pv, re.I):
            vids.append({"url": pv, "kind": "video"})

    furn = ""
    ft = str(det.get("furnishingType") or "").lower()
    if "semi" in ft:
        furn = "semi"
    elif "unfurn" in ft:
        furn = "unfurnished"
    elif "full" in ft or "furn" in ft:
        furn = "furnished"

    soc_nm = ""
    alt0 = str((cov or {}).get("alt") or "")
    am = re.search(r"\bfor\s+(?:rent|sale)\s+in\s+([^,]{3,65})", alt0, re.I)
    if am:
        soc_nm = _clean_soc_candidate(am.group(1))
    return {"imgs": imgs, "vids": vids[:2], "furn": furn, "soc": soc_nm, "dep": 0, "flr": "", "fac": "", "dead": False, "st": 200}

def fetch_one(item):
    src, url = item
    try:
        if src == "housing":
            res = _extract_housing_gql(url)
            res["ts"] = int(time.time())
            return url, res
        r = creq.get(url, impersonate="chrome124", timeout=14, headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        })
        if r.status_code != 200 or len(r.text or "") < 4000:
            return url, {"imgs": [], "vids": [], "furn": "", "st": r.status_code, "ts": int(time.time())}
        if src == "nobroker":
            res = _extract_nobroker(r.text, url)
        elif src == "magicbricks":
            res = _extract_magicbricks(r.text, url)
        elif src == "99acres":
            res = _extract_99acres(r.text, url)
        else:
            res = {"imgs": [], "vids": [], "furn": ""}
        res["st"] = 200
        res["ts"] = int(time.time())
        return url, res
    except Exception as e:
        return url, {"imgs": [], "vids": [], "furn": "", "st": -1, "err": str(e)[:60], "ts": int(time.time())}

def collect_targets(socs_all, cache, limit=400, focus_names=None, allowed_portals=None):
    prio, seen_u = [], set()
    focus_low = [x.lower() for x in (focus_names or [])]

    for s in socs_all:
        nm = str(s.get("name") or "").lower()
        is_focus = any(fn in nm for fn in focus_low)
        for uk in ("units_rent", "units_buy"):
            for u in (s.get(uk) or []):
                src, url = u.get("s"), u.get("u")
                _ok_p = allowed_portals or {"housing", "nobroker", "magicbricks", "99acres"}
                if src not in _ok_p or not url or url in seen_u:
                    continue
                if url in cache and not is_focus:
                    continue
                seen_u.add(url)
                u_imgs = ([u["img"]] if u.get("img") else []) + list(u.get("imgs") or [])
                n_img = len(set(u_imgs))
                is_t_only = src == "99acres" and n_img > 0 and all(re.search(r"/\d+T-\d+\.", x) for x in u_imgs)
                mode_pen = 0 if uk == "units_rent" else 10
                if is_focus:
                    p = 0
                elif src == "housing" and n_img <= 1:
                    p = 1 + mode_pen
                elif src == "99acres" and n_img == 0:
                    p = 2 + mode_pen
                elif src == "nobroker" and n_img <= 1:
                    p = 3 + mode_pen
                elif src == "magicbricks" and n_img <= 1:
                    p = 4 + mode_pen
                elif is_t_only:
                    p = 5 + mode_pen
                else:
                    continue
                prio.append((p, src, url))

    prio.sort(key=lambda x: x[0])
    by_p = {"housing": [], "nobroker": [], "magicbricks": [], "99acres": []}
    ordered = []
    for p, src, url in prio:
        if p == 0:
            ordered.append((src, url))
        else:
            by_p[src].append((src, url))
    while len(ordered) < limit and any(by_p.values()):
        for src in ("housing", "nobroker", "magicbricks", "99acres"):
            if by_p[src] and len(ordered) < limit:
                ordered.append(by_p[src].pop(0))
    return ordered[:limit]

def apply_cache_to_societies(socs, cache):
    updated_units, vids_added, furn_added = 0, 0, 0
    for s in socs:
        soc_vids = list(s.get("videos") or [])
        seen_v = {v.get("url") for v in soc_vids if isinstance(v, dict)}
        soc_raw_imgs = ([s["thumb"]] if s.get("thumb") else []) + list(s.get("photos") or [])
        changed = False

        for uk in ("units_rent", "units_buy"):
            for u in (s.get(uk) or []):
                url = u.get("u")
                entry = cache.get(url) if url else None
                if not entry:
                    continue
                e_imgs = entry.get("imgs") or []
                e_vids = entry.get("vids") or []
                e_furn = entry.get("furn") or ""
                if e_imgs:
                    u_raw = ([u["img"]] if u.get("img") else []) + list(u.get("imgs") or []) + e_imgs
                    u_clean, _ = _dedupe_rank_urls(u_raw, cap=8)
                    if len(u_clean) > len(u.get("imgs") or []) or (u_clean and u.get("img") != u_clean[0]):
                        u["img"] = u_clean[0]
                        if len(u_clean) > 1:
                            u["imgs"] = u_clean
                        updated_units += 1
                        changed = True
                    soc_raw_imgs.extend(u_clean)
                if e_vids:
                    u["vids"] = e_vids[:2]
                    for v in e_vids:
                        if v.get("url") and v["url"] not in seen_v:
                            seen_v.add(v["url"])
                            soc_vids.append(v)
                            vids_added += 1
                            changed = True
                if e_furn and not u.get("f"):
                    u["f"] = e_furn
                    furn_added += 1
                if entry.get("dep") and not u.get("dep"):
                    u["dep"] = entry["dep"]
                if entry.get("flr") and not u.get("flr"):
                    u["flr"] = entry["flr"]
                if entry.get("fac") and not u.get("fac"):
                    u["fac"] = entry["fac"]
                if entry.get("soc") and re.match(r"^(?:\d(?:\.\d)?\s*(?:bhk|rk)|flat|studio|apartment)\b", str(s.get("name") or ""), re.I):
                    s["name"] = entry["soc"]

        if changed:
            soc_clean, _ = _dedupe_rank_urls(soc_raw_imgs, cap=12)
            if soc_clean:
                s["thumb"] = soc_clean[0]
                if len(soc_clean) > 1:
                    s["photos"] = soc_clean
            if soc_vids:
                s["videos"] = soc_vids[:4]
    return updated_units, vids_added, furn_added

def run(limit=400, workers=6, max_seconds=600, focus=None, apply_only=False, portals=None):
    man_p = ROOT / "web/public/data/manifest.json"
    man = json.loads(man_p.read_text(encoding="utf-8-sig"))
    shard_groups, all_socs = [], []
    for key in ("rent_shards", "buy_shards"):
        paths = [ROOT / "web/public/data" / sf for sf in (man.get(key) or []) if (ROOT / "web/public/data" / sf).exists()]
        group_socs = []
        for sp in paths:
            b = json.loads(sp.read_text(encoding="utf-8-sig"))
            group_socs.extend(b if isinstance(b, list) else (b.get("societies") or []))
        shard_groups.append((key, paths, group_socs))
        all_socs.extend(group_socs)

    cache = load_cache()
    if not apply_only and limit > 0:
        targets = collect_targets(all_socs, cache, limit=limit, focus_names=focus, allowed_portals=portals)
        print(f"[MEDIA HARVEST] Cache={len(cache):,} | Targets={len(targets):,} | workers={workers}")
        t0 = time.time()
        ok_n, img_n, vid_n, done_n = 0, 0, 0, 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(fetch_one, t) for t in targets]
            for fut in as_completed(futs):
                url, res = fut.result()
                cache[url] = res
                done_n += 1
                if res.get("st") == 200:
                    ok_n += 1
                    img_n += len(res.get("imgs") or [])
                    vid_n += len(res.get("vids") or [])
                if done_n % 50 == 0:
                    save_cache(cache)
                    print(f"  progress {done_n}/{len(targets)} | ok={ok_n} | imgs={img_n} | vids={vid_n} | {round(time.time()-t0)}s")
                if time.time() - t0 > max_seconds:
                    break
        save_cache(cache)
        print(f"[MEDIA HARVEST DONE] Fetched={done_n} | HTTP200={ok_n} | TotalImgs={img_n} | Videos={vid_n} | Time={round(time.time()-t0)}s")

    tot_u, tot_v, tot_f = 0, 0, 0
    for key, paths, group_socs in shard_groups:
        u_n, v_n, f_n = apply_cache_to_societies(group_socs, cache)
        tot_u += u_n; tot_v += v_n; tot_f += f_n
        chunk = math.ceil(len(group_socs) / max(1, len(paths)))
        for i, sp in enumerate(paths):
            sp.write_text(json.dumps(group_socs[i * chunk : (i + 1) * chunk], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[MEDIA APPLIED] Units upgraded={tot_u:,} | Videos added={tot_v:,} | Furnishing recovered={tot_f:,}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-seconds", type=int, default=600)
    ap.add_argument("--focus", type=str, default="")
    ap.add_argument("--apply-only", action="store_true")
    ap.add_argument("--portals", type=str, default="")
    args = ap.parse_args()
    flist = [x.strip() for x in args.focus.split(",") if x.strip()]
    pset = {x.strip().lower() for x in args.portals.split(",") if x.strip()} or None
    run(limit=args.limit, workers=args.workers, max_seconds=args.max_seconds, focus=flist, apply_only=args.apply_only, portals=pset)
