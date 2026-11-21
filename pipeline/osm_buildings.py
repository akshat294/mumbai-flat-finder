from __future__ import annotations
import json, re, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx
from pipeline.geo_guard import is_valid_mmr_land, SAFE_CENTROIDS, _hav_km

PROTO = "https" + "://"
OVERPASS_URLS = [
    PROTO + "overpass-api.de/api/interpreter",
    PROTO + "overpass.kumi.systems/api/interpreter",
    PROTO + "maps.mail.ru/osm/tools/overpass/api/interpreter",
]
BLDG_CACHE = Path("data/mumbai_osm_buildings.json")

STOP_WORDS = {
    "chs","chsl","co","op","hsg","soc","society","cooperative","housing",
    "apartment","apartments","apt","apts","building","bldg","tower","towers",
    "residency","residence","residences","complex","enclave","heights","plaza",
    "court","park","gardens","garden","view","villa","villas","mansion",
    "palace","arcade","manor","estate","phase","wing","sector","mumbai",
    "thane","navi","west","east","north","south","the","shri","shree","new",
    "flat","flats","for","rent","sale","bhk","rk","near","road","rd","lane","marg",
}

def _norm(name: str) -> str:
    s = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return " ".join(t for t in s.split() if len(t) > 1 and t not in STOP_WORDS)

def _norm_road(name: str) -> str:
    s = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return " ".join(t for t in s.split() if len(t) > 1 and t not in {"mumbai","thane","west","east","near","opp","opposite"})

def load_osm_buildings(allow_fetch: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    if BLDG_CACHE.exists() and (time.time() - BLDG_CACHE.stat().st_mtime) / 86400.0 < 45.0:
        try:
            data = json.loads(BLDG_CACHE.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and len(data.get("buildings") or []) > 500: return data
            if isinstance(data, list) and len(data) > 500: return {"buildings": data, "roads": []}
        except Exception: pass
    if not allow_fetch: return {"buildings": [], "roads": []}

    q = (
        '[out:json][timeout:45];('
        'way["building"]["name"](18.89,72.79,19.31,73.15);'
        'node["building"]["name"](18.89,72.79,19.31,73.15);'
        'way["landuse"="residential"]["name"](18.89,72.79,19.31,73.15);'
        'way["highway"]["name"](18.89,72.79,19.31,73.15);'
        ');out center 35000;'
    )
    bldgs, roads, seen_b, seen_r = [], [], set(), set()
    for url in OVERPASS_URLS:
        try:
            print("[osm-buildings] Downloading Mumbai MMR buildings & streets...", flush=True)
            with httpx.Client(timeout=55.0, headers={"User-Agent": "MumbaiHomesFinder/1.0"}) as client:
                r = client.post(url, data={"data": q})
                if r.status_code != 200: continue
                for el in (r.json().get("elements") or []):
                    tags = el.get("tags") or {}
                    name = (tags.get("name") or "").strip()
                    if not name or len(name) < 3 or len(name) > 80: continue
                    c = el.get("center") or {}
                    lat = el.get("lat") if el.get("lat") is not None else c.get("lat")
                    lng = el.get("lon") if el.get("lon") is not None else c.get("lon")
                    if not is_valid_mmr_land(lat, lng, None): continue
                    la, ln = round(float(lat), 6), round(float(lng), 6)
                    if tags.get("highway") and not tags.get("building"):
                        rk = _norm_road(name)
                        if len(rk) >= 4 and (rk, round(la, 2), round(ln, 2)) not in seen_r:
                            seen_r.add((rk, round(la, 2), round(ln, 2)))
                            roads.append({"k": rk, "lat": la, "lng": ln})
                    else:
                        nk = _norm(name)
                        if len(nk) >= 3 and (nk, round(la, 3), round(ln, 3)) not in seen_b:
                            seen_b.add((nk, round(la, 3), round(ln, 3)))
                            bldgs.append({"k": nk, "lat": la, "lng": ln})
                if bldgs: break
        except Exception as exc:
            print(f"[osm-buildings] Mirror warning: {str(exc)[:80]}", flush=True)
    payload = {"buildings": bldgs, "roads": roads}
    if bldgs:
        BLDG_CACHE.parent.mkdir(parents=True, exist_ok=True)
        BLDG_CACHE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[osm-buildings] Cached {len(bldgs):,} buildings & {len(roads):,} streets!", flush=True)
    return payload

class OSMBuildingIndex:
    def __init__(self, data: Dict[str, List[Dict[str, Any]]] | List[Dict[str, Any]]):
        bldgs = data.get("buildings") if isinstance(data, dict) else (data or [])
        roads = data.get("roads") if isinstance(data, dict) else []
        self.exact: Dict[str, List[Tuple[float, float]]] = {}
        self.by_token: Dict[str, List[Tuple[str, float, float]]] = {}
        self.roads_by_tok: Dict[str, List[Tuple[str, float, float]]] = {}
        for it in (bldgs or []):
            k, la, ln = it["k"], it["lat"], it["lng"]
            self.exact.setdefault(k, []).append((la, ln))
            toks = k.split()
            if toks and len(max(toks, key=len)) >= 4:
                self.by_token.setdefault(max(toks, key=len), []).append((k, la, ln))
        for it in (roads or []):
            k, la, ln = it["k"], it["lat"], it["lng"]
            toks = [t for t in k.split() if len(t) >= 4 and t not in {"road","lane","marg","street","cross","main"}]
            if toks:
                self.roads_by_tok.setdefault(max(toks, key=len), []).append((k, la, ln))

    def lookup(self, society_name: str, locality: str) -> Optional[Tuple[float, float]]:
        nk, centroid = _norm(society_name), SAFE_CENTROIDS.get(locality)
        def _pick(cands, max_km):
            if not cands: return None
            if not centroid: return cands[0]
            cla, cln = centroid
            scored = sorted(((_hav_km(la, ln, cla, cln), la, ln) for la, ln in cands), key=lambda x: x[0])
            return (scored[0][1], scored[0][2]) if scored[0][0] <= max_km else None
        if len(nk) >= 3:
            if nk in self.exact:
                hit = _pick(self.exact[nk], 4.8)
                if hit: return hit
            toks = set(nk.split())
            if len(toks) >= 2:
                kt = max(toks, key=len)
                hit = _pick([(la, ln) for ck, la, ln in (self.by_token.get(kt) or []) if toks.issubset(set(ck.split())) or set(ck.split()).issubset(toks)], 4.0)
                if hit: return hit
        rk = _norm_road(society_name)
        rtoks = [t for t in rk.split() if len(t) >= 4 and t not in {"road","lane","marg","street","cross","main","apt","chs","society"}]
        for kt in sorted(rtoks, key=len, reverse=True)[:2]:
            hit = _pick([(la, ln) for ck, la, ln in (self.roads_by_tok.get(kt) or []) if ck in rk], 3.8)
            if hit: return hit
        return None
