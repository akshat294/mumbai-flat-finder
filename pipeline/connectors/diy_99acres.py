import sys; from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parent.parent.parent))
from pipeline.index_io import load_index
import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.connectors.v19_common import detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name, merge_records_into_societies
from pipeline.compact_index import save_compacted_index

DIY_CACHE = ROOT / "data/diy_99acres_cache.json"

HUB_SLUGS = [
    ("Mumbai", "mumbai"),
    ("Bandra West", "bandra-west-western-mumbai"),
    ("Khar West", "khar-west-western-mumbai"),
    ("Andheri West", "andheri-west-mumbai-andheri-dahisar"),
    ("Andheri East", "andheri-east-mumbai-andheri-dahisar"),
    ("Powai", "powai-central-mumbai-suburbs"),
    ("Worli", "worli-south-mumbai"),
    ("Lower Parel", "lower-parel-south-mumbai"),
    ("Dadar West", "dadar-west-south-mumbai"),
    ("Goregaon West", "goregaon-west-mumbai-andheri-dahisar"),
    ("Malad West", "malad-west-mumbai-andheri-dahisar"),
    ("Chembur", "chembur-mumbai-harbour"),
    ("Thane West", "thane-west-thane"),
    ("Kharghar", "kharghar-navi-mumbai"),
]

EXTRACT_JS = (
    "() => {"
    "  const out = [];"
    "  const seen = new Set();"
    "  for (const a of document.querySelectorAll('a[href*=\"-spid-\"]')) {"
    "    const href = (a.href || '').split('?')[0];"
    "    if (!href || seen.has(href)) continue;"
    "    let cur = a, card = a.parentElement;"
    "    for (let i = 0; i < 8 && cur && cur.parentElement; i++) {"
    "      cur = cur.parentElement;"
    "      const t = (cur.innerText || '');"
    "      if (t.length > 1800) break;"
    "      if (/(?:\\u20b9|Rs\\.?|Lac|Lakh|Cr\\b|\\d{2},\\d{3})/i.test(t) && t.length >= 25) {"
    "        card = cur;"
    "        if (t.length >= 70) break;"
    "      }"
    "    }"
    "    seen.add(href);"
    "    const txt = (card ? card.innerText : a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 700);"
    "    const title = (a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 140);"
    "    const imgs = [];"
    "    if (card) {"
    "      for (const im of card.querySelectorAll('img')) {"
    "        const u = im.currentSrc || im.src || im.getAttribute('data-src') || '';"
    "        if (u.startsWith('http') && !/logo|icon|svg|avatar|verified/i.test(u) && !imgs.includes(u)) imgs.push(u);"
    "      }"
    "    }"
    "    out.push({ href, title, txt, imgs: imgs.slice(0, 5) });"
    "  }"
    "  return out;"
    "}"
)

def _extract_99_price(txt, mode):
    m = re.search(r"(?:\u20b9|Rs\.?)\s*([\d,.]+)\s*(Cr|Crore|Lac|Lakh|L|K)?", txt or "", re.I)
    if m:
        return parse_price(m.group(0), mode=mode)
    return parse_price(txt, mode=mode)

def _extract_soc_name(title, txt, loc):
    for src in (title, txt):
        m = re.search(r"(?:in|at)\s+([A-Z][A-Za-z0-9\s&'.-]{2,42}?)(?:,|\s+(?:Mumbai|Thane|Navi|West|East|Bandra|Andheri|Powai|Worli|Dadar|Goregaon|Malad|Chembur|Khar))", src or "")
        if m:
            cand = m.group(1).strip(" ,.-")
            if len(cand) >= 3 and cand.lower() != loc.lower():
                return clean_soc_name(cand, loc)
    if title and len(title) >= 4:
        return clean_soc_name(title, loc)
    return f"{loc} Flat"

def scrape_99acres_diy(modes=("rent",), max_hubs=14, pages_per_hub=2, merge_now=True):
    from playwright.sync_api import sync_playwright
    captured, seen_u = [], set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel="chrome", headless=False,
            args=["--disable-blink-features=AutomationControlled", "--window-position=-32000,-32000"],
        )
        ctx = browser.new_context(viewport={"width": 1366, "height": 860})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = ctx.new_page()

        try:
            page.goto("https://www.99acres.com/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        for mode in modes:
            prefix = "flats-for-rent-in" if mode == "rent" else "flats-in"
            for loc_name, slug in HUB_SLUGS[:max_hubs]:
                for pg_no in range(1, pages_per_hub + 1):
                    url = f"https://www.99acres.com/{prefix}-{slug}-ffid" + (f"-page-{pg_no}" if pg_no > 1 else "")
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=22000)
                        page.wait_for_timeout(3200)
                        for y in (900, 2200, 3600):
                            page.evaluate(f"window.scrollTo(0, {y})")
                            page.wait_for_timeout(550)

                        cards = page.evaluate(EXTRACT_JS)
                        pg_added = 0
                        for c in cards:
                            u = (c.get("href") or "").split("?")[0]
                            if not u.startswith("http") or u in seen_u:
                                continue
                            txt = c.get("txt") or ""
                            title = c.get("title") or ""
                            price = _extract_99_price(txt, mode)
                            det = detect_locality(f"{title} {txt} {loc_name}")
                            if not price or not det:
                                continue
                            seen_u.add(u)
                            sq_m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", txt, re.I)
                            is_owner = bool(re.search(r"\bowner\b", txt, re.I)) and not bool(re.search(r"\bdealer\b|\bfeatured dealer\b", txt, re.I))
                            imgs = c.get("imgs") or []
                            captured.append({
                                "name": _extract_soc_name(title, txt, det[0]),
                                "locality": det[0], "mode": mode, "p": price,
                                "b": parse_bhk(f"{title} {txt}") or 1,
                                "sq": int(sq_m.group(1)) if sq_m else None,
                                "s": "99acres", "u": u,
                                "zb": is_owner, "lt": "owner" if is_owner else "broker",
                                "f": norm_furnishing(txt),
                                "img": imgs[0] if imgs else None, "imgs": imgs,
                            })
                            pg_added += 1
                        print(f"  [DIY 99] {mode}/{loc_name} p{pg_no} | dom_cards={len(cards)} -> captured={pg_added}")
                        if len(cards) == 0:
                            break
                    except Exception as e:
                        print(f"  [DIY 99] {mode}/{loc_name} p{pg_no} err={str(e)[:80]}")
                        continue
        browser.close()

    print(f"[DIY 99ACRES] Total captured: {len(captured)} fresh Mumbai listings at Rs.0!")
    if captured:
        old = json.loads(DIY_CACHE.read_text(encoding="utf-8")).get("records", []) if DIY_CACHE.exists() else []
        by_u = {r["u"]: r for r in old if r.get("u")}
        for r in captured:
            by_u[r["u"]] = r
        DIY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        DIY_CACHE.write_text(json.dumps({"updated": int(time.time()), "records": list(by_u.values())}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        if merge_now:
            idx_p = ROOT / "web/public/data/mumbai-index.json"
            data = load_index()
            socs = data.get("societies", [])
            au, asoc = merge_records_into_societies(socs, list(by_u.values()))
            data["societies"] = socs
            data["count"] = len(socs)
            _, sz = save_compacted_index(idx_p, data, max_bytes=20_800_000)
            print(f"[DIY 99ACRES MERGE] +{au} new units ({asoc} new buildings) | Index: {sz/1048576:.2f} MiB")
    return len(captured)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="rent,buy")
    ap.add_argument("--hubs", type=int, default=14)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()
    scrape_99acres_diy(modes=tuple(args.modes.split(",")), max_hubs=args.hubs, pages_per_hub=args.pages, merge_now=not args.no_merge)
