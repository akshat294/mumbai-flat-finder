import json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.mumbai_transit import enrich_transit_context, _hav_km
from pipeline.data_hygiene import _media_key_rank, _RE_FLOAT_BHK

ACRONYMS = {
    "chs", "chsl", "co-op", "bhk", "rk", "bkc", "lic", "mhada", "cidco", "hdil",
    "jvpd", "midc", "seepz", "ic", "sv", "mg", "lbs", "db", "jp", "rn",
    "nk", "gs", "ii", "iii", "iv", "vi", "vii", "viii", "sr", "jr", "it", "ai", "rd",
}
COMMON_PREFIX_WORDS = {
    "sai", "om", "shree", "shri", "sri", "shiv", "ganesh", "ram", "krishna",
    "lakshmi", "mahalaxmi", "siddhi", "riddhi", "guru", "jai", "dev", "radha",
    "gokul", "tulsi", "new", "royal", "green", "silver", "golden", "grand",
    "blue", "sun", "star", "lake", "sea", "palm", "crystal", "diamond", "pearl",
    "baba", "mata", "maa", "mahadev", "balaji", "tirupati", "hanuman", "durga",
}
STOP_WORDS = {
    "chs", "chsl", "society", "tower", "towers", "heights", "apartment", "apartments",
    "residency", "residences", "complex", "building", "wing", "phase", "sector",
    "west", "east", "north", "south", "mumbai", "thane", "navi", "road", "marg", "nagar",
    "colony", "park", "enclave", "plaza", "court", "view", "new", "shree", "shri", "sri",
}
PLUS_OR_FLAT_RE = re.compile(r"^(?:[2-9a-z]{4}\+[2-9a-z]{2,4}|(?:[a-z]{1,2}[\s\-/]*)?\d{1,4}[a-z]?)$", re.I)
AD_SENTENCE_RE = re.compile(
    r"\b(?:for\s+rent|for\s+sale|looking\s+for\s+(?:a\s+)?(?:female|male)?\s*flatmate|"
    r"available\s+for|sq\.?\s*ft\.?|immediate\s+possession|well\s+maintained)\b",
    re.I,
)

def _smart_title_case(name):
    s = re.sub(r"\s+", " ", str(name or "").strip())
    s = _RE_FLOAT_BHK.sub(r"\1 \2", s)
    if not s:
        return s
    if s == s.lower() or (len(s) > 4 and s == s.upper()):
        out = []
        for w in s.split(" "):
            clean_w = re.sub(r"[^a-zA-Z0-9]", "", w).lower()
            if clean_w in ACRONYMS:
                out.append(w.upper())
            elif re.match(r"^[a-z]\.[a-z]\.?$", w, re.I):
                out.append(w.upper())
            else:
                out.append(w[:1].upper() + w[1:].lower() if w else w)
        s = " ".join(out)
    return s

def upgrade_media_url(raw):
    if not isinstance(raw, str):
        return raw
    u = raw.strip()
    if "img.staticmb.com/mbphoto/property/" in u and "Photo_h180_w240" in u:
        u = u.replace("Photo_h180_w240", "Photo_h600_w900").replace("_180_240.", "_600_900.")
    elif "img.staticmb.com/mbimages/project/Photo_h310_w462/" in u:
        u = u.replace("Photo_h310_w462/", "").replace("_310_462.", ".")
    elif "images.nobroker.in/images/" in u:
        u = re.sub(r"_(?:thumbnail|small|medium)\.", "_large.", u, flags=re.I)
    return u

def _res_tier(url):
    if "squareyards.com" in str(url or "").lower():
        return 99
    u = str(url or "")
    if "Photo_h180_w240" in u or "_180_240." in u:
        return 1
    if "Photo_h310_w462" in u:
        return 2
    if "imagecdn.99acres.com" in u and re.search(r"/\d+T-\d+\.", u):
        return 2
    if "images.nobroker.in" in u and "_medium." in u:
        return 3
    if "Photo_h300_w450" in u:
        return 4
    if "Photo_h600_w900" in u or "housingcdn.com" in u or "images.nobroker.in" in u or "imagecdn.99acres.com" in u:
        return 5
    return 3

def _dedupe_rank_urls(urls, cap=20):
    by_k, order = {}, []
    for raw in (urls or []):
        up = upgrade_media_url(raw)
        info = _media_key_rank(up)
        if not info:
            continue
        u, k, rank = info
        if k not in by_k:
            by_k[k] = (u, rank)
            order.append(k)
        elif rank > by_k[k][1]:
            by_k[k] = (u, rank)
    ordered = [by_k[k][0] for k in order]
    ordered.sort(key=lambda x: -_res_tier(x))
    return ordered[:cap], {k: v[0] for k, v in by_k.items()}

def _infer_furn_from_url(u):
    low = str(u or "").lower()
    if "unfurnished" in low:
        return "unfurnished"
    if "semi-furnished" in low or "semifurnished" in low:
        return "semi"
    if "fully-furnished" in low or "-furnished-" in low:
        return "furnished"
    return ""

def _load_google_place_names():
    p = ROOT / "data/google_places_cache.json"
    by_id, by_url = {}, {}
    if not p.exists():
        return by_id, by_url
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        for k, v in (d.items() if isinstance(d, dict) else []):
            if not isinstance(v, dict):
                continue
            dn = v.get("displayName")
            nm = dn.get("text") if isinstance(dn, dict) else (dn if isinstance(dn, str) else "")
            if not nm:
                continue
            by_id[k] = nm
            u = str(v.get("googleMapsUri") or "").strip()
            if u:
                by_url[u] = nm
                cm = re.search(r"cid=(\d+)", u)
                if cm:
                    by_url["cid:" + cm.group(1)] = nm
    except Exception:
        pass
    return by_id, by_url

def _load_dead_urls():
    p = ROOT / "data/media_cache.json"
    dead = set()
    if not p.exists():
        return dead
    try:
        mc = json.loads(p.read_text(encoding="utf-8-sig"))
        for u, v in (mc.items() if isinstance(mc, dict) else []):
            if isinstance(v, dict) and (v.get("dead") is True or v.get("st") in (404, 410)):
                dead.add(u)
    except Exception:
        pass
    return dead


def repair_societies(socs, mode="rent"):
    stats = Counter()
    unit_k = "units_buy" if mode == "buy" else "units_rent"
    g_by_id, g_by_url = _load_google_place_names()
    dead_urls = _load_dead_urls()

    for s in socs:
        loc = str(s.get("locality") or "").strip()
        nm = _smart_title_case(s.get("name") or "")
        if AD_SENTENCE_RE.search(nm) or PLUS_OR_FLAT_RE.match(nm) or nm.lower() == loc.lower() or not nm:
            us0 = s.get(unit_k) or []
            b0 = us0[0].get("b") if us0 else None
            bl = "1 RK" if b0 == 0 else (f"{int(float(b0))} BHK" if b0 else "Flat")
            nm = f"{bl} - {loc}" if loc else bl
            s["coords_approx"] = True
            stats["bad_names_cleaned"] += 1
        elif nm != s.get("name"):
            stats["names_cased"] += 1
        s["name"] = nm

        clean_u, seen_sig = [], set()
        for u in (s.get(unit_k) or []):
            if not isinstance(u, dict):
                continue
            p, b, sq, lt = u.get("p") or 0, u.get("b"), u.get("sq"), u.get("lt") or "broker"
            if mode == "rent":
                if p <= 0 or (p < 8000 and lt != "shared") or p > 2500000:
                    stats["rent_outliers_dropped"] += 1
                    continue
                if b is not None and float(b) >= 2 and p < 12000 and lt != "shared":
                    stats["rent_outliers_dropped"] += 1
                    continue
            else:
                if p < 1500000 or p > 1500000000:
                    stats["buy_outliers_dropped"] += 1
                    continue

            if sq is not None:
                try:
                    sq_n = int(float(sq))
                    if sq_n < 120 or sq_n > 10000:
                        u["sq"] = None
                        stats["absurd_sqft_cleared"] += 1
                    elif mode == "rent" and p and (p / sq_n < 12 or p / sq_n > 450):
                        u["sq"] = None
                        stats["absurd_psf_cleared"] += 1
                    elif mode == "buy" and p and (p / sq_n < 2500 or p / sq_n > 250000):
                        u["sq"] = None
                        stats["buy_absurd_psf_cleared"] += 1
                    else:
                        u["sq"] = sq_n
                except Exception:
                    u["sq"] = None

            if u.get("b") is None and u.get("u"):
                bm = re.search(r"(\d)\s*[-_]?\s*bhk", str(u["u"]), re.I)
                if bm:
                    u["b"] = int(bm.group(1))
                    stats["bhk_from_url"] += 1
                elif re.search(r"1\s*[-_]?\s*rk", str(u["u"]), re.I):
                    u["b"] = 0
                    stats["bhk_from_url"] += 1
            if not u.get("sq") and u.get("u"):
                sm = re.search(r"(\d{3,4})\s*[-_]?\s*sq[-_]?ft", str(u["u"]), re.I)
                if sm and 150 <= int(sm.group(1)) <= 9000:
                    cand_sq = int(sm.group(1))
                    ok_psf = (mode == "rent" and 12 <= p / cand_sq <= 450) or (mode == "buy" and 2500 <= p / cand_sq <= 250000)
                    if ok_psf:
                        u["sq"] = cand_sq
                        stats["sqft_from_url"] += 1
            if not u.get("f") and u.get("u"):
                inf_f = _infer_furn_from_url(u["u"])
                if inf_f:
                    u["f"] = inf_f
                    stats["furn_inferred"] += 1

            sig = (b, p, round((u.get("sq") or 0) / 50), u.get("s"))
            if sig in seen_sig:
                stats["same_soc_dup_units"] += 1
                continue
            seen_sig.add(sig)
            clean_u.append(u)
        s[unit_k] = clean_u

    socs[:] = [s for s in socs if (s.get(unit_k) or [])]

    merged_map, deduped = {}, []
    for s in socs:
        loc = str(s.get("locality") or "").strip().lower()
        nm = str(s.get("name") or "").strip().lower()
        is_gen = bool(re.match(r"^(?:\d(?:\.\d)?\s*(?:bhk|rk)|flat|studio|apartment|independent|on request)", nm, re.I)) or nm == loc
        if is_gen:
            deduped.append(s)
            continue
        mk = (loc, re.sub(r"[^a-z0-9]", "", nm))
        if mk not in merged_map:
            merged_map[mk] = s
            deduped.append(s)
        else:
            host = merged_map[mk]
            seen_urls = {u.get("u") for u in (host.get(unit_k) or []) if u.get("u")}
            seen_sigs = {(u.get("b"), u.get("p"), round((u.get("sq") or 0) / 50)) for u in (host.get(unit_k) or [])}
            for u in (s.get(unit_k) or []):
                uu = u.get("u")
                sig = (u.get("b"), u.get("p"), round((u.get("sq") or 0) / 50))
                if (uu and uu in seen_urls) or sig in seen_sigs:
                    stats["cross_entry_dups_dropped"] += 1
                    continue
                host.setdefault(unit_k, []).append(u)
                if uu:
                    seen_urls.add(uu)
                seen_sigs.add(sig)
            if s.get("photos"):
                host.setdefault("photos", []).extend(s["photos"])
            elif s.get("thumb"):
                host.setdefault("photos", []).append(s["thumb"])
            if s.get("coords_approx") is False and host.get("coords_approx"):
                host["lat"], host["lng"], host["coords_approx"] = s.get("lat"), s.get("lng"), False
            stats["cross_entry_socs_merged"] += 1
    socs[:] = deduped

    loc_pts = defaultdict(list)
    for s in socs:
        if s.get("lat") and s.get("lng") and s.get("locality") and not s.get("coords_approx"):
            loc_pts[s["locality"]].append((float(s["lat"]), float(s["lng"])))
    for s in socs:
        if s.get("lat") and s.get("lng") and s.get("locality") and s["locality"] not in loc_pts:
            loc_pts[s["locality"]].append((float(s["lat"]), float(s["lng"])))
    loc_med = {
        k: (sorted(p[0] for p in v)[len(v) // 2], sorted(p[1] for p in v)[len(v) // 2])
        for k, v in loc_pts.items() if len(v) >= 3
    }

    for idx, s in enumerate(socs):
        lat, lng, loc = s.get("lat"), s.get("lng"), s.get("locality")
        if lat and lng and loc in loc_med:
            mlat, mlng = loc_med[loc]
            if _hav_km(float(lat), float(lng), mlat, mlng) > 3.0:
                ang = ((abs(hash(s.get("id") or s.get("name") or str(idx))) % 360) * math.pi) / 180.0
                rad = 0.0012 + ((idx % 8) * 0.0003)
                s["lat"] = round(mlat + rad * math.cos(ang), 6)
                s["lng"] = round(mlng + rad * math.sin(ang), 6)
                s["coords_approx"] = True
                stats["drifted_pins_fixed"] += 1

    coord_groups = defaultdict(list)
    for s in socs:
        if s.get("lat") and s.get("lng"):
            coord_groups[(round(float(s["lat"]), 5), round(float(s["lng"]), 5))].append(s)
    for (clat, clng), grp in coord_groups.items():
        if len(grp) < 2:
            continue
        for k_i, s in enumerate(grp[1:], 1):
            ang = (k_i * 137.508) * math.pi / 180.0
            rad = 0.00024 * math.sqrt(k_i)
            s["lat"] = round(clat + rad * math.cos(ang), 6)
            s["lng"] = round(clng + rad * math.sin(ang), 6)
            stats["stacked_pins_spread"] += 1

    enrich_transit_context(socs)

    loc_bhk_ps = defaultdict(list)
    zone_bhk_ps = defaultdict(list)
    for s in socs:
        loc, zone = s.get("locality") or "", s.get("zone") or ""
        for u in (s.get(unit_k) or []):
            p, b = u.get("p") or 0, u.get("b")
            if p > 0 and b is not None:
                bi = int(float(b))
                loc_bhk_ps[(loc, bi)].append(p)
                zone_bhk_ps[(zone, bi)].append(p)
    med_loc_bhk = {k: sorted(v)[len(v) // 2] for k, v in loc_bhk_ps.items() if len(v) >= 5}
    med_zone_bhk = {k: sorted(v)[len(v) // 2] for k, v in zone_bhk_ps.items() if len(v) >= 5}

    for s in socs:
        us = s.get(unit_k) or []
        ps = sorted(int(u["p"]) for u in us if u.get("p"))
        pr = s.setdefault("pricing", {})
        if mode == "rent" and ps:
            pr["rent_min"], pr["rent_max"], pr["rent_med"] = ps[0], ps[-1], ps[len(ps) // 2]
            pr["has_zero_brokerage"] = any(bool(u.get("zb")) or u.get("lt") == "owner" for u in us)
        elif mode == "buy" and ps:
            pr["buy_min"], pr["buy_max"], pr["buy_med"] = ps[0], ps[-1], ps[len(ps) // 2]
        bhks = sorted({int(float(u["b"])) for u in us if u.get("b") is not None})
        if bhks:
            s["bhks"] = bhks

        loc, zone = s.get("locality") or "", s.get("zone") or ""
        best_deal = None
        for u in us:
            p, b = u.get("p") or 0, u.get("b")
            if p <= 0 or b is None:
                continue
            bi = int(float(b))
            ref = med_loc_bhk.get((loc, bi)) or med_zone_bhk.get((zone, bi))
            if not ref or ref <= 0:
                continue
            pct = round((p / ref - 1.0) * 100)
            if -55 <= pct <= -15:
                if best_deal is None or pct < best_deal["pct"]:
                    best_deal = {"pct": pct, "label": "Great Value", "loc_median": ref, "bhk": bi}
        d_obj = s.get("deal") if isinstance(s.get("deal"), dict) else {}
        if best_deal:
            d_obj[mode] = best_deal
            s["deal"] = d_obj
            stats["true_great_value"] += 1
        else:
            d_obj.pop(mode, None)
            if d_obj:
                s["deal"] = d_obj
            else:
                s.pop("deal", None)

        g = s.get("google")
        if isinstance(g, dict) and (g.get("reviews") or g.get("rating")):
            s_all = {w for w in re.findall(r"[a-z]{3,}", str(s.get("name") or "").lower()) if w not in STOP_WORDS}
            s_dist = s_all - COMMON_PREFIX_WORDS
            gu = str(g.get("url") or "").strip()
            cm = re.search(r"cid=(\d+)", gu)
            g_disp = str(g.get("name") or g_by_id.get(s.get("id") or "") or g_by_url.get(gu) or (g_by_url.get("cid:" + cm.group(1)) if cm else "") or "").lower()
            bad_g = False
            if s_all and g_disp:
                g_words = {w for w in re.findall(r"[a-z]{3,}", g_disp) if w not in STOP_WORDS}
                if g_words:
                    if s_dist and not (s_dist & g_words):
                        bad_g = True
                    elif not (s_all & g_words):
                        bad_g = True
            if not bad_g and s_dist and g.get("reviews"):
                rblob = " ".join(str(r.get("text") or "") for r in (g.get("reviews") or []) if isinstance(r, dict)).lower()
                for rm in re.finditer(r"\b([a-z]{3,}(?:\s+[a-z]{3,}){0,2})\s+(?:apartment|apartments|chs|chsl|society|tower|towers|heights|residency|complex)\b", rblob):
                    rw = {w for w in re.findall(r"[a-z]{3,}", rm.group(1)) if w not in STOP_WORDS}
                    r_dist = rw - COMMON_PREFIX_WORDS
                    if r_dist and not (r_dist & s_dist):
                        bad_g = True
                        break
                    if not r_dist and rw and rw.isdisjoint(s_dist) and any(x in rw for x in ("baba", "mata", "ganesh", "shiv", "krishna", "ram")) and not (rw <= s_all):
                        bad_g = True
                        break
            if bad_g:
                g.pop("reviews", None)
                g.pop("rating", None)
                g.pop("review_count", None)
                g.pop("url", None)
                stats["bad_google_reviews_purged"] += 1

        raw_soc = ([s["thumb"]] if s.get("thumb") else []) + list(s.get("photos") or [])
        for u in us:
            if u.get("img"):
                raw_soc.append(u["img"])
            raw_soc.extend(u.get("imgs") or [])
        soc_clean, best_by_k = _dedupe_rank_urls(raw_soc, cap=20)
        for u in us:
            u_raw = ([u["img"]] if u.get("img") else []) + list(u.get("imgs") or [])
            u_up = []
            for r in u_raw:
                info = _media_key_rank(upgrade_media_url(r))
                if info:
                    u_up.append(best_by_k.get(info[1], info[0]))
            u_clean, _ = _dedupe_rank_urls(u_up, cap=16)
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
            if len(soc_clean) > 1:
                s["photos"] = soc_clean
            else:
                s.pop("photos", None)
        else:
            yt_poster = None
            for _v in (s.get("videos") or []):
                _ym = re.search(r"youtube\.com/embed/([A-Za-z0-9_-]{11})", str((_v or {}).get("url") or ""))
                if _ym:
                    yt_poster = "https:" + f"//i.ytimg.com/vi/{_ym.group(1)}/hqdefault.jpg"
                    break
            if yt_poster:
                s["thumb"] = yt_poster
                s.pop("photos", None)
            else:
                s.pop("thumb", None)
                s.pop("photos", None)

    return stats

def run_on_shards():
    man_p = ROOT / "web/public/data/manifest.json"
    man = json.loads(man_p.read_text(encoding="utf-8-sig"))
    for mode, key in (("rent", "rent_shards"), ("buy", "buy_shards")):
        socs = []
        shard_paths = [ROOT / "web/public/data" / sf for sf in (man.get(key) or []) if (ROOT / "web/public/data" / sf).exists()]
        for sp in shard_paths:
            b = json.loads(sp.read_text(encoding="utf-8-sig"))
            socs.extend(b if isinstance(b, list) else (b.get("societies") or []))
        st = repair_societies(socs, mode=mode)
        n_sh = max(1, len(shard_paths))
        chunk = math.ceil(len(socs) / n_sh)
        for i, sp in enumerate(shard_paths):
            part = socs[i * chunk : (i + 1) * chunk]
            sp.write_text(json.dumps(part, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[FLEET REPAIR {mode.upper()}] entries={len(socs):,} | {dict(st)}")

def _finalize_shards_and_manifest():
    # Single-pass shard finalizer: 99acres floors, curated Bright (vs>=97), HTML entity decode,
    # Rent typo-deposit cleanup, single-unit u.imgs dedupe (~5.6 MB saved) & manifest sync.
    import html as _html, math as _math, time as _t
    from datetime import datetime, timezone, timedelta
    mp = ROOT / "web/public/data/manifest.json"
    if not mp.exists():
        return
    m = json.loads(mp.read_text(encoding="utf-8-sig"))
    flr_p = ROOT / "data/99acres_floors_cache.json"
    flr_map = json.loads(flr_p.read_text(encoding="utf-8-sig")) if flr_p.exists() else {}

    added_flr = ent_fixed = dep_cleared = deduped_imgs = 0
    totals = {}
    all_ids = set()

    for sk, uk in (("rent_shards", "units_rent"), ("buy_shards", "units_buy")):
        paths = [ROOT / "web/public/data" / sf for sf in (m.get(sk) or []) if (ROOT / "web/public/data" / sf).exists()]
        if not paths:
            totals[sk] = (0, 0)
            continue
        socs = [x for sp in paths for x in json.loads(sp.read_text(encoding="utf-8-sig"))]
        for s in socs:
            if s.get("id"):
                all_ids.add(s["id"])
            for k in ("name", "locality"):
                v = s.get(k)
                if isinstance(v, str) and ("&" in v):
                    v2 = _html.unescape(_html.unescape(v))
                    v2 = re.sub(r"\s*\(\s*", " (", v2)
                    v2 = re.sub(r"\s*\)\s*", ") ", v2)
                    v2 = re.sub(r"\s+", " ", v2).strip()
                    if v2 != v:
                        s[k] = v2
                        ent_fixed += 1
            if isinstance(s.get("features"), dict):
                s["features"]["bright"] = bool((s.get("vs") or 0) >= 97 and not s.get("vr"))
            us = s.get(uk) or []
            s_photos = set(s.get("photos") or [])
            if s.get("thumb"):
                s_photos.add(s["thumb"])
            # BH_V63_URL_SCRUB: Drop SquareYards /agent/ profile links & fix mislabeled housing.com tags
            us = [u for u in us if not (str(u.get("s") or "") == "squareyards" and "/agent/" in str(u.get("u") or "").lower())]
            s[uk] = us
            for u in us:
                if str(u.get("s") or "") in ("99acres", "makaan") and "housing.com/" in str(u.get("u") or "").lower():
                    u["s"] = "housing"
                if flr_map and u.get("s") == "99acres" and not u.get("flr"):
                    mm = re.search(r"spid-([A-Z]\d{6,10})", str(u.get("u") or ""), re.I)
                    if mm:
                        fv = flr_map.get(mm.group(1).upper())
                        if fv:
                            u["flr"] = fv
                            added_flr += 1
                if sk == "rent_shards":
                    dep, p = u.get("dep"), u.get("p")
                    if dep and p and (dep < 5000 or dep > p * 24):
                        u.pop("dep", None)
                        dep_cleared += 1
            if len(us) == 1 and isinstance(us[0].get("imgs"), list) and us[0]["imgs"]:
                u0 = us[0]
                if set(u0["imgs"]).issubset(s_photos):
                    u0.pop("imgs", None)
                    deduped_imgs += 1

        chunk = _math.ceil(len(socs) / max(1, len(paths)))
        for i, sp in enumerate(paths):
            sp.write_text(json.dumps(socs[i * chunk : (i + 1) * chunk], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        totals[sk] = (len(socs), sum(len(s.get(uk) or []) for s in socs))

    ist_str = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST")
    r_b, r_f = totals.get("rent_shards", (0, 0))
    b_b, b_f = totals.get("buy_shards", (0, 0))
    tot_soc = len(all_ids)
    m.update({
        "count": tot_soc, "total_societies": tot_soc,
        "rent_buildings": r_b, "rent_societies": r_b,
        "buy_buildings": b_b, "buy_societies": b_b,
        "rent_flats": r_f, "total_rent_flats": r_f,
        "buy_flats": b_f, "total_buy_flats": b_f,
        "generated_at": ist_str, "updated_ist": ist_str,
        "generated_ts": int(_t.time()),
    })
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[FLEET FINALIZE] floors=+{added_flr:,} | entities={ent_fixed} | deposits_cleared={dep_cleared} | single_unit_imgs_deduped={deduped_imgs:,}", flush=True)

if __name__ == "__main__":
    run_on_shards()




if __name__ == '__main__':
    _finalize_shards_and_manifest()
