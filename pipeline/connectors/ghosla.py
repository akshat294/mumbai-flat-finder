from __future__ import annotations
import re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx
from pipeline.connectors.base import BaseConnector
from pipeline.connectors.portals import (
    COMM_RE, JUNK_NAME, clean_name, parse_bhk, parse_furnishing, parse_inr, parse_sqft, parse_tenant,
)

PROTO = "https" + "://"
ORIGIN = PROTO + "findghosla.com"
UA = {
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
        "marol":"Andheri East","chandivali":"Chandivali","oshiwara":"Oshiwara",
        "prabhadevi":"Prabhadevi","sion":"Sion","wadala":"Wadala","matunga":"Matunga",
        "colaba":"Colaba","cuffe parade":"Cuffe Parade","malabar hill":"Malabar Hill",
        "byculla":"Lower Parel","sewri":"Wadala","dindoshi":"Goregaon East",
    }
    by_name = {m["locality"]: m for m in loc_meta}
    for stem, target in stems.items():
        if re.search(r"\b" + re.escape(stem) + r"\b", low) and target in by_name:
            return by_name[target]
    return None

def _parse_ghosla_page(html: str, default_loc: str, page_url: str, is_flatmate: bool, loc_meta: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for idx, el in enumerate(soup.select("article, [class*='card'], [class*='listing'], [class*='item'], li, div")):
        txt = el.get_text(" ", strip=True)
        if "₹" not in txt or len(txt) < 30 or len(txt) > 650: continue
        if len(el.find_all(["article", "li"])) > 3: continue
        m_rent = re.search(r"₹\s*([0-9][0-9,\.]*)\s*(?:/\s*month|/mo|per\s*month|a\s*month)?", txt, re.I)
        if not m_rent: continue
        rent = parse_inr("₹" + m_rent.group(1))
        if not rent or not (6_000 <= rent <= 450_000): continue

        low = txt.lower()
        orig_src = "housing" if "housing.com" in low else ("99acres" if "99acres" in low else ("nobroker" if "nobroker" in low else ("magicbricks" if "magicbricks" in low else "community")))
        zb = bool("owner" in low or "no brokerage" in low or "zero brokerage" in low or is_flatmate or orig_src in ("nobroker","community"))

        name = None
        m_soc = re.search(r"\b(?:flat|room|apartment)\s+in\s+([A-Z][A-Za-z0-9\s&\.\-]{2,42})(?:,|\s+\d|\.)", txt)
        if m_soc:
            cand = clean_name(m_soc.group(1), default_loc)
            if len(cand) >= 3 and cand.lower() != default_loc.lower() and not COMM_RE.search(cand):
                name = cand
        if not name:
            h = el.select_one("h2, h3, h4, strong, a")
            ht = (h.get_text(" ", strip=True) if h else "")[:64]
            if is_flatmate:
                name = ht if len(ht) >= 6 else f"Shared Room in {default_loc}"
            else:
                name = clean_name(ht, default_loc)
                if len(name) < 4 or name.lower() == default_loc.lower(): continue

        li = _match_loc(txt, loc_meta) if default_loc == "Mumbai" else None
        loc_name = li["locality"] if li else default_loc
        zone_name = li["zone"] if li else None
        a_el = el.select_one("a[href]")
        href = a_el.get("href") if a_el else ""
        full_url = href if href.startswith("http") else (ORIGIN + href if href.startswith("/") else page_url)

        sig = (name.lower(), loc_name.lower(), rent)
        if sig in seen: continue
        seen.add(sig)
        items.append({
            "id": f"gh-{orig_src[:3]}-{_slug(loc_name)[:8]}-{idx}-{_slug(name)[:12]}",
            "name": name, "locality": loc_name, "zone": zone_name, "bhk": parse_bhk(txt),
            "rent_inr": rent, "buy_inr": None, "carpet_sqft": parse_sqft(txt),
            "furnishing": parse_furnishing(txt), "tenant": "bachelors_ok" if is_flatmate else parse_tenant(txt),
            "zero_brokerage": zb, "url": full_url, "_detected_source": orig_src,
        })
    return items

class GhoslaConnector(BaseConnector):
    source_name = "community"

    def run_localities(self, loc_meta: List[Dict[str, str]], limit_per_locality: int = 40, fresh_hours: float = 18.0) -> int:
        deadline, saved = time.monotonic() + 70.0, 0
        zone_map = {m["locality"]: m["zone"] for m in loc_meta}

        def _get(url: str) -> Optional[str]:
            try:
                with httpx.Client(headers=UA, timeout=8.0, follow_redirects=True) as client:
                    r = client.get(url)
                    if r.status_code == 200 and len(r.text) > 4000: return r.text
            except Exception:
                pass
            return None

        fm = self.read_cache("gh:flatmates_v1", max_age_hours=fresh_hours)
        if not fm:
            fm = []
            for pg in (1, 2, 3, 4):
                if time.monotonic() > deadline: break
                u = f"{ORIGIN}/flatmates-in-mumbai" + (f"?page={pg}" if pg > 1 else "")
                html = _get(u)
                if not html: break
                parsed = _parse_ghosla_page(html, "Mumbai", u, True, loc_meta)
                if not parsed: break
                fm.extend(parsed)
            if fm: self.write_cache("gh:flatmates_v1", fm)
        for it in (fm or []):
            zn = it.get("zone") or zone_map.get(it["locality"], "Mumbai")
            self.db.upsert_raw_record("community", it["id"], it["name"], it, locality=it["locality"], zone=zn, source_url=it.get("url"))
            saved += 1

        def _fetch_loc(info):
            if time.monotonic() > deadline: return info, []
            loc = info["locality"]
            ck = f"gh:loc:{loc}"
            cached = self.read_cache(ck, max_age_hours=fresh_hours)
            if cached: return info, cached
            u = f"{ORIGIN}/flats-for-rent-in-{_slug(loc)}-mumbai"
            html = _get(u)
            parsed = _parse_ghosla_page(html, loc, u, False, loc_meta) if html else []
            if parsed: self.write_cache(ck, parsed)
            return info, parsed

        with ThreadPoolExecutor(max_workers=5) as ex:
            for fut in as_completed([ex.submit(_fetch_loc, m) for m in loc_meta[:30]]):
                info, items = fut.result()
                for it in items:
                    self.db.upsert_raw_record(it.get("_detected_source") or "community", it["id"], it["name"], it, locality=info["locality"], zone=info["zone"], source_url=it.get("url"))
                    saved += 1
        return saved
