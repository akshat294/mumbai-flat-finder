from __future__ import annotations
import hashlib, json, math, re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import httpx

PROTO = "https" + "://"
PHOTON_URL = PROTO + "photon.komoot.io/api/"
OSM_CACHE = Path("data/osm_geo_cache.json")

COAST_LINE = [
    (18.900, 72.8155), (18.915, 72.8215), (18.932, 72.8235), (18.952, 72.7995),
    (18.972, 72.8070), (18.995, 72.8155), (19.018, 72.8185), (19.035, 72.8385),
    (19.050, 72.8235), (19.065, 72.8245), (19.082, 72.8280), (19.105, 72.8268),
    (19.126, 72.8185), (19.142, 72.8165), (19.160, 72.8280), (19.190, 72.8250),
    (19.225, 72.8310), (19.265, 72.8450),
]

EXCLUSION_BOXES = [
    ("Juhu Aerodrome", 19.0930, 19.1018, 72.8282, 72.8382),
    ("CSMIA Airport",  19.0785, 19.1022, 72.8475, 72.8838),
    ("Powai Lake",     19.1205, 19.1348, 72.8980, 72.9125),
    ("Vihar Lake",     19.1420, 19.1680, 72.9000, 72.9260),
    ("Mahim Bay",      19.0265, 19.0470, 72.8140, 72.8382),
    ("Thane Creek",    19.0100, 19.1580, 72.9520, 72.9875),
    ("Mumbai Harbour", 18.8900, 19.0050, 72.8520, 72.9850),
]

SAFE_CENTROIDS: Dict[str, List[float]] = {
    "Colaba":[18.9160,72.8275],"Cuffe Parade":[18.9135,72.8240],"Malabar Hill":[18.9545,72.8045],
    "Worli":[19.0145,72.8215],"Lower Parel":[18.9982,72.8295],"Prabhadevi":[19.0166,72.8296],
    "Dadar West":[19.0193,72.8384],"Matunga":[19.0269,72.8553],"Bandra West":[19.0605,72.8335],
    "Bandra East":[19.0600,72.8520],"Khar West":[19.0700,72.8350],"Santacruz West":[19.0835,72.8380],
    "Vile Parle West":[19.1045,72.8425],"BKC":[19.0653,72.8680],"Pali Hill":[19.0626,72.8285],
    "Juhu":[19.1065,72.8315],"Versova":[19.1360,72.8215],"Andheri West":[19.1364,72.8296],
    "Andheri East":[19.1165,72.8697],"Lokhandwala":[19.1430,72.8280],"Oshiwara":[19.1486,72.8350],
    "Marol":[19.1115,72.8825],"Goregaon East":[19.1663,72.8596],"Goregaon West":[19.1646,72.8397],
    "Malad West":[19.1874,72.8365],"Kandivali East":[19.2056,72.8680],"Kandivali West":[19.2080,72.8370],
    "Borivali West":[19.2307,72.8430],"Dahisar East":[19.2502,72.8650],"Powai":[19.1176,72.9060],
    "Chandivali":[19.1112,72.8980],"Vikhroli West":[19.1120,72.9220],"Ghatkopar East":[19.0790,72.9120],
    "Kanjurmarg":[19.1292,72.9310],"Bhandup West":[19.1470,72.9330],"Mulund West":[19.1726,72.9425],
    "Chembur":[19.0522,72.9005],"Wadala":[19.0170,72.8630],"Sion":[19.0434,72.8633],"Kurla West":[19.0726,72.8800],
    "Thane West":[19.2183,72.9781],"Ghodbunder Road":[19.2590,72.9680],"Hiranandani Estate":[19.2535,72.9815],
    "Majiwada":[19.2125,72.9830],"Kolshet Road":[19.2330,72.9890],"Pokhran Road":[19.2160,72.9630],
    "Vashi":[19.0771,72.9986],"Nerul":[19.0330,73.0169],"Seawoods":[19.0205,73.0185],
    "Kharghar":[19.0473,73.0699],"CBD Belapur":[19.0237,73.0404],"Airoli":[19.1590,72.9986],
    "Ulwe":[18.9722,73.0285],"Panvel":[18.9894,73.1175],
}

def _hav_km(la1: float, ln1: float, la2: float, ln2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(ln2 - ln1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))

def coastline_min_lng(lat: float) -> float:
    if lat <= COAST_LINE[0][0]: return COAST_LINE[0][1]
    if lat >= COAST_LINE[-1][0]: return COAST_LINE[-1][1]
    for i in range(len(COAST_LINE) - 1):
        la1, ln1 = COAST_LINE[i]
        la2, ln2 = COAST_LINE[i + 1]
        if la1 <= lat <= la2:
            return ln1 + ((lat - la1) / (la2 - la1)) * (ln2 - ln1)
    return 72.8200

def is_valid_mmr_land(lat: Optional[float], lng: Optional[float], locality: Optional[str] = None) -> bool:
    if lat is None or lng is None:
        return False
    try:
        lat, lng = float(lat), float(lng)
    except Exception:
        return False
    if not (18.88 <= lat <= 19.32 and 72.78 <= lng <= 73.18):
        return False
    if lng < coastline_min_lng(lat):
        return False
    for _, la1, la2, ln1, ln2 in EXCLUSION_BOXES:
        if la1 <= lat <= la2 and ln1 <= lng <= ln2:
            return False
    if locality and locality in SAFE_CENTROIDS:
        cla, cln = SAFE_CENTROIDS[locality]
        if _hav_km(lat, lng, cla, cln) > 5.5:
            return False
    return True

def safe_approx_coords(soc_id: str, locality: str) -> Tuple[float, float]:
    base = SAFE_CENTROIDS.get(locality) or [19.0760, 72.8777]
    h = int(hashlib.md5(soc_id.encode("utf-8")).hexdigest()[:8], 16)
    base_ang = (h % 360) * (math.pi / 180.0)
    rad = 0.0006 + ((h >> 8) % 100) * 0.000018
    for step in range(12):
        ang = base_ang + step * (math.pi / 6.0)
        la = round(base[0] + math.sin(ang) * rad, 6)
        ln = round(base[1] + math.cos(ang) * rad, 6)
        if is_valid_mmr_land(la, ln, locality):
            return la, ln
    return base[0], base[1]

def enrich_with_osm_photon(societies: List[Dict], max_calls: int = 40) -> Dict[str, List[float]]:
    import time
    cache: Dict[str, List[float]] = {}
    if OSM_CACHE.exists():
        try: cache = json.loads(OSM_CACHE.read_text(encoding="utf-8-sig"))
        except Exception: cache = {}
    if max_calls <= 0:
        return cache
    calls, consec_err = 0, 0
    deadline = time.monotonic() + 45.0
    with httpx.Client(timeout=5.0, headers={"User-Agent": "MumbaiHomesFinder/1.0"}) as client:
        for soc in societies:
            if calls >= max_calls or time.monotonic() > deadline or consec_err >= 3:
                break
            cid = soc["id"]
            if cid in cache:
                continue
            if is_valid_mmr_land(soc.get("lat"), soc.get("lng"), soc.get("locality")):
                continue
            loc = soc.get("locality") or "Mumbai"
            q = f"{soc['name']}, {loc}, Mumbai"
            calls += 1
            try:
                r = client.get(PHOTON_URL, params={"q": q, "limit": 1, "lat": 19.08, "lon": 72.88})
                if r.status_code != 200:
                    consec_err += 1
                    continue
                consec_err = 0
                feats = r.json().get("features") or []
                if not feats:
                    cache[cid] = []
                    continue
                lon, lat = feats[0]["geometry"]["coordinates"][:2]
                cache[cid] = [round(float(lat), 6), round(float(lon), 6)] if is_valid_mmr_land(lat, lon, loc) else []
            except Exception:
                consec_err += 1
                continue
    OSM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OSM_CACHE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    return cache
SUBLOC_ALIASES: Dict[str, str] = {
    "bhatt lane": "Borivali West", "khandivali": "Kandivali West",
    "kandivli west": "Kandivali West", "kandivli east": "Kandivali East",
    "borivli west": "Borivali West", "borivli east": "Borivali West",
    "yogi nagar": "Borivali West", "ic colony": "Borivali West", "i c colony": "Borivali West",
    "shimpoli": "Borivali West", "charkop": "Kandivali West", "mahavir nagar": "Kandivali West",
    "thakur village": "Kandivali East", "thakur complex": "Kandivali East",
    "evershine nagar": "Malad West", "orlem": "Malad West", "mindspace": "Malad West",
    "dindoshi": "Goregaon East", "gokuldham": "Goregaon East", "royal palms": "Goregaon East",
    "four bungalows": "Andheri West", "seven bungalows": "Versova", "yari road": "Versova",
    "jb nagar": "Andheri East", "chakala": "Andheri East", "saki naka": "Chandivali",
    "sakinaka": "Chandivali", "nahar amrit shakti": "Chandivali", "hiranandani gardens": "Powai",
    "vakola": "Santacruz West", "kalina": "Bandra East", "kalanagar": "Bandra East",
    "carter road": "Bandra West", "bandstand": "Bandra West", "hill road": "Bandra West",
    "chapel road": "Bandra West", "ranwar": "Bandra West", "shivaji park": "Dadar West",
    "byculla": "Lower Parel", "parel": "Lower Parel", "tardeo": "Malabar Hill",
    "pedder road": "Malabar Hill", "breach candy": "Malabar Hill", "walkeshwar": "Malabar Hill",
    "kemps corner": "Malabar Hill", "nariman point": "Colaba",
    "mira road": "Dahisar East", "bhayandar": "Dahisar East",
    "kasarvadavali": "Ghodbunder Road", "waghbil": "Ghodbunder Road",
    "manpada": "Ghodbunder Road", "brahmand": "Ghodbunder Road",
    "balkum": "Majiwada", "vartak nagar": "Pokhran Road", "vasant vihar": "Pokhran Road",
    "sanpada": "Vashi", "kopar khairane": "Vashi", "koparkhairane": "Vashi",
    "ghansoli": "Airoli", "kamothe": "Panvel", "kalamboli": "Panvel", "taloja": "Kharghar",
}

def nearest_locality(lat: float, lng: float) -> Tuple[str, float]:
    best_loc, best_km = "Mumbai", 999.0
    for loc, (cla, cln) in SAFE_CENTROIDS.items():
        d = _hav_km(lat, lng, cla, cln)
        if d < best_km:
            best_km, best_loc = d, loc
    return best_loc, best_km

def infer_true_locality(text: str, current_loc: str) -> str:
    low = (text or "").lower().replace("-", " ")
    for loc in sorted(SAFE_CENTROIDS.keys(), key=lambda x: -len(x)):
        if re.search(r"\b" + re.escape(loc.lower()) + r"\b", low):
            return loc
    for alias, target in sorted(SUBLOC_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            return target
    return current_loc
