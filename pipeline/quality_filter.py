import json, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "data/listing_registry.json"

DEAD_SOURCES = {"dwelo", "commonfloor", "stanza", "zolostays", "findghosla", "ghosla"}
PLACEHOLDER_IMG_RE = re.compile(r"(?:no[-_]?image|not[-_]?available|placeholder|default[-_]?prop|coming[-_]?soon|no[-_]?photo)", re.I)
SPAM_NAME_RE = re.compile(r"^(?:test|demo|sample|call\s+for\s+price|contact\s+for\s+price|na|n/a|none|null)$", re.I)
PORTAL_PRIORITY = {"nobroker": 0, "99acres": 1, "housing": 2, "magicbricks": 3, "squareyards": 4, "makaan": 5, "nextflat": 6, "community": 0}

def _clean_url(u):
    if not isinstance(u, str):
        return ""
    u = u.strip().split("?")[0].rstrip("/")
    return u if u.startswith("http") else ""

def _clean_img(u):
    if not isinstance(u, str) or not u.startswith("http"):
        return None
    if PLACEHOLDER_IMG_RE.search(u):
        return None
    if "housingcdn.com" in u and "/version/" in u:
        u = u.replace("/version/", "/fs/")
    return u

def _valid_price(p, mode):
    try:
        v = int(float(p))
    except Exception:
        return None
    if mode == "rent":
        return v if 4000 <= v <= 1_500_000 else None
    return v if 1_200_000 <= v <= 1_500_000_000 else None

def _load_registry():
    if not REGISTRY_PATH.exists():
        return {}
    try:
        d = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _save_registry(reg):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(reg, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

def filter_and_track_societies(socs, expire_days=21):
    reg = _load_registry()
    today_day = int(time.time() // 86400)
    stats = {
        "dropped_bad_price": 0, "dropped_dead_src": 0, "dropped_clones": 0,
        "dropped_spam": 0, "new_today": 0, "price_drops": 0, "expired_stale": 0,
    }

    cleaned_socs = []
    seen_global_urls = set()

    for s in socs:
        if not isinstance(s, dict):
            continue
        nm = str(s.get("name") or "").strip()
        if not nm or SPAM_NAME_RE.match(nm):
            stats["dropped_spam"] += 1
            continue

        if isinstance(s.get("lat"), float): s["lat"] = round(s["lat"], 5)
        if isinstance(s.get("lng"), float): s["lng"] = round(s["lng"], 5)

        thumb = _clean_img(s.get("thumb"))
        extra_photos = []
        def _addp(url):
            cu = _clean_img(url)
            if cu and cu != thumb and cu not in extra_photos:
                extra_photos.append(cu)
        for p in (s.get("photos") or []):
            _addp(p)

        soc_price_drop = False
        min_age_days = 999

        for uk, mode in (("units_rent", "rent"), ("units_buy", "buy")):
            raw_u = s.get(uk)
            if not isinstance(raw_u, list):
                s[uk] = []
                continue

            valid_units = []
            for u in raw_u:
                if not isinstance(u, dict):
                    continue
                src = str(u.get("s") or "").lower().strip()
                if src in DEAD_SOURCES:
                    stats["dropped_dead_src"] += 1
                    continue
                p_val = _valid_price(u.get("p"), mode)
                if not p_val:
                    stats["dropped_bad_price"] += 1
                    continue
                uu = _clean_url(u.get("u"))
                if uu and uu in seen_global_urls:
                    stats["dropped_clones"] += 1
                    continue

                sq = u.get("sq")
                if sq is not None:
                    try:
                        sq_i = int(float(sq))
                        sq = sq_i if 120 <= sq_i <= 15000 else None
                    except Exception:
                        sq = None

                u_img = _clean_img(u.get("img"))
                if u_img:
                    if not thumb:
                        thumb = u_img
                    else:
                        _addp(u_img)
                for xi in (u.get("imgs") or []):
                    _addp(xi)

                age_d = 0
                if uu:
                    ent = reg.get(uu)
                    if ent is None:
                        reg[uu] = [today_day, today_day, p_val, 0]
                        stats["new_today"] += 1
                        age_d = 0
                    else:
                        first_d, last_d, prev_p, drop_pct = ent
                        if prev_p and p_val < prev_p:
                            pct = round(100.0 * (prev_p - p_val) / prev_p, 1)
                            if pct >= 5.0:
                                drop_pct = max(drop_pct, pct)
                                stats["price_drops"] += 1
                                soc_price_drop = True
                        elif drop_pct >= 5.0:
                            soc_price_drop = True
                        reg[uu] = [first_d, today_day, p_val, drop_pct]
                        age_d = max(0, today_day - first_d)
                min_age_days = min(min_age_days, age_d)

                clean_u = {"p": p_val, "s": src or "portal"}
                if u.get("b") is not None: clean_u["b"] = u["b"]
                if sq: clean_u["sq"] = sq
                if uu: clean_u["u"] = uu
                if u.get("zb"): clean_u["zb"] = True
                if u.get("lt"): clean_u["lt"] = u["lt"]
                if u.get("f"): clean_u["f"] = u["f"]
                if u_img and u_img != thumb: clean_u["img"] = u_img
                valid_units.append(clean_u)

            valid_units.sort(
                key=lambda x: (
                    0 if x.get("zb") else 1,
                    0 if x.get("img") else 1,
                    0 if x.get("sq") else 1,
                    PORTAL_PRIORITY.get(x.get("s"), 9),
                    x.get("p") or 999999999,
                )
            )
            deduped = []
            for u in valid_units:
                is_clone = False
                up, ub, usq = u["p"], u.get("b"), u.get("sq")
                for ex in deduped:
                    if ex.get("b") == ub:
                        ep = ex["p"]
                        if ep > 0 and abs(up - ep) / ep <= 0.03:
                            esq = ex.get("sq")
                            if (not u.get("zb") and (ex.get("s") == u.get("s") or ex.get("zb"))) or (usq and esq and abs(usq - esq) / esq <= 0.05):
                                is_clone = True
                                break
                if is_clone:
                    stats["dropped_clones"] += 1
                    continue
                if u.get("u"):
                    seen_global_urls.add(u["u"])
                deduped.append(u)

            s[uk] = deduped

        if not (s.get("units_rent") or []) and not (s.get("units_buy") or []):
            continue

        if thumb: s["thumb"] = thumb
        else: s.pop("thumb", None)
        if extra_photos: s["photos"] = extra_photos[:6]
        else: s.pop("photos", None)

        if min_age_days < 999: s["age_days"] = min_age_days
        if soc_price_drop: s["price_drop"] = True

        comm = s.get("commutes")
        if isinstance(comm, dict):
            comm.pop("bkc_min", None)
            s["commutes"] = {k: v for k, v in comm.items() if v is not None}
        ctx = s.get("mumbai_context")
        if isinstance(ctx, dict):
            for sub in ("nearest_metro", "nearest_train"):
                if isinstance(ctx.get(sub), dict):
                    ctx[sub].pop("km", None)
            s["mumbai_context"] = {k: v for k, v in ctx.items() if v is not None}
        for dk in ("pricing", "civic", "google"):
            d = s.get(dk)
            if isinstance(d, dict):
                s[dk] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items() if v is not None and v != "" and v != []}
        for fk in ("is_unnamed", "is_new", "coords_approx", "deal", "rera_carpet_sqft", "furnishing"):
            if s.get(fk) in (False, None, ""):
                s.pop(fk, None)
        for ek in ("features", "rera_ids"):
            if s.get(ek) == []:
                s.pop(ek, None)
        for sk in ("sources", "sources_rent", "sources_buy"):
            sv = s.get(sk)
            if isinstance(sv, list):
                s[sk] = [x for x in sv if str(x).lower() not in DEAD_SOURCES]
            elif isinstance(sv, dict):
                for ds in DEAD_SOURCES:
                    sv.pop(ds, None)

        cleaned_socs.append(s)

    stale_keys = [k for k, v in reg.items() if isinstance(v, list) and len(v) >= 2 and (today_day - int(v[1])) > expire_days]
    for k in stale_keys:
        reg.pop(k, None)
    stats["expired_stale"] = len(stale_keys)

    _save_registry(reg)
    print(
        f"[QUALITY FILTER] Kept {len(cleaned_socs):,} buildings | "
        f"Dropped: {stats['dropped_clones']} clones, {stats['dropped_bad_price']} bad-price, "
        f"{stats['dropped_dead_src']} dead-src | "
        f"Delta: +{stats['new_today']} new, {stats['price_drops']} price-drops, {stats['expired_stale']} expired"
    )
    return cleaned_socs, stats
