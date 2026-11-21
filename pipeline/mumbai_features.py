from __future__ import annotations
import hashlib, json, math, re, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

COASTLINE_PTS: List[Tuple[float, float]] = [
    (18.9020, 72.8115), (18.9125, 72.8185), (18.9265, 72.8215), (18.9435, 72.8230),
    (18.9535, 72.7965), (18.9675, 72.8010), (18.9830, 72.8110), (18.9990, 72.8145),
    (19.0165, 72.8170), (19.0275, 72.8350), (19.0430, 72.8200), (19.0545, 72.8195),
    (19.0690, 72.8225), (19.0830, 72.8260), (19.0990, 72.8255), (19.1135, 72.8230),
    (19.1310, 72.8135), (19.1460, 72.7960), (19.1670, 72.7890), (19.1885, 72.7940),
    (19.2240, 72.7850), (19.2520, 72.7830),
]

WORK_HUBS: Dict[str, Tuple[float, float]] = {
    "bkc": (19.0653, 72.8681),
    "lower_parel": (18.9985, 72.8295),
    "nariman_point": (18.9281, 72.8235),
    "seepz": (19.1242, 72.8742),
    "powai": (19.1197, 72.9051),
    "mindspace": (19.1802, 72.8334),
}

OUTER_CITY_RE = re.compile(
    r"\b(kalyan|dombivli|dombivali|badlapur|ambernath|ulhasnagar|vasai|virar|nallasopara|nalasopara|naigaon|bhiwandi|boisar|karjat|khopoli|palghar|titwala|shahad|dahanu)\b",
    re.I,
)
BALCONY_RE = re.compile(r"\b(balcon(?:y|ies)|sit[\s-]?out|verandah|veranda|french\s+balcony|attached\s+balcony|open\s+balcony)\b", re.I)
TERRACE_RE = re.compile(r"\b(terrace|sky\s*deck|private\s*deck|sundeck|sun\s*deck|rooftop|penthouse\s*deck|open\s*deck|attached\s*terrace)\b", re.I)
GARDEN_RE  = re.compile(r"\b(private\s*garden|garden\s*facing|garden\s*view|park\s*facing|lawn|courtyard|overlooking\s*garden|landscaped\s*garden)\b", re.I)
SEA_RE     = re.compile(r"\b(sea\s*view|sea[\s-]?facing|arabian\s*sea|ocean\s*view|ocean[\s-]?facing|overlooking\s*(?:the\s*)?sea|water\s*view|beach\s*facing|bandstand\s*view|marine\s*drive\s*view)\b", re.I)

def is_outer_city_mismatch(text: str, locality: str) -> bool:
    if not text: return False
    m = OUTER_CITY_RE.search(text.replace("-", " "))
    if not m: return False
    return m.group(1).lower() not in (locality or "").lower()

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))

def _pt_seg_dist_km(lat: float, lng: float, a: Tuple[float, float], b: Tuple[float, float]) -> float:
    kx, ky = 111.32 * math.cos(math.radians(19.08)), 110.57
    px, py = lng * kx, lat * ky
    ax, ay = a[1] * kx, a[0] * ky
    bx, by = b[1] * kx, b[0] * ky
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 <= 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def dist_to_coast_km(lat: float, lng: float) -> float:
    best = 99.0
    for i in range(len(COASTLINE_PTS) - 1):
        d = _pt_seg_dist_km(lat, lng, COASTLINE_PTS[i], COASTLINE_PTS[i + 1])
        if d < best: best = d
    return round(best, 2)

def compute_commutes(lat: float, lng: float) -> Dict[str, int]:
    return {
        hub: max(6, min(115, int(round(((_haversine_km(lat, lng, hlat, hlng) * 1.28) / 19.5) * 60 + 4))))
        for hub, (hlat, hlng) in WORK_HUBS.items()
    }

def url_hash(u: Optional[str]) -> Optional[str]:
    return hashlib.sha1(u.strip().encode("utf-8")).hexdigest()[:16] if (u and isinstance(u, str)) else None

def load_vision_cache(path: str | Path = "data/vision_tags_cache.json") -> Dict[str, Dict[str, Any]]:
    p = Path(path)
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}

def extract_outdoor_features(
    name: str, recs: List[Dict[str, Any]], lat: float, lng: float,
    thumb: Optional[str], vision_cache: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    d_sea = dist_to_coast_km(lat, lng)
    text_parts = [name or ""]
    balc_num = 0
    for r in recs[:12]:
        for k in ("name","title","description","url","highlights","amenities"):
            v = r.get(k)
            if isinstance(v, str): text_parts.append(v)
            elif isinstance(v, list): text_parts.extend(str(x) for x in v[:12])
        bn = r.get("balconies") or r.get("balcony")
        try:
            if bn and int(bn) > 0: balc_num = max(balc_num, int(bn))
        except Exception: pass
    blob = " ".join(text_parts)

    tags, vision_tags = set(), set()
    if balc_num > 0 or BALCONY_RE.search(blob): tags.add("balcony")
    if TERRACE_RE.search(blob): tags.add("terrace")
    if GARDEN_RE.search(blob): tags.add("garden")
    if SEA_RE.search(blob) and d_sea <= 1.85: tags.add("sea_view")

    bright = False
    imgs = [thumb] + [r.get("image") for r in recs[:6] if isinstance(r.get("image"), str)]
    for im in imgs:
        vh = url_hash(im)
        vrec = vision_cache.get(vh) if vh else None
        if isinstance(vrec, dict):
            for vt in (vrec.get("tags") or []):
                if vt == "sea_view":
                    if d_sea <= 1.85:
                        tags.add("sea_view"); vision_tags.add("sea_view")
                elif vt in ("balcony","terrace","garden"):
                    tags.add(vt); vision_tags.add(vt)
            if vrec.get("bright"): bright = True

    return {
        "tags": sorted(tags), "vision_tags": sorted(vision_tags),
        "dist_sea_km": d_sea, "waterfront": d_sea <= 0.45, "bright": bright,
    }

def update_price_history(compiled: List[Dict[str, Any]], path: str | Path = "data/price_history.json") -> Tuple[int, int]:
    p = Path(path)
    now_ts = int(time.time())
    hist: Dict[str, Dict[str, Any]] = {}
    if p.exists():
        try: hist = json.loads(p.read_text(encoding="utf-8"))
        except Exception: hist = {}

    drops, new_cnt = 0, 0
    for s in compiled:
        sid = s["id"]
        cur_r = s["units_rent"][0]["p"] if s["units_rent"] else None
        cur_b = s["units_buy"][0]["p"] if s["units_buy"] else None
        rec = hist.get(sid)
        if not rec:
            hist[sid] = {"first_seen": now_ts, "last_seen": now_ts, "r_init": cur_r, "r_min": cur_r, "b_init": cur_b, "b_min": cur_b}
            s["is_new"] = True; new_cnt += 1
            continue
        rec["last_seen"] = now_ts
        if (now_ts - int(rec.get("first_seen", now_ts))) <= 48 * 3600:
            s["is_new"] = True; new_cnt += 1
        drop_info = {}
        if cur_r:
            prev_r = rec.get("r_init") or cur_r
            if cur_r > prev_r: rec["r_init"] = cur_r
            elif prev_r and cur_r <= prev_r * 0.94:
                pct = round(((prev_r - cur_r) / prev_r) * 100)
                if 5 <= pct <= 45: drop_info["rent"] = {"pct": pct, "from": int(prev_r)}
            rec["r_min"] = min(cur_r, rec.get("r_min") or cur_r)
        if cur_b:
            prev_b = rec.get("b_init") or cur_b
            if cur_b > prev_b: rec["b_init"] = cur_b
            elif prev_b and cur_b <= prev_b * 0.95:
                pct = round(((prev_b - cur_b) / prev_b) * 100)
                if 5 <= pct <= 35: drop_info["buy"] = {"pct": pct, "from": int(prev_b)}
            rec["b_min"] = min(cur_b, rec.get("b_min") or cur_b)
        if drop_info:
            s["price_drop"] = drop_info; drops += 1

    cutoff = now_ts - 45 * 86400
    hist = {k: v for k, v in hist.items() if v.get("last_seen", now_ts) >= cutoff}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")
    return drops, new_cnt
