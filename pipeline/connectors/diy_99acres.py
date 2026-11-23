import argparse, json, random, re, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.connectors.v19_common import (
    detect_locality, parse_price, parse_bhk, norm_furnishing, clean_soc_name, merge_records_into_societies
)
from pipeline.index_io import load_index, save_sharded_index
from pipeline.quality_filter import filter_and_track_societies, REGISTRY_PATH
from pipeline.mumbai_transit import enrich_transit_context

DIY_CACHE = ROOT / "data/diy_99acres_cache.json"
SLUG_CACHE = ROOT / "data/diy_99acres_slugs.json"
CHECKPOINT_PATH = ROOT / "data/diy_99acres_checkpoint.json"

HUB_SPECS = [
    ("Mumbai", "mumbai-without-brokerage", "apartments-flats-for-rent-in"),
    ("Bandra West", "bandra-west-western-mumbai", None),
    ("Khar West", "khar-west-western-mumbai", None),
    ("Santacruz West", "santacruz-west-western-mumbai", None),
    ("Juhu", "juhu-western-mumbai", None),
    ("Vile Parle West", "vile-parle-west-western-mumbai", None),
    ("Bandra East", "bandra-east-western-mumbai", None),
    ("Santacruz East", "santacruz-east-western-mumbai", None),
    ("Vile Parle East", "vile-parle-east-western-mumbai", None),
    ("Colaba", "colaba-south-mumbai", None),
    ("Cuffe Parade", "cuffe-parade-south-mumbai", None),
    ("Malabar Hill", "malabar-hill-south-mumbai", None),
    ("Worli", "worli-south-mumbai", None),
    ("Lower Parel", "lower-parel-south-mumbai", None),
    ("Prabhadevi", "prabhadevi-south-mumbai", None),
    ("Mahalaxmi", "mahalaxmi-south-mumbai", None),
    ("Byculla", "byculla-south-mumbai", None),
    ("Dadar West", "dadar-west-south-mumbai", None),
    ("Dadar East", "dadar-east-south-mumbai", None),
    ("Matunga", "matunga-central-mumbai", None),
    ("Mahim", "mahim-south-mumbai", None),
    ("Sion", "sion-central-mumbai", None),
    ("Wadala", "wadala-central-mumbai", None),
    ("Andheri West", "andheri-west-mumbai-andheri-dahisar", None),
    ("Versova", "versova-mumbai-andheri-dahisar", None),
    ("Andheri East", "andheri-east-mumbai-andheri-dahisar", None),
    ("Jogeshwari West", "jogeshwari-west-mumbai-andheri-dahisar", None),
    ("Goregaon West", "goregaon-west-mumbai-andheri-dahisar", None),
    ("Goregaon East", "goregaon-east-mumbai-andheri-dahisar", None),
    ("Malad West", "malad-west-mumbai-andheri-dahisar", None),
    ("Malad East", "malad-east-mumbai-andheri-dahisar", None),
    ("Kandivali West", "kandivali-west-mumbai-andheri-dahisar", None),
    ("Kandivali East", "kandivali-east-mumbai-andheri-dahisar", None),
    ("Borivali West", "borivali-west-mumbai-andheri-dahisar", None),
    ("Borivali East", "borivali-east-mumbai-andheri-dahisar", None),
    ("Dahisar East", "dahisar-east-mumbai-andheri-dahisar", None),
    ("Mira Road", "mira-road-mira-bhayandar", None),
    ("Powai", "powai-central-mumbai-suburbs", None),
    ("Chandivali", "chandivali-central-mumbai-suburbs", None),
    ("Chembur", "chembur-central-mumbai", None),
    ("Ghatkopar West", "ghatkopar-west-central-mumbai-suburbs", None),
    ("Ghatkopar East", "ghatkopar-east-central-mumbai-suburbs", None),
    ("Vikhroli", "vikhroli-central-mumbai-suburbs", None),
    ("Kanjurmarg", "kanjurmarg-central-mumbai-suburbs", None),
    ("Bhandup West", "bhandup-west-central-mumbai-suburbs", None),
    ("Mulund West", "mulund-west-central-mumbai-suburbs", None),
    ("Thane West", "thane-west-thane", None),
    ("Ghodbunder Road", "ghodbunder-road-thane", None),
    ("Vashi", "vashi-navi-mumbai", None),
    ("Nerul", "nerul-navi-mumbai", None),
    ("Seawoods", "seawoods-navi-mumbai", None),
    ("Kharghar", "kharghar-navi-mumbai", None),
    ("Airoli", "airoli-navi-mumbai", None),
    ("Panvel", "panvel-navi-mumbai", None),
]

FALLBACK_ZONES = [
    "western-mumbai",
    "south-mumbai",
    "mumbai-andheri-dahisar",
    "central-mumbai-suburbs",
    "central-mumbai",
    "mumbai-harbour",
    "thane",
    "navi-mumbai",
    "mira-bhayandar",
    "mumbai",
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
    "      if (t.length > 2200) break;"
    "      if (/(?:\\u20b9|Rs\\.?|Lac|Lakh|Cr\\b|\\d{2},\\d{3})/i.test(t) && t.length >= 25) {"
    "        card = cur;"
    "        if (t.length >= 90) break;"
    "      }"
    "    }"
    "    seen.add(href);"
    "    const txt = (card ? card.innerText : a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 900);"
    "    const title = (a.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 160);"
    "    let soc = '';"
    "    if (card) {"
    "      const socEl = card.querySelector('a[href*=\"-npxid-\"], a[href*=\"-ffid\"], [class*=\"society\"], [class*=\"projectName\"], [class*=\"tupleHeading\"]');"
    "      if (socEl && socEl !== a) {"
    "        const st = (socEl.innerText || '').replace(/\\s+/g, ' ').trim();"
    "        if (st.length >= 3 && st.length <= 70 && !/bhk|flat|rent|sale|deposit/i.test(st)) soc = st;"
    "      }"
    "    }"
    "    const imgs = [];"
    "    if (card) {"
    "      for (const im of card.querySelectorAll('img')) {"
    "        const u = im.currentSrc || im.src || im.getAttribute('data-src') || '';"
    "        if (u.startsWith('http') && !/logo|icon|svg|avatar|verified|badge|spacer|placeholder/i.test(u) && !imgs.includes(u)) imgs.push(u);"
    "      }"
    "    }"
    "    out.push({ href, title, soc, txt, imgs: imgs.slice(0, 5) });"
    "  }"
    "  return out;"
    "}"
)

def _load_json(p, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default

def _save_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

def _extract_99_price(txt, mode):
    cleaned = re.sub(r"\+?\s*Deposit\s*(?:\u20b9|Rs\.?)?\s*[\d,.]+\s*(?:months?\s*rent|Cr|Crore|Lac|Lakh|L|K)?", " ", txt or "", flags=re.I)
    m = re.search(r"(?:\u20b9|Rs\.?)\s*([\d,.]+)\s*(Cr|Crore|Lac|Lakh|L|K)?", cleaned, re.I)
    if m:
        return parse_price(m.group(0), mode=mode)
    return parse_price(cleaned, mode=mode)

def _extract_soc_name(soc_dom, title, txt, loc):
    if soc_dom and len(soc_dom) >= 3 and soc_dom.lower() != loc.lower():
        return clean_soc_name(soc_dom, loc)
    for src in (title, txt):
        m = re.search(
            r"(?:in|at)\s+([A-Z][A-Za-z0-9\s&'.-]{2,42}?)(?:,|\s+(?:Mumbai|Thane|Navi|West|East|Bandra|Andheri|Powai|Worli|Dadar|Goregaon|Malad|Chembur|Khar|Kandivali|Borivali|Vashi|Kharghar))",
            src or "",
        )
        if m:
            cand = m.group(1).strip(" ,.-")
            if len(cand) >= 3 and cand.lower() != loc.lower() and not re.match(r"^(?:sector|phase|stage)\s*\d+$", cand, re.I):
                return clean_soc_name(cand, loc)
    if title and len(title) >= 4:
        return clean_soc_name(title, loc)
    return f"{loc} Flat"

def _is_404_page(title, cards_n):
    tl = (title or "").lower()
    if cards_n > 0:
        return False
    return ("page is gone" in tl) or ("404" in tl) or ("not found" in tl)

def _build_url(mode, slug, special_prefix, pg_no):
    if special_prefix:
        prefix = special_prefix if mode == "rent" else "apartments-flats-in"
    else:
        prefix = "flats-for-rent-in" if mode == "rent" else "flats-in"
    base = f"https://www.99acres.com/{prefix}-{slug}-ffid"
    if pg_no > 1:
        base += f"-page-{pg_no}"
    return base

def _dismiss_modal(page):
    try:
        btn = page.locator("button:has-text('Ok, Understood'), text=Ok, Understood").first
        if btn.is_visible(timeout=600):
            btn.click()
    except Exception:
        pass

def publish_all_cached():
    # Merge DIY 99acres cache into sharded index -> 2026 Transit -> Vibe Score -> 6-Stage Quality Filter -> Shards
    cache_recs = _load_json(DIY_CACHE, {}).get("records") or []
    if not cache_recs:
        print("[DIY 99 PUBLISH] Cache empty, skipping publish.")
        return {}

    data = load_index()
    socs = data.get("societies") or []
    au, asoc = merge_records_into_societies(socs, cache_recs)
    enrich_transit_context(socs)
    cleaned_socs, qstats = filter_and_track_societies(socs)

    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    data["generated_at"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    data["generated_ts"] = int(now_ist.timestamp())
    data["societies"] = cleaned_socs
    data["count"] = len(cleaned_socs)
    sh_stats = save_sharded_index(data, max_shard_bytes=3_800_000)

    try:
        from pipeline.vision_vibe import score_societies
        score_societies()
    except Exception as e:
        print(f"[DIY 99 PUBLISH WARN] vision_vibe skip: {e}")

    print(
        f"[DIY 99 PUBLISH] Merged {len(cache_recs):,} cached 99acres recs (+{au:,} new units, +{asoc:,} new bldgs) | "
        f"Shards: {sh_stats['rent_shards']}R + {sh_stats['buy_shards']}B ({sh_stats['total_mb']} MB, max {sh_stats['max_shard_mb']} MB) | "
        f"Live totals: {sh_stats['rent_flats']:,} Rent + {sh_stats['buy_flats']:,} Buy flats"
    )
    return sh_stats

def scrape_99acres_diy(
    modes=("rent", "buy"),
    max_hubs=54,
    pages_per_hub=4,
    incremental=True,
    reset_checkpoint=False,
    merge_now=True,
):
    from playwright.sync_api import sync_playwright

    old_cache = _load_json(DIY_CACHE, {"records": []})
    by_u = {r["u"]: r for r in (old_cache.get("records") or []) if isinstance(r, dict) and r.get("u")}
    slug_map = _load_json(SLUG_CACHE, {})
    reg = _load_json(REGISTRY_PATH, {})
    ckpt = {"done": []} if reset_checkpoint else _load_json(CHECKPOINT_PATH, {"done": []})
    done_set = set(ckpt.get("done") or [])

    session_new, session_price_upd, session_seen = 0, 0, 0
    hubs_done_now, early_stops = 0, 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--window-position=-32000,-32000"],
        )
        ctx = browser.new_context(viewport={"width": 1366, "height": 880})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = ctx.new_page()

        try:
            page.goto("https://www.99acres.com/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            _dismiss_modal(page)
        except Exception:
            pass

        for mode in modes:
            for loc_name, default_slug, special_prefix in HUB_SPECS[:max_hubs]:
                if mode == "buy" and special_prefix == "apartments-flats-for-rent-in":
                    continue

                hub_key = f"{mode}::{loc_name}::{special_prefix or 'std'}"
                if hub_key in done_set:
                    continue

                slug = slug_map.get(hub_key) or default_slug
                blocked_streak = 0

                for pg_no in range(1, pages_per_hub + 1):
                    url = _build_url(mode, slug, special_prefix, pg_no)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=22000)
                        page.wait_for_timeout(random.randint(2300, 3200))
                        _dismiss_modal(page)
                        for y in (950, 2300, 3800):
                            page.evaluate(f"window.scrollTo(0, {y})")
                            page.wait_for_timeout(420)

                        title = page.title()
                        cards = page.evaluate(EXTRACT_JS)

                        if pg_no == 1 and _is_404_page(title, len(cards)) and not special_prefix:
                            base_loc_slug = re.sub(r"[^a-z0-9]+", "-", loc_name.lower()).strip("-")
                            for z_suf in FALLBACK_ZONES:
                                cand_slug = f"{base_loc_slug}-{z_suf}"
                                if cand_slug == slug:
                                    continue
                                test_url = _build_url(mode, cand_slug, None, 1)
                                page.goto(test_url, wait_until="domcontentloaded", timeout=18000)
                                page.wait_for_timeout(2200)
                                t2 = page.title()
                                c2 = page.evaluate(EXTRACT_JS)
                                if c2:
                                    slug = cand_slug
                                    slug_map[hub_key] = slug
                                    _save_json(SLUG_CACHE, slug_map)
                                    title, cards = t2, c2
                                    print(f"  [SLUG RESOLVED] {mode}/{loc_name} -> {slug}")
                                    break

                        if "access denied" in (title or "").lower() or "security" in (title or "").lower():
                            blocked_streak += 1
                            print(f"  [DIY 99 WARN] {mode}/{loc_name} p{pg_no} hit WAF ({title[:40]}); cooling 8s...")
                            page.wait_for_timeout(8000)
                            if blocked_streak >= 2:
                                break
                            continue

                        if not cards:
                            break

                        pg_total, pg_unchanged, pg_new = 0, 0, 0
                        for c in cards:
                            u = (c.get("href") or "").split("?")[0].rstrip("/")
                            if not u.startswith("http"):
                                continue
                            txt = c.get("txt") or ""
                            c_title = c.get("title") or ""
                            price = _extract_99_price(txt, mode)
                            det = detect_locality(f"{c_title} {txt} {loc_name}")
                            if not price or not det:
                                continue

                            pg_total += 1
                            session_seen += 1

                            prev_rec = by_u.get(u)
                            prev_reg = reg.get(u)
                            known_price = prev_rec.get("p") if prev_rec else (prev_reg[2] if isinstance(prev_reg, list) and len(prev_reg) >= 3 else None)

                            if known_price is not None and int(known_price) == int(price):
                                pg_unchanged += 1
                                continue

                            sq_m = re.search(r"(\d{3,4})\s*(?:sq\.?\s*ft|sqft)", txt, re.I)
                            is_owner = bool(special_prefix == "apartments-flats-for-rent-in") or (
                                bool(re.search(r"\bowner\b", txt, re.I)) and not bool(re.search(r"\bdealer\b|\bfeatured dealer\b", txt, re.I))
                            )
                            imgs = c.get("imgs") or []
                            rec = {
                                "name": _extract_soc_name(c.get("soc") or "", c_title, txt, det[0]),
                                "locality": det[0],
                                "mode": mode,
                                "p": price,
                                "b": parse_bhk(f"{c_title} {txt}") or 1,
                                "sq": int(sq_m.group(1)) if sq_m else None,
                                "s": "99acres",
                                "u": u,
                                "zb": is_owner,
                                "lt": "owner" if is_owner else "broker",
                                "f": norm_furnishing(txt),
                                "img": imgs[0] if imgs else None,
                                "imgs": imgs,
                            }
                            if prev_rec:
                                session_price_upd += 1
                            else:
                                pg_new += 1
                                session_new += 1
                            by_u[u] = rec

                        if incremental and pg_total >= 10 and (pg_unchanged / pg_total) >= 0.85:
                            early_stops += 1
                            print(f"  [DIY 99] {mode}/{loc_name} p{pg_no} | cards={pg_total} new={pg_new} unchanged={pg_unchanged} -> EARLY STOP")
                            break
                        else:
                            print(f"  [DIY 99] {mode}/{loc_name} p{pg_no} | cards={pg_total} new={pg_new} unchanged={pg_unchanged}")

                        if pg_total < 12:
                            break
                    except Exception as e:
                        print(f"  [DIY 99 ERR] {mode}/{loc_name} p{pg_no}: {str(e)[:80]}")
                        break

                done_set.add(hub_key)
                hubs_done_now += 1
                _save_json(DIY_CACHE, {"updated": int(time.time()), "count": len(by_u), "records": list(by_u.values())})
                _save_json(CHECKPOINT_PATH, {"updated": int(time.time()), "done": sorted(done_set)})

        browser.close()

    print(
        f"[DIY 99ACRES SUMMARY] Hubs scanned={hubs_done_now} | Cards seen={session_seen:,} | "
        f"NEW={session_new:,} | Price-Updated={session_price_upd:,} | Early-Stops={early_stops} | "
        f"Total DIY 99acres Cache={len(by_u):,}"
    )

    total_expected = sum(
        1 for mode in modes for _, _, sp in HUB_SPECS[:max_hubs]
        if not (mode == "buy" and sp == "apartments-flats-for-rent-in")
    )
    if len(done_set) >= total_expected and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print("[DIY 99ACRES] Pass complete - checkpoint cleared for next run.")

    if merge_now:
        publish_all_cached()
    return session_new

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="rent,buy")
    ap.add_argument("--hubs", type=int, default=54)
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--full", action="store_true", help="Disable incremental early-stop for a deep harvest")
    ap.add_argument("--reset", action="store_true", help="Ignore previous checkpoint and start from hub 1")
    ap.add_argument("--publish-only", action="store_true", help="Merge existing cache into shards without scraping")
    ap.add_argument("--no-merge", action="store_true")
    args = ap.parse_args()
    if args.publish_only:
        publish_all_cached()
    else:
        scrape_99acres_diy(
            modes=tuple(m.strip() for m in args.modes.split(",") if m.strip()),
            max_hubs=args.hubs,
            pages_per_hub=args.pages,
            incremental=not args.full,
            reset_checkpoint=args.reset,
            merge_now=not args.no_merge,
        )
