import json, math, re, sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.high_signal_sources import fetch_all_high_signal

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def run():
    idx_p = ROOT / "web/public/data/mumbai-index.json"
    data = json.loads(idx_p.read_text(encoding="utf-8"))
    socs = data.get("societies", [])

    unit_key = "units"
    for s in socs[:50]:
        for cand in ("units", "listings", "flats"):
            if isinstance(s.get(cand), list) and s[cand]:
                unit_key = cand
                break

    loc_pts = {}
    for s in socs:
        loc, lat, lng = s.get("locality"), s.get("lat"), s.get("lng")
        if loc and lat and lng:
            loc_pts.setdefault(loc, []).append((float(lat), float(lng)))

    loc_med = {
        loc: (sorted(p[0] for p in pts)[len(pts) // 2], sorted(p[1] for p in pts)[len(pts) // 2])
        for loc, pts in loc_pts.items()
    }

    fixed_pins, fixed_names = 0, 0
    for i, s in enumerate(socs):
        raw_name = str(s.get("name") or "").strip()
        if "," in raw_name:
            parts = [p.strip() for p in raw_name.split(",") if p.strip()]
            clean_parts, seen_p = [], set()
            loc_low = str(s.get("locality") or "").lower()
            for p in parts:
                pl = p.lower()
                if pl in seen_p or pl in ("mumbai", "navi mumbai", "thane", loc_low):
                    continue
                if clean_parts and ((loc_low and loc_low in pl) or "mumbai" in pl):
                    continue
                seen_p.add(pl)
                clean_parts.append(p)
            new_name = clean_parts[0] if clean_parts else parts[0]
            if new_name and new_name != raw_name:
                s["name"] = new_name
                fixed_names += 1

        loc, lat, lng = s.get("locality"), s.get("lat"), s.get("lng")
        if loc in loc_med and lat and lng:
            mlat, mlng = loc_med[loc]
            if haversine_km(float(lat), float(lng), mlat, mlng) > 3.8:
                ang = (hash(s.get("id") or s.get("name") or str(i)) % 360) * math.pi / 180.0
                rad = 0.0012 + ((i % 7) * 0.0003)
                s["lat"] = round(mlat + rad * math.cos(ang), 6)
                s["lng"] = round(mlng + rad * math.sin(ang), 6)
                s["pin_precision"] = "locality"
                s["exact_pin"] = False
                ctx = s.get("mumbai_context")
                if isinstance(ctx, dict):
                    nm = ctx.get("nearest_metro")
                    if isinstance(nm, dict) and (nm.get("walk_min") or 0) > 60:
                        ctx.pop("nearest_metro", None)
                    nt = ctx.get("nearest_train")
                    if isinstance(nt, dict) and (nt.get("walk_min") or 0) > 60:
                        ctx.pop("nearest_train", None)
                fixed_pins += 1

    hs_items = fetch_all_high_signal()
    existing_urls = {u.get("url") for s in socs for u in (s.get(unit_key) or []) if u.get("url")}
    added_hs = 0
    for j, it in enumerate(hs_items):
        if it["url"] in existing_urls:
            continue
        existing_urls.add(it["url"])
        ang = ((j * 47) % 360) * math.pi / 180.0
        rad = 0.0015 + ((j % 5) * 0.0004)
        sid = f"hs-{it['src']}-{abs(hash(it['url'])) % 1000000}"
        socs.append({
            "id": sid, "name": it["name"], "locality": it["locality"], "zone": it["zone"],
            "lat": round(it["lat"] + rad * math.cos(ang), 6),
            "lng": round(it["lng"] + rad * math.sin(ang), 6),
            "pin_precision": "locality", "exact_pin": False,
            "thumb": it.get("img"), "min_rent": it["p"], "sources": [it["src"]],
            unit_key: [{
                "m": "rent", "p": it["p"], "bhk": it["bhk"], "src": it["src"],
                "url": it["url"], "img": it.get("img"), "zb": True,
                "lister": it["lister"], "lt": it["lister"]
            }]
        })
        added_hs += 1

    r_src, b_src = Counter(), Counter()
    for s in socs:
        for u in (s.get(unit_key) or []):
            m = u.get("m") or u.get("mode") or ("buy" if (u.get("p") or 0) >= 2000000 else "rent")
            src = u.get("src") or u.get("s") or u.get("source") or "unknown"
            if m == "buy": b_src[src] += 1
            else: r_src[src] += 1

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["count"] = len(socs)
    data["societies"] = socs
    idx_p.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    print(f"[v18 DATA] Fixed {fixed_pins} misplaced pins (>3.8km off) | Cleaned {fixed_names} dirty names | Added {added_hs} high-signal units")
    print(f"[v18 SOURCES] Rent ({sum(r_src.values())}): {dict(r_src.most_common())}")
    print(f"[v18 SOURCES] Buy  ({sum(b_src.values())}): {dict(b_src.most_common())}")

if __name__ == "__main__":
    run()
