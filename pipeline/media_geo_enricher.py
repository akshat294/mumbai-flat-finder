from __future__ import annotations
import json, re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup
from pipeline.geo_guard import is_valid_mmr_land

PROTO = "https" + "://"
BAD_IMG_RE = re.compile(
    r"(logo|icon|avatar|placeholder|default|spinner|loader|blank|pixel|badge|sprite|banner|ads|\.svg(?:\?|$)|\.gif(?:\?|$)|data:image|1x1|no[-_]?image|no[-_]?photo|whatsapp|facebook|twitter|playstore|appstore)",
    re.I,
)
HALF_BHK_RE = re.compile(r"\b([1-5]\.5)\s*[-]?\s*bhk\b|\b([1-5])-5-bhk\b", re.I)
BALC_NUM_RE = re.compile(r"\b(\d+)\s*balcon(?:y|ies)\b|\bbalcon(?:y|ies)\s*[:\-]?\s*(\d+)\b", re.I)
SHARED_TXT_RE = re.compile(r"\b(flatmate|flat\s*mate|roommate|room\s*mate|twin\s*sharing|double\s*sharing|triple\s*sharing|single\s*occupancy|double\s*occupancy|sharing\s*room|shared\s*flat|paying\s*guest|pg\s*for|co[\s-]?living|bed\s*space|girls?\s*pg|boys?\s*pg)\b", re.I)
OWNER_TXT_RE  = re.compile(r"\b(posted\s*by\s*owner|direct\s*owner|owner\s*listing|owner\s*flat|zero\s*brokerage|no\s*brokerage|by\s*owner)\b", re.I)
BROKER_TXT_RE = re.compile(r"\b(posted\s*by\s*(?:dealer|agent|broker)|verified\s*agent|prime\s*agent|channel\s*partner|real\s*estate\s*agent|brokerage\s*applicable)\b", re.I)

def _clean_img(u: Any) -> Optional[str]:
    if not u or not isinstance(u, str): return None
    u = u.strip().replace("\\u002F", "/").replace("\\/", "/")
    if u.startswith("//"): u = "https:" + u
    if not u.startswith("http") or len(u) < 20 or len(u) > 480: return None
    if BAD_IMG_RE.search(u): return None
    return u

def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def _extract_half_bhk(text: str) -> Optional[float]:
    if not text: return None
    m = HALF_BHK_RE.search(text)
    if not m: return None
    raw = m.group(1) or (f"{m.group(2)}.5" if m.group(2) else None)
    try: return float(raw) if raw else None
    except Exception: return None

def _detect_lister(text: str, low_u: str = "") -> Optional[str]:
    if SHARED_TXT_RE.search(text or "") or any(k in low_u for k in ("pg-", "/pg/", "flatmate", "coliving", "sharing")):
        return "shared"
    if "nobroker.in" in low_u or OWNER_TXT_RE.search(text or ""):
        return "owner"
    if BROKER_TXT_RE.search(text or ""):
        return "broker"
    return None

class MediaGeoHarvester:
    def __init__(self) -> None:
        self.by_url: Dict[str, Dict[str, Any]] = {}
        self.by_id: Dict[str, Dict[str, Any]] = {}
        self.by_name: Dict[str, Dict[str, Any]] = {}
        self.stats = {
            "pages": 0, "geo_hits": 0, "img_hits": 0, "desc_hits": 0,
            "applied_geo": 0, "applied_img": 0, "applied_desc": 0,
        }

    def _put(
        self, url: Optional[str], pid: Optional[str], name: Optional[str],
        lat: Any = None, lng: Any = None, img: Any = None,
        desc: Optional[str] = None, balconies: Optional[int] = None,
        lister_type: Optional[str] = None, bhk_exact: Optional[float] = None,
    ) -> None:
        la = ln = None
        try:
            if lat is not None and lng is not None:
                fla, fln = float(lat), float(lng)
                if is_valid_mmr_land(fla, fln, None):
                    la, ln = round(fla, 6), round(fln, 6)
        except Exception:
            la = ln = None
        im = _clean_img(img)
        clean_desc = re.sub(r"\s+", " ", (desc or "")).strip()[:420] if desc else None
        if clean_desc and len(clean_desc) < 12: clean_desc = None
        if la is None and im is None and clean_desc is None and not balconies and not lister_type and not bhk_exact:
            return

        def _merge(store: Dict[str, Dict[str, Any]], k: str) -> None:
            if not k or len(k) < 3: return
            ent = store.setdefault(k, {})
            if la is not None and "lat" not in ent:
                ent["lat"], ent["lng"] = la, ln; self.stats["geo_hits"] += 1
            if im is not None and "image" not in ent:
                ent["image"] = im; self.stats["img_hits"] += 1
            if clean_desc and (len(clean_desc) > len(ent.get("description") or "")):
                if "description" not in ent: self.stats["desc_hits"] += 1
                ent["description"] = clean_desc
            if balconies and balconies > int(ent.get("balconies") or 0):
                ent["balconies"] = int(balconies)
            if lister_type and ("lister_type" not in ent or lister_type == "shared"):
                ent["lister_type"] = lister_type
            if bhk_exact and "bhk_exact" not in ent:
                ent["bhk_exact"] = bhk_exact

        if url and isinstance(url, str):
            cu = url.split("?")[0].rstrip("/").lower()
            _merge(self.by_url, cu)
            tail = cu.rsplit("/", 1)[-1]
            if len(tail) >= 6: _merge(self.by_id, tail)
        if pid: _merge(self.by_id, str(pid).lower())
        if name:
            nk = _norm_key(name)
            if len(nk) >= 4: _merge(self.by_name, nk)

    def observe(self, req_url: str, text: str) -> None:
        if not text or len(text) < 400: return
        low_u = (req_url or "").lower()
        if not any(d in low_u for d in ("magicbricks","nobroker","squareyards","makaan","commonfloor","olx")):
            return
        self.stats["pages"] += 1
        try:
            st = text.lstrip()
            if st.startswith("{") or st.startswith("["):
                self._scan_json(json.loads(st), low_u)
                return

            for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', text, re.I):
                raw = m.group(1).strip()
                if raw:
                    try: self._scan_json(json.loads(raw), low_u)
                    except Exception: pass

            if "magicbricks" in low_u:
                for m in re.finditer(r'"(?:id|pdpId)"\s*:\s*"?([0-9a-zA-Z_-]{5,24})"?[^\}]{0,600}?"(?:lt|lat|latitude)"\s*:\s*"?([0-9.]+)"?[^\}]{0,120}?"(?:lg|lng|lon|longitude)"\s*:\s*"?([0-9.]+)"?', text):
                    self._put(None, m.group(1), None, m.group(2), m.group(3))
                for m in re.finditer(r'"(?:pdpUrl|url)"\s*:\s*"([^"]+)"[^\}]{0,500}?"(?:lt|lat|latitude)"\s*:\s*"?([0-9.]+)"?[^\}]{0,120}?"(?:lg|lng|lon|longitude)"\s*:\s*"?([0-9.]+)"?', text):
                    self._put(m.group(1), None, None, m.group(2), m.group(3))

            if "nobroker" in low_u:
                for m in re.finditer(r'"id"\s*:\s*"([a-f0-9]{16,32})"[^\}]{0,800}?"latitude"\s*:\s*([0-9.]+)[^\}]{0,120}?"longitude"\s*:\s*([0-9.]+)', text):
                    self._put(None, m.group(1), None, m.group(2), m.group(3))

            soup = BeautifulSoup(text, "html.parser")
            base_m = re.match(r"https?://[^/]+", req_url or "")
            base_origin = base_m.group(0) if base_m else ""
            for card in soup.select("article, .mb-srp__card, [class*='card'], [class*='tuple'], [class*='listing'], [data-id], [data-propid]"):
                a = card.select_one("a[href]")
                href = a.get("href") if a else None
                if href and href.startswith("/") and base_origin: href = base_origin + href
                img_el = card.select_one("img[data-src], img[data-original], img[data-lazy], img[src]")
                img_u = None
                if img_el:
                    for attr in ("data-src","data-original","data-lazy","src"):
                        cand = _clean_img(img_el.get(attr))
                        if cand: img_u = cand; break
                lat = card.get("data-lat") or card.get("data-latitude")
                lng = card.get("data-lng") or card.get("data-lon") or card.get("data-longitude")
                title_el = card.select_one("h2, h3, [class*='title'], [class*='society'], a[title]")
                nm = (title_el.get("title") or title_el.get_text(" ", strip=True))[:80] if title_el else None
                pid = card.get("data-id") or card.get("data-propid") or card.get("id")
                card_txt = card.get_text(" ", strip=True)[:500]
                bm = BALC_NUM_RE.search(card_txt)
                balc_n = int(bm.group(1) or bm.group(2)) if bm else (1 if re.search(r"\bbalcon(?:y|ies)\b", card_txt, re.I) else None)
                lt = _detect_lister(card_txt, (href or low_u).lower())
                hb = _extract_half_bhk(f"{nm or ''} {card_txt} {href or ''}")
                if img_u or (lat and lng) or card_txt:
                    self._put(href, pid, nm, lat, lng, img_u, card_txt, balc_n, lt, hb)
        except Exception:
            return

    def _scan_json(self, obj: Any, low_u: str, depth: int = 0) -> None:
        if depth > 7: return
        if isinstance(obj, list):
            for el in obj[:160]: self._scan_json(el, low_u, depth + 1)
            return
        if not isinstance(obj, dict): return

        geo = obj.get("geo") if isinstance(obj.get("geo"), dict) else {}
        lat = geo.get("latitude") or obj.get("latitude") or obj.get("lat") or obj.get("lt")
        lng = geo.get("longitude") or obj.get("longitude") or obj.get("lng") or obj.get("lon") or obj.get("lg")

        img = obj.get("image") or obj.get("imageUrl") or obj.get("thumbnail") or obj.get("photo") or obj.get("coverImage")
        if isinstance(img, list) and img: img = img[0]
        if isinstance(img, dict): img = img.get("url") or img.get("medium") or img.get("original") or img.get("thumbnail")
        if not img and isinstance(obj.get("photos"), list) and obj["photos"]:
            ph0 = obj["photos"][0]
            if isinstance(ph0, dict):
                im_map = ph0.get("imagesMap") or {}
                fn = im_map.get("medium") or im_map.get("thumbnail") or im_map.get("original")
                pid_nb = obj.get("id") or obj.get("propertyId")
                if fn and pid_nb and "nobroker" in low_u:
                    img = f"{PROTO}images.nobroker.in/images/{pid_nb}/{fn}"
                elif isinstance(fn, str) and fn.startswith("http"):
                    img = fn

        url = obj.get("url") or obj.get("detailUrl") or obj.get("pdpUrl") or obj.get("propertyUrl")
        pid = obj.get("id") or obj.get("propertyId") or obj.get("pdpId") or obj.get("listingId")
        name = obj.get("society") or obj.get("societyName") or obj.get("projectName") or obj.get("name") or obj.get("propertyTitle")

        desc_bits = []
        for dk in ("description","desc","summary","seoDesc","highlights","overlooking","facingDesc","propertyTitle","title","usp"):
            dv = obj.get(dk)
            if isinstance(dv, str) and dv.strip(): desc_bits.append(dv.strip())
            elif isinstance(dv, list): desc_bits.extend(str(x) for x in dv[:10] if x)
        am = obj.get("amenitiesMap") or obj.get("amenities")
        if isinstance(am, dict):
            desc_bits.extend(k for k, v in am.items() if v)
        elif isinstance(am, list):
            desc_bits.extend(str(x) for x in am[:12])
        desc = " ".join(desc_bits)[:420] if desc_bits else None

        balc_n = None
        for bk in ("balconies","balcony","noOfBalconies","balconyCount"):
            bv = obj.get(bk)
            try:
                if bv is not None and int(bv) > 0:
                    balc_n = int(bv); break
            except Exception: pass

        lt = None
        pby = str(obj.get("postedBy") or obj.get("userType") or obj.get("sellerType") or obj.get("ownerType") or "").lower()
        if obj.get("sharedAccomodation") or obj.get("shared") or "pg" in pby or "flatmate" in pby:
            lt = "shared"
        elif obj.get("isOwner") is True or "owner" in pby:
            lt = "owner"
        elif any(k in pby for k in ("agent","dealer","broker","builder")):
            lt = "broker"
        elif desc:
            lt = _detect_lister(desc, (url or low_u).lower())

        hb = _extract_half_bhk(f"{name or ''} {desc or ''} {url or ''} {obj.get('type') or ''} {obj.get('bhk') or ''}")

        if (lat is not None and lng is not None) or img or desc or balc_n or lt or hb:
            self._put(
                url if isinstance(url, str) else None,
                str(pid) if pid else None,
                str(name) if isinstance(name, str) else None,
                lat, lng, img, desc, balc_n, lt, hb,
            )

        for k, v in obj.items():
            if isinstance(v, (dict, list)) and k not in ("geo","photos","amenitiesMap"):
                self._scan_json(v, low_u, depth + 1)

    def enrich_record(self, source_id: str, name: str, payload: Dict[str, Any], source_url: Optional[str]) -> Dict[str, Any]:
        need_geo  = not (payload.get("lat") and payload.get("lng"))
        need_img  = not _clean_img(payload.get("image"))
        need_desc = not payload.get("description")
        need_lt   = not payload.get("lister_type")
        need_bhk  = payload.get("bhk_exact") is None

        cands = []
        u = (payload.get("url") or source_url or "").split("?")[0].rstrip("/").lower()
        if u:
            if u in self.by_url: cands.append(self.by_url[u])
            tail = u.rsplit("/", 1)[-1]
            if tail in self.by_id: cands.append(self.by_id[tail])
        if source_id and str(source_id).lower() in self.by_id: cands.append(self.by_id[str(source_id).lower()])
        nk = _norm_key(name)
        if nk in self.by_name: cands.append(self.by_name[nk])

        for c in cands:
            if need_geo and c.get("lat") and c.get("lng"):
                payload["lat"], payload["lng"] = c["lat"], c["lng"]
                need_geo = False; self.stats["applied_geo"] += 1
            if need_img and c.get("image"):
                payload["image"] = c["image"]
                need_img = False; self.stats["applied_img"] += 1
            if need_desc and c.get("description"):
                payload["description"] = c["description"]
                need_desc = False; self.stats["applied_desc"] += 1
            if c.get("balconies") and not payload.get("balconies"):
                payload["balconies"] = c["balconies"]
            if need_lt and c.get("lister_type"):
                payload["lister_type"] = c["lister_type"]
                need_lt = False
            if need_bhk and c.get("bhk_exact"):
                payload["bhk"] = c["bhk_exact"]
                payload["bhk_exact"] = c["bhk_exact"]
                need_bhk = False
        return payload

HARVESTER = MediaGeoHarvester()
_INSTALLED = False

def install_harvester(db: Any = None) -> MediaGeoHarvester:
    global _INSTALLED
    if not _INSTALLED:
        _INSTALLED = True
        try:
            import httpx
            _orig_cget = httpx.Client.get
            def _wrapped_cget(self, url, *args, **kwargs):
                resp = _orig_cget(self, url, *args, **kwargs)
                try:
                    if resp.status_code == 200 and resp.text: HARVESTER.observe(str(resp.url), resp.text)
                except Exception: pass
                return resp
            httpx.Client.get = _wrapped_cget

            _orig_get = httpx.get
            def _wrapped_get(url, *args, **kwargs):
                resp = _orig_get(url, *args, **kwargs)
                try:
                    if resp.status_code == 200 and resp.text: HARVESTER.observe(str(resp.url), resp.text)
                except Exception: pass
                return resp
            httpx.get = _wrapped_get

            _orig_aget = httpx.AsyncClient.get
            async def _wrapped_aget(self, url, *args, **kwargs):
                resp = await _orig_aget(self, url, *args, **kwargs)
                try:
                    if resp.status_code == 200 and resp.text: HARVESTER.observe(str(resp.url), resp.text)
                except Exception: pass
                return resp
            httpx.AsyncClient.get = _wrapped_aget
        except Exception: pass
        try:
            import requests as _req
            _orig_rreq = _req.Session.request
            def _wrapped_rreq(self, method, url, *args, **kwargs):
                resp = _orig_rreq(self, method, url, *args, **kwargs)
                try:
                    if resp.status_code == 200 and resp.text: HARVESTER.observe(str(resp.url), resp.text)
                except Exception: pass
                return resp
            _req.Session.request = _wrapped_rreq
        except Exception: pass
        try:
            from curl_cffi import requests as c_req
            _orig_cf_get = c_req.get
            def _wrapped_cf_get(url, *args, **kwargs):
                resp = _orig_cf_get(url, *args, **kwargs)
                try:
                    if resp.status_code == 200 and resp.text: HARVESTER.observe(str(getattr(resp, "url", url)), resp.text)
                except Exception: pass
                return resp
            c_req.get = _wrapped_cf_get
            if hasattr(c_req, "Session"):
                _orig_csget = c_req.Session.get
                def _wrapped_csget(self, url, *args, **kwargs):
                    resp = _orig_csget(self, url, *args, **kwargs)
                    try:
                        if resp.status_code == 200 and resp.text: HARVESTER.observe(str(getattr(resp, "url", url)), resp.text)
                    except Exception: pass
                    return resp
                c_req.Session.get = _wrapped_csget
        except Exception: pass

    try:
        from pipeline.core.checkpoint import CheckpointDB
        if not getattr(CheckpointDB, "_harvester_cls_hooked", False):
            _orig_cls_upsert = CheckpointDB.upsert_raw_record
            def _wrapped_cls_upsert(self, source, source_id, name, payload, *args, **kwargs):
                try:
                    if isinstance(payload, dict):
                        HARVESTER.enrich_record(source_id, name, payload, kwargs.get("source_url"))
                except Exception: pass
                return _orig_cls_upsert(self, source, source_id, name, payload, *args, **kwargs)
            CheckpointDB.upsert_raw_record = _wrapped_cls_upsert
            CheckpointDB._harvester_cls_hooked = True
    except Exception:
        pass
    return HARVESTER
