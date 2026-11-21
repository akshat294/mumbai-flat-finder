from __future__ import annotations
import json, re, time, xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx
from pipeline.connectors.base import BaseConnector
from pipeline.connectors.portals import (
    COMM_RE, JUNK_NAME, RERA_RE,
    clean_name, parse_bhk, parse_furnishing, parse_inr, parse_sqft, parse_tenant,
)

PROTO = "https" + "://"
UA_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")

def _match_loc(text: str, loc_meta: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
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
        "versova":"Versova","juhu":"Juhu","powai":"Powai","chembur":"Chembur",
        "worli":"Worli","parel":"Lower Parel","vashi":"Vashi","nerul":"Nerul",
        "kharghar":"Kharghar","airoli":"Airoli","panvel":"Panvel","ulwe":"Ulwe",
    }
    by_name = {m["locality"]: m for m in loc_meta}
    for stem, target in stems.items():
        if re.search(r"\b" + re.escape(stem) + r"\b", low) and target in by_name:
            return by_name[target]
    return None

def _extract_ld_items(html: str, default_url: str, locality: str, prefix: str, mode: str) -> List[Dict[str, Any]]:
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
            else:
                flat.append(nd)
        for obj in flat:
            if not isinstance(obj, dict): continue
            title = str(obj.get("name") or obj.get("headline") or "").strip()
            if len(title) < 4: continue
            name = clean_name(title, locality)
            if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name):
                continue
            offers = obj.get("offers") or {}
            if isinstance(offers, list): offers = offers[0] if offers else {}
            p_raw = offers.get("price") or offers.get("lowPrice") or obj.get("price")
            p_val = None
            if p_raw is not None:
                try: p_val = int(float(str(p_raw).replace(",", "")))
                except Exception: p_val = parse_inr(str(p_raw))
            desc = str(obj.get("description") or "")
            full = f"{title} {desc}"
            if not p_val:
                prices = [parse_inr(m) for m in re.findall(r"(?:₹|Rs\.?)\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L|K)?", full, re.I)]
                prices = [p for p in prices if p]
                p_val = prices[0] if prices else None
            if not p_val: continue
            is_buy = (mode == "buy") or (p_val >= 1_800_000)
            if is_buy and not (2_500_000 <= p_val <= 600_000_000): continue
            if not is_buy and not (6_000 <= p_val <= 850_000): continue
            geo = obj.get("geo") or {}
            try:
                lat = float(geo["latitude"]) if geo.get("latitude") is not None else None
                lng = float(geo["longitude"]) if geo.get("longitude") is not None else None
            except Exception:
                lat = lng = None
            seen.add(name.lower())
            u = obj.get("url") or default_url
            if isinstance(u, str) and u.startswith("/"):
                u = "/".join(default_url.split("/", 3)[:3]) + u
            rm = RERA_RE.search(full)
            items.append({
                "id": f"{prefix}-{_slug(locality)[:10]}-{len(items)}-{_slug(name)[:14]}",
                "name": name, "locality": locality, "bhk": parse_bhk(full),
                "buy_inr": p_val if is_buy else None, "rent_inr": None if is_buy else p_val,
                "carpet_sqft": parse_sqft(full), "furnishing": parse_furnishing(full),
                "tenant": parse_tenant(full), "rera_id": rm.group(0) if rm else None,
                "lat": lat, "lng": lng, "url": u if isinstance(u, str) and u.startswith("http") else None,
            })
    return items

def _extract_cards_generic(html: str, base_origin: str, locality: str, prefix: str, mode: str, limit: int = 35) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    items = _extract_ld_items(html, base_origin, locality, prefix, mode)
    seen = {x["name"].lower() for x in items}
    if len(items) >= limit: return items[:limit]
    cards = soup.select("article, [class*='tile'], [class*='card'], [class*='listing'], [class*='property'], li[data-id]")
    for idx, card in enumerate(cards):
        txt = card.get_text(" ", strip=True)
        if ("₹" not in txt and "Lac" not in txt and "Cr" not in txt and "K" not in txt) or len(txt) < 35 or len(txt) > 2200:
            continue
        h = card.select_one("h2 a, h3 a, a[title], h2, h3, [class*='title'] a, [class*='name'] a")
        if not h: continue
        name = clean_name(h.get_text(" ", strip=True), locality)
        if len(name) < 3 or name.lower() in seen or name.lower() == locality.lower() or COMM_RE.search(name) or JUNK_NAME.search(name):
            continue
        prices = [parse_inr(m) for m in re.findall(r"(?:₹|Rs\.?)\s*[0-9,.]+\s*(?:Cr|Crore|Lac|Lakh|L|K)?", txt, re.I)]
        buys = [p for p in prices if p and 2_500_000 <= p <= 600_000_000]
        rents = [p for p in prices if p and 6_000 <= p <= 850_000]
        if mode == "buy" and not buys: continue
        if mode == "rent" and not rents: continue
        if not buys and not rents: continue
        href = h.get("href") or (card.select_one("a[href]") or {}).get("href") or ""
        full_url = href if href.startswith("http") else (base_origin.rstrip("/") + href if href.startswith("/") else None)
        rm = RERA_RE.search(txt)
        seen.add(name.lower())
        items.append({
            "id": f"{prefix}-{_slug(locality)[:10]}-{idx}-{_slug(name)[:14]}",
            "name": name, "locality": locality, "bhk": parse_bhk(txt),
            "buy_inr": buys[0] if (mode == "buy" or not rents) and buys else None,
            "rent_inr": rents[0] if rents else None,
            "carpet_sqft": parse_sqft(txt), "furnishing": parse_furnishing(txt),
            "tenant": parse_tenant(txt), "rera_id": rm.group(0) if rm else None,
            "url": full_url,
        })
        if len(items) >= limit: break
    return items

def _fast_get(url: str, timeout: float = 8.0) -> Optional[str]:
    try:
        from curl_cffi import requests as c_req
        r = c_req.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 3000: return r.text
    except Exception:
        pass
    try:
        with httpx.Client(headers=UA_HDRS, timeout=timeout, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code == 200 and len(r.text) > 3000: return r.text
    except Exception:
        pass
    return None

class SquareYardsConnector(BaseConnector):
    source_name = "squareyards"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 35, fresh_hours: float = 20.0) -> int:
        origin = PROTO + "www.squareyards.com"
        deadline, saved, consec_fail = time.monotonic() + 120.0, 0, 0
        for info in loc_meta:
            if time.monotonic() > deadline or consec_fail >= 6: break
            loc, city_slug = info["locality"], _slug(info["city"])
            cached = self.read_cache(f"sy:{loc}", max_age_hours=fresh_hours)
            if not cached:
                cached, sl = [], _slug(loc)
                for mode, path in (("rent", f"/rent/property-for-rent-in-{sl}-{city_slug}"), ("buy", f"/sale/property-for-sale-in-{sl}-{city_slug}")):
                    if time.monotonic() > deadline: break
                    html = _fast_get(origin + path, timeout=7.0)
                    if html: cached.extend(_extract_cards_generic(html, origin, loc, "sy", mode, limit=limit_per_locality // 2))
                if cached: self.write_cache(f"sy:{loc}", cached)
            if cached:
                consec_fail = 0
                for it in cached:
                    self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], rera_id=it.get("rera_id"), source_url=it.get("url"))
                    saved += 1
            else: consec_fail += 1
        return saved

class CommonFloorConnector(BaseConnector):
    source_name = "commonfloor"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 35, fresh_hours: float = 20.0) -> int:
        origin = PROTO + "www.commonfloor.com"
        deadline, saved, consec_fail = time.monotonic() + 70.0, 0, 0
        for mode, path in (("rent", "/mumbai-property/for-rent"), ("buy", "/mumbai-property/for-sale"), ("rent", "/thane-property/for-rent"), ("rent", "/navi-mumbai-property/for-rent")):
            if time.monotonic() > deadline: break
            cached = self.read_cache(f"cf:city:{path}", max_age_hours=fresh_hours)
            if not cached:
                html = _fast_get(origin + path, timeout=8.0)
                cached = _extract_cards_generic(html, origin, "Mumbai", "cf", mode, limit=50) if html else []
                if cached: self.write_cache(f"cf:city:{path}", cached)
            for it in cached:
                li = _match_loc(f"{it['name']} {it.get('url') or ''}", loc_meta)
                ln = li["locality"] if li else ("Thane West" if "thane" in path else ("Vashi" if "navi" in path else "Andheri West"))
                zn = li["zone"] if li else ("Thane" if "thane" in path else ("Navi Mumbai" if "navi" in path else "Andheri-Juhu"))
                self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=ln, zone=zn, rera_id=it.get("rera_id"), source_url=it.get("url"))
                saved += 1
        for info in loc_meta:
            if time.monotonic() > deadline or consec_fail >= 6: break
            loc = info["locality"]
            cached = self.read_cache(f"cf:{loc}", max_age_hours=fresh_hours)
            if not cached:
                html = _fast_get(f"{origin}/{_slug(loc)}-mumbai/for-rent", timeout=7.0)
                cached = _extract_cards_generic(html, origin, loc, "cf", "rent", limit=20) if html else []
                if cached: self.write_cache(f"cf:{loc}", cached)
            if cached:
                consec_fail = 0
                for it in cached:
                    self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], rera_id=it.get("rera_id"), source_url=it.get("url"))
                    saved += 1
            else: consec_fail += 1
        return saved

class MakaanConnector(BaseConnector):
    source_name = "makaan"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 30, fresh_hours: float = 20.0) -> int:
        origin = PROTO + "www.makaan.com"
        deadline, saved, consec_fail = time.monotonic() + 65.0, 0, 0
        for info in loc_meta:
            if time.monotonic() > deadline or consec_fail >= 5: break
            loc = info["locality"]
            cached = self.read_cache(f"mk:{loc}", max_age_hours=fresh_hours)
            if not cached:
                cached, sl = [], _slug(loc)
                for mode, path in (("rent", f"/mumbai-property/{sl}-flats-for-rent"), ("buy", f"/mumbai-property/{sl}-flats-for-sale")):
                    if time.monotonic() > deadline: break
                    html = _fast_get(origin + path, timeout=7.0)
                    if html: cached.extend(_extract_cards_generic(html, origin, loc, "mk", mode, limit=limit_per_locality // 2))
                if cached: self.write_cache(f"mk:{loc}", cached)
            if cached:
                consec_fail = 0
                for it in cached:
                    self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=loc, zone=info["zone"], rera_id=it.get("rera_id"), source_url=it.get("url"))
                    saved += 1
            else: consec_fail += 1
        return saved

class NoBrokerageConnector(BaseConnector):
    source_name = "nobrokerage"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 40, fresh_hours: float = 20.0) -> int:
        origin = PROTO + "nobrokerage.com"
        deadline, saved = time.monotonic() + 45.0, 0
        for mode, path in (("buy", "/residential/mumbai"), ("rent", "/residential/mumbai/rent"), ("buy", "/residential/thane"), ("buy", "/residential/navi-mumbai")):
            if time.monotonic() > deadline: break
            cached = self.read_cache(f"nbg:{path}", max_age_hours=fresh_hours)
            if not cached:
                html = _fast_get(origin + path, timeout=8.0)
                cached = _extract_cards_generic(html, origin, "Mumbai", "nbg", mode, limit=limit_per_locality) if html else []
                for it in cached: it["zero_brokerage"] = True
                if cached: self.write_cache(f"nbg:{path}", cached)
            for it in cached:
                li = _match_loc(f"{it['name']} {it.get('url') or ''}", loc_meta)
                ln = li["locality"] if li else ("Thane West" if "thane" in path else ("Vashi" if "navi" in path else "Chembur"))
                zn = li["zone"] if li else ("Thane" if "thane" in path else ("Navi Mumbai" if "navi" in path else "Chembur-Wadala"))
                self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=ln, zone=zn, rera_id=it.get("rera_id"), source_url=it.get("url"))
                saved += 1
        return saved

class CommunityFlatmatesConnector(BaseConnector):
    source_name = "community"
    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 60, fresh_hours: float = 12.0) -> int:
        cached = self.read_cache("comm:mmr_v2", max_age_hours=fresh_hours)
        if not cached:
            cached = self._fetch_reddit_rss(loc_meta) + self._fetch_olx_flatmates(loc_meta)
            if cached: self.write_cache("comm:mmr_v2", cached)
        saved = 0
        for it in cached:
            self.db.upsert_raw_record(self.source_name, it["id"], it["name"], it, locality=it["locality"], zone=it["zone"], source_url=it.get("url"))
            saved += 1
        return saved

    def _fetch_reddit_rss(self, loc_meta: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        rent_sig = re.compile(r"\b(rent|flatmate|flat\s*mate|bhk|1\s*rk|roommate|occupancy|brokerage|deposit|lease|available)\b", re.I)
        wanted_sig = re.compile(r"\b(looking\s+for|need\s+a\s+flat|searching\s+for|want\s+to\s+rent|any\s+leads|required\s+1|budget\s+is)\b", re.I)
        price_re = re.compile(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,\.]*)\s*(k|lac|lakh|l\b)?|\b([1-9]\d)\s*k\b", re.I)
        items, seen = [], set()
        for rss_u in (f"{PROTO}www.reddit.com/r/mumbai/search.rss?q=rent+OR+flatmate&restrict_sr=1&sort=new&limit=40", f"{PROTO}www.reddit.com/r/MumbaiRealEstate/new/.rss?limit=30"):
            xml_txt = _fast_get(rss_u, timeout=8.0)
            if not xml_txt or "<entry>" not in xml_txt: continue
            try: root = ET.fromstring(xml_txt)
            except Exception: continue
            ns = {"a": "http" + "://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = (entry.findtext("a:title", "", ns) or "").strip()
                content = BeautifulSoup(entry.findtext("a:content", "", ns) or "", "html.parser").get_text(" ", strip=True)
                link_el = entry.find("a:link", ns)
                url = link_el.attrib.get("href") if link_el is not None else None
                full = f"{title} {content[:700]}"
                if not title or not rent_sig.search(full) or wanted_sig.search(title): continue
                rent = None
                for m in price_re.finditer(full):
                    if m.group(3):
                        v = int(m.group(3)) * 1000
                        if 7000 <= v <= 300000: rent = v; break
                    else:
                        try: num = float(m.group(1).replace(",", ""))
                        except Exception: continue
                        u = (m.group(2) or "").lower().strip()
                        val = int(num * 1000) if u == "k" else (int(num * 100000) if u in ("lac", "lakh", "l") else int(num))
                        if 7000 <= val <= 350000: rent = val; break
                if not rent: continue
                li = _match_loc(full, loc_meta)
                if not li: continue
                eid = re.sub(r"[^a-zA-Z0-9]", "", (entry.findtext("a:id", "", ns) or title)[-12:])
                if eid in seen: continue
                seen.add(eid)
                ct = re.sub(r"\[[^\]]+\]", "", title).strip(" -|:")
                ct = (ct[:66] + "...") if len(ct) > 69 else ct
                items.append({
                    "id": f"rd-{eid}", "name": ct or f"Direct Rental in {li['locality']}",
                    "locality": li["locality"], "zone": li["zone"], "bhk": parse_bhk(full),
                    "rent_inr": rent, "buy_inr": None, "carpet_sqft": parse_sqft(full),
                    "furnishing": parse_furnishing(full), "tenant": parse_tenant(full) or "bachelors_ok",
                    "zero_brokerage": True, "url": url,
                })
        return items

    def _fetch_olx_flatmates(self, loc_meta: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        origin, items, seen = PROTO + "www.olx.in", [], set()
        for u in (f"{origin}/mumbai_g4058997/properties_c3/q-flatmates-mumbai", f"{origin}/andheri-west_g5386406/properties_c3/q-flatmate", f"{origin}/bandra-west_g5386411/properties_c3/q-flatmate"):
            html = _fast_get(u, timeout=8.0)
            if not html: continue
            soup = BeautifulSoup(html, "html.parser")
            for idx, card in enumerate(soup.select("li[data-aut-id='itemBox'], li[data-aut-id='itemBox3'], a[href*='/item/']")):
                txt = card.get_text(" ", strip=True)
                if "₹" not in txt or len(txt) < 18 or len(txt) > 500: continue
                rents = [p for p in (parse_inr(m) for m in re.findall(r"₹\s*[0-9,.]+", txt)) if p and 5_000 <= p <= 150_000]
                if not rents: continue
                li = _match_loc(txt, loc_meta)
                if not li: continue
                a = card if card.name == "a" else card.select_one("a[href]")
                href = a.get("href") if a else ""
                full_url = href if href.startswith("http") else (origin + href if href.startswith("/") else None)
                t_el = card.select_one("[data-aut-id='itemTitle'], span[data-aut-id='itemTitle']")
                title = (t_el.get_text(" ", strip=True) if t_el else re.sub(r"₹\s*[0-9,.]+", "", txt))[:68].strip(" -|")
                if len(title) < 6 or title.lower() in seen: continue
                seen.add(title.lower())
                items.append({
                    "id": f"olx-{_slug(li['locality'])[:8]}-{idx}-{_slug(title)[:12]}",
                    "name": title, "locality": li["locality"], "zone": li["zone"],
                    "bhk": parse_bhk(txt), "rent_inr": rents[0], "buy_inr": None,
                    "carpet_sqft": parse_sqft(txt), "furnishing": parse_furnishing(txt),
                    "tenant": "bachelors_ok", "zero_brokerage": True, "url": full_url,
                })
                if len(items) >= 45: break
        return items
