from __future__ import annotations
import math, re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

STOPWORDS = {"chs","chsl","co-operative","cooperative","co","op","housing","society","tower","towers","wing","phase","building","bldg","apartments","apartment","residency","residence","heights","enclave","complex","mumbai","thane","navi","west","east","road","rd","marg","ltd","limited","the","a","b","c","d"}

def normalize_name(name: str) -> str:
    clean = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    tokens = [t for t in clean.split() if t not in STOPWORDS and not t.isdigit()]
    return " ".join(tokens) or clean.strip()

def _sim(a: str, b: str) -> float:
    return float(fuzz.token_sort_ratio(a, b)) if fuzz else SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio() * 100.0

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")

def resolve_entities(raw_records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    priority = {"maharera": 0, "magicbricks": 1, "housing": 2, "99acres": 3, "nobroker": 4}
    ordered = sorted(raw_records, key=lambda r: priority.get(r["source"], 9))
    canonicals, seen_ids, rera_idx, loc_buckets = [], set(), {}, {}

    for rec in ordered:
        matched: Optional[int] = None
        rid = (rec.get("rera_id") or "").strip().upper() or None
        loc_key = (rec.get("locality") or "mumbai").strip().lower()
        norm_rec = normalize_name(rec["name"])
        if len(norm_rec) < 2: continue

        if rid and rid in rera_idx:
            matched = rera_idx[rid]
        else:
            best_score, best_i = 0.0, None
            lat, lng = rec.get("lat"), rec.get("lng")
            for idx in loc_buckets.get(loc_key, []):
                can = canonicals[idx]
                if norm_rec == can["_norm"]:
                    best_i = idx; break
                sc = _sim(norm_rec, can["_norm"])
                if sc < 75.0: continue
                if lat and lng and can.get("lat") and can.get("lng"):
                    if haversine_m(lat, lng, can["lat"], can["lng"]) <= 200.0 and sc >= 82.0 and sc > best_score:
                        best_score, best_i = sc, idx
                elif sc >= 88.0 and sc > best_score:
                    best_score, best_i = sc, idx
            matched = best_i

        if matched is None:
            base_cid = f"mum-{slugify(loc_key)[:20]}-{slugify(rec['name'])[:36]}".strip("-")
            cid, n = base_cid, 2
            while cid in seen_ids:
                cid = f"{base_cid}-{n}"; n += 1
            seen_ids.add(cid)
            can = {
                "id": cid, "name": rec["name"], "_norm": norm_rec, "aliases": [rec["name"]],
                "locality": rec.get("locality") or "Mumbai", "zone": rec.get("zone"),
                "lat": rec.get("lat"), "lng": rec.get("lng"), "rera_ids": [rid] if rid else [],
                "sources": {rec["source"]: rec.get("source_url")},
                "raw_by_source": {rec["source"]: [rec["payload"]]},
            }
            idx = len(canonicals); canonicals.append(can)
            loc_buckets.setdefault(loc_key, []).append(idx)
            if rid: rera_idx[rid] = idx
        else:
            can = canonicals[matched]
            if rec["name"] not in can["aliases"]: can["aliases"].append(rec["name"])
            if not can["lat"] and rec.get("lat"): can["lat"], can["lng"] = rec["lat"], rec["lng"]
            if not can.get("zone") and rec.get("zone"): can["zone"] = rec["zone"]
            if rid and rid not in can["rera_ids"]: can["rera_ids"].append(rid); rera_idx[rid] = matched
            if rec.get("source_url"): can["sources"][rec["source"]] = rec["source_url"]
            can["raw_by_source"].setdefault(rec["source"], []).append(rec["payload"])

    for c in canonicals: c.pop("_norm", None)
    return canonicals, []
