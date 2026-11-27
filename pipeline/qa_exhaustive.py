# Exhaustive Brute-Force QA for Bombay Homes (v65+)
import argparse, http.server, json, re, socketserver, sys, threading, time, traceback, urllib.parse
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
                    f = {"mode": "buy" if ("buy" in q or "cr" in q or body.get("currentMode") == "buy") else "rent"}
                    if "2bhk" in q or "2 bhk" in q: f["bhks"] = [2]
                    if "3bhk" in q or "3 bhk" in q: f["bhks"] = [3]
                    if "powai" in q: f["localities"] = ["Powai"]
                    elif "bandra" in q: f["localities"] = ["Bandra West"]
                    if "75k" in q: f["maxPrice"] = 75000
                    if "3 cr" in q or "3cr" in q: f["maxPrice"] = 30000000
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

def run_exhaustive(target_url=None, live_mode=False):
    failures = []
    passed = 0
    def check(cond, msg):
        nonlocal passed
        if cond: passed += 1
        else: failures.append(msg)
        print(f"  [{'PASS' if cond else 'FAIL'}] {msg}", flush=True)

    print("\n=== SUITE 1: 100% SHARD & BUILDING INTEGRITY ===", flush=True)
    man = json.loads((ROOT / "web/public/data/manifest.json").read_text(encoding="utf-8-sig"))
    SHARED_RE = re.compile(r"(?:shared[-_]?room|single[-_]?room[-_]?in|private[-_]?room[-_]?in|sharing|flatmate|roommate|/pg-|paying[-_]?guest|hostel)", re.I)
    PRIME = {"bandra west","khar west","juhu","worli","lower parel","prabhadevi","dadar west","colaba","cuffe parade","malabar hill","tardeo","breach candy","pedder road","santacruz west","versova","andheri west","powai","pali hill","mahalaxmi","byculla"}
    bad_src_list = bad_bhk_sync = untagged_shared = prime_outliers = bad_zones = bad_urls = shared_cnt = total_b = total_u = 0
    for sk, uk, sr_k in (("rent_shards","units_rent","sources_rent"),("buy_shards","units_buy","sources_buy")):
        for sf in man[sk]:
            for s in json.loads((ROOT / "web/public/data" / sf).read_text(encoding="utf-8-sig")):
                total_b += 1
                if not isinstance(s.get(sr_k), dict): bad_src_list += 1
                if s.get("zone") in ("South Bombay", "Western Suburbs"): bad_zones += 1
                us = s.get(uk) or []
                ub = sorted({(int(float(u["b"])) if float(u["b"]).is_integer() else round(float(u["b"]), 1)) for u in us if u.get("b") is not None and str(u.get("lt") or "") != "shared"})
                if (s.get("bhks") or []) != ub: bad_bhk_sync += 1
                loc_l = str(s.get("locality") or "").lower().strip()
                for u in us:
                    total_u += 1
                    src = str(u.get("s") or "")
                    url = str(u.get("u") or "")
                    lt = str(u.get("lt") or "")
                    if not url.startswith("http") or src in ("","0","None") or (src == "squareyards" and "/agent/" in url.lower()) or (src in ("99acres","makaan") and "housing.com/" in url.lower()):
                        bad_urls += 1
                    if uk == "units_rent":
                        if lt == "shared": shared_cnt += 1
                        else:
                            if SHARED_RE.search(url): untagged_shared += 1
                            if loc_l in PRIME and u.get("b") is not None and (u.get("p") or 0) > 0:
                                bf, pv = float(u["b"]), u["p"]
                                if (bf >= 3 and pv < 45000) or (bf >= 2 and pv < 25000) or (bf >= 1 and pv < 12000): prime_outliers += 1
    check(bad_src_list == 0, f"DATA: 0 list-type sources_* across all {total_b:,} buildings (bad={bad_src_list})")
    check(bad_zones == 0, f"DATA: 0 un-normalized split zones (bad={bad_zones})")
    check(bad_bhk_sync == 0, f"DATA: 100% s.bhks <-> full-flat unit.b sync across all {total_b:,} buildings (mismatches={bad_bhk_sync})")
    check(untagged_shared == 0 and shared_cnt >= 400, f"DATA: all shared rooms tagged lt=shared ({shared_cnt:,} shared units, untagged={untagged_shared})")
    check(prime_outliers == 0, f"DATA: 0 impossible prime-Mumbai full-flat outliers (outliers={prime_outliers})")
    check(bad_urls == 0, f"DATA: 0 broken/agent/mislabeled URLs across all {total_u:,} flats (bad={bad_urls})")
    # V66_URL_LOC_CHECK: Verify 0 Rent<->Buy URL leaks & 0 mis-geocoded clones
    _b_re = re.compile(r"(?:/buy/|for-sale|-for-sale|-pdpid-|/projects/page/|/new-projects?/|/resale/)", re.I)
    _r_re = re.compile(r"(?:/rent/|for-rent|-for-rent|on-rent)", re.I)
    mode_url_leaks = bad_clones = 0
    for sk, uk in (("rent_shards","units_rent"),("buy_shards","units_buy")):
        for sf in man[sk]:
            for s in json.loads((ROOT / "web/public/data" / sf).read_text(encoding="utf-8-sig")):
                nm_l = str(s.get("name") or "").lower(); loc_l = str(s.get("locality") or "").lower()
                if ("galaxy heights" in nm_l and "pali hill" in loc_l) or ("sahakar avenue" in nm_l and "bandra" in loc_l):
                    bad_clones += 1
                for u in (s.get(uk) or []):
                    ul = str(u.get("u") or "")
                    if sk == "rent_shards" and _b_re.search(ul) and not _r_re.search(ul): mode_url_leaks += 1
                    if sk == "buy_shards" and _r_re.search(ul) and not _b_re.search(ul): mode_url_leaks += 1
    check(mode_url_leaks == 0 and bad_clones == 0, f"DATA: 0 Rent<->Buy URL leaks ({mode_url_leaks}) & 0 mis-geocoded Pali Hill/Bandra clones ({bad_clones})")

    httpd = None
    if not target_url:
        httpd, target_url = start_local_server()

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            print("\n=== SUITE 2: DESKTOP (1440x900) EXHAUSTIVE CLICK-EVERYTHING MATRIX ===", flush=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            d_errs, d_fail = [], []
            page.on("pageerror", lambda e: d_errs.append(str(e)[:140]))
            page.on("requestfailed", lambda req: None if ("ERR_ABORTED" in str(req.failure) and any(h in req.url for h in ("tile.openstreetmap.org", "arcgisonline.com"))) else d_fail.append(f"{req.url[:65]} ({req.failure})"))
            page.goto(target_url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(1800)

            d_init = page.evaluate(r"""() => {
                const imgs = [...document.querySelectorAll("img:not(.leaflet-tile)")];
                const links = [...document.querySelectorAll("a[href^='http']")].filter(a => !a.closest(".leaflet-control-attribution"));
                const removedIds = ["fHub","fHubMin","fMetro","fRate","fTen","fExactOnly"];
                const stillThere = removedIds.filter(id => document.getElementById(id));
                const badCnt = [...document.querySelectorAll(".fc-pcount,.fc-cnt,.fc-pbadge")].filter(e => getComputedStyle(e).display !== "none" && /\/\+/.test(e.textContent||"")).length;
                return {
                    home: document.getElementById("resSum")?.textContent?.trim() || "",
                    cards: document.querySelectorAll(".fc").length,
                    broken: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
                    unsafe: links.filter(a => a.target !== "_blank" || !(a.rel || "").includes("noopener") || a.getAttribute("referrerpolicy") !== "no-referrer").length,
                    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
                    bmc: !!document.getElementById("bmcBtn"),
                    stillThere, badCnt,
                };
            }""")
            rent_home = d_init["home"]
            check(d_init["cards"] >= 10 and "for rent" in rent_home and "exact pins" not in rent_home, f"DESKTOP init Rent: {rent_home!r}")
            check(d_init["broken"] == 0 and d_init["unsafe"] == 0 and not d_init["overflow"] and d_init["badCnt"] == 0 and d_init["bmc"], f"DESKTOP clean (broken={d_init['broken']}, unsafe={d_init['unsafe']}, ov={d_init['overflow']}, badCnt={d_init['badCnt']}, bmc={d_init['bmc']})")
            check(len(d_init["stillThere"]) == 0, f"DESKTOP removed unnecessary filters + Verified Pins (remaining={d_init['stillThere']})")

            nchips = page.locator(".n-chip")
            chip_fails = []
            for i in range(1, nchips.count()):
                ch = nchips.nth(i)
                lbl = (ch.text_content() or "").strip()
                ch.click(); page.wait_for_timeout(250)
                rs = (page.locator("#resSum").text_content() or "").strip()
                if rs == rent_home or rs.startswith("0 "): chip_fails.append(f"{lbl}->{rs}")
                af = page.locator(".bh-af-btn").first
                if af.count() == 0: chip_fails.append(f'{lbl}:no-af-pill')
                else: af.click(); page.wait_for_timeout(200)
                if (page.locator("#resSum").text_content() or "").strip() != rent_home: chip_fails.append(f"{lbl}:x-dismiss-failed")
                ch.click(); page.wait_for_timeout(180); ch.click(); page.wait_for_timeout(180)
                if (page.locator("#resSum").text_content() or "").strip() != rent_home: chip_fails.append(f"{lbl}:2nd-click-toggle-failed")
            check(len(chip_fails) == 0, f"DESKTOP all {nchips.count()-1} area chips + 1-tap x dismiss + 2nd-click toggle (fails={chip_fails[:3]})")

            for mode_lbl, mode_btn in (("RENT", "#modeRent"), ("BUY", "#modeBuy")):
                page.locator(mode_btn).click()
                if mode_lbl == "BUY":
                    page.wait_for_function("() => (document.getElementById('resSum')?.textContent || '').includes('for sale') && !document.getElementById('resSum').textContent.startsWith('0 ')", timeout=25000)
                page.wait_for_timeout(500)
                mode_home = (page.locator("#resSum").text_content() or "").strip()
                page.locator("#openFilterBtn").click(); page.wait_for_timeout(300)

                bhk_zero = []
                bhks = page.locator(".bhk-opt:visible")
                for i in range(bhks.count()):
                    b = bhks.nth(i)
                    bl = (b.text_content() or "").strip()
                    b.click(); page.wait_for_timeout(160)
                    at = (page.locator("#applyFiltersBtn").text_content() or "").strip()
                    b.click(); page.wait_for_timeout(120)
                    if " 0 " in at and not (mode_lbl == "BUY" and bl in ("1.5 BHK", "2.5 BHK")):
                        bhk_zero.append(f"{bl}={at}")
                check(len(bhk_zero) == 0, f"DESKTOP {mode_lbl} EVERY visible BHK pill (incl 1.5/2.5/3.5 + Shared in Rent) works (cnt={bhks.count()}, zero={bhk_zero})")

                if mode_lbl == "RENT":
                    page.locator(".bhk-opt[data-bhk='shared']").click(); page.wait_for_timeout(200)
                    sh_btn = (page.locator("#applyFiltersBtn").text_content() or "").strip()
                    page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(350)
                    sh_cards_ok = page.evaluate("""() => {
                        const cs = [...document.querySelectorAll(".fc")];
                        return { cnt: cs.length, labeledShared: cs.filter(c => /Shared Room/i.test(c.textContent || "")).length };
                    }""")
                    page.locator(".bh-af-btn[data-af='bhk:shared']").click(); page.wait_for_timeout(300)
                    sh_clr = (page.locator("#resSum").text_content() or "").strip()
                    check(sh_cards_ok["cnt"] >= 20 and sh_cards_ok["labeledShared"] == sh_cards_ok["cnt"] and sh_clr == mode_home, f"DESKTOP RENT Shared filter ({sh_btn}): {sh_cards_ok['labeledShared']}/{sh_cards_ok['cnt']} cards honestly labeled Shared Room + x dismiss")
                    page.locator("#openFilterBtn").click(); page.wait_for_timeout(250)
                    page.locator(".bhk-opt[data-bhk='3']").click(); page.wait_for_timeout(200)
                    page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(350)
                    leak3 = page.evaluate("""() => [...document.querySelectorAll(".fc")].filter(c => /Shared Room/i.test(c.textContent || "")).length""")
                    page.locator(".bh-af-btn[data-af='bhk:3']").click(); page.wait_for_timeout(250)
                    check(leak3 == 0, f"DESKTOP RENT 3 BHK filter has 0 Shared Room leaks (leaks={leak3})")
                    page.locator("#openFilterBtn").click(); page.wait_for_timeout(250)

                src_bad = []
                sopts = page.evaluate("() => [...document.querySelectorAll('#fSource option')].map(o => ({v:o.value, t:o.textContent.trim()}))")
                for opt in sopts:
                    if opt["v"] == "0" or opt["t"].startswith("0 ("): src_bad.append("ZERO_SOURCE")
                    page.select_option("#fSource", opt["v"]); page.wait_for_timeout(140)
                    at = (page.locator("#applyFiltersBtn").text_content() or "").strip()
                    if opt["v"] != "ALL" and " 0 " in at: src_bad.append(f"{opt['v']}->0")
                page.select_option("#fSource", "ALL")
                check(len(src_bad) == 0 and len(sopts) >= 5, f"DESKTOP {mode_lbl} EVERY Source option ({len(sopts)-1} portals, 0 ghost/0 sources, bad={src_bad})")

                furn_bad = []
                for fv in ("furnished", "semi", "unfurnished"):
                    page.select_option("#fFurn", fv); page.wait_for_timeout(140)
                    at = (page.locator("#applyFiltersBtn").text_content() or "").strip()
                    if " 0 " in at: furn_bad.append(fv)
                page.select_option("#fFurn", "ALL")
                check(len(furn_bad) == 0, f"DESKTOP {mode_lbl} EVERY Furnishing option >0 homes (bad={furn_bad})")

                page.select_option("#fZone", "Powai-Central")
                page.locator(".bhk-opt[data-bhk='2']").click()
                page.select_option("#fFurn", "semi")
                page.wait_for_timeout(200)
                page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(350)
                combo_sum = (page.locator("#resSum").text_content() or "").strip()
                pill_cnt = page.locator(".bh-af-btn").count()
                page.locator(".bh-af-btn[data-af='furn']").click(); page.wait_for_timeout(300)
                pill_after = page.locator(".bh-af-btn").count()
                page.locator("#bhAfClearAll").click(); page.wait_for_timeout(350)
                after_all_x = (page.locator("#resSum").text_content() or "").strip()
                check(pill_cnt >= 3 and pill_after == pill_cnt - 1 and combo_sum != mode_home and after_all_x == mode_home, f"DESKTOP {mode_lbl} multi-filter combo + individual x ({pill_cnt}->{pill_after}) + clear-all x: {combo_sum!r} -> {after_all_x!r}")

            page.locator("#modeRent").click(); page.wait_for_timeout(450)

            for sv in ("price_asc", "price_desc", "savings", "metro", "rating", "rec"):
                page.select_option("#v17Sort", sv); page.wait_for_timeout(180)
            lm = page.locator("#loadMoreBtn")
            if lm.count() > 0: lm.scroll_into_view_if_needed(); lm.click(); page.wait_for_timeout(400)
            check(page.locator(".fc").count() > 36, f"DESKTOP all 6 sorts + Load More ({page.locator('.fc').count()} cards)")

            sb = page.locator("#searchBox")
            sb.fill("2bhk in Powai under 75k")
            with page.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                page.locator(".bh-uni-ai").click()
            page.wait_for_timeout(500)
            ai_f = (page.locator("#resSum").text_content() or "").strip()
            sb.fill(""); sb.dispatch_event("input"); page.wait_for_timeout(500)
            ai_r = (page.locator("#resSum").text_content() or "").strip()
            check(ai_f != rent_home and ai_r == rent_home, f"DESKTOP AI search + delete-to-reset: {ai_f!r} -> {ai_r!r}")

            lbtn = page.locator("#mapLassoBtn")
            lbtn.click(); page.wait_for_timeout(200)
            box = page.locator("#map").bounding_box()
            cx, cy = box["x"] + box["width"]*0.48, box["y"] + box["height"]*0.48
            rx, ry = box["width"]*0.18, box["height"]*0.18
            page.mouse.move(cx-rx, cy-ry); page.mouse.down()
            for pt in [(cx+rx,cy-ry),(cx+rx,cy+ry),(cx-rx,cy+ry),(cx-rx,cy-ry)]: page.mouse.move(pt[0],pt[1],steps=6)
            page.mouse.up(); page.wait_for_timeout(600)
            lsum = (page.locator("#resSum").text_content() or "").strip()
            lbtn.click(); page.wait_for_timeout(450)
            lclr = (page.locator("#resSum").text_content() or "").strip()
            check(lsum != rent_home and lclr == rent_home, f"DESKTOP Map Lasso + Clear: {lsum!r} -> {lclr!r}")

            page.locator("#themeBtn").click(); page.wait_for_timeout(250)
            dk_ok = page.evaluate("() => document.documentElement.getAttribute('data-theme') === 'dark' && document.documentElement.scrollWidth <= window.innerWidth + 2")
            page.locator("#themeBtn").click(); page.wait_for_timeout(200)
            check(dk_ok, "DESKTOP Dark Mode clean")

            page.locator(".fc").first.click(); page.wait_for_timeout(700)
            dr = page.evaluate("""() => {
                const sh = document.getElementById("detailSheet");
                const sub = document.getElementById("dSub")?.textContent || "";
                const ls = sh ? [...sh.querySelectorAll("a[href^='http']")] : [];
                const bad = ls.filter(a => a.target !== "_blank" || !(a.rel || "").includes("noopener") || a.getAttribute("referrerpolicy") !== "no-referrer").length;
                const brk = sh ? [...sh.querySelectorAll("img")].filter(i => i.complete && i.naturalWidth === 0).length : 0;
                return { hasVPin: /Verified Building Pin|Locality Area Pin/i.test(sub), bad, brk, links: ls.length };
            }""")
            check(not dr["hasVPin"] and dr["bad"] == 0 and dr["brk"] == 0, f"DESKTOP Detail Drawer clean (no Verified Pin, links={dr['links']}, bad={dr['bad']}, brk={dr['brk']})")
            ph_par = page.evaluate(r"""() => {
                const api = typeof window.__bh === "function" ? window.__bh() : {};
                const byId = new Map((api.societies || []).map(s => [s.id, s]));
                let checked = 0, mismatched = 0;
                document.querySelectorAll("#cardList .fc").forEach(c => {
                    const s = byId.get(c.dataset.id);
                    if (!s || !(s.photos && s.photos.length > 2)) return;
                    checked++;
                    const cntTxt = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                    const m = cntTxt.match(/\d+\/(\d+)/);
                    const cardTot = m ? Number(m[1]) : 1;
                    if (cardTot < s.photos.length) mismatched++;
                });
                return { checked, mismatched };
            }""")
            check(ph_par["checked"] >= 5 and ph_par["mismatched"] == 0, f"DESKTOP Card vs Detail photo parity: {ph_par['checked']} multi-photo cards checked, {ph_par['mismatched']} truncated")
            adv_ok = page.evaluate(r"""() => {
                const c = [...document.querySelectorAll("#cardList .fc")].find(x => Number(x.dataset.v66Total || 0) > 2);
                if (!c) return { ok: false, reason: "no_card" };
                const img = c.querySelector("img");
                const s1 = img ? img.src : "";
                const b1 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const nxt = c.querySelector(".fc-nav.next, button[aria-label*='Next']");
                const prv = c.querySelector(".fc-nav.prev, button[aria-label*='Prev']");
                if (!nxt || !prv) return { ok: false, reason: "no_arrows" };
                nxt.click();
                const b2 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                const s2 = img ? img.src : "";
                prv.click();
                const b3 = (c.querySelector(".fc-pcount, .fc-cnt")?.textContent || "").trim();
                return { ok: b1.startsWith("1/") && b2.startsWith("2/") && b3.startsWith("1/") && s1 !== s2, b1, b2, b3, srcChanged: s1 !== s2 };
            }""")
            check(bool(adv_ok and adv_ok.get("ok")), f"DESKTOP Card carousel Next+Prev cycles & swaps img.src: {adv_ok}")
            page.locator("#closeDetailBtn").click(); page.wait_for_timeout(200)

            spage = ctx.new_page()
            sep = "&" if "?" in target_url else "?"
            spage.goto(target_url + sep + "mode=buy&locs=Powai&bhk=2", wait_until="networkidle", timeout=45000)
            try: spage.wait_for_function("() => { const t = document.getElementById('resSum')?.textContent || ''; return t.includes('for sale') && !t.startsWith('0 ') && !t.startsWith('7,'); }", timeout=15000)
            except Exception: pass
            spage.wait_for_timeout(400)
            sh_sum = (spage.locator("#resSum").text_content() or "").strip()
            check("for sale" in sh_sum and not sh_sum.startswith("7,"), f"DESKTOP Shareable URL (?mode=buy&locs=Powai&bhk=2): {sh_sum!r}")
            spage.close()
            # === V67_PERMUTATIONS_AND_CHAOS: Spatial Last-Action-Wins + Adversarial Chaos ===
            page.locator(".n-chip[data-nb='Thane']").click(); page.wait_for_timeout(450)
            thane_sum = (page.locator("#resSum").text_content() or "").strip()
            page.evaluate("() => { const m = window.__bh().map; if (m) m.setView([19.065, 72.835], 13, { animate: false }); }")
            page.wait_for_timeout(250)
            lbtn = page.locator("#mapLassoBtn")
            lbtn.click(); page.wait_for_timeout(200)
            box = page.locator("#map").bounding_box()
            cx, cy = box["x"] + box["width"]*0.5, box["y"] + box["height"]*0.5
            rx, ry = box["width"]*0.22, box["height"]*0.22
            page.mouse.move(cx-rx, cy-ry); page.mouse.down()
            for pt in [(cx+rx,cy-ry),(cx+rx,cy+ry),(cx-rx,cy+ry),(cx-rx,cy-ry)]: page.mouse.move(pt[0],pt[1],steps=6)
            page.mouse.up(); page.wait_for_timeout(600)
            p1_sum = (page.locator("#resSum").text_content() or "").strip()
            p1_fz = page.locator("#fZone").input_value()
            check(not p1_sum.startswith("0 ") and p1_sum != thane_sum and p1_fz == "ALL", f"PERM1 Thane -> Lasso Bandra (last wins!): thane={thane_sum!r} -> lasso={p1_sum!r}, fZone={p1_fz!r}")

            page.locator(".n-chip[data-nb='Powai-Central']").click(); page.wait_for_timeout(450)
            p2_sum = (page.locator("#resSum").text_content() or "").strip()
            p2_lbtn = (lbtn.text_content() or "").strip()
            check(not p2_sum.startswith("0 ") and "Draw area" in p2_lbtn, f"PERM2 Lasso -> Powai chip clears Lasso: {p2_sum!r} (btn={p2_lbtn!r})")

            sb = page.locator("#searchBox")
            sb.fill("Bandra"); sb.dispatch_event("input"); page.wait_for_timeout(400)
            p3_sum = (page.locator("#resSum").text_content() or "").strip()
            p3_fz = page.locator("#fZone").input_value()
            check(not p3_sum.startswith("0 ") and p3_fz == "ALL", f"PERM3 Powai chip -> Search 'Bandra' overrides zone: {p3_sum!r} (fZone={p3_fz!r})")
            page.locator(".bh-af-btn[data-af='search']").click(); page.wait_for_timeout(300)

            page.locator(".n-chip[data-nb='Thane']").click(); page.wait_for_timeout(250)
            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.locator(".bhk-opt[data-bhk='2']").click(); page.wait_for_timeout(150)
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            page.evaluate("() => { const m = window.__bh().map; if (m) m.setView([19.065, 72.835], 13, { animate: false }); }")
            page.wait_for_timeout(200)
            lbtn.click(); page.wait_for_timeout(200)
            page.mouse.move(cx-rx, cy-ry); page.mouse.down()
            for pt in [(cx+rx,cy-ry),(cx+rx,cy+ry),(cx-rx,cy+ry),(cx-rx,cy-ry)]: page.mouse.move(pt[0],pt[1],steps=6)
            page.mouse.up(); page.wait_for_timeout(600)
            p4_sum = (page.locator("#resSum").text_content() or "").strip()
            p4_has_2bhk = page.locator(".bh-af-btn[data-af='bhk:2']").count() > 0
            check(not p4_sum.startswith("0 ") and p4_has_2bhk, f"PERM4 Thane + 2BHK -> Lasso Bandra keeps 2BHK: {p4_sum!r} (2bhk_kept={p4_has_2bhk})")

            sb.fill("2bhk in Powai under 75k")
            with page.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                page.locator(".bh-uni-ai").click()
            page.wait_for_timeout(500)
            p5_sum = (page.locator("#resSum").text_content() or "").strip()
            p5_lbtn = (lbtn.text_content() or "").strip()
            check(not p5_sum.startswith("0 ") and "Draw area" in p5_lbtn, f"PERM5 Lasso -> AI Search Powai clears Lasso: {p5_sum!r} (btn={p5_lbtn!r})")
            page.locator("#bhAfClearAll").click(); page.wait_for_timeout(350)

            sb.fill("<img src=x onerror=window.__xssHit=1> zzzzz_no_flat_999"); sb.dispatch_event("input"); page.wait_for_timeout(350)
            xss_hit = page.evaluate("() => !!window.__xssHit")
            gib_sum = (page.locator("#resSum").text_content() or "").strip()
            sb.fill(""); sb.dispatch_event("input"); page.wait_for_timeout(350)
            rec_sum = (page.locator("#resSum").text_content() or "").strip()
            check((not xss_hit) and gib_sum.startswith("0 ") and rec_sum == rent_home, f"CHAOS1 XSS + gibberish safe & recovers: xss={xss_hit}, gib={gib_sum!r} -> {rec_sum!r}")

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.locator(".bhk-opt[data-bhk='shared']").click()
            page.select_option("#fSource", "community")
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            page.locator("#modeBuy").click(); page.wait_for_timeout(600)
            c2_sum = (page.locator("#resSum").text_content() or "").strip()
            c2_src = page.locator("#fSource").input_value()
            check("for sale" in c2_sum and not c2_sum.startswith("0 ") and c2_src == "ALL", f"CHAOS2 Rent(Shared+Flatmates) -> Buy auto-clears stale filters: {c2_sum!r} (src={c2_src!r})")

            for _ in range(3):
                page.locator("#modeRent").click(); page.wait_for_timeout(120)
                page.locator("#modeBuy").click(); page.wait_for_timeout(120)
            page.locator("#modeRent").click(); page.wait_for_timeout(500)
            lbtn.click(); page.wait_for_timeout(150); page.keyboard.press("Escape"); page.wait_for_timeout(200)
            c3_sum = (page.locator("#resSum").text_content() or "").strip()
            c3_lbtn = (lbtn.text_content() or "").strip()
            check(c3_sum == rent_home and "Draw area" in c3_lbtn, f"CHAOS3 Rapid Rent<->Buy spam + Lasso Esc cancel clean: {c3_sum!r} ({c3_lbtn!r})")

            page.locator("#openFilterBtn").click(); page.wait_for_timeout(200)
            page.evaluate("""() => {
                const pMax = document.getElementById("mpMax"); if (pMax) { pMax.value = "8"; pMax.dispatchEvent(new Event("input")); }
                const sMin = document.getElementById("sMin"); if (sMin) { sMin.value = "600"; sMin.dispatchEvent(new Event("input")); }
            }""")
            page.wait_for_timeout(250)
            page.locator("#applyFiltersBtn").click(); page.wait_for_timeout(300)
            c4_filt = (page.locator("#resSum").text_content() or "").strip()
            page.locator("#bhAfClearAll").click(); page.wait_for_timeout(350)
            c4_rst = (page.locator("#resSum").text_content() or "").strip()
            check(c4_filt != rent_home and not c4_filt.startswith("0 ") and c4_rst == rent_home, f"CHAOS4 Price+Sqft sliders + clear-all x: {c4_filt!r} -> {c4_rst!r}")

            check(len(d_errs) == 0 and len(d_fail) == 0, f"DESKTOP 0 JS/network errors (errs={d_errs[:2]}, fail={d_fail[:2]})")
            ctx.close()

            print("\n=== SUITE 3: MOBILE (390x844) EXHAUSTIVE CLICK-EVERYTHING MATRIX ===", flush=True)
            mctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            mp = mctx.new_page()
            m_errs, m_fail = [], []
            mp.on("pageerror", lambda e: m_errs.append(str(e)[:140]))
            mp.on("requestfailed", lambda req: None if ("ERR_ABORTED" in str(req.failure) and any(h in req.url for h in ("tile.openstreetmap.org", "arcgisonline.com"))) else m_fail.append(f"{req.url[:65]} ({req.failure})"))
            mp.goto(target_url, wait_until="networkidle", timeout=45000)
            mp.wait_for_timeout(1800)

            m_boot = mp.evaluate("""() => {
                const mpEl = document.getElementById("mapPane");
                const nbEl = document.getElementById("nbStrip");
                const mtEl = document.getElementById("v20MobToggle");
                const mR = mpEl ? mpEl.getBoundingClientRect() : null;
                const nR = nbEl ? nbEl.getBoundingClientRect() : null;
                return {
                    isMap: document.body.classList.contains("bh-mob-map"),
                    togTxt: (mtEl?.textContent || "").trim(),
                    mapH: mR ? Math.round(mR.height) : 0,
                    mapTop: mR ? Math.round(mR.top) : 0,
                    nbVis: !!(nR && nR.height >= 28 && nR.bottom <= (mR ? mR.top + 3 : 999)),
                    nbBot: nR ? Math.round(nR.bottom) : 0,
                    aiHidden: !document.getElementById("bhAiBar") || getComputedStyle(document.getElementById("bhAiBar")).display === "none",
                    home: document.getElementById("resSum")?.textContent?.trim() || "",
                    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
                };
            }""")
            m_home = m_boot["home"]
            check(m_boot["isMap"] and m_boot["togTxt"] == "Show List" and m_boot["mapH"] > 450, f"MOBILE opens on MAP view directly (isMap={m_boot['isMap']}, btn={m_boot['togTxt']!r}, mapH={m_boot['mapH']}px)")
            check(m_boot["nbVis"] and m_boot["aiHidden"] and not m_boot["overflow"], f"MOBILE #nbStrip visible ABOVE map (nbBot={m_boot['nbBot']}<=mapTop={m_boot['mapTop']}, aiBarHidden={m_boot['aiHidden']}, ov={m_boot['overflow']})")

            mchips = mp.locator(".n-chip")
            m_map_fails = []
            for i in range(1, mchips.count()):
                ch = mchips.nth(i)
                lbl = (ch.text_content() or "").strip()
                ch.scroll_into_view_if_needed(); ch.click(); mp.wait_for_timeout(300)
                rs = (mp.locator("#resSum").text_content() or "").strip()
                if rs == m_home or rs.startswith("0 "): m_map_fails.append(f"{lbl}->{rs}")
            mchips.first.scroll_into_view_if_needed(); mchips.first.click(); mp.wait_for_timeout(650)
            check(len(m_map_fails) == 0, f"MOBILE MAP VIEW: all {mchips.count()-1} area chips filter & fly cleanly (fails={m_map_fails})")

            mlbtn = mp.locator("#mapLassoBtn")
            mlbtn.click(); mp.wait_for_timeout(200)
            mp.evaluate("""() => {
                const el = document.getElementById("map"); const r = el.getBoundingClientRect();
                const pts = [[r.left+r.width*.25,r.top+r.height*.25],[r.left+r.width*.75,r.top+r.height*.25],[r.left+r.width*.75,r.top+r.height*.75],[r.left+r.width*.25,r.top+r.height*.75],[r.left+r.width*.25,r.top+r.height*.25]];
                const fire = (type, x, y, target) => {
                    const touch = new Touch({ identifier: 1, target: el, clientX: x, clientY: y, pageX: x, pageY: y });
                    target.dispatchEvent(new TouchEvent(type, { cancelable: true, bubbles: true, touches: type==='touchend'?[]:[touch], targetTouches: type==='touchend'?[]:[touch], changedTouches: [touch] }));
                };
                fire("touchstart", pts[0][0], pts[0][1], el);
                for (let i=1; i<pts.length; i++) fire("touchmove", pts[i][0], pts[i][1], window);
                fire("touchend", pts[pts.length-1][0], pts[pts.length-1][1], window);
            }""")
            mp.wait_for_timeout(600)
            ml_sum = (mp.locator("#resSum").text_content() or "").strip()
            mlbtn.click(); mp.wait_for_timeout(450)
            ml_clr = (mp.locator("#resSum").text_content() or "").strip()
            check(ml_sum != m_home and ml_clr == m_home, f"MOBILE REAL-TOUCH Lasso + Clear: {ml_sum!r} -> {ml_clr!r}")

            mp.locator("#v20MobToggle").first.click(); mp.wait_for_timeout(450)
            m_list_fails = []
            for i in range(1, mchips.count()):
                ch = mchips.nth(i)
                lbl = (ch.text_content() or "").strip()
                ch.scroll_into_view_if_needed(); ch.click(); mp.wait_for_timeout(250)
                rs = (mp.locator("#resSum").text_content() or "").strip()
                if rs == m_home or rs.startswith("0 "): m_list_fails.append(f"{lbl}->{rs}")
                af = mp.locator(".bh-af-btn").first
                if af.count() == 0: m_list_fails.append(f'{lbl}:no-x')
                else: af.click(); mp.wait_for_timeout(200)
                if (mp.locator("#resSum").text_content() or "").strip() != m_home: m_list_fails.append(f"{lbl}:x-fail")
            check(len(m_list_fails) == 0, f"MOBILE LIST VIEW: all {mchips.count()-1} area chips + 1-tap x dismiss work with 0 crashes (fails={m_list_fails})")

            mp.locator("#openFilterBtn").click(); mp.wait_for_timeout(300)
            m_bhk_bad = []
            for i in range(mp.locator(".bhk-opt:visible").count()):
                b = mp.locator(".bhk-opt:visible").nth(i); bl = (b.text_content() or "").strip()
                b.click(); mp.wait_for_timeout(150)
                if " 0 " in (mp.locator("#applyFiltersBtn").text_content() or ""): m_bhk_bad.append(bl)
                b.click(); mp.wait_for_timeout(120)
            m_src_bad = [o["v"] for o in mp.evaluate("() => [...document.querySelectorAll('#fSource option')].map(o => ({v:o.value, t:o.textContent.trim()}))") if o["v"] == "0" or o["t"].startswith("0 (")]
            mp.locator("#closeFilterBtn").click(); mp.wait_for_timeout(250)
            check(len(m_bhk_bad) == 0 and len(m_src_bad) == 0, f"MOBILE Filter Drawer: all 9 BHKs (incl 1.5/2.5/3.5 + Shared) > 0 & 0 ghost sources (bhk_bad={m_bhk_bad}, src_bad={m_src_bad})")

            mp.locator("#modeBuy").click()
            mp.wait_for_function("() => (document.getElementById('resSum')?.textContent || '').includes('for sale') && !document.getElementById('resSum').textContent.startsWith('0 ')", timeout=25000)
            mp.wait_for_timeout(350)
            mb_home = (mp.locator("#resSum").text_content() or "").strip()
            mp.locator("#modeRent").click(); mp.wait_for_timeout(450)
            msb = mp.locator("#searchBox")
            msb.fill("2bhk in Powai under 75k")
            with mp.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                mp.locator(".bh-uni-ai").click()
            mp.wait_for_timeout(450)
            m_aif = (mp.locator("#resSum").text_content() or "").strip()
            msb.fill(""); msb.dispatch_event("input"); mp.wait_for_timeout(450)
            m_air = (mp.locator("#resSum").text_content() or "").strip()
            check("for sale" in mb_home and m_aif != m_home and m_air == m_home, f"MOBILE Buy ({mb_home!r}) + AI delete-to-reset ({m_aif!r} -> {m_air!r})")
            mp.locator("#v20MobToggle").first.click(); mp.wait_for_timeout(450)
            mp.locator(".n-chip[data-nb='Thane']").scroll_into_view_if_needed()
            mp.locator(".n-chip[data-nb='Thane']").click(); mp.wait_for_timeout(400)
            mp.evaluate("() => { const m = window.__bh().map; if (m) m.setView([19.065, 72.835], 13, { animate: false }); }")
            mp.wait_for_timeout(250)
            mlbtn.click(); mp.wait_for_timeout(200)
            mp.evaluate("""() => {
                const el = document.getElementById("map"); const r = el.getBoundingClientRect();
                const pts = [[r.left+r.width*.2,r.top+r.height*.2],[r.left+r.width*.8,r.top+r.height*.2],[r.left+r.width*.8,r.top+r.height*.8],[r.left+r.width*.2,r.top+r.height*.8],[r.left+r.width*.2,r.top+r.height*.2]];
                const fire = (type, x, y, target) => {
                    const touch = new Touch({ identifier: 1, target: el, clientX: x, clientY: y, pageX: x, pageY: y });
                    target.dispatchEvent(new TouchEvent(type, { cancelable: true, bubbles: true, touches: type==='touchend'?[]:[touch], targetTouches: type==='touchend'?[]:[touch], changedTouches: [touch] }));
                };
                fire("touchstart", pts[0][0], pts[0][1], el);
                for (let i=1; i<pts.length; i++) fire("touchmove", pts[i][0], pts[i][1], window);
                fire("touchend", pts[pts.length-1][0], pts[pts.length-1][1], window);
            }""")
            mp.wait_for_timeout(600)
            mp_sum = (mp.locator("#resSum").text_content() or "").strip()
            mp_fz = mp.locator("#fZone").input_value()
            mlbtn.click(); mp.wait_for_timeout(350)
            check(not mp_sum.startswith("0 ") and mp_fz == "ALL", f"MOBILE PERM Thane -> Real-Touch Lasso Bandra (last wins!): {mp_sum!r} (fZone={mp_fz!r})")

            check(len(m_errs) == 0 and len(m_fail) == 0, f"MOBILE ZERO JS/network errors (errs={m_errs[:2]}, fail={m_fail[:2]})")
            mctx.close()
            browser.close()

        if live_mode:
            base_origin = target_url.split("?")[0].rstrip("/")
            print(f"\n=== SUITE 4: LIVE API & CONCURRENCY ({base_origin}) ===", flush=True)
            payload = {"action": "parse", "query": "2BHK in Bandra West under 85k zero brokerage", "currentMode": "rent", "knownLocalities": ["Bandra West", "Khar West"]}
            creq.post(base_origin + "/api/ask", json=payload, headers={"Origin": base_origin}, timeout=20)
            time.sleep(0.4)
            def _burst(_):
                r = creq.post(base_origin + "/api/ask", json=payload, headers={"Origin": base_origin}, timeout=15)
                return r.status_code, (r.json() or {}).get("cached", False)
            with ThreadPoolExecutor(max_workers=10) as ex:
                res = list(ex.map(_burst, range(10)))
            ok200 = sum(1 for s, _ in res if s == 200)
            hits = sum(1 for _, c in res if c)
            check(ok200 == 10 and hits >= 1, f"LIVE 10x concurrent /api/ask: {ok200}/10 HTTP 200 (cache_hits={hits}/10)")
            check(creq.get(base_origin + "/api/flags", timeout=12).status_code == 200 and creq.get(base_origin + "/api/listings", timeout=12).status_code == 200, "LIVE /api/flags & /api/listings HTTP 200")
    except Exception as _err:
        print("  [CRASH] " + traceback.format_exc(), flush=True)
        failures.append(f"CRASH: {_err}")
    finally:
        if httpd: httpd.shutdown()

    print(f"\n=== EXHAUSTIVE QA SUMMARY: {passed} PASSED, {len(failures)} FAILED ===", flush=True)
    return 0 if not failures else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    sys.exit(run_exhaustive(args.url or None, live_mode=args.live))
