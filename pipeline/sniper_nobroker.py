import sys; from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from pipeline.index_io import load_index
import base64, json, os, sys, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.v19_common import detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name, merge_records_into_societies
from pipeline.compact_index import save_compacted_index

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

try:
    from curl_cffi import requests as _cffi_req
except Exception:
    _cffi_req = None

def _get(url, headers=None, timeout=12):
    h = {"User-Agent": UA, "Accept": "application/json", "Referer": "https://www.nobroker.in/"}
    if headers:
        h.update(headers)
    if _cffi_req is not None:
        r = _cffi_req.get(url, headers=h, impersonate="chrome", timeout=timeout)
        r.raise_for_status()
        return r.text
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

HOT_HUBS = [
    ("Bandra West", 19.0596, 72.8295), ("Khar West", 19.0700, 72.8339),
    ("Santacruz West", 19.0825, 72.8350), ("Juhu", 19.1075, 72.8263),
    ("Andheri West", 19.1364, 72.8296), ("Powai", 19.1197, 72.9051),
    ("Worli", 19.0176, 72.8162), ("Lower Parel", 18.9977, 72.8290),
    ("Dadar West", 19.0213, 72.8376), ("Chembur", 19.0522, 72.9005),
    ("Goregaon West", 19.1663, 72.8426), ("Malad West", 19.1864, 72.8358),
]

def _extract_imgs(prop):
    pid = prop.get("id") or ""
    imgs = []
    for ph in (prop.get("photos") or [])[:20]:
        if not isinstance(ph, dict): continue
        im = ph.get("imagesMap") or {}
        for k in ("large", "original", "medium", "thumbnail"):
            fn = im.get(k)
            if fn:
                u = fn if str(fn).startswith("http") else f"https://images.nobroker.in/images/{pid}/{fn}"
                if u not in imgs: imgs.append(u)
                break
    return imgs

def _send_telegram(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not cid:
        return
    try:
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        body = urllib.parse.urlencode({"chat_id": cid, "text": msg[:3900], "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=10)
    except Exception:
        pass

def run_sniper():
    idx_p = ROOT / "web/public/data/mumbai-index.json"
    data = load_index()
    socs = data.get("societies", [])
    existing_urls = {u.get("u") for s in socs for u in (s.get("units_rent") or []) if u.get("u")}

    tasks = [(t, lt, name, lat, lng) for name, lat, lng in HOT_HUBS for t, lt in (("RENT", "owner"), ("SHARED_ACCOMMODATION", "shared"))]

    def _poll(task):
        api_t, lt, loc_name, lat, lng = task
        sp = json.dumps([{"type": "place", "placeId": "", "lat": lat, "lon": lng, "placeName": loc_name, "showMap": False}])
        sp_b64 = base64.b64encode(sp.encode()).decode()
        url = f"https://www.nobroker.in/api/v3/multi/property/{api_t}/filter?searchParam={urllib.parse.quote(sp_b64)}&radius=2.8&city=mumbai&pageNo=1&orderBy=activationDate,desc"
        rows = []
        try:
            d = json.loads(_get(url))
        except Exception:
            return rows
        for prop in (d.get("data") or []):
            if not isinstance(prop, dict): continue
            detail = prop.get("detailUrl") or ""
            if detail.startswith("/"): detail = "https://www.nobroker.in" + detail
            detail = detail.split("?")[0]
            if not detail.startswith("http") or detail in existing_urls: continue
            price = parse_price(prop.get("rent") or prop.get("price"), mode="rent")
            if not price: continue
            det = detect_locality(f"{prop.get('locality', '')} {prop.get('street', '')} {loc_name}")
            if not det: continue
            # BH_V65_TAG_SHARED: Detect shared-room/PG listings so they route to the Shared filter
            _nb_t = f"{prop.get('propertyTitle','')} {prop.get('detailUrl','')} {prop.get('type','')}".lower()
            _is_sh = bool(prop.get('sharedAccomodation') or any(k in _nb_t for k in ('shared-room','shared room','single-room','single room','sharing','flatmate','pg ')))
            imgs = _extract_imgs(prop)
            rows.append({
                "name": clean_soc_name(prop.get("society") or prop.get("propertyTitle") or f"{det[0]} Flat", det[0]),
                "locality": det[0], "mode": "rent", "p": price,
                "b": parse_bhk(str(prop.get("typeDesc") or prop.get("type") or "")) or 1,
                "sq": prop.get("propertySize"), "s": "nobroker", "u": detail, "zb": True, "lt": ("shared" if _is_sh else "owner"), "lt": lt,
                "f": norm_furnishing(prop.get("furnishingDesc") or prop.get("furnishing")),
                "img": imgs[0] if imgs else None, "imgs": imgs,
                "lat": prop.get("latitude"), "lng": prop.get("longitude"),
            })
        return rows

    fresh, seen = [], set()
    with ThreadPoolExecutor(max_workers=8) as ex:
        for fut in as_completed([ex.submit(_poll, t) for t in tasks]):
            for r in fut.result():
                if r["u"] not in seen:
                    seen.add(r["u"])
                    fresh.append(r)

    if not fresh:
        print("[SNIPER] 0 brand-new zero-brokerage drops in the last 2h.")
        return

    added_u, added_s = merge_records_into_societies(socs, fresh)
    for s in (socs[-added_s:] if added_s else []):
        s["age_days"] = 0
        s["is_new"] = True

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["count"] = len(socs)
    data["societies"] = socs
    _, size_b = save_compacted_index(idx_p, data)

    print(f"[SNIPER] +{added_u} new zero-brokerage flats ({added_s} new buildings) | Index: {size_b/1048576:.2f} MiB")
    top_lines = [f"- {r['b']}BHK {r['name']} ({r['locality']}) Rs.{r['p']:,} {r['u']}" for r in fresh[:8]]
    _send_telegram(f"Bombay Homes Sniper: {added_u} new Zero-Brokerage drops!\n" + "\n".join(top_lines))

if __name__ == "__main__":
    run_sniper()
