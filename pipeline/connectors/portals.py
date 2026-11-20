from __future__ import annotations
import json, os, re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from pipeline.connectors.base import BaseConnector

HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36", "Accept-Language": "en-IN,en;q=0.9"}
RERA_RE = re.compile(r"P51[789]\d{8}")

def _http() -> httpx.Client:
    return httpx.Client(headers=HDRS, timeout=25, follow_redirects=True, proxy=os.getenv("PROXY_URL") or None)

def parse_inr(text: Any) -> Optional[int]:
    if not text: return None
    s = re.sub(r"[₹,\s]+", " ", str(text)).strip().lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(cr|crore|lac|lakh|l\b|k\b)?", s)
    if not m: return None
    val, unit = float(m.group(1)), (m.group(2) or "").strip()
    if unit in ("cr", "crore"): return int(val * 10_000_000)
    if unit in ("lac", "lakh", "l"): return int(val * 100_000)
    if unit == "k": return int(val * 1_000)
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if (digits and len(digits) >= 4) else (int(val) if val >= 5000 else None)

def parse_bhk(t: str) -> Optional[int]:
    m = re.search(r"(\d)\s*(?:bhk|rk)", t or "", re.I)
    return int(m.group(1)) if m else None

def parse_sqft(t: str) -> Optional[float]:
    m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", t or "", re.I)
    return float(m.group(1)) if m else None

def clean_name(title: str, locality: str) -> str:
    t = re.sub(r"\s+", " ", title or "").strip()
    m = re.search(r"\bin\s+(.+?)(?:,\s*" + re.escape(locality) + r"|\s*,\s*(?:Mumbai|Thane|Navi Mumbai)|$)", t, re.I)
    if m and len(m.group(1).strip(" ,.-")) >= 3 and m.group(1).strip(" ,.-").lower() != locality.lower():
        return m.group(1).strip(" ,.-")
    return re.sub(r"^\d\s*(?:BHK|RK)\s*(?:Flat|Apartment|House|Studio)?\s*(?:for\s*(?:Rent|Sale))?\s*(?:in\s*)?", "", t, flags=re.I).strip(" ,.-") or t

def extract_ld(html: str) -> List[Any]:
    out = []
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.I | re.S):
        try: out.append(json.loads(raw.strip()))
        except Exception: pass
    return out

class MagicBricksConnector(BaseConnector):
    source_name = "magicbricks"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 20, fresh_hours: float = 20.0) -> int:
        meta_map = {m["locality"]: m for m in loc_meta}
        self.db.register_jobs(self.source_name, list(meta_map.keys()))
        pending = [j for j in self.db.next_pending_jobs(self.source_name) if j["locality"] in meta_map]
        saved = 0
        with _http() as client:
            for job in pending:
                loc, info = job["locality"], meta_map[job["locality"]]
                self.db.mark_job(job["job_key"], "in_progress")
                try:
                    cached = self.read_cache(f"mb4:{loc}", max_age_hours=fresh_hours)
                    if not cached:
                        cp = info["city"].replace(" ", "-")
                        cached = self._fetch(client, loc, cp, "rent", limit_per_locality) + self._fetch(client, loc, cp, "sale", limit_per_locality)
                        if cached: self.write_cache(f"mb4:{loc}", cached)
                    for it in cached:
                        self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], lat=it.get("lat"), lng=it.get("lng"), rera_id=it.get("rera_id"), source_url=it.get("url"))
                        saved += 1
                    self.db.mark_job(job["job_key"], "done" if cached else "failed", None if cached else "0 records")
                    self.polite_sleep(0.5, 1.1)
                except Exception as exc:
                    self.db.mark_job(job["job_key"], "failed", str(exc)[:300])
        return saved

    def _fetch(self, client: httpx.Client, locality: str, city_param: str, mode: str, limit: int) -> List[Dict[str, Any]]:
        url = f"https://www.magicbricks.com/property-for-{mode}/residential-real-estate?Locality={quote_plus(locality.replace(' ', '-'))}&cityName={quote_plus(city_param)}"
        resp = client.get(url)
        if resp.status_code != 200: return []
        soup = BeautifulSoup(resp.text, "html.parser")
        ld_geo = []
        for blk in extract_ld(resp.text):
            for node in (blk.get("@graph", []) if isinstance(blk, dict) else (blk if isinstance(blk, list) else [])):
                if not isinstance(node, dict): continue
                obj = node.get("object") if isinstance(node.get("object"), dict) else node
                geo = obj.get("geo") if isinstance(obj, dict) else None
                if isinstance(geo, dict) and geo.get("latitude"):
                    try: ld_geo.append({"lat": float(geo["latitude"]), "lng": float(geo["longitude"]), "url": obj.get("url") or node.get("url")})
                    except Exception: pass
        items = []
        for idx, card in enumerate(soup.select(".mb-srp__card")[:limit]):
            t_el, p_el = card.select_one(".mb-srp__card--title"), card.select_one(".mb-srp__card__price--amount")
            if not t_el or not p_el: continue
            title, price = t_el.get_text(" ", strip=True), parse_inr(p_el.get_text(" ", strip=True))
            if not price: continue
            s_el = card.select_one(".mb-srp__card__society--name")
            name = s_el.get_text(" ", strip=True) if s_el else clean_name(title, locality)
            if len(name) < 3 or name.lower() == locality.lower(): continue
            txt = card.get_text(" ", strip=True)
            rm = RERA_RE.search(txt)
            items.append({
                "id": f"mb-{mode}-{re.sub(r'[^a-z0-9]','',locality.lower())[:10]}-{idx}-{re.sub(r'[^a-z0-9]','',name.lower())[:16]}",
                "name": name, "locality": locality, "lat": ld_geo[idx]["lat"] if idx < len(ld_geo) else None,
                "lng": ld_geo[idx]["lng"] if idx < len(ld_geo) else None, "bhk": parse_bhk(title),
                "rent_inr": price if mode == "rent" else None, "buy_inr": price if mode == "sale" else None,
                "carpet_sqft": parse_sqft(txt), "rera_id": rm.group(0) if rm else None,
                "url": (ld_geo[idx].get("url") if idx < len(ld_geo) else None) or url,
            })
        return items

class NoBrokerConnector(BaseConnector):
    source_name = "nobroker"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 20, fresh_hours: float = 20.0) -> int:
        meta_map = {m["locality"]: m for m in loc_meta}
        self.db.register_jobs(self.source_name, list(meta_map.keys()))
        pending = [j for j in self.db.next_pending_jobs(self.source_name) if j["locality"] in meta_map]
        saved = 0
        with _http() as client:
            for job in pending:
                loc, info = job["locality"], meta_map[job["locality"]]
                self.db.mark_job(job["job_key"], "in_progress")
                try:
                    cached = self.read_cache(f"nb4:{loc}", max_age_hours=fresh_hours)
                    if not cached:
                        slug = re.sub(r"[^a-z0-9]+", "_", loc.lower()).strip("_")
                        url = f"https://www.nobroker.in/flats-for-rent-in-{slug}_mumbai"
                        resp = client.get(url)
                        cached = []
                        if resp.status_code == 200:
                            res_list = []
                            for blk in extract_ld(resp.text):
                                for node in (blk if isinstance(blk, list) else [blk]):
                                    if isinstance(node, dict) and node.get("@type") in ("Residence","Apartment","SingleFamilyResidence"):
                                        murl = (((node.get("containedInPlace") or {}).get("hasMap") or {}).get("url") or "")
                                        qm = re.search(r"query=([0-9.]+),([0-9.]+)", murl)
                                        res_list.append({"name": node.get("name") or (node.get("address") or {}).get("streetAddress") or "", "lat": float(qm.group(1)) if qm else None, "lng": float(qm.group(2)) if qm else None, "url": node.get("url") or url})
                            cards = BeautifulSoup(resp.text, "html.parser").select("article, [id^='article_'], section[aria-label]")
                            for idx in range(min(max(len(cards), len(res_list)), limit_per_locality)):
                                ct = cards[idx].get_text(" ", strip=True) if idx < len(cards) else ""
                                rs = res_list[idx] if idx < len(res_list) else {}
                                h = cards[idx].select_one("h2, h3, a[title]") if idx < len(cards) else None
                                title = h.get_text(" ", strip=True) if h else ""
                                name = clean_name(rs.get("name") or title, loc)
                                if len(name) < 3 or name.lower() == loc.lower(): continue
                                money = [m for m in (parse_inr(x) for x in re.findall(r"(?:₹|Rs\.?)\s*[0-9,.]+\s*(?:Lac|Lakh|Cr|k)?", ct, re.I)) if m and 8000 <= m <= 2_500_000]
                                rent = money[0] if money else None
                                dep = money[1] if len(money) > 1 and money[1] >= (rent or 0) else None
                                cached.append({"id": f"nb-{re.sub(r'[^a-z0-9]','',loc.lower())[:10]}-{idx}-{re.sub(r'[^a-z0-9]','',name.lower())[:16]}", "name": name, "locality": loc, "lat": rs.get("lat"), "lng": rs.get("lng"), "bhk": parse_bhk(title or ct), "rent_inr": rent, "deposit_inr": dep, "carpet_sqft": parse_sqft(ct), "zero_brokerage": True, "url": rs.get("url") or url})
                        if cached: self.write_cache(f"nb4:{loc}", cached)
                    for it in cached:
                        self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], lat=it.get("lat"), lng=it.get("lng"), source_url=it.get("url"))
                        saved += 1
                    self.db.mark_job(job["job_key"], "done" if cached else "failed", None if cached else "0 records")
                    self.polite_sleep(0.5, 1.1)
                except Exception as exc:
                    self.db.mark_job(job["job_key"], "failed", str(exc)[:300])
        return saved
