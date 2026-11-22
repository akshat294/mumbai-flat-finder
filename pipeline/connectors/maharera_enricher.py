import json, re, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = ROOT / "data/maharera_cache.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

RERA_RE = re.compile(r"\bP5(?:1[7-9]|2[0-1])\d{8}\b", re.I)

try:
    from curl_cffi import requests as _cffi_req
except Exception:
    _cffi_req = None

def _get(url, timeout=10):
    h = {"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "en-IN,en;q=0.9"}
    if _cffi_req is not None:
        r = _cffi_req.get(url, headers=h, impersonate="chrome", timeout=timeout)
        r.raise_for_status()
        return r.text
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def _norm_proj(name):
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())

def _extract_meta_from_html(html):
    rids = sorted({m.upper() for m in RERA_RE.findall(html or "")})[:4]
    dev, poss = None, None
    for pat in (
        r'"(?:builderName|developerName|developer|promoterName)"\s*:\s*"([^"]{3,64})"',
        r'(?:Developed|Builder|Promoter)\s*(?:by|:)\s*</[^>]+>\s*<[^>]+>([^<]{3,60})<',
        r'(?:Developed\s+by|By)\s+([A-Z][A-Za-z0-9\s&.-]{2,45}(?:Group|Developers|Realty|Constructions|Infratech|Builders|Homes|Properties|Ltd|LLP))',
    ):
        m = re.search(pat, html or "", re.I)
        if m:
            cand = re.sub(r"\s+", " ", m.group(1)).strip(" ,|-:")
            if 3 <= len(cand) <= 64 and not any(bad in cand.lower() for bad in ("magicbricks", "squareyards", "housing.com", "99acres", "nobroker")):
                dev = cand
                break
    for pat in (
        r'"(?:possessionStatus|possessionDate|completionDate)"\s*:\s*"([^"]{3,36})"',
        r'Possession(?:\s+Starts|\s+by|\s+Date)?[:\s]+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,.-]*20[2-3]\d|Ready\s+to\s+Move)',
        r'\b(Ready\s+to\s+Move)\b',
    ):
        m = re.search(pat, html or "", re.I)
        if m:
            poss = re.sub(r"\s+", " ", m.group(1)).strip(" ,|-:")
            break
    return rids, dev, poss

def _load_cache():
    if not CACHE_PATH.exists():
        return {}
    try:
        blob = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return blob if isinstance(blob, dict) else {}
    except Exception:
        return {}

def _save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

def enrich_societies(socs, max_fetch=200):
    cache = _load_cache()
    now_ts = int(time.time())

    if (ROOT / "data").exists():
        for cand in (ROOT / "data").glob("*rera*.json"):
            if cand.resolve() == CACHE_PATH.resolve():
                continue
            try:
                blob = json.loads(cand.read_text(encoding="utf-8"))
                rows = blob if isinstance(blob, list) else (blob.get("projects") or blob.get("records") or list(blob.values()))
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    k = _norm_proj(r.get("name") or r.get("project_name"))
                    if len(k) < 4:
                        continue
                    rid = r.get("rera_id") or r.get("registration_no") or r.get("id")
                    rids = [rid.upper()] if isinstance(rid, str) and RERA_RE.search(rid) else []
                    if rids:
                        ent = cache.setdefault(k, {"rera_ids": [], "checked_ts": now_ts})
                        for x in rids:
                            if x not in ent["rera_ids"]:
                                ent["rera_ids"].append(x)
                        if r.get("developer") or r.get("promoter"):
                            ent["developer"] = str(r.get("developer") or r.get("promoter"))[:64]
                        if r.get("possession") or r.get("completion_date"):
                            ent["possession"] = str(r.get("possession") or r.get("completion_date"))[:32]
            except Exception:
                continue

    for s in socs:
        k = _norm_proj(s.get("name"))
        if len(k) < 4:
            continue
        existing_rids = [x.upper() for x in (s.get("rera_ids") or []) if isinstance(x, str) and RERA_RE.search(x)]
        if existing_rids:
            ent = cache.setdefault(k, {"rera_ids": [], "checked_ts": now_ts})
            for x in existing_rids:
                if x not in ent["rera_ids"]:
                    ent["rera_ids"].append(x)

    targets, seen_k = [], set()
    buy_socs = sorted([s for s in socs if s.get("units_buy")], key=lambda s: len(s.get("units_buy") or []), reverse=True)
    for s in buy_socs:
        k = _norm_proj(s.get("name"))
        if len(k) < 4 or k in seen_k:
            continue
        ent = cache.get(k)
        if ent and (ent.get("rera_ids") or (now_ts - int(ent.get("checked_ts") or 0) < 14 * 86400)):
            continue
        url = None
        for pref in ("squareyards", "magicbricks", "makaan", "99acres", "housing"):
            u_obj = next((u for u in (s.get("units_buy") or []) if u.get("s") == pref and str(u.get("u") or "").startswith("http")), None)
            if u_obj:
                url = u_obj["u"]
                break
        if url:
            seen_k.add(k)
            targets.append((k, url))
        if len(targets) >= max_fetch:
            break

    def _probe(pair):
        k, url = pair
        try:
            html = _get(url, timeout=9)
            rids, dev, poss = _extract_meta_from_html(html)
            return k, rids, dev, poss
        except Exception:
            return k, [], None, None

    newly_found = 0
    if targets:
        with ThreadPoolExecutor(max_workers=12) as ex:
            for fut in as_completed([ex.submit(_probe, t) for t in targets]):
                k, rids, dev, poss = fut.result()
                ent = cache.setdefault(k, {"rera_ids": []})
                ent["checked_ts"] = now_ts
                if rids:
                    for x in rids:
                        if x not in ent["rera_ids"]:
                            ent["rera_ids"].append(x)
                    newly_found += 1
                if dev and not ent.get("developer"):
                    ent["developer"] = dev
                if poss and not ent.get("possession"):
                    ent["possession"] = poss

    _save_cache(cache)

    applied = 0
    for s in socs:
        k = _norm_proj(s.get("name"))
        ent = cache.get(k)
        if not ent:
            continue
        changed = False
        if ent.get("rera_ids"):
            cur = list(s.get("rera_ids") or [])
            for x in ent["rera_ids"]:
                if x not in cur:
                    cur.append(x)
                    changed = True
            s["rera_ids"] = cur[:4]
        if ent.get("developer") and not s.get("rera_developer"):
            s["rera_developer"] = ent["developer"]
            changed = True
        if ent.get("possession") and not s.get("rera_possession"):
            s["rera_possession"] = ent["possession"]
            changed = True
        if changed:
            applied += 1

    total_rera_socs = sum(1 for s in socs if s.get("rera_ids"))
    print(f"  [maharera] Probed {len(targets)} Buy projects -> +{newly_found} new RERA IDs | {total_rera_socs} total RERA buildings ({applied} enriched)")
    return total_rera_socs
