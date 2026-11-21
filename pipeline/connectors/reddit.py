from __future__ import annotations
import re, time
from typing import Any, Dict, List, Optional
import httpx
from pipeline.connectors.base import BaseConnector
from pipeline.connectors.portals import parse_bhk, parse_sqft, parse_furnishing, parse_tenant

PROTO = "https" + "://"
SUBS = ["mumbairentals", "mumbai"]
RENT_SIGNAL = re.compile(r"\b(rent|flatmate|flat\s*mate|bhk|1\s*rk|pg|roommate|occupancy|brokerage|deposit|lease|available\s+from)\b", re.I)
WANTED_SIGNAL = re.compile(r"\b(looking\s+for|need\s+a\s+flat|searching\s+for|want\s+to\s+rent|any\s+leads|required\s+1|budget\s+is)\b", re.I)
PRICE_RE = re.compile(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,\.]*)\s*(k|lac|lakh|l\b|cr)?|\b([1-9]\d)\s*k\b", re.I)

def _extract_rent(text: str) -> Optional[int]:
    for m in PRICE_RE.finditer(text or ""):
        if m.group(3):
            v = int(m.group(3)) * 1000
            if 8000 <= v <= 300000: return v
            continue
        try: num = float(m.group(1).replace(",", ""))
        except Exception: continue
        unit = (m.group(2) or "").lower().strip()
        if unit == "k": val = int(num * 1000)
        elif unit in ("lac", "lakh", "l"): val = int(num * 100000)
        elif unit == "cr": continue
        else: val = int(num) if num >= 8000 else 0
        if 8000 <= val <= 350000: return val
    return None

def _match_locality(text: str, loc_meta: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    low = (text or "").lower()
    for m in sorted(loc_meta, key=lambda x: -len(x["locality"])):
        if re.search(r"\b" + re.escape(m["locality"].lower()) + r"\b", low):
            return m
    stems = {
        "bandra":"Bandra West","andheri":"Andheri West","goregaon":"Goregaon West",
        "malad":"Malad West","kandivali":"Kandivali West","borivali":"Borivali West",
        "santacruz":"Santacruz West","khar":"Khar West","vile parle":"Vile Parle West",
        "dadar":"Dadar West","thane":"Thane West","mulund":"Mulund West",
        "ghatkopar":"Ghatkopar East","vikhroli":"Vikhroli West","bhandup":"Bhandup West",
        "kurla":"Kurla West","dahisar":"Dahisar East","lokhandwala":"Lokhandwala",
    }
    by_name = {m["locality"]: m for m in loc_meta}
    for stem, target in stems.items():
        if re.search(r"\b" + re.escape(stem) + r"\b", low) and target in by_name:
            return by_name[target]
    return None

class RedditRentalsConnector(BaseConnector):
    source_name = "reddit"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 50, fresh_hours: float = 12.0) -> int:
        cached = self.read_cache("reddit:mmr_v1", max_age_hours=fresh_hours)
        if not cached:
            cached = self._fetch_posts(loc_meta)
            if cached: self.write_cache("reddit:mmr_v1", cached)
        saved = 0
        for it in cached:
            self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=it["locality"], zone=it["zone"], source_url=it["url"])
            saved += 1
        return saved

    def _fetch_posts(self, loc_meta: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        hdrs = {"User-Agent": "MumbaiHomesFinder/1.0 (community-aggregator)"}
        items, seen, deadline = [], set(), time.monotonic() + 25.0
        with httpx.Client(headers=hdrs, timeout=8.0, follow_redirects=True) as client:
            for sub in SUBS:
                if time.monotonic() > deadline: break
                try:
                    resp = client.get(f"{PROTO}www.reddit.com/r/{sub}/new.json?limit=60")
                    if resp.status_code != 200: continue
                    children = (resp.json().get("data") or {}).get("children") or []
                except Exception:
                    continue
                for ch in children:
                    d = ch.get("data") or {}
                    title, body = (d.get("title") or "").strip(), (d.get("selftext") or "").strip()
                    full = f"{title} {body[:600]}"
                    if not title or not RENT_SIGNAL.search(full) or WANTED_SIGNAL.search(title): continue
                    rent = _extract_rent(full)
                    if not rent: continue
                    loc_info = _match_locality(full, loc_meta)
                    if not loc_info: continue
                    pid = d.get("id")
                    if not pid or pid in seen: continue
                    seen.add(pid)
                    clean_t = re.sub(r"\[[^\]]+\]", "", title).strip(" -|:")
                    clean_t = (clean_t[:66] + "...") if len(clean_t) > 69 else clean_t
                    pl = d.get("permalink") or ""
                    items.append({
                        "id": f"rd-{pid}", "name": clean_t or f"Direct Rental in {loc_info['locality']}",
                        "locality": loc_info["locality"], "zone": loc_info["zone"],
                        "bhk": parse_bhk(full), "rent_inr": rent, "buy_inr": None,
                        "carpet_sqft": parse_sqft(full), "furnishing": parse_furnishing(full),
                        "tenant": parse_tenant(full) or ("bachelors_ok" if re.search(r"flatmate|roommate|bachelor|female|male", full, re.I) else None),
                        "zero_brokerage": True, "url": f"{PROTO}www.reddit.com{pl}" if pl.startswith("/") else d.get("url"),
                    })
        return items
