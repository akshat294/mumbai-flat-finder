# Bombay Homes Ultra-Exhaustive Permutation, Edge-Case & Chaos Fuzzer (v68)
import argparse, http.server, json, math, re, socketserver, sys, threading, time, traceback, urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from curl_cffi import requests as creq

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent

def start_local_server():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str((ROOT / "web").resolve()), **kwargs)
        def do_POST(self):
            if self.path == "/api/ask":
                ln = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(ln).decode("utf-8", "replace") or "{}")
                q = str(body.get("query") or "").lower()
                act = body.get("action") or "parse"
                if act == "parse":
                    f = {"mode": "buy" if ("buy" in q or "cr" in q or "crore" in q) else ("rent" if ("rent" in q or "k" in q) else (body.get("currentMode") or "rent"))}
                    if "2bhk" in q or "2 bhk" in q: f["bhks"] = [2]
                    if "3bhk" in q or "3 bhk" in q: f["bhks"] = [3]
                    if "5bhk" in q or "5 bhk" in q: f["bhks"] = [5]
                    if "powai" in q: f["localities"] = ["Powai"]
                    elif "bandra" in q: f["localities"] = ["Bandra West"]
                    elif "colaba" in q: f["localities"] = ["Colaba"]
                    elif "thane" in q: f["localities"] = ["Thane West"]
                    if "75k" in q: f["maxPrice"] = 75000
                    elif "10k" in q: f["maxPrice"] = 10000
                    elif "3 cr" in q or "3cr" in q: f["maxPrice"] = 30000000
                    resp = {"ok": True, "engine": "local-mock", "filters": f}
                else:
                    resp = {"ok": True, "engine": "local-mock", "summary": "Mock summary."}
                raw = json.dumps(resp).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers()
                self.wfile.write(raw); return
            self.send_response(404); self.end_headers()
        def do_GET(self):
            if self.path in ("/api/flags", "/api/listings"):
                raw = b'{"flags":{}}' if self.path == "/api/flags" else b'{"listings":[]}'
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers()
                self.wfile.write(raw); return
            if self.path.startswith("/api/img?"):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                u = (qs.get("u") or [""])[0]
                if u.startswith("https:" + "//static.squareyards.com/"):
                    try:
                        r = creq.get(u, impersonate="chrome124", timeout=10, headers={"Referer": "https:" + "//www.squareyards.com/"})
                        ct = (r.headers.get("content-type") or "").lower()
                        if r.status_code == 200 and ct.startswith("image/"):
                            self.send_response(200); self.send_header("Content-Type", ct); self.end_headers()
                            self.wfile.write(r.content); return
                    except Exception:
                        pass
                self.send_response(404); self.end_headers(); return
            return super().do_GET()
        def log_message(self, *args):
            pass
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http:" + f"//127.0.0.1:{port}/"

def parse_card_prices(page):
    return page.evaluate(r"""() => {
        const out = [];
        document.querySelectorAll("#cardList .fc .fc-price").forEach(el => {
            const raw = (el.childNodes[0]?.textContent || el.textContent || "").trim();
            let v = 0;
            const mCr = raw.match(/([\d.]+)\s*Cr/i);
            const mL  = raw.match(/([\d.]+)\s*L/i);
            const mN  = raw.match(/([\d,]+)/);
            if (mCr) v = parseFloat(mCr[1]) * 1e7;
            else if (mL) v = parseFloat(mL[1]) * 1e5;
            else if (mN) v = parseFloat(mN[1].replace(/,/g, ""));
            if (v > 0) out.push(v);
        });
        return out;
    }""")

def draw_mouse_lasso(page, lat=19.065, lng=72.835, zoom=13, frac=0.22):
    page.evaluate(f"() => {{ const m = window.__bh().map; if (m) m.setView([{lat}, {lng}], {zoom}, {{ animate: false }}); }}")
    page.wait_for_timeout(200)
    lbtn = page.locator("#mapLassoBtn")
    if "Clear area" in (lbtn.text_content() or ""):
        lbtn.click(); page.wait_for_timeout(250)
    lbtn.click(); page.wait_for_timeout(180)
    box = page.locator("#map").bounding_box()
    cx, cy = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5
    rx, ry = box["width"] * frac, box["height"] * frac
    page.mouse.move(cx - rx, cy - ry); page.mouse.down()
    for pt in [(cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry), (cx - rx, cy - ry)]:
        page.mouse.move(pt[0], pt[1], steps=5)
    page.mouse.up()
    page.wait_for_timeout(550)

def draw_touch_lasso(mp, lat=19.065, lng=72.835, zoom=13, frac=0.28):
    mp.evaluate(f"() => {{ const m = window.__bh().map; if (m) m.setView([{lat}, {lng}], {zoom}, {{ animate: false }}); }}")
    mp.wait_for_timeout(200)
    lbtn = mp.locator("#mapLassoBtn")
    if "Clear area" in (lbtn.text_content() or ""):
        lbtn.click(); mp.wait_for_timeout(250)
    lbtn.click(); mp.wait_for_timeout(180)
    mp.evaluate(f"""() => {{
        const el = document.getElementById("map"); const r = el.getBoundingClientRect();
        const f = {frac};
        const cx = r.left + r.width*0.5, cy = r.top + r.height*0.5;
        const rx = r.width*f, ry = r.height*f;
        const pts = [[cx-rx,cy-ry],[cx+rx,cy-ry],[cx+rx,cy+ry],[cx-rx,cy+ry],[cx-rx,cy-ry]];
        const fire = (type, x, y, target) => {{
            const touch = new Touch({{ identifier: 1, target: el, clientX: x, clientY: y, pageX: x, pageY: y }});
            target.dispatchEvent(new TouchEvent(type, {{ cancelable: true, bubbles: true, touches: type==='touchend'?[]:[touch], targetTouches: type==='touchend'?[]:[touch], changedTouches: [touch] }}));
        }};
        fire("touchstart", pts[0][0], pts[0][1], el);
        for (let i=1; i<pts.length; i++) fire("touchmove", pts[i][0], pts[i][1], window);
        fire("touchend", pts[pts.length-1][0], pts[pts.length-1][1], window);
    }}""")
    mp.wait_for_timeout(550)

def get_state_snap(page):
    return page.evaluate("""() => {
        const api = typeof window.__bh === "function" ? window.__bh() : {};
        const st = api.st || {};
        return {
            sum: (document.getElementById("resSum")?.textContent || "").trim(),
            cards: document.querySelectorAll("#cardList .fc").length,
            mode: st.mode || "",
            fZone: document.getElementById("fZone")?.value || "",
            fLoc: document.getElementById("fLoc")?.value || "",
            fSource: document.getElementById("fSource")?.value || "",
            fFurn: document.getElementById("fFurn")?.value || "",
            q: (document.getElementById("searchBox")?.value || "").trim(),
            hasLasso: !!(Array.isArray(st.lasso) && st.lasso.length >= 3),
            mapBounds: !!st.mapBounds,
            multiLocs: Array.isArray(st.multiLocs) ? st.multiLocs.slice() : [],
            bhks: st.bhks ? [...st.bhks] : [],
            activeChips: [...document.querySelectorAll(".n-chip.active")].map(e => e.dataset.nb),
            afPills: [...document.querySelectorAll("#activeBar .bh-af-btn")].map(e => e.dataset.af),
            locBarDisp: document.getElementById("locChipsBar") ? getComputedStyle(document.getElementById("locChipsBar")).display : "none",
            lassoTxt: (document.getElementById("mapLassoBtn")?.textContent || "").trim(),
            filterBadge: (document.getElementById("filterCount")?.textContent || "").trim(),
            overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
        };
    }""")

def run_permutations(target_url=None, live_mode=False):
    out = ["=== BOMBAY HOMES ULTRA-EXHAUSTIVE PERMUTATION, EDGE-CASE & CHAOS AUDIT (V68) ==="]
    failures = []
    passed = 0

    def log(s=""):
        print(s, flush=True)
        out.append(str(s))

    def check(cond, msg, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            log(f"  [PASS] {msg}")
        else:
            full = f"{msg}" + (f" | DETAIL={detail}" if detail else "")
            failures.append(full)
            log(f"  [FAIL] {full}")

    log("\n=== PART 1: DEEP STATISTICAL & DATA ANOMALY SCAN (ALL 17,629 BUILDINGS / 29,217 FLATS) ===")
    man = json.loads((ROOT / "web/public/data/manifest.json").read_text(encoding="utf-8-sig"))
    dup_urls_in_soc = bad_photos = empty_names = null_coords = 0
    bad_prices, bad_sqfts, buy_extremes, rent_extremes = [], [], [], []

    for mode, sk, uk in (("rent", "rent_shards", "units_rent"), ("buy", "buy_shards", "units_buy")):
        for sf in man[sk]:
            for s in json.loads((ROOT / "web/public/data" / sf).read_text(encoding="utf-8-sig")):
                if not str(s.get("name") or "").strip(): empty_names += 1
                la, lo = s.get("lat"), s.get("lng")
                if not (isinstance(la, (int, float)) and isinstance(lo, (int, float)) and 18.7 <= la <= 19.6 and 72.6 <= lo <= 73.4):
                    null_coords += 1
                for im in ([s.get("thumb")] + (s.get("photos") or [])):
                    if im is not None and (not isinstance(im, str) or (not im.startswith("http") and not im.startswith("/api/img"))):
                        bad_photos += 1
                seen_u = set()
                for u in (s.get(uk) or []):
                    url = str(u.get("u") or "")
                    if url in seen_u: dup_urls_in_soc += 1
                    seen_u.add(url)
                    p = u.get("p")
                    sq = u.get("sq")
                    if not isinstance(p, (int, float)) or p <= 0:
                        bad_prices.append((mode, s.get("name"), p))
                    elif mode == "rent" and (p < 3000 or p > 5000000):
                        rent_extremes.append((s.get("name"), s.get("locality"), u.get("b"), p, u.get("s")))
                    elif mode == "buy" and (p < 800000 or p > 3000000000):
                        buy_extremes.append((s.get("name"), s.get("locality"), u.get("b"), p, u.get("s")))
                    if sq is not None and (not isinstance(sq, (int, float)) or sq < 80 or sq > 35000):
                        bad_sqfts.append((mode, s.get("name"), sq, u.get("s")))

    check(empty_names == 0 and null_coords == 0 and bad_photos == 0, f"DATA-1: 0 empty names ({empty_names}), 0 bad coords ({null_coords}), 0 malformed photo URLs ({bad_photos})")
    check(len(bad_prices) == 0, f"DATA-2: 0 zero/negative/null prices across all flats (bad={len(bad_prices)})", str(bad_prices[:4]))
    check(len(rent_extremes) == 0, f"DATA-3: 0 absurd Rent prices (<3k or >50L/mo) (found={len(rent_extremes)})", str(rent_extremes[:5]))
    check(len(buy_extremes) == 0, f"DATA-4: 0 absurd Buy prices (<8L or >300Cr) (found={len(buy_extremes)})", str(buy_extremes[:5]))
    check(len(bad_sqfts) == 0, f"DATA-5: 0 absurd Sqft values (<80 or >35,000 sqft) (found={len(bad_sqfts)})", str(bad_sqfts[:6]))
    check(dup_urls_in_soc == 0, f"DATA-6: 0 duplicate unit URLs inside same building (dups={dup_urls_in_soc})")

    httpd = None
    if not target_url:
        httpd, target_url = start_local_server()

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            log("\n=== PART 2: DESKTOP (1440x900) SPATIAL PERMUTATIONS, FILTER COMBINATIONS & CHAOS ===")
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            d_errs, d_fail = [], []
            page.on("pageerror", lambda e: d_errs.append(str(e)[:160]))
            page.on("requestfailed", lambda req: None if ("ERR_ABORTED" in str(req.failure) and any(h in req.url for h in ("tile.openstreetmap.org", "arcgisonline.com"))) else d_fail.append(f"{req.url[:65]} ({req.failure})"))
            page.goto(target_url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1800)

            base_snap = get_state_snap(page)
            rent_home = base_snap["sum"]
            log(f"  Baseline Rent: {rent_home!r} | cards={base_snap['cards']}")

            page.locator(".n-chip[data-nb='Thane']").click(); page.wait_for_timeout(250)
            s1 = get_state_snap(page)
            check(s1["fZone"] == "Thane" and not s1["sum"].startswith("0 ") and s1["activeChips"] == ["Thane"], f"SPATIAL-01 Zone chip Thane: {s1['sum']!r}", str(s1))

            draw_mouse_lasso(page, 19.065, 72.835, 13, 0.22)
            s2 = get_state_snap(page)
            check(s2["hasLasso"] and s2["fZone"] == "ALL" and s2["activeChips"] == ["ALL"] and not s2["sum"].startswith("0 "), f"SPATIAL-02 Thane -> Lasso(Bandra) clears Thane: {s2['sum']!r}", str(s2))

            page.locator(".n-chip[data-nb='South Mumbai']").click(); page.wait_for_timeout(250)
            s3 = get_state_snap(page)
            check((not s3["hasLasso"]) and s3["fZone"] == "South Mumbai" and "Draw area" in s3["lassoTxt"] and not s3["sum"].startswith("0 "), f"SPATIAL-03 Lasso -> South Mumbai chip clears Lasso: {s3['sum']!r}", str(s3))

            sb = page.locator("#searchBox")
            sb.fill("Powai"); sb.dispatch_event("input"); page.wait_for_timeout(350)
            s4 = get_state_snap(page)
            check(s4["fZone"] == "ALL" and s4["activeChips"] == ["ALL"] and not s4["sum"].startswith("0 ") and "search" in s4["afPills"], f"SPATIAL-04 South Mumbai -> Search 'Powai' clears zone & adds search pill: {s4['sum']!r}", str(s4))

            sb.click(); sb.fill("Juhu"); sb.dispatch_event("input"); page.wait_for_timeout(350)
            sug_loc = page.locator("#searchSuggest .ss-item[data-ss-type='loc']").first
            sug_any = page.locator("#searchSuggest .ss-item").first
            sug_item = sug_loc if sug_loc.count() > 0 else sug_any
            if sug_item.count() > 0 and sug_item.is_visible():
                sug_item.click(); page.wait_for_timeout(350)
                ss_closed = page.evaluate("() => { const ss = document.getElementById('searchSuggest'); return !ss || getComputedStyle(ss).display === 'none'; }")
                s5 = get_state_snap(page)
                check(ss_closed and not s5["sum"].startswith("0 ") and s5["fZone"] == "ALL", f"SPATIAL-05 Search -> Autocomplete .ss-item click + closes: {s5['sum']!r} (closed={ss_closed}, multiLocs={s5['multiLocs']})", str(s5))
            else:
                check(False, "SPATIAL-05 Autocomplete .ss-item did not appear for 'Juhu'!")
            sb.click(); sb.fill("Bandra"); sb.dispatch_event("input"); page.wait_for_timeout(250)
            page.locator("#resSum").click(force=True); page.wait_for_timeout(200)
            ss_out_closed = page.evaluate("() => { const ss = document.getElementById('searchSuggest'); return !ss || getComputedStyle(ss).display === 'none'; }")
            check(ss_out_closed, f"SPATIAL-05b Outside click closes #searchSuggest so map buttons are never blocked: closed={ss_out_closed}")

            draw_mouse_lasso(page, 19.118, 72.908, 13, 0.22)
            s6 = get_state_snap(page)
            check(s6["hasLasso"] and len(s6["multiLocs"]) == 0 and s6["locBarDisp"] == "none" and s6["q"] == "" and not s6["sum"].startswith("0 "), f"SPATIAL-06 MultiLoc/Search -> Lasso(Powai) clears multiLocs + #locChipsBar + search: {s6['sum']!r}", str(s6))

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            has_worli = page.evaluate("() => [...document.querySelectorAll('#fLoc option')].some(o => o.value === 'Worli')")
            if has_worli:
                page.select_option("#fLoc", "Worli"); page.wait_for_timeout(250)
                page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
                s7 = get_state_snap(page)
                check((not s7["hasLasso"]) and s7["fLoc"] == "Worli" and not s7["sum"].startswith("0 "), f"SPATIAL-07 Lasso -> Drawer #fLoc(Worli) clears Lasso: {s7['sum']!r}", str(s7))
            else:
                page.locator("#closeFilterBtn").click()
                check(False, "SPATIAL-07 Worli not found in #fLoc options")

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.select_option("#fZone", "Thane"); page.wait_for_timeout(250)
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            s8 = get_state_snap(page)
            check(s8["fZone"] == "Thane" and s8["fLoc"] == "ALL" and not s8["sum"].startswith("0 "), f"SPATIAL-08 #fLoc(Worli) -> #fZone(Thane) resets fLoc (no 0-result conflict!): {s8['sum']!r}", str(s8))

            if page.locator("#mapAreaBtn").count() > 0 and page.locator("#mapAreaBtn").is_visible():
                page.evaluate("() => { const m = window.__bh().map; if (m) m.setView([19.065, 72.835], 14, { animate: false }); }")
                page.wait_for_timeout(200)
                page.locator("#mapAreaBtn").click(); page.wait_for_timeout(350)
                s9 = get_state_snap(page)
                check(s9["mapBounds"] and s9["fZone"] == "ALL" and not s9["sum"].startswith("0 "), f"SPATIAL-09 Thane -> #mapAreaBtn(Bandra) clears Thane: {s9['sum']!r}", str(s9))

            draw_mouse_lasso(page, 18.935, 72.895, 14, 0.14)
            s_sea = get_state_snap(page)
            page.locator("#mapLassoBtn").click(); page.wait_for_timeout(350)
            s_sea_clr = get_state_snap(page)
            check(s_sea["hasLasso"] and s_sea["sum"].startswith("0 ") and "(0)" in s_sea["lassoTxt"] and s_sea_clr["sum"] == rent_home, f"SPATIAL-10 Ocean Lasso shows 0 + Clear area (0) & recovers: sea={s_sea['sum']!r} ({s_sea['lassoTxt']!r}) -> {s_sea_clr['sum']!r}", str((s_sea, s_sea_clr)))

            page.locator("#mapLassoBtn").click(); page.wait_for_timeout(150)
            box = page.locator("#map").bounding_box()
            page.mouse.move(box["x"] + 200, box["y"] + 200); page.mouse.down(); page.mouse.move(box["x"] + 202, box["y"] + 201); page.mouse.up()
            page.wait_for_timeout(300)
            s_tap = get_state_snap(page)
            if "Cancel" in s_tap["lassoTxt"]:
                page.keyboard.press("Escape"); page.wait_for_timeout(200)
                s_tap = get_state_snap(page)
            check((not s_tap["hasLasso"]) and s_tap["sum"] == rent_home, f"SPATIAL-11 Tiny 2px accidental tap in Lasso mode doesn't corrupt state: {s_tap['sum']!r} ({s_tap['lassoTxt']!r})", str(s_tap))

            sb.fill("3BHK in Powai under 3 Cr")
            with page.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                page.locator(".bh-uni-ai").click()
            try:
                page.wait_for_function("() => (document.getElementById('resSum')?.textContent || '').includes('for sale') && !document.getElementById('resSum').textContent.startsWith('Loading')", timeout=20000)
            except Exception:
                pass
            page.wait_for_timeout(600)
            s_xai = get_state_snap(page)
            check(s_xai["mode"] == "buy" and "for sale" in s_xai["sum"] and not s_xai["sum"].startswith("0 "), f"SPATIAL-12 Cross-mode AI (Rent -> '3BHK in Powai under 3 Cr') switches to Buy cleanly: {s_xai['sum']!r}", str(s_xai))
            page.locator("#modeRent").click(); page.wait_for_timeout(350)
            if page.locator("#bhAfClearAll").count() > 0 and page.locator("#bhAfClearAll").is_visible():
                page.locator("#bhAfClearAll").click(); page.wait_for_timeout(350)
            else:
                page.evaluate("() => { const b = document.getElementById('resetMiniBtn'); if (b) b.click(); }"); page.wait_for_timeout(350)

            log("\n--- 2B. REAL SORT ORDER, MULTI-BHK, SLIDER & CHIP COMBINATIONS ---")
            page.select_option("#v17Sort", "price_asc"); page.wait_for_timeout(450)
            p_asc = parse_card_prices(page)[:15]
            asc_ok = len(p_asc) >= 10 and all(p_asc[i] <= p_asc[i + 1] for i in range(len(p_asc) - 1))
            check(asc_ok, f"SORT-1 Rent price_asc truly monotonic ascending ({p_asc[:6]})", str(p_asc))

            page.select_option("#v17Sort", "price_desc"); page.wait_for_timeout(450)
            p_desc = parse_card_prices(page)[:15]
            desc_ok = len(p_desc) >= 10 and all(p_desc[i] >= p_desc[i + 1] for i in range(len(p_desc) - 1))
            check(desc_ok, f"SORT-2 Rent price_desc truly monotonic descending ({p_desc[:6]})", str(p_desc))
            page.select_option("#v17Sort", "rec"); page.wait_for_timeout(300)

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.locator(".bhk-opt[data-bhk='1.5']").click()
            page.locator(".bhk-opt[data-bhk='2.5']").click()
            page.wait_for_timeout(250)
            half_txt = (page.locator("#applyFiltersBtn").text_content() or "").strip()
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            s_half = get_state_snap(page)
            check(not s_half["sum"].startswith("0 ") and "bhk:1.5" in s_half["afPills"] and "bhk:2.5" in s_half["afPills"], f"COMBO-1 Half-BHK pair (1.5+2.5 BHK): {half_txt!r} | pills={s_half['afPills']}", str(s_half))
            page.locator("#bhAfClearAll").click(); page.wait_for_timeout(250)

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.locator(".bhk-opt[data-bhk='2']").click()
            page.locator(".bhk-opt[data-bhk='shared']").click()
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            s_2sh = get_state_snap(page)
            check(not s_2sh["sum"].startswith("0 ") and "bhk:2" in s_2sh["afPills"] and "bhk:shared" in s_2sh["afPills"], f"COMBO-2 Union (2 BHK + Shared): {s_2sh['sum']!r}", str(s_2sh))
            page.locator("#bhAfClearAll").click(); page.wait_for_timeout(250)

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.select_option("#fZone", "Bandra-Santacruz")
            page.locator(".bhk-opt[data-bhk='2']").click()
            page.select_option("#fFurn", "furnished")
            page.select_option("#fSource", "nobroker")
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(350)
            s_4w = get_state_snap(page)
            nb_only_ok = page.evaluate("""() => {
                const cs = [...document.querySelectorAll("#cardList .fc")];
                return { n: cs.length, nb: cs.filter(c => /NoBroker/i.test(c.textContent || "")).length };
            }""")
            check(not s_4w["sum"].startswith("0 ") and nb_only_ok["n"] > 0 and nb_only_ok["nb"] == nb_only_ok["n"], f"COMBO-3 4-way (Bandra+2BHK+Furnished+NoBroker): {s_4w['sum']!r} ({nb_only_ok['nb']}/{nb_only_ok['n']} NoBroker)", str((s_4w, nb_only_ok)))
            page.locator("#bhAfClearAll").click(); page.wait_for_timeout(250)

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.evaluate("() => { const el = document.getElementById('mpMax'); if (el) { el.value = '4'; el.dispatchEvent(new Event('input')); } }")
            page.wait_for_timeout(200)
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(250)
            s_rlow = get_state_snap(page)
            page.locator("#modeBuy").click(); page.wait_for_timeout(600)
            s_breset = get_state_snap(page)
            check(s_rlow["sum"] != rent_home and "for sale" in s_breset["sum"] and not s_breset["sum"].startswith("0 "), f"COMBO-4 Rent low price cap -> switch to Buy resets price scale cleanly: rent={s_rlow['sum']!r} -> buy={s_breset['sum']!r}", str(s_breset))

            page.select_option("#v17Sort", "price_asc"); page.wait_for_timeout(450)
            bp_asc = parse_card_prices(page)[:12]
            b_asc_ok = len(bp_asc) >= 8 and all(bp_asc[i] <= bp_asc[i + 1] for i in range(len(bp_asc) - 1))
            check(b_asc_ok, f"SORT-3 Buy price_asc truly monotonic ascending ({bp_asc[:5]})", str(bp_asc))
            page.select_option("#v17Sort", "rec"); page.wait_for_timeout(300)

            buy_car = page.evaluate("""() => {
                const c = [...document.querySelectorAll("#cardList .fc")].find(x => Number(x.dataset.v66Total || 0) > 2);
                if (!c) return { ok: false, reason: "no_buy_multi_card" };
                const b1 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const nxt = c.querySelector(".fc-nav.next");
                if (!nxt) return { ok: false, reason: "no_nxt" };
                nxt.click();
                const b2 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const ds = document.getElementById("detailSheet");
                const drawerOpened = ds && getComputedStyle(ds).display !== "none";
                return { ok: b1.startsWith("1/") && b2.startsWith("2/") && !drawerOpened, b1, b2, drawerOpened };
            }""")
            check(bool(buy_car and buy_car.get("ok")), f"BUY-CAROUSEL: Next advances 1/N->2/N & does NOT accidentally open Detail Drawer: {buy_car}")

            page.locator("#modeRent").click(); page.wait_for_timeout(450)
            for _ in range(2):
                lm = page.locator("#loadMoreBtn")
                if lm.count() > 0:
                    lm.scroll_into_view_if_needed(); lm.click(); page.wait_for_timeout(450)
            post_lm_car = page.evaluate("""() => {
                const cs = [...document.querySelectorAll("#cardList .fc")];
                const c = cs.slice(36).find(x => Number(x.dataset.v66Total || 0) > 2);
                if (!c) return { ok: false, totalCards: cs.length, reason: "no_post_lm_multi" };
                const b1 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const nxt = c.querySelector(".fc-nav.next");
                if (!nxt) return { ok: false, totalCards: cs.length, reason: "no_nxt" };
                nxt.click();
                const b2 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                return { ok: cs.length >= 100 && b1.startsWith("1/") && b2.startsWith("2/"), totalCards: cs.length, b1, b2 };
            }""")
            check(bool(post_lm_car and post_lm_car.get("ok")), f"PAGINATION-CAROUSEL: 2x Load More ({post_lm_car.get('totalCards')} cards) & post-Load-More card #37+ carousel works: {post_lm_car}")

            vis_chips = page.evaluate("""() => {
                return [...document.querySelectorAll(".chip, #bhBrightBtn, .bh-vibe-chip")]
                    .filter(e => getComputedStyle(e).display !== "none" && e.offsetParent !== null)
                    .map((e, i) => ({ i, id: e.id, q: e.dataset.q || "", txt: (e.textContent || "").trim() }));
            }""")
            chip_bad = []
            for ch in vis_chips:
                sel = f"#{ch['id']}" if ch["id"] else (f".chip[data-q='{ch['q']}']" if ch["q"] else "")
                if not sel: continue
                el = page.locator(sel).first
                if el.count() == 0 or not el.is_visible(): continue
                el.click(); page.wait_for_timeout(250)
                s_on = get_state_snap(page)
                el.click(); page.wait_for_timeout(250)
                s_off = get_state_snap(page)
                if s_on["sum"] == rent_home or s_off["sum"] != rent_home:
                    chip_bad.append(f"{ch['txt']}({s_on['sum']}->{s_off['sum']})")
            check(len(chip_bad) == 0, f"QUICK-CHIPS: all {len(vis_chips)} visible quick chips toggle ON & OFF cleanly (bad={chip_bad})")

            log("\n--- 2C. MAP CLUSTERS, PRICE PILLS, DETAIL GALLERY, KEYBOARD & URL STATE ---")
            pin_res = page.evaluate("""() => ({ hasCluster: !!document.querySelector(".cluster-pill"), hasPin: !!document.querySelector(".price-pill") })""")
            if pin_res["hasCluster"]:
                page.locator(".cluster-pill").first.click(force=True); page.wait_for_timeout(500)
                cl_open = page.evaluate("() => { const cs = document.getElementById('clusterSheet'); return !!(cs && getComputedStyle(cs).display !== 'none'); }")
                if cl_open:
                    page.keyboard.press("Escape"); page.wait_for_timeout(250)
                check(True, f"MAP-CLUSTER click handled cleanly (clusterSheetOpened={cl_open}, no crash)")
            else:
                check(False, "MAP-CLUSTER no .cluster-pill rendered on map at zoom 11!")

            page.evaluate("() => { const m = window.__bh().map; if (m) m.setView([19.060, 72.830], 16, { animate: false }); }")
            page.wait_for_timeout(500)
            if page.locator(".price-pill").count() > 0:
                page.locator(".price-pill").first.click(force=True); page.wait_for_timeout(450)
                pp_ok = page.evaluate("""() => {
                    const mp = document.getElementById("mapPreview");
                    const ds = document.getElementById("detailSheet");
                    return (mp && getComputedStyle(mp).display !== "none") || (ds && getComputedStyle(ds).display !== "none");
                }""")
                page.keyboard.press("Escape"); page.wait_for_timeout(250)
                check(bool(pp_ok), f"MAP-PIN click at zoom 16 opens preview/detail & Esc closes cleanly: {pp_ok}")
            else:
                check(False, "MAP-PIN no individual .price-pill rendered in Bandra West at zoom 16!")

            multi_idx = page.evaluate("""() => [...document.querySelectorAll("#cardList .fc")].findIndex(c => Number(c.dataset.v66Total || 0) >= 4)""")
            if multi_idx >= 0:
                page.locator("#cardList .fc").nth(multi_idx).click(); page.wait_for_timeout(600)
                det_deep = page.evaluate("""() => {
                    const ds = document.getElementById("detailSheet");
                    if (!ds || getComputedStyle(ds).display === "none") return { ok: false, reason: "not_open" };
                    const cnt = ds.querySelector(".bh-dgal-cnt, .dgal-cnt, [class*='gal-cnt']");
                    const nxt = ds.querySelector(".bh-dgal-next, button[aria-label*='Next']");
                    const prv = ds.querySelector(".bh-dgal-prev, button[aria-label*='Prev']");
                    const c1 = cnt ? cnt.textContent.trim() : "";
                    if (nxt) nxt.click();
                    const c2 = cnt ? cnt.textContent.trim() : "";
                    if (prv) prv.click();
                    const c3 = cnt ? cnt.textContent.trim() : "";
                    const gm = [...ds.querySelectorAll("a")].find(a => /google\\.com\\/maps/i.test(a.href));
                    const wa = [...ds.querySelectorAll("a")].find(a => /wa\\.me|whatsapp/i.test(a.href));
                    const gmOk = !gm || (!/NaN/.test(gm.href) && gm.target === "_blank");
                    const waOk = !wa || (wa.href.length > 15 && wa.target === "_blank");
                    return { ok: gmOk && waOk && (!nxt || (c1 !== c2 && c1 === c3)), c1, c2, c3, gmOk, waOk };
                }""")
                page.keyboard.press("Escape"); page.wait_for_timeout(250)
                check(bool(det_deep and det_deep.get("ok")), f"DETAIL-DEEP gallery Next/Prev + Google Maps/WhatsApp links + Esc close: {det_deep}")
            else:
                check(False, "DETAIL-DEEP no 4+ photo card found on page!")

            for th_i in range(2):
                page.locator("#themeBtn").click(); page.wait_for_timeout(150)
                for mid in ("#msDark", "#msSat", "#msStreet"):
                    page.locator(mid).click(); page.wait_for_timeout(120)
                page.locator("#togMetro").click(); page.wait_for_timeout(100); page.locator("#togMetro").click()
                page.locator("#togFlood").click(); page.wait_for_timeout(100); page.locator("#togFlood").click()
            check(not get_state_snap(page)["overflow"], "MAP-THEME-OVERLAY 2x3x2 matrix (Light/Dark x Street/Dark/Sat x Metro/Flood) clean")

            page.locator("body").click(position={"x": 5, "y": 5}); page.wait_for_timeout(100)
            page.keyboard.press("/"); page.wait_for_timeout(150)
            focused_id = page.evaluate("() => document.activeElement?.id || ''")
            check(focused_id == "searchBox", f"KEYBOARD '/' focuses #searchBox (got={focused_id!r})")

            log("\n--- 2D. SHARE URL ROUND-TRIP, SHARED-BHK URL & MALFORMED URL FUZZING ---")
            page.locator("#modeBuy").click(); page.wait_for_timeout(500)
            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.select_option("#fLoc", "Powai")
            page.locator(".bhk-opt[data-bhk='2']").click()
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            page.select_option("#v17Sort", "price_asc"); page.wait_for_timeout(300)
            page.locator("#v17ShareBtn").click(); page.wait_for_timeout(300)
            shared_href = page.evaluate("() => location.href")
            orig_shared_sum = get_state_snap(page)["sum"]

            sp1 = ctx.new_page()
            sp1.goto(shared_href, wait_until="networkidle", timeout=45000)
            try: sp1.wait_for_function("() => { const t = document.getElementById('resSum')?.textContent || ''; return t.includes('for sale') && !t.startsWith('0 ') && !t.startsWith('7,'); }", timeout=15000)
            except Exception: pass
            sp1.wait_for_timeout(500)
            restored_snap = get_state_snap(sp1)
            sp1.close()
            check(restored_snap["mode"] == "buy" and restored_snap["sum"] == orig_shared_sum, f"SHARE-ROUNDTRIP ({shared_href.split('?')[-1]}): orig={orig_shared_sum!r} == restored={restored_snap['sum']!r}", str(restored_snap))

            sp2 = ctx.new_page()
            sep = "&" if "?" in target_url else "?"
            sp2.goto(target_url + sep + "bhk=shared", wait_until="networkidle", timeout=45000)
            sp2.wait_for_timeout(1400)
            sh_url_snap = get_state_snap(sp2)
            sp2.close()
            check("shared" in sh_url_snap["bhks"] and not sh_url_snap["sum"].startswith("0 ") and sh_url_snap["sum"] != rent_home, f"URL-SHARED (?bhk=shared) boots straight into Shared listings: {sh_url_snap['sum']!r}", str(sh_url_snap))

            sp3 = ctx.new_page()
            evil_errs = []
            sp3.on("pageerror", lambda e: evil_errs.append(str(e)[:120]))
            sp3.goto(target_url + sep + "mode=hacker&bhk=abc,-99,999&locs=AtlantisMars&sort=drop_table&open=does_not_exist", wait_until="networkidle", timeout=45000)
            sp3.wait_for_timeout(1200)
            evil_ok = len(evil_errs) == 0 and sp3.locator("#resSum").count() > 0
            sp3.close()
            check(evil_ok, f"URL-EVIL malformed params handled with 0 JS crashes (errs={evil_errs})")

            log("\n--- 2E. RESPONSIVE BREAKPOINT & BMC BUTTON NON-OVERLAP MATRIX ---")
            bp_fails = []
            for vw, vh, lbl in [(1440, 900, "Desktop"), (1280, 720, "Laptop"), (768, 1024, "Tablet"), (390, 844, "iPhone14"), (375, 667, "iPhoneSE"), (844, 390, "LandscapePhone"), (1440, 900, "DesktopReturn")]:
                page.set_viewport_size({"width": vw, "height": vh})
                page.wait_for_timeout(250)
                chk = page.evaluate("""() => {
                    const ov = document.documentElement.scrollWidth > window.innerWidth + 2;
                    const bmc = document.getElementById("bmcBtn");
                    const th = document.getElementById("themeBtn");
                    const br = bmc ? bmc.getBoundingClientRect() : null;
                    const tr = th ? th.getBoundingClientRect() : null;
                    const overlap = !!(br && tr && br.right > tr.left + 2 && br.left < tr.right - 2 && br.bottom > tr.top + 2 && br.top < tr.bottom - 2);
                    return { ov, bmcVis: !!(br && br.width > 12 && br.right <= window.innerWidth + 2), overlap };
                }""")
                if chk["ov"] or not chk["bmcVis"] or chk["overlap"]:
                    bp_fails.append(f"{lbl}({vw}x{vh}):{chk}")
            check(len(bp_fails) == 0, f"VIEWPORT-MATRIX all 7 sizes (incl 375px iPhone SE & 844x390 Landscape) 0 overflow/overlap (fails={bp_fails})")

            check(len(d_errs) == 0 and len(d_fail) == 0, f"DESKTOP-ERRORS 0 JS/network errors across entire chaos run (errs={d_errs[:3]}, fail={d_fail[:3]})")
            ctx.close()

            log("\n=== PART 3: MOBILE (390x844) FULL SPATIAL PERMUTATIONS, TOUCH CAROUSEL & MODE CHAOS ===")
            mctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            mp = mctx.new_page()
            m_errs, m_fail = [], []
            mp.on("pageerror", lambda e: m_errs.append(str(e)[:160]))
            mp.on("requestfailed", lambda req: None if ("ERR_ABORTED" in str(req.failure) and any(h in req.url for h in ("tile.openstreetmap.org", "arcgisonline.com"))) else m_fail.append(f"{req.url[:65]} ({req.failure})"))
            mp.goto(target_url, wait_until="networkidle", timeout=45000)
            mp.wait_for_timeout(1800)

            ms0 = get_state_snap(mp)
            m_home = ms0["sum"]

            mp.locator(".n-chip[data-nb='Thane']").scroll_into_view_if_needed()
            mp.locator(".n-chip[data-nb='Thane']").click(); mp.wait_for_timeout(300)
            draw_touch_lasso(mp, 19.065, 72.835, 13, 0.28)
            ms1 = get_state_snap(mp)
            check(ms1["hasLasso"] and ms1["fZone"] == "ALL" and not ms1["sum"].startswith("0 "), f"MOB-PERM1 Thane -> Touch Lasso Bandra (last wins!): {ms1['sum']!r}", str(ms1))

            mp.locator(".n-chip[data-nb='Powai-Central']").scroll_into_view_if_needed()
            mp.locator(".n-chip[data-nb='Powai-Central']").click(); mp.wait_for_timeout(300)
            ms2 = get_state_snap(mp)
            check((not ms2["hasLasso"]) and ms2["fZone"] == "Powai-Central" and not ms2["sum"].startswith("0 "), f"MOB-PERM2 Lasso -> Powai chip clears Lasso: {ms2['sum']!r}", str(ms2))

            msb = mp.locator("#searchBox")
            msb.fill("Worli"); msb.dispatch_event("input"); mp.wait_for_timeout(350)
            ms3 = get_state_snap(mp)
            check(ms3["fZone"] == "ALL" and not ms3["sum"].startswith("0 "), f"MOB-PERM3 Powai chip -> Search 'Worli' overrides zone: {ms3['sum']!r}", str(ms3))

            draw_touch_lasso(mp, 19.065, 72.835, 13, 0.28)
            ms4 = get_state_snap(mp)
            check(ms4["hasLasso"] and ms4["q"] == "" and not ms4["sum"].startswith("0 "), f"MOB-PERM4 Search 'Worli' -> Touch Lasso Bandra clears search: {ms4['sum']!r}", str(ms4))
            mp.locator("#mapLassoBtn").click(); mp.wait_for_timeout(300)

            draw_touch_lasso(mp, 18.960, 72.730, 13, 0.16)
            ms_sea = get_state_snap(mp)
            mp.locator("#mapLassoBtn").click(); mp.wait_for_timeout(300)
            ms_sea_r = get_state_snap(mp)
            check(ms_sea["sum"].startswith("0 ") and "(0)" in ms_sea["lassoTxt"] and ms_sea_r["sum"] == m_home, f"MOB-PERM5 Ocean Touch Lasso (0) + Clear recovers: {ms_sea['sum']!r} -> {ms_sea_r['sum']!r}", str(ms_sea))

            mp.locator("#v20MobToggle").first.click(); mp.wait_for_timeout(450)
            mob_car = mp.evaluate("""() => {
                const c = [...document.querySelectorAll("#cardList .fc")].find(x => Number(x.dataset.v66Total || 0) > 2);
                if (!c) return { ok: false, reason: "no_mob_multi" };
                const b1 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const nxt = c.querySelector(".fc-nav.next");
                if (!nxt) return { ok: false, reason: "no_nxt" };
                nxt.click();
                const b2 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const ds = document.getElementById("detailSheet");
                const opened = ds && getComputedStyle(ds).display !== "none";
                return { ok: b1.startsWith("1/") && b2.startsWith("2/") && !opened, b1, b2, opened };
            }""")
            check(bool(mob_car and mob_car.get("ok")), f"MOB-CAROUSEL: Next advances 1/N->2/N & does NOT open Detail Drawer: {mob_car}")

            mp.locator("#openFilterBtn").click(); mp.wait_for_timeout(250)
            mp.locator(".bhk-opt[data-bhk='shared']").click()
            mp.select_option("#fSource", "community")
            mp.locator("#applyFiltersBtn").click(); mp.wait_for_timeout(350)
            mp.locator("#modeBuy").click()
            mp.wait_for_function("() => (document.getElementById('resSum')?.textContent || '').includes('for sale') && !document.getElementById('resSum').textContent.startsWith('0 ')", timeout=25000)
            mp.wait_for_timeout(350)
            ms_buy = get_state_snap(mp)
            check("for sale" in ms_buy["sum"] and ms_buy["fSource"] == "ALL" and "shared" not in ms_buy["bhks"], f"MOB-CHAOS1 Rent(Shared+Flatmates) -> Buy auto-clears stale filters: {ms_buy['sum']!r}", str(ms_buy))

            mp.locator("#v20MobToggle").first.click(); mp.wait_for_timeout(450)
            draw_touch_lasso(mp, 19.118, 72.908, 13, 0.28)
            ms_bl = get_state_snap(mp)
            mp.locator("#mapLassoBtn").click(); mp.wait_for_timeout(300)
            check("for sale" in ms_bl["sum"] and not ms_bl["sum"].startswith("0 "), f"MOB-BUY-LASSO works in Buy mode on Mobile Map: {ms_bl['sum']!r}", str(ms_bl))

            mp.locator("#modeRent").click(); mp.wait_for_timeout(400)
            mp.evaluate("() => { const m = window.__bh().map; if (m) m.setView([19.060, 72.830], 16, { animate: false }); }")
            mp.wait_for_timeout(500)
            if mp.locator(".price-pill").count() > 0:
                mp.locator(".price-pill").first.click(force=True); mp.wait_for_timeout(400)
                m_pop = mp.evaluate("() => { const a = document.getElementById('mapPreview'), b = document.getElementById('detailSheet'); return (a && getComputedStyle(a).display !== 'none') || (b && getComputedStyle(b).display !== 'none'); }")
                mp.keyboard.press("Escape"); mp.wait_for_timeout(200)
                check(bool(m_pop), f"MOB-MAP-PIN tap at zoom 16 opens preview/detail cleanly: {m_pop}")
            else:
                check(False, "MOB-MAP-PIN no .price-pill visible in Bandra West at zoom 16!")

            check(len(m_errs) == 0 and len(m_fail) == 0, f"MOBILE-ERRORS 0 JS/network errors across entire mobile chaos run (errs={m_errs[:3]}, fail={m_fail[:3]})")
            mctx.close()
            browser.close()

        if live_mode:
            base_origin = target_url.split("?")[0].rstrip("/")
            log(f"\n=== PART 4: LIVE API MIXED-QUERY & EDGE-INPUT STRESS ({base_origin}) ===")
            qs = [
                ("rent", "2BHK in Bandra West under 85k zero brokerage"),
                ("buy", "3BHK in Powai under 3 Cr"),
                ("rent", "1BHK furnished in Andheri West under 45k"),
                ("rent", "shared room in Lower Parel under 20k"),
                ("rent", "5BHK in Colaba under 10k"),
            ]
            def _ask_one(item):
                m, q = item
                r = creq.post(base_origin + "/api/ask", json={"action": "parse", "currentMode": m, "query": q, "knownLocalities": ["Bandra West", "Powai", "Andheri West", "Lower Parel", "Colaba"]}, headers={"Origin": base_origin}, timeout=20)
                return r.status_code, (r.json() or {}).get("ok", False)
            with ThreadPoolExecutor(max_workers=5) as ex:
                mres = list(ex.map(_ask_one, qs))
            ok_cnt = sum(1 for sc, ok in mres if sc == 200 and ok)
            check(ok_cnt == len(qs), f"LIVE-MIXED-API 5 distinct concurrent /api/ask queries: {ok_cnt}/{len(qs)} HTTP 200+ok")

    except Exception as _err:
        log("  [CRASH] " + traceback.format_exc())
        failures.append(f"CRASH: {_err}")
    finally:
        if httpd: httpd.shutdown()

    log(f"\n=== PERMUTATION & CHAOS SUMMARY: {passed} PASSED, {len(failures)} FAILED ===")
    if failures:
        log("--- FAILURES LIST ---")
        for i, f in enumerate(failures, 1):
            log(f"  {i}. {f}")
    (ROOT / "bombayhomes_v68_permutations.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    return 0 if not failures else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    sys.exit(run_permutations(args.url or None, live_mode=args.live))
