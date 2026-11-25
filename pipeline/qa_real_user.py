# Permanent Real-User E2E Audit for Bombay Homes (v62+)
import argparse, http.server, json, socketserver, sys, threading, time, urllib.parse
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
                    f = {"mode": "buy" if "buy" in q else "rent"}
                    if "2bhk" in q or "2 bhk" in q: f["bhks"] = [2]
                    if "powai" in q: f["localities"] = ["Powai"]
                    elif "bandra" in q: f["localities"] = ["Bandra West"]
                    if "75k" in q: f["maxPrice"] = 75000
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
            for label, vp, is_mob in (("DESKTOP", {"width": 1440, "height": 900}, False), ("MOBILE", {"width": 390, "height": 844}, True)):
                print(f"\n--- {label} REAL-USER JOURNEY ---", flush=True)
                ctx = browser.new_context(viewport=vp, is_mobile=is_mob, has_touch=is_mob)
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
                check(base["cards"] >= 10 and "10," in base["home"], f"{label} initial load: {base['home']!r} ({base['cards']} cards)")
                check(base["broken"] == 0 and base["noAlt"] == 0, f"{label} images clean (broken={base['broken']}, noAlt={base['noAlt']})")
                check(len(base["unsafeLinks"]) == 0, f"{label} all external links safe + no-referrer (unsafe={base['unsafeLinks'][:3]})")
                check(not base["overflow"], f"{label} zero horizontal overflow")
                check(len(errs) == 0 and len(failed) == 0, f"{label} zero page/network errors (errs={errs}, failed={failed[:2]})")

                if not is_mob:
                    ai_inp = page.locator("#bhAiInput")
                    ai_inp.fill("2bhk in Powai under 75k")
                    page.locator("#bhAiGo").click()
                    page.wait_for_timeout(1600)
                    ai_filt = (page.locator("#resSum").text_content() or "").strip()
                    ai_inp.fill("")
                    ai_inp.dispatch_event("input")
                    page.wait_for_timeout(700)
                    ai_after = (page.locator("#resSum").text_content() or "").strip()
                    check(ai_filt != base["home"] and ai_after == base["home"], f"{label} #bhAiInput delete-to-reset: {ai_filt!r} -> {ai_after!r}")

                sb = page.locator("#searchBox")
                sb.fill("2bhk in Powai under 75k")
                page.locator(".bh-uni-ai").click()
                page.wait_for_timeout(1800)
                uni_filt = (page.locator("#resSum").text_content() or "").strip()
                sb.fill("")
                sb.dispatch_event("input")
                page.wait_for_timeout(700)
                uni_after = (page.locator("#resSum").text_content() or "").strip()
                check(uni_filt != base["home"] and uni_after == base["home"], f"{label} #searchBox AI delete-to-reset: {uni_filt!r} -> {uni_after!r}")

                if is_mob:
                    mtog = page.locator('#v20MobToggle').first
                    if mtog.count() > 0 and mtog.is_visible():
                        mtog.click(); page.wait_for_timeout(700)

                lbtn = page.locator("#mapLassoBtn")
                check(lbtn.count() > 0 and lbtn.is_visible(), f"{label} #mapLassoBtn visible on map")
                if lbtn.count() > 0 and lbtn.is_visible():
                    lbtn.click(); page.wait_for_timeout(250)
                    box = page.locator("#map").bounding_box()
                    if box and box["width"] > 100 and box["height"] > 100:
                        cx, cy = box["x"] + box["width"] * 0.48, box["y"] + box["height"] * 0.48
                        rx, ry = box["width"] * 0.18, box["height"] * 0.18
                        page.mouse.move(cx - rx, cy - ry)
                        page.mouse.down()
                        for pt in [(cx + rx, cy - ry), (cx + rx, cy + ry), (cx - rx, cy + ry), (cx - rx, cy - ry)]:
                            page.mouse.move(pt[0], pt[1], steps=6)
                        page.mouse.up()
                        page.wait_for_timeout(700)
                        lasso_sum = (page.locator("#resSum").text_content() or "").strip()
                        lasso_btn_txt = (lbtn.text_content() or "").strip()
                        check(lasso_sum != base["home"] and "Clear area" in lasso_btn_txt, f"{label} Map Lasso filtered: {lasso_sum!r} (btn={lasso_btn_txt!r})")
                        lbtn.click(); page.wait_for_timeout(600)
                        after_clear = (page.locator("#resSum").text_content() or "").strip()
                        check(after_clear == base["home"], f"{label} Map Lasso Clear restored: {after_clear!r}")

                if is_mob:
                    mtog2 = page.locator('#v20MobToggle').first
                    if mtog2.count() > 0 and mtog2.is_visible():
                        mtog2.click(); page.wait_for_timeout(500)
                fc0 = page.locator(".fc").first
                if fc0.count() > 0 and fc0.is_visible():
                    fc0.click(); page.wait_for_timeout(900)
                    dr = page.evaluate("""() => {
                        const sh = document.getElementById("detailSheet");
                        const ls = sh ? [...sh.querySelectorAll("a[href^='http']")] : [];
                        const bad = ls.filter(a => a.target !== "_blank" || !(a.rel || "").includes("noopener") || a.getAttribute("referrerpolicy") !== "no-referrer").map(a => a.href.slice(0, 50));
                        const ims = sh ? [...sh.querySelectorAll("img")] : [];
                        return { links: ls.length, bad, broken: ims.filter(i => i.complete && i.naturalWidth === 0).length };
                    }""")
                    check(dr["broken"] == 0 and len(dr["bad"]) == 0, f"{label} detail drawer clean (links={dr['links']}, bad={dr['bad']}, broken={dr['broken']})")
                    cd = page.locator("#closeDetailBtn")
                    if cd.count() > 0 and cd.is_visible(): cd.click(); page.wait_for_timeout(300)
                ctx.close()
            browser.close()

        if live_mode:
            base_origin = target_url.split("?")[0].rstrip("/")
            print(f"\n--- LIVE CONCURRENCY & EDGE-CACHE TEST ({base_origin}) ---", flush=True)
            payload = {"action": "parse", "query": "2BHK in Bandra West under 85k zero brokerage", "currentMode": "rent", "knownLocalities": ["Bandra West", "Khar West"]}
            creq.post(base_origin + "/api/ask", json=payload, headers={"Origin": base_origin}, timeout=20)
            time.sleep(0.5)
            def _burst(_):
                t0 = time.time()
                r = creq.post(base_origin + "/api/ask", json=payload, headers={"Origin": base_origin}, timeout=15)
                return r.status_code, (r.json() or {}).get("cached", False), int((time.time() - t0) * 1000)
            with ThreadPoolExecutor(max_workers=10) as ex:
                res = list(ex.map(_burst, range(10)))
            ok_200 = sum(1 for s, _, _ in res if s == 200)
            hits = sum(1 for _, c, _ in res if c)
            max_ms = max(ms for _, _, ms in res)
            check(ok_200 == 10, f"10 concurrent /api/ask calls: {ok_200}/10 HTTP 200 (cache_hits={hits}/10, max={max_ms}ms)")
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
