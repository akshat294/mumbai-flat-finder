import json

def _dedupe_unit_clones(units, max_per_bldg=12):
    if not isinstance(units, list):
        return [], 0
    seen_u = set()
    kept = []
    removed = 0
    ordered = sorted(
        [u for u in units if isinstance(u, dict)],
        key=lambda u: (0 if u.get("zb") else 1, 0 if u.get("img") else 1, u.get("p") or 999999999),
    )
    for u in ordered:
        uu = u.get("u") or ""
        if uu and uu in seen_u:
            removed += 1
            continue
        p = u.get("p") or 0
        b = u.get("b")
        is_clone = False
        if not u.get("zb") and p > 0:
            for x in kept:
                if x.get("b") == b and x.get("s") == u.get("s") and not x.get("zb"):
                    xp = x.get("p") or 0
                    if xp > 0 and abs(p - xp) / xp <= 0.04:
                        is_clone = True
                        break
        if is_clone:
            removed += 1
            continue
        if uu:
            seen_u.add(uu)
        kept.append(u)
        if len(kept) >= max_per_bldg:
            removed += max(0, len(ordered) - len(kept))
            break
    return kept, removed

def compact_societies_for_pages(socs, max_extra_photos=4, strip_dup_unit_img=False, trim_secondary=False):
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
            dedup_raw, rem = _dedupe_unit_clones(raw_u, max_per_bldg=8 if trim_secondary else 12)
            removed_dups += rem
            dedup_u = []
            for u in dedup_raw:
                _addp(u.get("img"))
                for x in (u.get("imgs") or []):
                    _addp(x)
                clean_u = {}
                for k, v in u.items():
                    if k == "imgs" or v is None or v == "":
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

        if trim_secondary:
            if str(s.get("id", "")).startswith("solo-"):
                s.pop("civic", None)
                s.pop("google", None)
            civ = s.get("civic")
            if isinstance(civ, dict):
                for ck in list(civ.keys()):
                    if isinstance(civ[ck], list) and len(civ[ck]) > 2:
                        civ[ck] = civ[ck][:2]
            pr = s.get("pricing")
            if isinstance(pr, dict):
                for pk in list(pr.keys()):
                    if pr[pk] in (0, False, None, ""):
                        pr.pop(pk, None)
    return removed_dups

def save_compacted_index(idx_path, data, max_bytes=20_800_000):
    socs = data.get("societies", [])
    removed = compact_societies_for_pages(socs, max_extra_photos=4, strip_dup_unit_img=False, trim_secondary=False)
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > max_bytes:
        removed += compact_societies_for_pages(socs, max_extra_photos=2, strip_dup_unit_img=True, trim_secondary=True)
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(payload.encode("utf-8")) > max_bytes:
        removed += compact_societies_for_pages(socs, max_extra_photos=0, strip_dup_unit_img=True, trim_secondary=True)
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    idx_path.write_text(payload, encoding="utf-8")
    return removed, len(payload.encode("utf-8"))
