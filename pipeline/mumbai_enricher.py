from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict
from pipeline.entity_resolver import haversine_m

def load_transit(path: str | Path = "data/mumbai_transit_2026.json") -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def enrich_mumbai(lat: float, lng: float, transit: Dict[str, Any]) -> Dict[str, Any]:
    best_m, best_md = None, float("inf")
    for line, stations in transit["metro_lines"].items():
        for st in stations:
            d = haversine_m(lat, lng, st["lat"], st["lng"])
            if d < best_md:
                best_md = d
                best_m = {"name": st["name"], "line": line, "distance_m": int(d), "walk_min": max(1, int(round((d * 1.25) / 78.0)))}
    best_l, best_ld = None, float("inf")
    for st in transit["local_stations"]:
        d = haversine_m(lat, lng, st["lat"], st["lng"])
        if d < best_ld:
            best_ld = d
            best_l = {"name": st["name"], "distance_m": int(d), "walk_min": max(1, int(round((d * 1.25) / 78.0)))}
    commutes = {
        hid: max(6, int(round(((haversine_m(lat, lng, h["lat"], h["lng"]) / 1000.0) * 1.35 / 18.0) * 60.0)))
        for hid, h in transit["commute_hubs"].items()
    }
    flood = "low"
    for spot in transit["monsoon_hotspots"]:
        d = haversine_m(lat, lng, spot["lat"], spot["lng"])
        if d <= spot["radius_m"]:
            flood = spot["severity"]
            break
        elif d <= spot["radius_m"] * 1.7 and flood == "low":
            flood = "moderate"
    return {"nearest_metro": best_m, "nearest_local": best_l, "commute_hubs_min": commutes, "monsoon_flood_risk": flood}
