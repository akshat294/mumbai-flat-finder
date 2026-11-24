#!/usr/bin/env python3
# Recurring 18-hub Mumbai NoBroker Shared/Flatmates Sync (0 API credits).
import base64
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from curl_cffi import requests as creq

ROOT = Path(__file__).resolve().parent.parent
MAN_PATH = ROOT / "web/public/data/manifest.json"

NB_HUBS = [
    ("Bandra West", 19.0596, 72.8295), ("Khar West", 19.0700, 72.8338),
    ("Andheri West", 19.1364, 72.8296), ("Andheri East", 19.1136, 72.8697),
    ("Powai", 19.1176, 72.9060), ("Lower Parel", 18.9982, 72.8269),
    ("Worli", 19.0176, 72.8162), ("Dadar West", 19.0178, 72.8428),
    ("Goregaon East", 19.1663, 72.8526), ("Malad West", 19.1874, 72.8484),
    ("Kandivali West", 19.2056, 72.8364), ("Chembur", 19.0522, 72.9005),
    ("Santacruz West", 19.0843, 72.8360), ("Juhu", 19.1075, 72.8263),
    ("Versova", 19.1351, 72.8146), ("Wadala", 19.0170, 72.8682),
    ("Kurla West", 19.0726, 72.8845), ("Thane West", 19.2183, 72.9781),
]


def _fetch_hub(hub):
    loc, lat, lng = hub
    try:
        sp = base64.b64encode(
            json.dumps([{"lat": lat, "lon": lng, "placeName": loc, "showMap": False}]).encode()
        ).decode()
        rows_all = []
        for kind in ("SHARED", "RENT"):
            for pg in (1, 2):
                api = (
                    "https:" + f"//www.nobroker.in/api/v3/multi/property/{kind}/filter"
                    f"?city=mumbai&isMetro=false&latitude={lat}&longitude={lng}&pageNo={pg}&radius=2.5"
                    f"&searchParam={sp}&sharedAccomodation=1"
                )
                r = creq.get(
                    api,
                    impersonate="chrome124",
                    timeout=12,
                    headers={"Accept": "application/json", "Referer": "https:" + "//www.nobroker.in/"},
                )
                if r.status_code == 200:
                    d = (r.json() or {}).get("data") or []
                    rows_all.extend(d)
                    if len(d) < 10:
                        break
                else:
                    break
            if rows_all:
                break
        return loc, rows_all
    except Exception:
        return loc, []


def main():
    if not MAN_PATH.exists():
        print("[sync_flatmates] manifest.json missing, skipping.")
        return
    man = json.loads(MAN_PATH.read_text(encoding="utf-8-sig"))
    r_paths = [ROOT / "web/public/data" / sf for sf in (man.get("rent_shards") or []) if (ROOT / "web/public/data" / sf).exists()]
    if not r_paths:
        print("[sync_flatmates] No rent shards found, skipping.")
        return

    raw_rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for loc, rows in ex.map(_fetch_hub, NB_HUBS):
            for row in rows:
                row["_hub_loc"] = loc
                raw_rows.append(row)

    r_all = [x for sp in r_paths for x in json.loads(sp.read_text(encoding="utf-8-sig"))]
    existing_urls = {u.get("u") for s in r_all for u in (s.get("units_rent") or []) if u.get("u")}
    loc_zone, loc_flood = {}, {}
    for s in r_all:
        lc = s.get("locality")
        if lc and s.get("zone") and lc not in loc_zone:
            loc_zone[lc] = s["zone"]
        fr_v = (s.get("mumbai_context") or {}).get("monsoon_flood_risk")
        if lc and fr_v and lc not in loc_flood:
            loc_flood[lc] = fr_v

    added, seen_pid = 0, set()
    for row in raw_rows:
        pid = str(row.get("id") or "").strip()
        if not pid or pid in seen_pid:
            continue
        seen_pid.add(pid)
        du = str(row.get("detailUrl") or "").strip()
        if not du:
            continue
        url = du if du.startswith("http") else ("https:" + "//www.nobroker.in" + (du if du.startswith("/") else "/" + du))
        if url in existing_urls:
            continue
        rent = int(row.get("rent") or 0)
        if not (4500 <= rent <= 150000):
            continue
        lat, lng = float(row.get("latitude") or 0), float(row.get("longitude") or 0)
        if not (18.88 <= lat <= 19.45 and 72.75 <= lng <= 73.25):
            continue
        loc = row.get("_hub_loc") or str(row.get("locality") or "").split(",")[0].strip()
        soc = re.sub(r"\s+", " ", str(row.get("society") or row.get("propertyTitle") or "").strip())[:60]
        if not soc or len(soc) < 3:
            soc = f"Shared Flat - {loc}"
        imgs = []
        for ph in (row.get("photos") or []):
            im_map = ph.get("imagesMap") if isinstance(ph, dict) else None
            if isinstance(im_map, dict):
                fn = im_map.get("large") or im_map.get("original") or im_map.get("medium")
                if fn:
                    iu = fn if fn.startswith("http") else ("https:" + f"//images.nobroker.in/images/{pid}/{fn}")
                    iu = re.sub(r"_(?:thumbnail|small|medium)\.", "_large.", iu, flags=re.I)
                    if iu not in imgs:
                        imgs.append(iu)
        bm = re.search(r"(\d)", str(row.get("type") or ""))
        bhk = int(bm.group(1)) if bm else 2
        sq = int(row.get("propertySize") or 0) or None
        if sq and not (120 <= sq <= 5000):
            sq = None
        f_raw = str(row.get("furnishing") or "").upper()
        furn = "furnished" if "FULLY" in f_raw else ("semi" if "SEMI" in f_raw else ("unfurnished" if "UNFURN" in f_raw else ""))
        dep = int(row.get("deposit") or 0)
        dep = dep if 5000 <= dep <= 5000000 else 0
        fl, tf = row.get("floor"), row.get("totalFloor")
        flr = f"{fl}/{tf}" if (fl is not None and tf) else (str(fl) if fl is not None else "")
        fac = str(row.get("facingDesc") or "").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", f"mum-{loc}-{soc}-{pid[-6:]}".lower()).strip("-")

        unit = {"p": rent, "b": bhk, "sq": sq, "s": "nobroker", "u": url, "lt": "shared", "zb": True}
        if furn:
            unit["f"] = furn
        if imgs:
            unit["img"] = imgs[0]
            if len(imgs) > 1:
                unit["imgs"] = imgs[:8]
        if dep:
            unit["dep"] = dep
        if flr:
            unit["flr"] = flr
        if fac:
            unit["fac"] = fac

        entry = {
            "id": slug,
            "name": soc,
            "locality": loc,
            "zone": loc_zone.get(loc, "Mumbai"),
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "pricing": {"rent_min": rent, "rent_max": rent, "has_zero_brokerage": True},
            "units_rent": [unit],
            "units_buy": [],
            "bhks": [bhk],
            "sources": ["nobroker"],
            "sources_rent": ["nobroker"],
            "mumbai_context": {"monsoon_flood_risk": loc_flood.get(loc, "Low")},
            "commutes": {},
            "features": {"tags": [], "vision_tags": []},
            "tenant": ["bachelors_ok"],
            "google": {},
            "age_days": 0,
            "is_new": True,
            "vs": 0,
        }
        if imgs:
            entry["thumb"] = imgs[0]
            if len(imgs) > 1:
                entry["photos"] = imgs[:8]
        if furn:
            entry["furnishing"] = furn
        r_all.append(entry)
        existing_urls.add(url)
        added += 1

    if added > 0:
        chunk = math.ceil(len(r_all) / max(1, len(r_paths)))
        for i, sp in enumerate(r_paths):
            sp.write_text(json.dumps(r_all[i * chunk : (i + 1) * chunk], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[sync_flatmates] Fetched={len(raw_rows)} raw | Added=+{added} new Zero-Brokerage Mumbai shared listings")


if __name__ == "__main__":
    main()
