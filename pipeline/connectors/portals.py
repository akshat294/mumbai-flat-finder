from __future__ import annotations
import json, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from pipeline.connectors.base import BaseConnector

HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}
RERA_RE = re.compile(r"P51[789]\d{8}")
JUNK_NAME = re.compile(r"(flats?,?\s*apartments?|houses?\s+for\s+(rent|sale)|properties\s+for\s+(rent|sale)|\bfor\s+(rent|sale)\s+in\b|\bnear\s+me\b|^\d+\s*(bhk|rk)\s*(flat|apartment|house)?$)", re.I)
COMM_RE = re.compile(
    r"\b(office|commercial|shop|showroom|warehouse|godown|business\s*park|corporate|chambers|"
    r"trade\s*star|trade\s*center|town\s*center|it\s*park|coworking|co-working|the\s*summit|industrial\s*estate|mindspace|tech\s*park|infotech|cyber\s*park|knowledge\s*park|business\s*bay|corporate\s*park|\bsez\b)\b",
    re.I,
)

def _http() -> httpx.Client:
    return httpx.Client(headers=HDRS, timeout=10, follow_redirects=True, proxy=os.getenv("PROXY_URL") or None)

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
    if re.search(r"\b1[\s\-]*rk\b|\bstudio\b", t or "", re.I): return 0
    m = re.search(r"(\d)\s*bhk", t or "", re.I)
    return int(m.group(1)) if m else None

def parse_sqft(t: str) -> Optional[float]:
    m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", t or "", re.I)
    return float(m.group(1)) if m else None

def parse_furnishing(t: str) -> Optional[str]:
    low = (t or "").lower()
    if "semi-furnished" in low or "semi furnished" in low: return "semi"
    if "unfurnished" in low: return "unfurnished"
    if "furnished" in low: return "furnished"
    return None

def parse_tenant(t: str) -> Optional[str]:
    low = (t or "").lower()
    if "bachelor" in low: return "bachelors_ok"
    if "family" in low: return "family"
    return None

def clean_name(title: str, locality: str) -> str:
    t = re.sub(r"\s+", " ", title or "").strip()
    m_nb = re.search(r"\bin\s+(.+?)\s+for\s+(?:rent|sale)\b", t, re.I)
    if m_nb:
        cand = m_nb.group(1).strip(" ,.-")
        if len(cand) >= 3 and cand.lower() != locality.lower():
            return cand
    m = re.search(r"\bin\s+(.+?)(?:,\s*" + re.escape(locality) + r"|\s*,\s*(?:Mumbai|Thane|Navi Mumbai)|$)", t, re.I)
    if m:
        cand = m.group(1).strip(" ,.-")
        if len(cand) >= 3 and cand.lower() != locality.lower():
            return cand
    return re.sub(r"^\d\s*(?:BHK|RK)\s*(?:Flat|Apartment|House|Studio)?\s*(?:for\s*(?:Rent|Sale))?\s*(?:in\s*)?", "", t, flags=re.I).strip(" ,.-") or t

def extract_ld(html: str) -> List[Any]:
    out = []
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.I | re.S):
        try: out.append(json.loads(raw.strip()))
        except Exception: pass
    return out


class MagicBricksConnector(BaseConnector):
    source_name = "magicbricks"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 150, fresh_hours: float = 20.0) -> int:
        meta_map = {m["locality"]: m for m in loc_meta}
        self.db.register_jobs(self.source_name, list(meta_map.keys()))
        pending = [j for j in self.db.next_pending_jobs(self.source_name) if j["locality"] in meta_map]
        if not pending: return 0

        def _worker(job):
            loc, info = job["locality"], meta_map[job["locality"]]
            cached = self.read_cache(f"mb5:{loc}:{limit_per_locality}", max_age_hours=fresh_hours)
            if cached: return job, info, cached, None
            try:
                cp = info["city"].replace(" ", "-")
                with _http() as client:
                    items = self._fetch(client, loc, cp, "rent", limit_per_locality) + self._fetch(client, loc, cp, "sale", limit_per_locality)
                if items: self.write_cache(f"mb5:{loc}:{limit_per_locality}", items)
                return job, info, items, None
            except Exception as exc:
                return job, info, [], str(exc)[:300]

        saved = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            for fut in as_completed([ex.submit(_worker, j) for j in pending]):
                job, info, items, err = fut.result()
                loc = job["locality"]
                if err:
                    self.db.mark_job(job["job_key"], "failed", err); continue
                for it in items:
                    self.db.upsert_raw_record(
                        self.source_name, it["id"], it["name"], it,
                        locality=loc, zone=info["zone"], lat=it.get("lat"), lng=it.get("lng"),
                        rera_id=it.get("rera_id"), source_url=it.get("url"),
                    )
                    saved += 1
                self.db.mark_job(job["job_key"], "done" if items else "failed", None if items else "0 records")
        return saved

    def _fetch(self, client: httpx.Client, locality: str, city_param: str, mode: str, limit: int) -> List[Dict[str, Any]]:
        items, seen_ids = [], set()
        max_pages = max(1, min(6, (limit + 29) // 30))
        for pg in range(1, max_pages + 1):
            url = f"https://www.magicbricks.com/property-for-{mode}/residential-real-estate?Locality={quote_plus(locality.replace(' ', '-'))}&cityName={quote_plus(city_param)}&page={pg}"
            resp = client.get(url)
            if resp.status_code != 200: break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".mb-srp__card")
            if not cards: break

            ld_entries = []
            for blk in extract_ld(resp.text):
                nodes = blk.get("@graph", []) if isinstance(blk, dict) else (blk if isinstance(blk, list) else [])
                for node in nodes:
                    if not isinstance(node, dict): continue
                    t = str(node.get("@type") or "")
                    if any(k in t for k in ("RentAction", "BuyAction", "Apartment", "SingleFamilyResidence", "Residence")):
                        obj = node.get("object") if isinstance(node.get("object"), dict) else node
                        geo = obj.get("geo") if isinstance(obj, dict) else None
                        lat = lng = None
                        if isinstance(geo, dict) and geo.get("latitude"):
                            try: lat, lng = float(geo["latitude"]), float(geo["longitude"])
                            except Exception: pass
                        ld_entries.append({"lat": lat, "lng": lng, "url": obj.get("url") or node.get("url")})

            for idx, card in enumerate(cards):
                t_el, p_el = card.select_one(".mb-srp__card--title"), card.select_one(".mb-srp__card__price--amount")
                if not t_el or not p_el: continue
                title, price = t_el.get_text(" ", strip=True), parse_inr(p_el.get_text(" ", strip=True))
                if not price or COMM_RE.search(title): continue
                s_el = card.select_one(".mb-srp__card__society--name")
                name = s_el.get_text(" ", strip=True) if s_el else clean_name(title, locality)
                if len(name) < 3 or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
                if mode == "rent" and price > 850_000: continue
                if mode == "sale" and price < 1_500_000: continue

                exact_url = None
                for a in card.select("a[href]"):
                    href = (a.get("href") or "").strip()
                    if not href: continue
                    full = href if href.startswith("http") else (f"https://www.magicbricks.com{href}" if href.startswith("/") else "")
                    if "propertyDetails" in full or "-pdpid-" in full:
                        exact_url = full
                        if "propertyDetails" in full: break
                if not exact_url:
                    m_u = re.search(r"https?://www\.magicbricks\.com/(?:propertyDetails/|[^\"'\s<>]+-pdpid-[^\"'\s<>]+)[^\"'\s<>]*", str(card))
                    if m_u: exact_url = m_u.group(0)
                if not exact_url and idx < len(ld_entries) and ld_entries[idx].get("url"):
                    exact_url = ld_entries[idx]["url"]

                lat = ld_entries[idx]["lat"] if idx < len(ld_entries) else None
                lng = ld_entries[idx]["lng"] if idx < len(ld_entries) else None
                txt = card.get_text(" ", strip=True)
                rm = RERA_RE.search(txt)
                uid = f"mb-{mode}-{re.sub(r'[^a-z0-9]','',locality.lower())[:10]}-{pg}-{idx}-{re.sub(r'[^a-z0-9]','',name.lower())[:14]}"
                if uid in seen_ids: continue
                seen_ids.add(uid)
                items.append({
                    "id": uid, "name": name, "locality": locality, "lat": lat, "lng": lng,
                    "bhk": parse_bhk(title), "rent_inr": price if mode == "rent" else None,
                    "buy_inr": price if mode == "sale" else None, "carpet_sqft": parse_sqft(txt),
                    "furnishing": parse_furnishing(txt), "tenant": parse_tenant(txt),
                    "rera_id": rm.group(0) if rm else None, "url": exact_url,
                })
                if len(items) >= limit: return items
        return items


class NoBrokerConnector(BaseConnector):
    source_name = "nobroker"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 40, fresh_hours: float = 20.0) -> int:
        meta_map = {m["locality"]: m for m in loc_meta}
        self.db.register_jobs(self.source_name, list(meta_map.keys()))
        pending = [j for j in self.db.next_pending_jobs(self.source_name) if j["locality"] in meta_map]
        if not pending: return 0

        def _worker(job):
            loc, info = job["locality"], meta_map[job["locality"]]
            cached = self.read_cache(f"nb5:{loc}", max_age_hours=fresh_hours)
            if cached: return job, info, cached, None
            try:
                slug = re.sub(r"[^a-z0-9]+", "_", loc.lower()).strip("_")
                url = f"https://www.nobroker.in/flats-for-rent-in-{slug}_mumbai"
                with _http() as client:
                    resp = client.get(url)
                if resp.status_code != 200: return job, info, [], None
                items = self._parse_page(resp.text, loc, limit_per_locality)
                if items: self.write_cache(f"nb5:{loc}", items)
                return job, info, items, None
            except Exception as exc:
                return job, info, [], str(exc)[:300]

        saved = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            for fut in as_completed([ex.submit(_worker, j) for j in pending]):
                job, info, items, err = fut.result()
                loc = job["locality"]
                if err:
                    self.db.mark_job(job["job_key"], "failed", err); continue
                for it in items:
                    self.db.upsert_raw_record(
                        self.source_name, it["id"], it["name"], it,
                        locality=loc, zone=info["zone"], lat=it.get("lat"), lng=it.get("lng"),
                        source_url=it.get("url"),
                    )
                    saved += 1
                self.db.mark_job(job["job_key"], "done" if items else "failed", None if items else "0 records")
        return saved

    def _parse_page(self, html: str, locality: str, limit: int) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        res_geo = []
        for blk in extract_ld(html):
            for node in (blk if isinstance(blk, list) else [blk]):
                if isinstance(node, dict) and node.get("@type") in ("Residence", "Apartment", "SingleFamilyResidence"):
                    murl = (((node.get("containedInPlace") or {}).get("hasMap") or {}).get("url") or "")
                    qm = re.search(r"query=([0-9.]+),([0-9.]+)", murl)
                    res_geo.append({"lat": float(qm.group(1)) if qm else None, "lng": float(qm.group(2)) if qm else None, "url": node.get("url")})

        items, seen = [], set()
        for h in soup.select("h2, h3"):
            title = h.get_text(" ", strip=True)
            if not re.search(r"for\s+rent", title, re.I): continue
            name = clean_name(title, locality)
            if len(name) < 3 or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
            a = h.select_one("a[href]") or h.find_parent("a", href=True)
            href = (a.get("href") or "").strip() if a else ""
            exact_url = href if href.startswith("http") else (f"https://www.nobroker.in{href}" if href.startswith("/") else None)
            container = h
            for _ in range(4):
                if container.parent and len(container.get_text(" ", strip=True)) < 260:
                    container = container.parent
            ct = container.get_text(" ", strip=True)
            money = [m for m in (parse_inr(x) for x in re.findall(r"(?:₹|Rs\.?)\s*[0-9,.]+\s*(?:Lac|Lakh|Cr|k)?", ct, re.I)) if m and 8000 <= m <= 2_500_000]
            if not money: continue
            rent = money[0]
            dep = money[1] if len(money) > 1 and money[1] >= rent else None
            key = f"{name.lower()}:{rent}"
            if key in seen: continue
            seen.add(key)
            geo = res_geo[len(items)] if len(items) < len(res_geo) else {}
            items.append({
                "id": f"nb-{re.sub(r'[^a-z0-9]','',locality.lower())[:10]}-{len(items)}-{re.sub(r'[^a-z0-9]','',name.lower())[:14]}",
                "name": name, "locality": locality, "lat": geo.get("lat"), "lng": geo.get("lng"),
                "bhk": parse_bhk(title), "rent_inr": rent, "deposit_inr": dep,
                "carpet_sqft": parse_sqft(ct), "furnishing": parse_furnishing(ct), "tenant": parse_tenant(ct),
                "zero_brokerage": True, "url": exact_url or geo.get("url"),
            })
            if len(items) >= limit: break
        return items

NOISE_PRICE_99 = re.compile(
    r"(?:₹|Rs\.?|INR)\s*[0-9,.]+\s*(?:k|lac|lakh|l|cr|crore)?\s*(?:/\s*sq\.?\s*ft|per\s+sq\.?\s*ft|per\s+sqft|psf|/\s*sq\.?\s*m)"
    r"|\b(?:emi|deposit|security\s*deposit|maintenance|brokerage|booking\s*amount)\s*[:\-–]?\s*(?:₹|Rs\.?|INR)?\s*[0-9,.]+\s*(?:k|lac|lakh|l|cr|crore)?",
    re.I,
)

class NinetyNineAcresConnector(BaseConnector):
    source_name = "99acres"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 40, fresh_hours: float = 20.0) -> int:
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        try:
            from curl_cffi import requests as c_req
        except ImportError:
            print("[99acres] curl_cffi not installed - skipping.", flush=True)
            return 0

        PROTO = "https" + "://"
        zmap = {
            "South Mumbai":"south-mumbai","Bandra-Santacruz":"mumbai-south-west",
            "Andheri-Juhu":"mumbai-andheri-dahisar","Western Suburbs North":"mumbai-andheri-dahisar",
            "Powai-Central":"central-mumbai-suburbs","Chembur-Wadala":"mumbai-harbour",
            "Thane":"thane","Navi Mumbai":"navi-mumbai",
        }
        priority = {
            "Bandra West":0,"Bandra East":1,"Pali Hill":2,"Khar West":3,"Santacruz West":4,
            "Juhu":5,"Andheri West":6,"Versova":7,"Powai":8,"Worli":9,"Lower Parel":10,
            "Dadar West":11,"Goregaon West":12,"Goregaon East":13,"Malad West":14,"Chembur":15,
            "Thane West":16,"Vashi":17,"Colaba":18,"Cuffe Parade":19,
        }
        ordered = sorted(loc_meta, key=lambda m: (priority.get(m["locality"], 99), m["locality"]))
        deadline = time.monotonic() + 125.0
        diag_logs = []

        def _fetch_one(idx, info):
            if time.monotonic() > deadline: return info, []
            loc = info["locality"]
            cached = self.read_cache(f"99c5:{loc}", max_age_hours=fresh_hours)
            if cached: return info, cached
            time.sleep(0.25)
            slug = re.sub(r"[^a-z0-9]+", "-", loc.lower()).strip("-")
            reg = zmap.get(info.get("zone", ""), info["city"].lower().replace(" ", "-"))
            out = []
            for mode, prefix in (("rent", "property-for-rent-in"), ("buy", "property-in")):
                if time.monotonic() > deadline: break
                u = f"{PROTO}www.99acres.com/{prefix}-{slug}-{reg}-ffid"
                try:
                    hdrs_99 = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-IN,en;q=0.9",
                        "Referer": PROTO + "www.99acres.com/",
                    }
                    resp = c_req.get(u, impersonate="safari15_5", headers=hdrs_99, timeout=9, allow_redirects=True)
                    if resp.status_code == 417:
                        with httpx.Client(http2=False, headers=hdrs_99, timeout=9.0, follow_redirects=True) as hc:
                            resp = hc.get(u)
                    sc, bl = resp.status_code, len(resp.text)
                    parsed, stats = self._parse_html(resp.text, loc, str(resp.url), mode, limit_per_locality // 2) if (sc == 200 and bl > 40000) else ([], "short/err")
                    out.extend(parsed)
                    if idx < 3:
                        diag_logs.append(f"[99acres-diag] {loc} ({mode}): HTTP {sc} | {bl:,} B | {stats} -> {len(parsed)} items")
                except Exception as exc:
                    if idx < 3: diag_logs.append(f"[99acres-diag] {loc} ({mode}): EXC {str(exc)[:70]}")
                    continue
            if out: self.write_cache(f"99c5:{loc}", out)
            return info, out

        saved = 0
        with ThreadPoolExecutor(max_workers=2) as ex:
            for fut in as_completed([ex.submit(_fetch_one, i, m) for i, m in enumerate(ordered)]):
                info, items = fut.result()
                for it in items:
                    self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=info["locality"], zone=info["zone"], rera_id=it.get("rera_id"), source_url=it.get("url"))
                    saved += 1
        for dl in diag_logs: print(dl, flush=True)
        return saved

    def _extract_initial_data(self, html: str, locality: str, mode: str, limit: int) -> List[Dict[str, Any]]:
        import json as _json
        PROTO = "https" + "://"
        idx = html.find("window.__initialData__")
        if idx < 0: return []
        eq = html.find("=", idx)
        if eq < 0: return []
        start = html.find("{", eq)
        if start < 0: return []
        try: data, _ = _json.JSONDecoder().raw_decode(html, start)
        except Exception: return []

        props: List[Dict[str, Any]] = []
        def _walk(node, depth=0):
            if depth > 7 or len(props) >= limit * 2: return
            if isinstance(node, list):
                for el in node:
                    if isinstance(el, dict) and (el.get("PROP_ID") or el.get("SPID") or el.get("SOCIETY_NAME") or el.get("PROP_NAME")):
                        props.append(el)
                    elif isinstance(el, (dict, list)): _walk(el, depth + 1)
            elif isinstance(node, dict):
                for k, v in node.items():
                    if k in ("properties","tuples","results") and isinstance(v, list):
                        for el in v:
                            if isinstance(el, dict): props.append(el)
                    elif depth < 5 and isinstance(v, (dict, list)): _walk(v, depth + 1)
        _walk(data)

        items, seen = [], set()
        for idx_p, pr in enumerate(props):
            raw_name = str(pr.get("SOCIETY_NAME") or pr.get("BUILDING_NAME") or pr.get("PROP_NAME") or pr.get("HEADING") or "").strip()
            if len(raw_name) < 3: continue
            name = clean_name(raw_name, locality)
            if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
            pv = None
            for pk in ("MIN_PRICE","PRICE","MAX_PRICE","price","FORMATTED_PRICE"):
                val = pr.get(pk)
                if val is None: continue
                if isinstance(val, (int, float)) and val > 5000: pv = int(val); break
                if isinstance(val, str):
                    p2 = parse_inr(NOISE_PRICE_99.sub(" ", val))
                    if p2: pv = p2; break
            if not pv: continue
            if mode == "rent" and not (7_000 <= pv <= 550_000): continue
            if mode == "buy" and not (2_500_000 <= pv <= 600_000_000): continue
            md = pr.get("MAP_DETAILS") or {}
            lat = md.get("LATITUDE") or pr.get("LATITUDE") or pr.get("lat")
            lng = md.get("LONGITUDE") or pr.get("LONGITUDE") or pr.get("lng")
            try:
                lat = float(lat) if lat is not None and str(lat).strip() else None
                lng = float(lng) if lng is not None and str(lng).strip() else None
            except Exception: lat = lng = None
            bhk = pr.get("BEDROOM_NUM")
            try: bhk = int(bhk) if bhk is not None else parse_bhk(str(pr.get("PROP_HEADING") or raw_name))
            except Exception: bhk = parse_bhk(str(pr.get("PROP_HEADING") or raw_name))
            sqft = pr.get("MIN_AREA_NUM") or pr.get("CARPET_SQFT") or pr.get("SUPER_SQFT")
            try: sqft = int(float(sqft)) if sqft and 140 <= float(sqft) <= 8000 else parse_sqft(str(pr.get("AREA") or ""))
            except Exception: sqft = parse_sqft(str(pr.get("AREA") or ""))
            pd_u = str(pr.get("PD_URL") or pr.get("URL") or "").strip()
            full_url = pd_u if pd_u.startswith("http") else (f"{PROTO}www.99acres.com/{pd_u.lstrip('/')}" if pd_u else None)
            photo = pr.get("PHOTO_URL") or pr.get("MEDIUM_PHOTO_URL")
            photo = photo if isinstance(photo, str) and photo.startswith("http") else None
            rm = RERA_RE.search(str(pr))
            rera = pr.get("RERA_REGISTRATION_ID") or (rm.group(0) if rm else None)
            seen.add(name.lower())
            items.append({
                "id": f"99a-{mode[0]}-{pr.get('PROP_ID') or pr.get('SPID') or idx_p}",
                "name": name, "locality": locality, "bhk": bhk,
                "buy_inr": pv if mode == "buy" else None, "rent_inr": pv if mode == "rent" else None,
                "carpet_sqft": sqft, "furnishing": parse_furnishing(str(pr.get("FURNISH") or pr.get("FURNISHING") or "")),
                "tenant": parse_tenant(str(pr.get("PREFERENCE") or pr.get("DESCRIPTION") or "")),
                "rera_id": rera if isinstance(rera, str) and rera.startswith("P") else None,
                "lat": lat, "lng": lng, "image": photo, "url": full_url,
            })
            if len(items) >= limit: break
        return items

    def _parse_html(self, html: str, locality: str, url: str, mode: str, limit: int):
        import json as _json
        PROTO = "https" + "://"
        init_items = self._extract_initial_data(html, locality, mode, limit)
        if init_items:
            return init_items, f"initData={len(init_items)}"
        soup = BeautifulSoup(html, "html.parser")
        items, seen, ld_total = [], set(), 0
        for sc in soup.find_all("script", type="application/ld+json"):
            raw = sc.string or sc.get_text() or ""
            if not raw.strip(): continue
            try: data = _json.loads(raw)
            except Exception: continue
            nodes = data if isinstance(data, list) else [data]
            flat = []
            for nd in nodes:
                if not isinstance(nd, dict): continue
                if "@graph" in nd and isinstance(nd["@graph"], list): flat.extend(nd["@graph"])
                elif "itemListElement" in nd and isinstance(nd["itemListElement"], list):
                    for el in nd["itemListElement"]:
                        flat.append(el.get("item") if isinstance(el, dict) and isinstance(el.get("item"), dict) else el)
                else: flat.append(nd)
            ld_total += len(flat)
            for obj in flat:
                if not isinstance(obj, dict): continue
                addr = obj.get("address") or {}
                street = addr.get("streetAddress") if isinstance(addr, dict) else ""
                raw_t = str(street or obj.get("name") or "").strip()
                m_in = re.search(r"\bin\s+([^,|]+)", raw_t, re.I)
                if m_in and len(m_in.group(1).strip()) >= 3: raw_t = m_in.group(1).strip()
                name = clean_name(raw_t, locality)
                if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
                full = NOISE_PRICE_99.sub(" ", f"{obj.get('name') or ''} {street} {obj.get('description') or ''}")
                offers = obj.get("offers") or {}
                if isinstance(offers, list): offers = offers[0] if offers else {}
                prices = [parse_inr(m) for m in re.findall(r"(?:₹|Rs\.?)\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L|K)?", full, re.I)]
                p_offer = offers.get("price") or offers.get("lowPrice")
                if p_offer is not None:
                    try: prices.insert(0, int(float(str(p_offer).replace(",", ""))))
                    except Exception: pass
                buys = [p for p in prices if p and 2_500_000 <= p <= 600_000_000]
                rents = [p for p in prices if p and 7_000 <= p <= 550_000]
                if mode == "rent" and not rents: continue
                if mode == "buy" and not buys: continue
                geo = obj.get("geo") or {}
                try:
                    lat = float(geo["latitude"]) if geo.get("latitude") is not None else None
                    lng = float(geo["longitude"]) if geo.get("longitude") is not None else None
                except Exception: lat = lng = None
                img = obj.get("image")
                if isinstance(img, list): img = img[0] if img else None
                if isinstance(img, dict): img = img.get("url")
                u = obj.get("url") or ""
                full_url = u if isinstance(u, str) and u.startswith("http") else (f"{PROTO}www.99acres.com{u}" if isinstance(u, str) and u.startswith("/") else None)
                seen.add(name.lower())
                items.append({
                    "id": f"99a-{mode[0]}-{re.sub(r'[^a-z0-9]','',locality.lower())[:9]}-ld{len(items)}-{re.sub(r'[^a-z0-9]','',name.lower())[:14]}",
                    "name": name, "locality": locality, "bhk": parse_bhk(full),
                    "buy_inr": buys[0] if mode == "buy" and buys else None, "rent_inr": rents[0] if mode == "rent" and rents else None,
                    "carpet_sqft": parse_sqft(full), "furnishing": parse_furnishing(full), "tenant": parse_tenant(full),
                    "rera_id": None, "lat": lat, "lng": lng, "image": img if isinstance(img, str) and img.startswith("http") else None, "url": full_url,
                })
                if len(items) >= limit: return items, f"initData=0, ld={len(items)}/{ld_total}"

        cards = soup.select("section[data-propid], [data-label='SRP_TUPLE'], [class*='tupleWrap'], [class*='projectTuple'], [class*='srpTuple']")
        for idx, card in enumerate(cards):
            txt = NOISE_PRICE_99.sub(" ", card.get_text(" ", strip=True))
            if "₹" not in txt or len(txt) < 35 or len(txt) > 3000: continue
            soc_el = card.select_one("[class*='locationName'], [class*='projectName'], [class*='propertyHeading'], h2 a, h2, h3, a[title]")
            if not soc_el: continue
            raw_t = soc_el.get("title") or soc_el.get_text(" ", strip=True)
            m_in = re.search(r"\bin\s+([^,|]+)", raw_t, re.I)
            if m_in and len(m_in.group(1).strip()) >= 3: raw_t = m_in.group(1).strip()
            name = clean_name(raw_t, locality)
            if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
            prices = [parse_inr(m) for m in re.findall(r"₹\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L)?", txt, re.I)]
            buys = [p for p in prices if p and 2_500_000 <= p <= 600_000_000]
            rents = [p for p in prices if p and 7_000 <= p <= 550_000]
            if mode == "rent" and not rents: continue
            if mode == "buy" and not buys: continue
            a_el = card.select_one("a[href*='-spid-'], a[href*='-npxid-'], a[href]")
            href = (a_el.get("href") if a_el else "") or ""
            full_url = href if href.startswith("http") else (f"{PROTO}www.99acres.com{href}" if href.startswith("/") else None)
            seen.add(name.lower())
            items.append({
                "id": f"99a-{mode[0]}-{re.sub(r'[^a-z0-9]','',locality.lower())[:9]}-c{idx}-{re.sub(r'[^a-z0-9]','',name.lower())[:14]}",
                "name": name, "locality": locality, "bhk": parse_bhk(txt),
                "buy_inr": buys[0] if mode == "buy" and buys else None, "rent_inr": rents[0] if mode == "rent" and rents else None,
                "carpet_sqft": parse_sqft(txt), "furnishing": parse_furnishing(txt), "tenant": parse_tenant(txt),
                "rera_id": None, "url": full_url,
            })
            if len(items) >= limit: break
        return items, f"initData=0, ld={ld_total}, cards={len(cards)}"
