import json

def compact_societies_for_pages(socs, max_extra_photos=4, strip_dup_unit_img=False):
    removed_dups = 0
    for s in socs:
        if isinstance(s.get("lat"), float): s["lat"] = round(s["lat"], 5)
        if isinstance(s.get("lng"), float): s["lng"] = round(s["lng"], 5)
        thumb = s.get("thumb")

        extra_photos = []
        def _addp(u):
            if isinstance(u, str) and u.startswith("http") and u != thumb and u not in extra_photos:
                extra_photos.append(u)

        for p in (s.get("photos") or []):
            _addp(p)

        for uk in ("units_rent", "units_buy"):
            raw_u = s.get(uk)
            if not isinstance(raw_u, list):
                continue
            dedup_u, seen_u = [], set()
            for u in raw_u:
                if not isinstance(u, dict):
                    continue
                uu = u.get("u") or ""
                if uu and uu in seen_u:
                    removed_dups += 1
                    continue
                if uu:
                    seen_u.add(uu)
                _addp(u.get("img"))
                for x in (u.get("imgs") or []):
                    _addp(x)
                clean_u = {}
                for k, v in u.items():
                    if k == "imgs" or v is None:
                        continue
                    if k == "zb" and not v:
                        continue
                    if strip_dup_unit_img and k == "img" and v == thumb:
                        continue
                    clean_u[k] = v
                dedup_u.append(clean_u)
            s[uk] = dedup_u

        if extra_photos and max_extra_photos > 0:
            s["photos"] = extra_photos[:max_extra_photos]
        else:
            s.pop("photos", None)

        for dk in ("pricing", "mumbai_context", "civic", "google", "commutes"):
            d = s.get(dk)
            if isinstance(d, dict):
                s[dk] = {k: v for k, v in d.items() if v is not None}

        for fk in ("is_unnamed", "is_new", "coords_approx", "deal", "rera_carpet_sqft"):
            if s.get(fk) in (False, None):
                s.pop(fk, None)
    return removed_dups

def save_compacted_index(idx_path, data, max_bytes=23_500_000):
    socs = data.get("societies", [])
    removed = compact_societies_for_pages(socs, max_extra_photos=4, strip_dup_unit_img=False)
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > max_bytes:
        compact_societies_for_pages(socs, max_extra_photos=2, strip_dup_unit_img=True)
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > max_bytes:
        compact_societies_for_pages(socs, max_extra_photos=0, strip_dup_unit_img=True)
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    idx_path.write_text(payload, encoding="utf-8")
    return removed, len(payload.encode("utf-8"))
