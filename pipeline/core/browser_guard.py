from __future__ import annotations
import gc, os, random, time
from typing import Callable, List, Optional
import psutil

BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
BLOCKED_DOMAINS = (
    "googletagmanager.com", "google-analytics.com", "doubleclick.net",
    "facebook.net", "hotjar.com", "clevertap", "moengage", "newrelic", "sentry.io",
)
LOW_RAM_ARGS = [
    "--disable-gpu", "--disable-dev-shm-usage", "--disable-extensions",
    "--disable-background-networking", "--disable-default-apps", "--disable-sync",
    "--metrics-recording-only", "--mute-audio", "--no-first-run",
    "--renderer-process-limit=2", "--js-flags=--max-old-space-size=384",
]

def get_tree_rss_mb(pid: Optional[int] = None) -> float:
    try:
        proc = psutil.Process(pid or os.getpid())
        total = proc.memory_info().rss
        for child in proc.children(recursive=True):
            try:
                total += child.memory_info().rss
            except psutil.Error:
                pass
        return round(total / (1024 * 1024), 1)
    except Exception:
        return 0.0

class SafeBrowserPool:
    def __init__(self, max_ram_mb: int = 600, recycle_every: int = 10, headless: bool = True,
                 min_delay_s: float = 1.2, max_delay_s: float = 2.5):
        self.max_ram_mb = max_ram_mb
        self.recycle_every = recycle_every
        self.headless = headless
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s
        self._pw = None
        self._browser = None
        self._context = None
        self._pages_served = 0

    def __enter__(self):
        self._start_browser()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _start_browser(self):
        from playwright.sync_api import sync_playwright
        if self._pw is None:
            self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless, args=LOW_RAM_ARGS)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        def _route(route):
            req = route.request
            u = req.url.lower()
            if any(d in u for d in BLOCKED_DOMAINS) or req.resource_type in BLOCKED_RESOURCE_TYPES:
                return route.abort()
            return route.continue_()
        self._context.route("**/*", _route)

    def _maybe_recycle(self):
        if self._pages_served >= self.recycle_every or get_tree_rss_mb() > self.max_ram_mb:
            self._pages_served = 0
            try:
                if self._context: self._context.close()
                if self._browser: self._browser.close()
            except Exception:
                pass
            gc.collect()
            self._start_browser()

    def fetch_json_responses(self, url: str, url_predicate: Callable[[str], bool], wait_ms: int = 3500, scroll_steps: int = 2) -> List[dict]:
        self._maybe_recycle()
        captured: List[dict] = []
        page = self._context.new_page()
        page.set_default_timeout(25000)

        def _on_response(resp):
            try:
                if resp.status == 200 and url_predicate(resp.url):
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "json" in ctype or "graphql" in resp.url.lower():
                        captured.append({"url": resp.url, "data": resp.json()})
            except Exception:
                pass

        page.on("response", _on_response)
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)
            for _ in range(scroll_steps):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(800)
        finally:
            try: page.close()
            except Exception: pass
            self._pages_served += 1
            time.sleep(random.uniform(self.min_delay_s, self.max_delay_s))
        return captured

    def close(self):
        for obj in (self._context, self._browser):
            if obj is not None:
                try: obj.close()
                except Exception: pass
        if self._pw is not None:
            try: self._pw.stop()
            except Exception: pass
        self._context = self._browser = self._pw = None
        gc.collect()
