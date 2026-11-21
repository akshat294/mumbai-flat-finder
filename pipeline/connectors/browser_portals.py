from __future__ import annotations
import json, re, time
from typing import Any, Dict, List
from bs4 import BeautifulSoup
from pipeline.connectors.base import BaseConnector
from pipeline.connectors.portals import (
    COMM_RE, JUNK_NAME, clean_name, parse_bhk, parse_furnishing, parse_inr, parse_sqft, parse_tenant,
)

PROTO = "https" + "://"
NOISE_RE = re.compile(
    r"(?:₹|Rs\.?|INR)\s*[0-9,.]+\s*(?:k|lac|lakh|l|cr|crore)?\s*(?:/\s*sq\.?\s*ft|per\s+sq\.?\s*ft|per\s+sqft|psf|/\s*sq\.?\s*m)"
    r"|\b(?:emi|deposit|security\s*deposit|maintenance|brokerage|booking\s*amount)\s*[:\-–]?\s*(?:₹|Rs\.?|INR)?\s*[0-9,.]+\s*(?:k|lac|lakh|l|cr|crore)?",
    re.I,
)
ACRES_ZMAP = {
    "South Mumbai":"south-mumbai","Bandra-Santacruz":"western-mumbai",
    "Andheri-Juhu":"western-mumbai","Western Suburbs North":"western-mumbai",
    "Powai-Central":"central-mumbai-suburbs","Chembur-Wadala":"mumbai-harbour",
    "Thane":"thane","Navi Mumbai":"navi-mumbai",
}
PRIORITY_LOCS = [
    "Bandra West","Bandra East","Khar West","Santacruz West","Juhu",
    "Andheri West","Andheri East","Versova","Powai","Worli",
    "Lower Parel","Dadar West","Goregaon West","Goregaon East","Malad West",
    "Chembur","Wadala","Thane West","Vashi","Kharghar","Colaba","Cuffe Parade",
]

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")

def _launch_browser(pw):
    args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    for ch in ("chrome", "msedge", None):
        try:
            kw = {"headless": True, "args": args}
            if ch: kw["channel"] = ch
            return pw.chromium.launch(**kw)
        except Exception:
            continue
    return None

def _extract_99_from_page(html: str, locality: str, mode: str, limit: int = 30) -> List[Dict[str, Any]]:
    items, seen = [], set()
    idx = html.find("window.__initialData__")
    if idx >= 0:
        eq = html.find("=", idx)
        st = html.find("{", eq) if eq >= 0 else -1
        if st >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(html, st)
                props = []
                def _walk(node, d=0):
                    if d > 7 or len(props) >= limit * 2: return
                    if isinstance(node, list):
                        for el in node:
                            if isinstance(el, dict) and (el.get("PROP_ID") or el.get("SPID") or el.get("SOCIETY_NAME")):
                                props.append(el)
                            elif isinstance(el, (dict, list)): _walk(el, d + 1)
                    elif isinstance(node, dict):
                        for k, v in node.items():
                            if k in ("properties","tuples","results") and isinstance(v, list):
                                for el in v:
                                    if isinstance(el, dict): props.append(el)
                            elif d < 5 and isinstance(v, (dict, list)): _walk(v, d + 1)
                _walk(data)
                for i, pr in enumerate(props):
                    raw_n = str(pr.get("SOCIETY_NAME") or pr.get("BUILDING_NAME") or pr.get("PROP_NAME") or "").strip()
                    name = clean_name(raw_n, locality)
                    if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
                    pv = None
                    for pk in ("MIN_PRICE","PRICE","MAX_PRICE","FORMATTED_PRICE"):
                        val = pr.get(pk)
                        if isinstance(val, (int, float)) and val > 5000: pv = int(val); break
                        if isinstance(val, str):
                            p2 = parse_inr(NOISE_RE.sub(" ", val))
                            if p2: pv = p2; break
                    if not pv: continue
                    if mode == "rent" and not (7_000 <= pv <= 550_000): continue
                    if mode == "buy" and not (2_500_000 <= pv <= 600_000_000): continue
                    md = pr.get("MAP_DETAILS") or {}
                    try:
                        lat = float(md.get("LATITUDE") or pr.get("LATITUDE")) if (md.get("LATITUDE") or pr.get("LATITUDE")) else None
                        lng = float(md.get("LONGITUDE") or pr.get("LONGITUDE")) if (md.get("LONGITUDE") or pr.get("LONGITUDE")) else None
                    except Exception: lat = lng = None
                    bhk = pr.get("BEDROOM_NUM")
                    try: bhk = int(bhk) if bhk is not None else parse_bhk(str(pr.get("PROP_HEADING") or raw_n))
                    except Exception: bhk = parse_bhk(str(pr.get("PROP_HEADING") or raw_n))
                    sqft = pr.get("MIN_AREA_NUM") or pr.get("CARPET_SQFT")
                    try: sqft = int(float(sqft)) if sqft and 140 <= float(sqft) <= 8000 else parse_sqft(str(pr.get("AREA") or ""))
                    except Exception: sqft = parse_sqft(str(pr.get("AREA") or ""))
                    pd_u = str(pr.get("PD_URL") or pr.get("URL") or "").strip()
                    full_u = pd_u if pd_u.startswith("http") else (f"{PROTO}www.99acres.com/{pd_u.lstrip('/')}" if pd_u else None)
                    photo = pr.get("PHOTO_URL") or pr.get("MEDIUM_PHOTO_URL")
                    photo = photo if isinstance(photo, str) and photo.startswith("http") else None
                    seen.add(name.lower())
                    items.append({
                        "id": f"99b-{mode[0]}-{pr.get('PROP_ID') or pr.get('SPID') or i}",
                        "name": name, "locality": locality, "bhk": bhk,
                        "buy_inr": pv if mode == "buy" else None, "rent_inr": pv if mode == "rent" else None,
                        "carpet_sqft": sqft, "furnishing": parse_furnishing(str(pr.get("FURNISH") or "")),
                        "tenant": parse_tenant(str(pr.get("PREFERENCE") or "")),
                        "rera_id": pr.get("RERA_REGISTRATION_ID") if isinstance(pr.get("RERA_REGISTRATION_ID"), str) and pr.get("RERA_REGISTRATION_ID").startswith("P") else None,
                        "lat": lat, "lng": lng, "image": photo, "url": full_u,
                    })
                    if len(items) >= limit: return items
            except Exception:
                pass

    soup = BeautifulSoup(html, "html.parser")
    for i, card in enumerate(soup.select("section[data-propid], [data-label='SRP_TUPLE'], [class*='tupleNew__tupleWrap'], [class*='projectTuple__cardWrap']")):
        txt = NOISE_RE.sub(" ", card.get_text(" ", strip=True))
        if "₹" not in txt or len(txt) < 30: continue
        el = card.select_one("[class*='locationName'], [class*='projectName'], [class*='propertyHeading'], h2 a, h2, a[title]")
        if not el: continue
        raw_t = el.get("title") or el.get_text(" ", strip=True)
        m_in = re.search(r"\bin\s+([^,|]+)", raw_t, re.I)
        if m_in and len(m_in.group(1).strip()) >= 3: raw_t = m_in.group(1).strip()
        name = clean_name(raw_t, locality)
        if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
        prices = [parse_inr(m) for m in re.findall(r"₹\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L|K)?", txt, re.I)]
        buys = [p for p in prices if p and 2_500_000 <= p <= 600_000_000]
        rents = [p for p in prices if p and 7_000 <= p <= 550_000]
        if mode == "rent" and not rents: continue
        if mode == "buy" and not buys: continue
        a = card.select_one("a[href*='-spid-'], a[href*='-npxid-'], a[href]")
        href = (a.get("href") if a else "") or ""
        full_u = href if href.startswith("http") else (f"{PROTO}www.99acres.com{href}" if href.startswith("/") else None)
        img = card.select_one("img[src^='http']")
        seen.add(name.lower())
        items.append({
            "id": f"99d-{mode[0]}-{_slug(locality)[:8]}-{i}-{_slug(name)[:12]}",
            "name": name, "locality": locality, "bhk": parse_bhk(txt),
            "buy_inr": buys[0] if mode == "buy" else None, "rent_inr": rents[0] if mode == "rent" else None,
            "carpet_sqft": parse_sqft(txt), "furnishing": parse_furnishing(txt), "tenant": parse_tenant(txt),
            "image": img.get("src") if img else None, "url": full_u,
        })
        if len(items) >= limit: break
    return items

def _extract_housing_from_page(html: str, locality: str, mode: str, limit: int = 30) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for sc in soup.find_all("script", type="application/ld+json"):
        raw = sc.string or sc.get_text() or ""
        if not raw.strip(): continue
        try: data = json.loads(raw)
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
        for obj in flat:
            if not isinstance(obj, dict): continue
            t = str(obj.get("name") or "").strip()
            m_in = re.search(r"\bin\s+([^,|]+)", t, re.I)
            name = clean_name(m_in.group(1).strip() if (m_in and len(m_in.group(1).strip()) >= 3) else t, locality)
            if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
            full = NOISE_RE.sub(" ", f"{t} {obj.get('description') or ''}")
            offers = obj.get("offers") or {}
            if isinstance(offers, list): offers = offers[0] if offers else {}
            prices = [parse_inr(m) for m in re.findall(r"(?:₹|Rs\.?)\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L|K)?", full, re.I)]
            po = offers.get("price") or offers.get("lowPrice")
            if po is not None:
                try: prices.insert(0, int(float(str(po).replace(",", ""))))
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
            full_u = u if isinstance(u, str) and u.startswith("http") else (f"{PROTO}housing.com{u}" if isinstance(u, str) and u.startswith("/") else None)
            seen.add(name.lower())
            items.append({
                "id": f"hsg-{mode[0]}-{_slug(locality)[:8]}-{len(items)}-{_slug(name)[:12]}",
                "name": name, "locality": locality, "bhk": parse_bhk(full),
                "buy_inr": buys[0] if mode == "buy" else None, "rent_inr": rents[0] if mode == "rent" else None,
                "carpet_sqft": parse_sqft(full), "furnishing": parse_furnishing(full), "tenant": parse_tenant(full),
                "lat": lat, "lng": lng, "image": img if isinstance(img, str) and img.startswith("http") else None, "url": full_u,
            })
            if len(items) >= limit: return items

    for i, card in enumerate(soup.select("article, [data-q='result-card'], [data-testid*='card']")):
        txt = NOISE_RE.sub(" ", card.get_text(" ", strip=True))
        if "₹" not in txt or len(txt) < 30 or len(txt) > 2000: continue
        el = card.select_one("h2, h3, a[data-q='title'], a[href*='/rent/'], a[href*='/buy/']")
        if not el: continue
        raw_t = el.get_text(" ", strip=True)
        m_in = re.search(r"\bin\s+([^,|]+)", raw_t, re.I)
        if m_in and len(m_in.group(1).strip()) >= 3: raw_t = m_in.group(1).strip()
        name = clean_name(raw_t, locality)
        if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name): continue
        prices = [parse_inr(m) for m in re.findall(r"₹\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L|K)?", txt, re.I)]
        buys = [p for p in prices if p and 2_500_000 <= p <= 600_000_000]
        rents = [p for p in prices if p and 7_000 <= p <= 550_000]
        if mode == "rent" and not rents: continue
        if mode == "buy" and not buys: continue
        a = card.select_one("a[href*='/rent/'], a[href*='/buy/'], a[href]")
        href = (a.get("href") if a else "") or ""
        full_u = href if href.startswith("http") else (f"{PROTO}housing.com{href}" if href.startswith("/") else None)
        img = card.select_one("img[src^='http']")
        seen.add(name.lower())
        items.append({
            "id": f"hsd-{mode[0]}-{_slug(locality)[:8]}-{i}-{_slug(name)[:12]}",
            "name": name, "locality": locality, "bhk": parse_bhk(txt),
            "buy_inr": buys[0] if mode == "buy" else None, "rent_inr": rents[0] if mode == "rent" else None,
            "carpet_sqft": parse_sqft(txt), "furnishing": parse_furnishing(txt), "tenant": parse_tenant(txt),
            "image": img.get("src") if img else None, "url": full_u,
        })
        if len(items) >= limit: break
    return items

class Browser99AcresConnector(BaseConnector):
    source_name = "99acres"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 35, fresh_hours: float = 20.0) -> int:
        try: from playwright.sync_api import sync_playwright
        except ImportError: print("[99acres-pw] playwright not installed", flush=True); return 0
        meta_by_loc = {m["locality"]: m for m in loc_meta}
        targets = [meta_by_loc[l] for l in PRIORITY_LOCS if l in meta_by_loc] + [m for m in loc_meta if m["locality"] not in PRIORITY_LOCS]
        deadline, saved = time.monotonic() + 140.0, 0
        with sync_playwright() as pw:
            browser = _launch_browser(pw)
            if not browser: print("[99acres-pw] Chrome/Edge launch failed", flush=True); return 0
            ctx = browser.new_context(viewport={"width":1366,"height":900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", locale="en-IN")
            page = ctx.new_page()
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image","font","media") else r.continue_())
            try:
                page.goto(PROTO + "www.99acres.com/", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1200)
            except Exception: pass
            for idx, info in enumerate(targets[:22]):
                if time.monotonic() > deadline: break
                loc, ck = info["locality"], f"99pw:{info['locality']}"
                cached = self.read_cache(ck, max_age_hours=fresh_hours)
                if not cached:
                    cached, reg, sl = [], ACRES_ZMAP.get(info["zone"], _slug(info["city"])), _slug(loc)
                    for mode, pref in (("rent", "property-for-rent-in"), ("buy", "property-in")):
                        if time.monotonic() > deadline: break
                        u = f"{PROTO}www.99acres.com/{pref}-{sl}-{reg}-ffid"
                        try:
                            resp = page.goto(u, wait_until="domcontentloaded", timeout=14000)
                            page.wait_for_timeout(1100)
                            html = page.content()
                            got = _extract_99_from_page(html, loc, mode, limit=limit_per_locality // 2)
                            cached.extend(got)
                            if idx < 3: print(f"[99acres-pw] {loc} ({mode}): HTTP {resp.status if resp else '?'} | {len(html):,} B -> {len(got)} items", flush=True)
                        except Exception as exc:
                            if idx < 3: print(f"[99acres-pw] {loc} ({mode}): ERR {str(exc)[:60]}", flush=True)
                    if cached: self.write_cache(ck, cached)
                for it in cached:
                    self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], rera_id=it.get("rera_id"), source_url=it.get("url"))
                    saved += 1
            browser.close()
        return saved

class BrowserHousingConnector(BaseConnector):
    source_name = "housing"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 35, fresh_hours: float = 20.0) -> int:
        try: from playwright.sync_api import sync_playwright
        except ImportError: print("[housing-pw] playwright not installed", flush=True); return 0
        meta_by_loc = {m["locality"]: m for m in loc_meta}
        targets = [meta_by_loc[l] for l in PRIORITY_LOCS if l in meta_by_loc]
        deadline, saved = time.monotonic() + 120.0, 0
        with sync_playwright() as pw:
            browser = _launch_browser(pw)
            if not browser: return 0
            ctx = browser.new_context(viewport={"width":1366,"height":900}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", locale="en-IN")
            page = ctx.new_page()
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image","font","media") else r.continue_())
            for idx, info in enumerate(targets[:16]):
                if time.monotonic() > deadline: break
                loc, ck = info["locality"], f"hsgpw:{info['locality']}"
                cached = self.read_cache(ck, max_age_hours=fresh_hours)
                if not cached:
                    cached, sl, cs = [], _slug(loc), _slug(info["city"])
                    for mode, path in (("rent", f"/rent/flats-for-rent-in-{sl}-{cs}"), ("buy", f"/in/buy/{cs}/{sl}")):
                        if time.monotonic() > deadline: break
                        try:
                            resp = page.goto(PROTO + "housing.com" + path, wait_until="domcontentloaded", timeout=14000)
                            page.wait_for_timeout(1300)
                            html = page.content()
                            got = _extract_housing_from_page(html, loc, mode, limit=limit_per_locality // 2)
                            cached.extend(got)
                            if idx < 3: print(f"[housing-pw] {loc} ({mode}): HTTP {resp.status if resp else '?'} | {len(html):,} B -> {len(got)} items", flush=True)
                        except Exception as exc:
                            if idx < 3: print(f"[housing-pw] {loc} ({mode}): ERR {str(exc)[:60]}", flush=True)
                    if cached: self.write_cache(ck, cached)
                for it in cached:
                    self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], source_url=it.get("url"))
                    saved += 1
            browser.close()
        return saved
