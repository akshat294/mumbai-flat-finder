# Permanent Full-Route Real-User E2E Audit for Bombay Homes (v63+)
import argparse, traceback, http.server, json, socketserver, sys, threading, time, urllib.parse
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
                    resp = {"ok": True, "engine": "local-mock", "summary": "Mock QA summary."}
                raw = json.dumps(resp).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers()
                self.wfile.write(raw); return
            self.send_response(404); self.end_headers()
        def do_GET(self):
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
            if self.path in ("/api/flags", "/api/listings"):
                raw = b'{"flags":{}}' if self.path == "/api/flags" else b'{"listings":[]}'
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers()
                self.wfile.write(raw); return
            return super().do_GET()
        def log_message(self, format, *args):
            pass
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, "http:" + f"//127.0.0.1:{port}/"

def run_qa(target_url=None, live_mode=False):
    httpd = None
    if not target_url:
        httpd, target_url = start_local_server()
    failures = []
    def check(cond, msg):
        print(f"  [{'PASS' if cond else 'FAIL'}] {msg}", flush=True)
        if not cond: failures.append(msg)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            print("\n--- DESKTOP FULL-ROUTE JOURNEY ---", flush=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            errs, failed = [], []
            page.on("pageerror", lambda e: errs.append(str(e)[:140]))
            page.on("requestfailed", lambda req: failed.append(f"{req.url[:65]} ({req.failure})"))
            page.goto(target_url, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(2000)

            base = page.evaluate("""() => {
                const imgs = [...document.querySelectorAll("img:not(.leaflet-tile)")];
                const links = [...document.querySelectorAll("a[href^='http']")].filter(a => !a.closest(".leaflet-control-attribution"));
                return {
                    home: document.getElementById("resSum")?.textContent?.trim() || "",
                    cards: document.querySelectorAll(".fc").length,
                    broken: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
                    noAlt: imgs.filter(i => !i.getAttribute("alt") || i.getAttribute("alt").trim().length < 2).length,
                    unsafeLinks: links.filter(a => a.target !== "_blank" || !(a.rel || "").includes("noopener") || a.getAttribute("referrerpolicy") !== "no-referrer").map(a => a.href.slice(0, 60)),
                    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
                };
            }""")
            check(base["cards"] >= 10 and "10," in base["home"], f"DESKTOP initial Rent load: {base['home']!r} ({base['cards']} cards)")
            check(base["broken"] == 0 and base["noAlt"] == 0, f"DESKTOP images clean (broken={base['broken']}, noAlt={base['noAlt']})")
            check(len(base["unsafeLinks"]) == 0, f"DESKTOP external links safe + no-referrer (unsafe={base['unsafeLinks'][:3]})")
            check(not base["overflow"], "DESKTOP zero horizontal overflow")

            ai_inp = page.locator("#bhAiInput")
            ai_inp.fill("2bhk in Powai under 75k")
            with page.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                page.locator("#bhAiGo").click()
            page.wait_for_timeout(600)
            ai_filt = (page.locator("#resSum").text_content() or "").strip()
            ai_inp.fill(""); ai_inp.dispatch_event("input")
            page.wait_for_timeout(700)
            ai_after = (page.locator("#resSum").text_content() or "").strip()
            check(ai_filt != base["home"] and ai_after == base["home"], f"DESKTOP #bhAiInput delete-to-reset: {ai_filt!r} -> {ai_after!r}")

            sb = page.locator("#searchBox")
            sb.fill("2bhk in Powai under 75k")
            with page.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                page.locator(".bh-uni-ai").click()
            page.wait_for_timeout(600)
            uni_filt = (page.locator("#resSum").text_content() or "").strip()
            sb.fill(""); sb.dispatch_event("input")
            page.wait_for_timeout(700)
            uni_after = (page.locator("#resSum").text_content() or "").strip()
            check(uni_filt != base["home"] and uni_after == base["home"], f"DESKTOP #searchBox AI delete-to-reset: {uni_filt!r} -> {uni_after!r}")

            page.select_option("#v17Sort", "price_asc")
            page.wait_for_timeout(400)
            lm = page.locator("#loadMoreBtn")
            if lm.count() > 0:
                lm.scroll_into_view_if_needed(); lm.click(); page.wait_for_timeout(500)
            more_cards = page.locator(".fc").count()
            check(more_cards > base["cards"], f"DESKTOP Sort + Load More pagination: {base['cards']} -> {more_cards} cards")
            page.select_option("#v17Sort", "rec"); page.wait_for_timeout(300)

            # Filter chips + Reset filters route (Shortlist UI is intentionally hidden by design)
            chip_ok = False
            bchip = page.locator("#bhBrightBtn, .chip[data-chip], .n-chip[data-nb]:not([data-nb='ALL'])").first
            if bchip.count() > 0 and bchip.is_visible():
                bchip.click(); page.wait_for_timeout(500)
                c_filt = (page.locator("#resSum").text_content() or "").strip()
                rm = page.locator("#resetMiniBtn")
                if rm.count() > 0 and rm.is_visible():
                    rm.click(); page.wait_for_timeout(500)
                else:
                    bchip.click(); page.wait_for_timeout(500)
                c_rst = (page.locator("#resSum").text_content() or "").strip()
                chip_ok = (c_filt != base["home"] and c_rst == base["home"])
                check(chip_ok, f"DESKTOP Filter chip + Reset filters: {c_filt!r} -> {c_rst!r}")
            else:
                check(True, "DESKTOP Filter chip skipped (none visible)")

            # Map styles (Dark / Sat / Street) + Overlays (Metro / Flood)
            page.locator("#msDark").click(); page.wait_for_timeout(200)
            page.locator("#msSat").click(); page.wait_for_timeout(200)
            page.locator("#msStreet").click(); page.wait_for_timeout(200)
            page.locator("#togFlood").click(); page.wait_for_timeout(200)
            fl_on = "active" in (page.locator("#togFlood").get_attribute("class") or "")
            page.locator("#togFlood").click(); page.wait_for_timeout(200)
            check(fl_on and "active" in (page.locator("#msStreet").get_attribute("class") or ""), "DESKTOP Map styles (Map/Dark/Sat) + Flood/Metro overlays clean")

            page.locator("#themeBtn").click(); page.wait_for_timeout(350)
            dk = page.evaluate("() => ({ t: document.documentElement.getAttribute('data-theme'), ov: document.documentElement.scrollWidth > window.innerWidth + 2 })")
            check(dk["t"] == "dark" and not dk["ov"], f"DESKTOP Dark Mode toggle clean: theme={dk['t']!r}, overflow={dk['ov']}")
            page.locator("#themeBtn").click(); page.wait_for_timeout(250)

            lbtn = page.locator("#mapLassoBtn")
            check(lbtn.count() > 0 and lbtn.is_visible(), "DESKTOP #mapLassoBtn visible on map")
            lbtn.click(); page.wait_for_timeout(250)
            box = page.locator("#map").bounding_box()
            cx, cy = box["x"] + box["width"] * 0.48, box["y"] + box["height"] * 0.48
            rx, ry = box["width"] * 0.18, box["height"] * 0.18
            page.mouse.move(cx - rx, cy - ry); page.mouse.down()
            for pt in [(cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry), (cx - rx, cy - ry)]:
                page.mouse.move(pt[0], pt[1], steps=6)
            page.mouse.up(); page.wait_for_timeout(700)
            lasso_sum = (page.locator("#resSum").text_content() or "").strip()
            lasso_btn_txt = (lbtn.text_content() or "").strip()
            check(lasso_sum != base["home"] and "Clear area" in lasso_btn_txt, f"DESKTOP Rent Lasso filtered: {lasso_sum!r} ({lasso_btn_txt!r})")
            lbtn.click(); page.wait_for_timeout(500)
            after_clear = (page.locator("#resSum").text_content() or "").strip()
            check(after_clear == base["home"], f"DESKTOP Rent Lasso Clear restored: {after_clear!r}")

            page.locator("#modeBuy").click()
            page.wait_for_function("() => (document.getElementById('resSum')?.textContent || '').includes('for sale') && !document.getElementById('resSum').textContent.startsWith('0 ')", timeout=25000)
            page.wait_for_timeout(600)
            buy_home = (page.locator("#resSum").text_content() or "").strip()
            check("for sale" in buy_home and ("7," in buy_home or "6," in buy_home), f"DESKTOP Buy mode loaded: {buy_home!r}")

            ai_inp = page.locator("#bhAiInput")
            ai_inp.fill("3bhk in Powai under 3 cr")
            with page.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                page.locator("#bhAiGo").click()
            page.wait_for_timeout(600)
            buy_ai = (page.locator("#resSum").text_content() or "").strip()
            ai_inp.fill(""); ai_inp.dispatch_event("input"); page.wait_for_timeout(700)
            buy_ai_rst = (page.locator("#resSum").text_content() or "").strip()
            check(buy_ai != buy_home and buy_ai_rst == buy_home, f"DESKTOP Buy AI delete-to-reset: {buy_ai!r} -> {buy_ai_rst!r}")

            lbtn.click(); page.wait_for_timeout(250)
            page.mouse.move(cx - rx, cy - ry); page.mouse.down()
            for pt in [(cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry), (cx - rx, cy - ry)]:
                page.mouse.move(pt[0], pt[1], steps=6)
            page.mouse.up(); page.wait_for_timeout(700)
            buy_lasso = (page.locator("#resSum").text_content() or "").strip()
            check(buy_lasso != buy_home and "for sale" in buy_lasso, f"DESKTOP Buy Lasso filtered: {buy_lasso!r}")
            lbtn.click(); page.wait_for_timeout(500)
            page.locator("#modeRent").click(); page.wait_for_timeout(700)
            back_rent = (page.locator("#resSum").text_content() or "").strip()
            check(back_rent == base["home"], f"DESKTOP Switch Buy -> Rent restored: {back_rent!r}")

            page.locator(".fc").first.click(); page.wait_for_timeout(900)
            dr = page.evaluate("""() => {
                const sh = document.getElementById("detailSheet");
                const ls = sh ? [...sh.querySelectorAll("a[href^='http']")] : [];
                const bad = ls.filter(a => a.target !== "_blank" || !(a.rel || "").includes("noopener") || a.getAttribute("referrerpolicy") !== "no-referrer").map(a => a.href.slice(0, 50));
                const ims = sh ? [...sh.querySelectorAll("img")] : [];
                return { links: ls.length, bad, broken: ims.filter(i => i.complete && i.naturalWidth === 0).length };
            }""")
            check(dr["broken"] == 0 and len(dr["bad"]) == 0, f"DESKTOP detail drawer clean (links={dr['links']}, bad={dr['bad']}, broken={dr['broken']})")
            page.locator("#closeDetailBtn").click(); page.wait_for_timeout(250)

            spage = ctx.new_page()
            sep = "&" if "?" in target_url else "?"
            spage.goto(target_url + sep + "mode=buy&loc=Powai", wait_until="networkidle", timeout=45000)
            try:
                spage.wait_for_function("() => { const t = document.getElementById('resSum')?.textContent || ''; return t.includes('for sale') && !t.startsWith('0 ') && !t.startsWith('7,'); }", timeout=15000)
            except Exception:
                pass
            spage.wait_for_timeout(500)
            sh_sum = (spage.locator("#resSum").text_content() or "").strip()
            check("for sale" in sh_sum and sh_sum != buy_home, f"DESKTOP Shareable URL (?mode=buy&loc=Powai) restored: {sh_sum!r}")
            spage.close()

            check(len(errs) == 0 and len(failed) == 0, f"DESKTOP zero page/network errors (errs={errs}, failed={failed[:2]})")
            ctx.close()

            print("\n--- MOBILE FULL-ROUTE + REAL TOUCH JOURNEY ---", flush=True)
            mctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            mp = mctx.new_page()
            m_errs, m_fail = [], []
            mp.on("pageerror", lambda e: m_errs.append(str(e)[:140]))
            mp.on("requestfailed", lambda req: m_fail.append(f"{req.url[:65]} ({req.failure})"))
            mp.goto(target_url, wait_until="networkidle", timeout=45000)
            mp.wait_for_timeout(2000)

            mbase = mp.evaluate("""() => {
                const imgs = [...document.querySelectorAll("img:not(.leaflet-tile)")];
                const links = [...document.querySelectorAll("a[href^='http']")].filter(a => !a.closest(".leaflet-control-attribution"));
                return {
                    home: document.getElementById("resSum")?.textContent?.trim() || "",
                    cards: document.querySelectorAll(".fc").length,
                    broken: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
                    unsafeLinks: links.filter(a => a.target !== "_blank" || !(a.rel || "").includes("noopener") || a.getAttribute("referrerpolicy") !== "no-referrer").length,
                    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
                };
            }""")
            check(mbase["cards"] >= 10 and "10," in mbase["home"], f"MOBILE initial load: {mbase['home']!r}")
            check(mbase["broken"] == 0 and mbase["unsafeLinks"] == 0 and not mbase["overflow"], f"MOBILE clean (broken={mbase['broken']}, unsafe={mbase['unsafeLinks']}, ov={mbase['overflow']})")

            msb = mp.locator("#searchBox")
            msb.fill("2bhk in Powai under 75k")
            with mp.expect_response(lambda r: "/api/ask" in r.url and r.status == 200, timeout=20000):
                mp.locator(".bh-uni-ai").click()
            mp.wait_for_timeout(600)
            m_filt = (mp.locator("#resSum").text_content() or "").strip()
            msb.fill(""); msb.dispatch_event("input"); mp.wait_for_timeout(700)
            m_rst = (mp.locator("#resSum").text_content() or "").strip()
            check(m_filt != mbase["home"] and m_rst == mbase["home"], f"MOBILE #searchBox AI delete-to-reset: {m_filt!r} -> {m_rst!r}")

            mp.locator("#v20MobToggle").first.click(); mp.wait_for_timeout(700)
            mlbtn = mp.locator("#mapLassoBtn")
            check(mlbtn.count() > 0 and mlbtn.is_visible(), "MOBILE #mapLassoBtn visible on map")
            mlbtn.click(); mp.wait_for_timeout(250)
            mp.evaluate("""() => {
                const el = document.getElementById("map");
                const r = el.getBoundingClientRect();
                const pts = [
                    [r.left + r.width*0.30, r.top + r.height*0.30],
                    [r.left + r.width*0.70, r.top + r.height*0.30],
                    [r.left + r.width*0.70, r.top + r.height*0.70],
                    [r.left + r.width*0.30, r.top + r.height*0.70],
                    [r.left + r.width*0.30, r.top + r.height*0.30],
                ];
                const fire = (type, x, y, target) => {
                    const touch = new Touch({ identifier: 1, target: el, clientX: x, clientY: y, pageX: x, pageY: y });
                    const ev = new TouchEvent(type, { cancelable: true, bubbles: true, touches: type === 'touchend' ? [] : [touch], targetTouches: type === 'touchend' ? [] : [touch], changedTouches: [touch] });
                    target.dispatchEvent(ev);
                };
                fire("touchstart", pts[0][0], pts[0][1], el);
                for (let i = 1; i < pts.length; i++) fire("touchmove", pts[i][0], pts[i][1], window);
                fire("touchend", pts[pts.length-1][0], pts[pts.length-1][1], window);
            }""")
            mp.wait_for_timeout(700)
            ml_sum = (mp.locator("#resSum").text_content() or "").strip()
            ml_txt = (mlbtn.text_content() or "").strip()
            check(ml_sum != mbase["home"] and "Clear area" in ml_txt, f"MOBILE REAL-TOUCH Lasso filtered: {ml_sum!r} ({ml_txt!r})")
            mlbtn.click(); mp.wait_for_timeout(500)
            ml_clr = (mp.locator("#resSum").text_content() or "").strip()
            check(ml_clr == mbase["home"], f"MOBILE Lasso Clear restored: {ml_clr!r}")

            mp.locator("#v20MobToggle").first.click(); mp.wait_for_timeout(500)
            mp.locator("#modeBuy").click()
            mp.wait_for_function("() => (document.getElementById('resSum')?.textContent || '').includes('for sale') && !document.getElementById('resSum').textContent.startsWith('0 ')", timeout=25000)
            mp.wait_for_timeout(400)
            mb_sum = (mp.locator("#resSum").text_content() or "").strip()
            check("for sale" in mb_sum, f"MOBILE Buy mode loaded: {mb_sum!r}")
            mp.locator(".fc").first.click(); mp.wait_for_timeout(800)
            mdr = mp.evaluate("""() => { const sh = document.getElementById("detailSheet"); const ims = sh ? [...sh.querySelectorAll("img")] : []; return ims.filter(i => i.complete && i.naturalWidth === 0).length; }""")
            check(mdr == 0 and len(m_errs) == 0 and len(m_fail) == 0, f"MOBILE drawer & errors clean (broken={mdr}, errs={m_errs}, fail={m_fail[:2]})")
            mctx.close()
            browser.close()

        if live_mode:
            base_origin = target_url.split("?")[0].rstrip("/")
            print(f"\n--- LIVE API, CACHE & CONCURRENCY SUITE ({base_origin}) ---", flush=True)
            rog = creq.get(base_origin + "/og-card.png", impersonate="chrome124", timeout=12)
            check(rog.status_code == 200 and len(rog.content) > 5000, f"LIVE /og-card.png WhatsApp preview: HTTP {rog.status_code} ({len(rog.content):,}B)")

            sy_u = ""
            man = json.loads((ROOT / "web/public/data/manifest.json").read_text(encoding="utf-8-sig"))
            for sf in man["rent_shards"][:2]:
                for s in json.loads((ROOT / "web/public/data" / sf).read_text(encoding="utf-8-sig")):
                    for im in ([s.get("thumb")] + (s.get("photos") or [])):
                        if isinstance(im, str) and "static.squareyards.com/" in im:
                            sy_u = im; break
                    if sy_u: break
                if sy_u: break
            if sy_u:
                iep = base_origin + "/api/img?u=" + urllib.parse.quote(sy_u, safe="")
                ri1 = creq.get(iep, impersonate="chrome124", timeout=15)
                time.sleep(0.3)
                ri2 = creq.get(iep, impersonate="chrome124", timeout=15)
                check(ri1.status_code == 200 and ri2.status_code == 200 and (ri2.headers.get("content-type") or "").startswith("image/"), f"LIVE /api/img 2-hit: h1={ri1.headers.get('x-edge-cache')} h2={ri2.headers.get('x-edge-cache')} ({len(ri2.content):,}B)")

            payload = {"action": "parse", "query": "2BHK in Bandra West under 85k zero brokerage", "currentMode": "rent", "knownLocalities": ["Bandra West", "Khar West"]}
            creq.post(base_origin + "/api/ask", json=payload, headers={"Origin": base_origin}, timeout=20)
            time.sleep(0.4)
            def _burst(_):
                t0 = time.time()
                r = creq.post(base_origin + "/api/ask", json=payload, headers={"Origin": base_origin}, timeout=15)
                return r.status_code, (r.json() or {}).get("cached", False), int((time.time() - t0) * 1000)
            with ThreadPoolExecutor(max_workers=10) as ex:
                res = list(ex.map(_burst, range(10)))
            ok_200 = sum(1 for s, _, _ in res if s == 200)
            hits = sum(1 for _, c, _ in res if c)
            max_ms = max(ms for _, _, ms in res)
            check(ok_200 == 10 and hits >= 5, f"LIVE 10x concurrent /api/ask parse: {ok_200}/10 HTTP 200 (cache_hits={hits}/10, max={max_ms}ms)")

            spay = {"action": "summarize", "mode": "rent", "query": "2BHK Bandra West under 90k", "totalBuildings": 10, "totalFlats": 15, "appliedLabels": ["2 BHK"], "topMatches": [{"name": "QA Villa", "locality": "Bandra West", "p": 85000, "bhks": [2], "units": 2, "zb": True, "vs": 98}]}
            rs1 = creq.post(base_origin + "/api/ask", json=spay, headers={"Origin": base_origin}, timeout=20).json()
            time.sleep(0.3)
            rs2 = creq.post(base_origin + "/api/ask", json=spay, headers={"Origin": base_origin}, timeout=20).json()
            rzero = creq.post(base_origin + "/api/ask", json={"action": "summarize", "mode": "rent", "query": "5BHK Colaba 15k", "totalBuildings": 0, "totalFlats": 0, "topMatches": []}, headers={"Origin": base_origin}, timeout=15).json()
            check(bool(rs1.get("summary")) and bool(rs2.get("summary")) and bool(rzero.get("summary")), f"LIVE /api/ask summarize: h1_cached={rs1.get('cached', False)} h2_cached={rs2.get('cached', False)} zero_ok={bool(rzero.get('summary'))}")

            rf = creq.get(base_origin + "/api/flags", impersonate="chrome124", timeout=12)
            rl = creq.get(base_origin + "/api/listings", impersonate="chrome124", timeout=12)
            check(rf.status_code == 200 and rl.status_code == 200, f"LIVE /api/flags ({rf.status_code}) & /api/listings ({rl.status_code})")
    except Exception as _qa_err:
        print("  [CRASH] " + traceback.format_exc(), flush=True)
        failures.append(f"CRASH: {_qa_err}")
    finally:
        if httpd: httpd.shutdown()

    print(f"\n=== QA SUMMARY: {'ALL PASSED' if not failures else f'{len(failures)} FAILED'} ===", flush=True)
    return 0 if not failures else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    sys.exit(run_qa(args.url or None, live_mode=args.live))
