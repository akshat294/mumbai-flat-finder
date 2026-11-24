import math, re
from pipeline.connectors.v19_common import LOC_MAP, haversine_km, clean_soc_name, is_generic_name

_LOC_SLUGS = sorted(
    [(loc.lower().replace(" ", "-"), val) for loc, val in LOC_MAP.items() if len(loc) >= 4],
    key=lambda x: -len(x[0]),
)

def _url_explicit_locality(url):
    if not url:
        return None
    path = str(url).lower().split("?")[0]
    for slug, val in _LOC_SLUGS:
        if re.search(r"(?:^|[-/_])" + re.escape(slug) + r"(?:$|[-/_])", path):
            return val
    return None

def _extract_name_from_url(url, loc):
    if not url:
        return None
    u = str(url).split("?")[0]
    m_mb = re.search(r"FOR-(?:Rent|Sale)-([A-Za-z0-9-]+?)-in-(?:Mumbai|Thane|Navi-Mumbai)", u, re.I)
    if m_mb:
        cand = m_mb.group(1).replace("-", " ").strip()
        if cand and cand.lower() != loc.lower() and not is_generic_name(cand, loc):
            return clean_soc_name(cand, loc)
    m_99 = re.search(r"for-(?:rent|sale)-in-([a-z0-9-]+?)-(?:mumbai|western-mumbai|south-mumbai|central-mumbai|navi-mumbai|thane)", u, re.I)
    if m_99:
        cand = re.sub(r"\b" + re.escape(loc.lower()) + r"\b", "", m_99.group(1).replace("-", " "), flags=re.I).strip()
        if len(cand) >= 4 and not is_generic_name(cand, loc):
            return clean_soc_name(cand.title(), loc)
    m_nb = re.search(r"for-(?:rent|sale)-in-([a-z0-9-]+?)-(?:mumbai|thane|navi-mumbai)-for-rs", u, re.I)
    if m_nb:
        cand = re.sub(r"\b" + re.escape(loc.lower()) + r"\b", "", m_nb.group(1).replace("-", " "), flags=re.I).strip()
        if len(cand) >= 4 and not is_generic_name(cand, loc):
            return clean_soc_name(cand.title(), loc)
    return None

def _is_mega_bucket_name(name, loc):
    n = str(name or "").strip()
    if not n or n.lower() == str(loc or "").strip().lower() or is_generic_name(n, loc):
        return True
    return bool(re.match(r"^(?:\d\s*(?:bhk|rk)|studio)\s*(?:flat|apartment|house)?$", n, re.I))

def _recompute_pricing(s):
    ur = [u for u in (s.get("units_rent") or []) if isinstance(u, dict) and u.get("p")]
    ub = [u for u in (s.get("units_buy") or []) if isinstance(u, dict) and u.get("p")]
    pr = s.setdefault("pricing", {})
    if ur:
        ps = sorted(int(u["p"]) for u in ur)
        pr["rent_min"], pr["rent_max"], pr["rent_med"] = ps[0], ps[-1], ps[len(ps) // 2]
        pr["has_zero_brokerage"] = any(bool(u.get("zb")) or u.get("lt") == "owner" for u in ur)
    if ub:
        ps = sorted(int(u["p"]) for u in ub)
        pr["buy_min"], pr["buy_max"], pr["buy_med"] = ps[0], ps[-1], ps[len(ps) // 2]
    bhks = sorted({int(float(u["b"])) for u in (ur + ub) if u.get("b") is not None})
    if bhks:
        s["bhks"] = bhks

def run_data_hygiene(socs):
    rehomed, split_b, renamed, typos, approx_f = 0, 0, 0, 0, 0
    extra_socs = []

    for idx, s in enumerate(socs):
        cur_loc = str(s.get("locality") or "").strip()
        cur_name = str(s.get("name") or "").strip()

        # 1. Strip obvious broker price typos (2BHK+ rent < Rs 12,000/mo)
        ur = s.get("units_rent") or []
        if ur:
            clean_ur = []
            for u in ur:
                if not isinstance(u, dict):
                    continue
                b, p = u.get("b"), u.get("p") or 0
                if b is not None and float(b) >= 2 and 0 < p < 12000:
                    typos += 1
                    continue
                clean_ur.append(u)
            s["units_rent"] = clean_ur

        # 2. Re-home units whose portal URL explicitly names a DIFFERENT Mumbai locality
        for mode_k, src_k in (("units_rent", "sources_rent"), ("units_buy", "sources_buy")):
            units = s.get(mode_k) or []
            if not units:
                continue
            stay, moved = [], {}
            for u in units:
                if not isinstance(u, dict):
                    continue
                det = _url_explicit_locality(u.get("u"))
                if det and det[0].lower() != cur_loc.lower():
                    if s.get("lat") and s.get("lng") and haversine_km(float(s["lat"]), float(s["lng"]), det[2], det[3]) <= 2.2:
                        stay.append(u)
                    else:
                        moved.setdefault(det[0], (det, []))[1].append(u)
                else:
                    stay.append(u)

            if moved:
                other_k = "units_buy" if mode_k == "units_rent" else "units_rent"
                if not stay and len(moved) == 1 and not s.get(other_k):
                    new_loc, new_zone, mlat, mlng = next(iter(moved.values()))[0]
                    s["locality"], s["zone"] = new_loc, new_zone
                    if not s.get("lat") or not s.get("lng") or haversine_km(float(s["lat"]), float(s["lng"]), mlat, mlng) > 3.5:
                        ang = (abs(hash(s.get("id") or cur_name)) % 360) * math.pi / 180.0
                        rad = 0.0014 + ((idx % 7) * 0.0003)
                        s["lat"] = round(mlat + rad * math.cos(ang), 6)
                        s["lng"] = round(mlng + rad * math.sin(ang), 6)
                        s["coords_approx"] = True
                    rehomed += sum(len(v[1]) for v in moved.values())
                    cur_loc = new_loc
                else:
                    s[mode_k] = stay
                    for new_loc, (det, m_u) in moved.items():
                        _, new_zone, mlat, mlng = det
                        ang = (abs(hash(cur_name + new_loc)) % 360) * math.pi / 180.0
                        rad = 0.0014 + ((len(extra_socs) % 7) * 0.0003)
                        new_s = {
                            "id": f"bh-rh-{abs(hash((m_u[0].get('u') or cur_name) + new_loc)) % 10000000}",
                            "name": _extract_name_from_url(m_u[0].get("u"), new_loc) or cur_name,
                            "locality": new_loc, "zone": new_zone,
                            "lat": round(mlat + rad * math.cos(ang), 6),
                            "lng": round(mlng + rad * math.sin(ang), 6),
                            "coords_approx": True,
                            "units_rent": m_u if mode_k == "units_rent" else [],
                            "units_buy": m_u if mode_k == "units_buy" else [],
                            "thumb": next((u.get("img") for u in m_u if u.get("img")), s.get("thumb")),
                            "mumbai_context": {}, "commutes": {},
                            "sources": {u.get("s"): u.get("u") for u in m_u if u.get("s") and u.get("u")},
                            src_k: {u.get("s"): u.get("u") for u in m_u if u.get("s") and u.get("u")},
                            "features": s.get("features") or {},
                            "is_new": bool(s.get("is_new")),
                        }
                        _recompute_pricing(new_s)
                        extra_socs.append(new_s)
                        rehomed += len(m_u)

        # 3. Split generic/locality mega-buckets & never mark them "Verified Building Pin"
        if _is_mega_bucket_name(s.get("name"), s.get("locality")):
            if not s.get("coords_approx"):
                s["coords_approx"] = True
                approx_f += 1
            all_u = [("rent", u) for u in (s.get("units_rent") or [])] + [("buy", u) for u in (s.get("units_buy") or [])]
            if len(all_u) >= 2:
                split_b += 1
                m0, u0 = all_u[0]
                s["units_rent"] = [u0] if m0 == "rent" else []
                s["units_buy"] = [u0] if m0 == "buy" else []
                un0 = _extract_name_from_url(u0.get("u"), cur_loc)
                if un0:
                    s["name"] = un0
                    renamed += 1
                else:
                    b0 = u0.get("b")
                    bl = "1 RK" if b0 == 0 else (f"{int(float(b0))} BHK" if b0 else "Flat")
                    s["name"] = f"{bl} in {cur_loc}"
                ph0 = [p for p in ([u0.get("img")] + list(u0.get("imgs") or [])) if isinstance(p, str) and p.startswith("http")][:5]
                if ph0:
                    s["thumb"], s["photos"] = ph0[0], ph0
                _recompute_pricing(s)

                mlat, mlng = LOC_MAP.get(cur_loc.lower(), (cur_loc, "", float(s.get("lat") or 19.07), float(s.get("lng") or 72.87)))[2:4]
                for ki, (mk, uk) in enumerate(all_u[1:], 1):
                    unk = _extract_name_from_url(uk.get("u"), cur_loc)
                    if unk:
                        nmk = unk
                        renamed += 1
                    else:
                        bk = uk.get("b")
                        bl = "1 RK" if bk == 0 else (f"{int(float(bk))} BHK" if bk else "Flat")
                        nmk = f"{bl} in {cur_loc}"
                    ang = ((abs(hash(uk.get("u") or str(ki))) + ki * 41) % 360) * math.pi / 180.0
                    rad = 0.0011 + ((ki % 9) * 0.00032)
                    phk = [p for p in ([uk.get("img")] + list(uk.get("imgs") or [])) if isinstance(p, str) and p.startswith("http")][:5]
                    ns = {
                        "id": f"bh-sp-{abs(hash(uk.get('u') or (cur_loc + str(ki)))) % 10000000}",
                        "name": nmk, "locality": cur_loc, "zone": s.get("zone") or "",
                        "lat": round(mlat + rad * math.cos(ang), 6),
                        "lng": round(mlng + rad * math.sin(ang), 6),
                        "coords_approx": True,
                        "units_rent": [uk] if mk == "rent" else [],
                        "units_buy": [uk] if mk == "buy" else [],
                        "thumb": phk[0] if phk else None, "photos": phk,
                        "mumbai_context": {}, "commutes": {},
                        "sources": {uk.get("s"): uk.get("u")} if uk.get("s") and uk.get("u") else {},
                        ("sources_rent" if mk == "rent" else "sources_buy"): {uk.get("s"): uk.get("u")} if uk.get("s") and uk.get("u") else {},
                        "features": s.get("features") or {},
                        "is_new": bool(s.get("is_new")),
                    }
                    _recompute_pricing(ns)
                    extra_socs.append(ns)
            elif len(all_u) == 1:
                un0 = _extract_name_from_url(all_u[0][1].get("u"), cur_loc)
                if un0:
                    s["name"] = un0
                    renamed += 1

    socs[:] = [s for s in socs if (s.get("units_rent") or s.get("units_buy"))] + extra_socs
    print(f"[v37 HYGIENE] Re-homed: {rehomed} | Split buckets: {split_b} (+{len(extra_socs)} cards) | Named from URL: {renamed} | Approx-pin fixed: {approx_f} | Typos dropped: {typos}")
    return socs
_BAD_IMG_RE = re.compile(
    r"(floor[-_]?plan|master[-_]?plan|site[-_]?plan|unit[-_]?plan|location[-_]?map|"
    r"3d[-_]?plan|3d[-_]?render|layout|blueprint|brochure|elevation|under_screening|"
    r"fbshare|static\.99acres\.com|assets\.nobroker\.in|no[-_]?image|no[-_]?photo|"
    r"placeholder|default[-_]?img|avatar|logo|\.svg(?:\?|$)|\.gif(?:\?|$))",
    re.I,
)
_RE_99_ID = re.compile(r"imagecdn\.99acres\.com/.*/(\d+)([A-Z])-\d+\.", re.I)
_RE_NB_VAR = re.compile(r"_(?:thumbnail|small|medium|large|original|enhance_large|enhance_medium)(?=\.[a-z]+$)", re.I)
_RE_HS_ID = re.compile(r"/([a-f0-9]{16,40})/v\d+/([^/]+)/", re.I)
_RE_FLOAT_BHK = re.compile(r"\b(\d+)\.0\s*(BHK|RK)\b", re.I)

def _media_key_rank(raw):
    if not isinstance(raw, str):
        return None
    u = raw.strip()
    if not re.match(r"^https?://", u, re.I) or len(u) < 24 or _BAD_IMG_RE.search(u):
        return None
    if "housingcdn.com/" in u or "housing-images.n7net.in/" in u:
        u = re.sub(r"/v(\d+)/(?:version|fs_medium|medium|small|thumb)/", r"/v\1/fs/", u, flags=re.I)
    elif "images.nobroker.in/images/" in u:
        u = re.sub(r"_(?:thumbnail|small)\.", "_large.", u, flags=re.I)

    clean = u.split("?")[0]
    m99 = _RE_99_ID.search(clean)
    if m99:
        c = m99.group(2).upper()
        rank = {"O": 5, "L": 4, "M": 3, "F": 2}.get(c, 1)
        return u, "99:" + m99.group(1), rank
    if "images.nobroker.in/images/" in clean:
        k = _RE_NB_VAR.sub("", clean).lower()
        rank = 4 if "_original." in clean.lower() else (3 if "_large." in clean.lower() else (2 if "_medium." in clean.lower() else 1))
        return u, "nb:" + k, rank
    if "housingcdn.com" in clean or "n7net.in" in clean:
        mh = _RE_HS_ID.search(clean)
        if mh:
            vn = mh.group(2).lower()
            rank = 4 if vn == "fs" else (3 if "large" in vn else 2)
            return u, "hs:" + mh.group(1).lower(), rank
    dk = re.sub(r"/(?:thumb|medium|small|large|original|cropped|resized|fs|fs_medium|version)/", "/", clean, flags=re.I)
    dk = re.sub(r"[_\-]\d+x\d+(?=\.[a-z]+$)", "", dk, flags=re.I)
    dk = re.sub(r"[_\-](?:small|medium|large|thumb|thumbnail|original)(?=\.[a-z]+$)", "", dk, flags=re.I).lower()
    return u, dk, 2

def _dedupe_urls(urls, cap=8):
    by_k, order = {}, []
    for raw in (urls or []):
        info = _media_key_rank(raw)
        if not info:
            continue
        u, k, rank = info
        if k not in by_k:
            by_k[k] = (u, rank)
            order.append(k)
        elif rank > by_k[k][1]:
            by_k[k] = (u, rank)
    return [by_k[k][0] for k in order][:cap], {k: v[0] for k, v in by_k.items()}

def clean_fleet_media(socs):
    stats = {"float_names": 0, "urls_before": 0, "urls_after": 0, "thumbs_upgraded": 0}
    for s in socs:
        if not isinstance(s, dict):
            continue
        nm = str(s.get("name") or "")
        nm2 = _RE_FLOAT_BHK.sub(r"\1 \2", nm)
        if nm2 != nm:
            s["name"] = nm2
            stats["float_names"] += 1

        raw_soc = []
        if s.get("thumb"):
            raw_soc.append(s["thumb"])
        raw_soc.extend(s.get("photos") or [])

        us = list(s.get("units_rent") or []) + list(s.get("units_buy") or [])
        for u in us:
            if not isinstance(u, dict):
                continue
            if u.get("img"):
                raw_soc.append(u["img"])
            raw_soc.extend(u.get("imgs") or [])

        stats["urls_before"] += len(s.get("photos") or []) + (1 if s.get("thumb") else 0)
        old_thumb = s.get("thumb")
        soc_clean, best_by_k = _dedupe_urls(raw_soc, cap=8)
        stats["urls_after"] += len(soc_clean)

        for u in us:
            if not isinstance(u, dict):
                continue
            u_raw = ([u.get("img")] if u.get("img") else []) + list(u.get("imgs") or [])
            stats["urls_before"] += len(u_raw)
            u_up = []
            for r in u_raw:
                info = _media_key_rank(r)
                if info:
                    u_up.append(best_by_k.get(info[1], info[0]))
            u_clean, _ = _dedupe_urls(u_up, cap=6)
            stats["urls_after"] += len(u_clean)
            if u_clean:
                u["img"] = u_clean[0]
                if len(u_clean) > 1:
                    u["imgs"] = u_clean
                else:
                    u.pop("imgs", None)
            else:
                u.pop("img", None)
                u.pop("imgs", None)

        if soc_clean:
            s["thumb"] = soc_clean[0]
            if old_thumb and old_thumb != soc_clean[0]:
                stats["thumbs_upgraded"] += 1
            if len(soc_clean) > 1:
                s["photos"] = soc_clean
            else:
                s.pop("photos", None)
        else:
            s.pop("thumb", None)
            s.pop("photos", None)
    return stats
