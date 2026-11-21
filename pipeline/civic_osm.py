from __future__ import annotations
import json, math, time
from pathlib import Path
from typing import Any, Dict, List
import httpx

PROTO = "https" + "://"
OVERPASS_URL = PROTO + "overpass-api.de/api/interpreter"
CIVIC_CACHE = Path("data/osm_civic_cache.json")

SEED_CIVIC: Dict[str, List[Dict[str, Any]]] = {
    "hospital": [
        {"n":"Lilavati Hospital","lat":19.0510,"lng":72.8292},{"n":"Kokilaben Ambani Hospital","lat":19.1312,"lng":72.8250},
        {"n":"Nanavati Max Hospital","lat":19.0956,"lng":72.8404},{"n":"Hinduja Hospital Mahim","lat":19.0337,"lng":72.8384},
        {"n":"Hiranandani Hospital Powai","lat":19.1205,"lng":72.9168},{"n":"Breach Candy Hospital","lat":18.9720,"lng":72.8047},
        {"n":"Jaslok Hospital","lat":18.9716,"lng":72.8096},{"n":"KEM Hospital Parel","lat":19.0024,"lng":72.8419},
        {"n":"Jupiter Hospital Thane","lat":19.2094,"lng":72.9735},{"n":"Bethany Hospital Thane","lat":19.2188,"lng":72.9634},
        {"n":"Fortis Hospital Mulund","lat":19.1620,"lng":72.9422},{"n":"Apollo Hospital Navi Mumbai","lat":19.0218,"lng":73.0289},
        {"n":"MGM Hospital Vashi","lat":19.0752,"lng":72.9923},{"n":"Terna Hospital Nerul","lat":19.0337,"lng":73.0180},
        {"n":"Zen Hospital Chembur","lat":19.0548,"lng":72.8992},{"n":"Criticare Hospital Andheri","lat":19.1154,"lng":72.8473},
        {"n":"Karuna Hospital Borivali","lat":19.2422,"lng":72.8485},{"n":"Thunga Hospital Malad","lat":19.1865,"lng":72.8427},
    ],
    "park": [
        {"n":"Shivaji Park","lat":19.0270,"lng":72.8384},{"n":"Joggers Park Bandra","lat":19.0604,"lng":72.8219},
        {"n":"Bandstand Promenade","lat":19.0510,"lng":72.8206},{"n":"Juhu Beach / Kaifi Azmi Park","lat":19.1068,"lng":72.8268},
        {"n":"Powai Lake Promenade","lat":19.1235,"lng":72.9050},{"n":"SGNP / Aarey Green Belt","lat":19.2314,"lng":72.8641},
        {"n":"Hanging Gardens","lat":18.9565,"lng":72.8050},{"n":"Priyadarshini Park","lat":18.9638,"lng":72.8012},
        {"n":"Five Gardens Matunga","lat":19.0241,"lng":72.8535},{"n":"Upvan Lake Park Thane","lat":19.2225,"lng":72.9567},
        {"n":"Central Park Kharghar","lat":19.0558,"lng":73.0630},{"n":"Jewel of Navi Mumbai","lat":19.0258,"lng":73.0160},
        {"n":"Mindspace Garden Malad","lat":19.1802,"lng":72.8331},{"n":"Diamond Garden Chembur","lat":19.0545,"lng":72.8980},
    ],
    "supermarket": [
        {"n":"D-Mart Powai","lat":19.1156,"lng":72.9088},{"n":"D-Mart Malad West","lat":19.1890,"lng":72.8347},
        {"n":"D-Mart Goregaon East","lat":19.1680,"lng":72.8548},{"n":"D-Mart Ghodbunder Thane","lat":19.2545,"lng":72.9765},
        {"n":"D-Mart Kolshet Thane","lat":19.2300,"lng":72.9875},{"n":"D-Mart Vashi","lat":19.0928,"lng":73.0050},
        {"n":"D-Mart Seawoods / Nerul","lat":19.0226,"lng":73.0185},{"n":"D-Mart Kharghar","lat":19.0445,"lng":73.0685},
        {"n":"Nature's Basket Bandra","lat":19.0595,"lng":72.8312},{"n":"Nature's Basket Juhu","lat":19.1032,"lng":72.8286},
        {"n":"Nature's Basket Worli","lat":19.0068,"lng":72.8172},{"n":"Reliance Smart Andheri W","lat":19.1362,"lng":72.8315},
        {"n":"D-Mart Kandivali West","lat":19.2102,"lng":72.8402},{"n":"D-Mart Borivali West","lat":19.2292,"lng":72.8452},
        {"n":"D-Mart Mulund West","lat":19.1740,"lng":72.9482},{"n":"D-Mart Chembur","lat":19.0570,"lng":72.8995},
    ],
    "school": [
        {"n":"Dhirubhai Ambani Intl BKC","lat":19.0642,"lng":72.8632},{"n":"Bombay Scottish Mahim","lat":19.0357,"lng":72.8380},
        {"n":"Bombay Scottish Powai","lat":19.1243,"lng":72.9096},{"n":"Jamnabai Narsee Juhu","lat":19.1055,"lng":72.8364},
        {"n":"Oberoi Intl Goregaon","lat":19.1712,"lng":72.8622},{"n":"Hiranandani Foundation Thane","lat":19.2540,"lng":72.9822},
        {"n":"Singhania School Thane","lat":19.2082,"lng":72.9648},{"n":"DPS Nerul","lat":19.0268,"lng":73.0124},
        {"n":"Podar Intl Santacruz","lat":19.0827,"lng":72.8380},{"n":"Cathedral & John Connon","lat":18.9348,"lng":72.8325},
        {"n":"Ryan Intl Kharghar","lat":19.0462,"lng":73.0680},{"n":"Vibgyor High Malad","lat":19.1840,"lng":72.8390},
    ],
}

def _fast_dist_m(la1: float, ln1: float, la2: float, ln2: float) -> int:
    return int(math.hypot((ln2 - ln1) * 105200.0, (la2 - la1) * 110700.0))

def load_civic_pois(allow_fetch: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    if CIVIC_CACHE.exists():
        if (time.time() - CIVIC_CACHE.stat().st_mtime) / 86400.0 < 30.0:
            try:
                data = json.loads(CIVIC_CACHE.read_text(encoding="utf-8-sig"))
                if data: return data
            except Exception: pass
    merged = {k: list(v) for k, v in SEED_CIVIC.items()}
    if allow_fetch:
        q = '[out:json][timeout:16];(node["amenity"="hospital"]["name"](18.89,72.79,19.30,73.15);node["shop"="supermarket"]["name"](18.89,72.79,19.30,73.15);node["leisure"="park"]["name"](18.89,72.79,19.30,73.15);node["amenity"="school"]["name"](18.89,72.79,19.30,73.15););out body 1200;'
        try:
            with httpx.Client(timeout=18.0, headers={"User-Agent": "MumbaiHomesFinder/1.0"}) as client:
                r = client.post(OVERPASS_URL, data={"data": q})
                if r.status_code == 200:
                    seen = {k: {x["n"].lower() for x in v} for k, v in merged.items()}
                    for el in (r.json().get("elements") or []):
                        tags = el.get("tags") or {}
                        name, lat, lon = (tags.get("name") or "").strip(), el.get("lat"), el.get("lon")
                        if not name or not lat or not lon or len(name) > 52: continue
                        cat = "hospital" if tags.get("amenity") == "hospital" else ("supermarket" if tags.get("shop") == "supermarket" else ("park" if tags.get("leisure") == "park" else ("school" if tags.get("amenity") == "school" else None)))
                        if cat and name.lower() not in seen[cat] and len(merged[cat]) < 350:
                            seen[cat].add(name.lower())
                            merged[cat].append({"n": name, "lat": round(float(lat), 5), "lng": round(float(lon), 5)})
        except Exception:
            pass
    CIVIC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CIVIC_CACHE.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return merged

def enrich_civic(lat: float, lng: float, pois: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for cat in ("hospital", "supermarket", "park", "school"):
        best_n, best_d = None, 999999
        for pt in (pois.get(cat) or []):
            d = _fast_dist_m(lat, lng, pt["lat"], pt["lng"])
            if d < best_d: best_d, best_n = d, pt["n"]
        out[cat] = {"name": best_n, "dist_m": best_d} if best_n else None
    return out
