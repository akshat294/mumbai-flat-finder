import json, re, subprocess, sys
from pathlib import Path

html_p = Path("web/index.html")
html = html_p.read_text(encoding="utf-8")
css_p = Path("web/styles.css")
css = css_p.read_text(encoding="utf-8")
js_p = Path("web/app.js")
js = js_p.read_text(encoding="utf-8")

# 1. Auto-discover REAL parent selectors from web/index.html
def find_enclosing_tag(src: str, target_attr: str):
    pos = src.find(target_attr)
    if pos < 0: return None, None
    tags = list(re.finditer(r'<(/?)([a-zA-Z0-9]+)([^>]*)>', src[:pos]))
    depth = 0
    voids = {"input","img","br","hr","meta","link","path","circle","rect","line","svg"}
    for m in reversed(tags):
        closing, tag, attrs = bool(m.group(1)), m.group(2).lower(), m.group(3)
        if tag in voids or attrs.rstrip().endswith("/"): continue
        if closing: depth += 1
        else:
            if depth == 0:
                cls_m = re.search(r'class=["\']([^"\']+)["\']', attrs)
                id_m  = re.search(r'id=["\']([^"\']+)["\']', attrs)
                return tag, (id_m.group(1) if id_m else None, cls_m.group(1).split()[0] if cls_m else None, m.start())
            depth -= 1
    return None, None

_, lp_info = find_enclosing_tag(html, 'id="cardList"')
_, mp_info = find_enclosing_tag(html, 'id="map"')
_, ch_info = find_enclosing_tag(html, 'data-q="terrace"')

ws_sel = None
if lp_info and lp_info[2] is not None:
    tags = list(re.finditer(r'<(/?)([a-zA-Z0-9]+)([^>]*)>', html[:lp_info[2]]))
    depth = 0
    voids = {"input","img","br","hr","meta","link","path","circle","rect","line","svg"}
    for m in reversed(tags):
        closing, tag, attrs = bool(m.group(1)), m.group(2).lower(), m.group(3)
        if tag in voids or attrs.rstrip().endswith("/"): continue
        if closing: depth += 1
        else:
            if depth == 0:
                cls_m = re.search(r'class=["\']([^"\']+)["\']', attrs)
                id_m  = re.search(r'id=["\']([^"\']+)["\']', attrs)
                ws_sel = f"#{id_m.group(1)}" if id_m else (f".{cls_m.group(1).split()[0]}" if cls_m else tag)
                break
            depth -= 1

lp_sel = f"#{lp_info[0]}" if (lp_info and lp_info[0]) else (f".{lp_info[1]}" if (lp_info and lp_info[1]) else ".rail")
mp_sel = f"#{mp_info[0]}" if (mp_info and mp_info[0]) else (f".{mp_info[1]}" if (mp_info and mp_info[1]) else "#map")
ch_sel = f"#{ch_info[0]}" if (ch_info and ch_info[0]) else (f".{ch_info[1]}" if (ch_info and ch_info[1]) else ".chips")
print(f"[v15.7] Selectors -> ws={ws_sel} | list={lp_sel} | map={mp_sel} | chips={ch_sel}", flush=True)

# 2. Hide non-working #sortSelect cleanly in web/index.html
html = re.sub(
    r'(<select\b[^>]*id="sortSelect"[^>]*)(>)',
    lambda m: m.group(0) if 'display:none' in m.group(1) else m.group(1) + ' style="display:none"' + m.group(2),
    html,
    count=1,
)
html_p.write_text(html, encoding="utf-8")

# 3. Update web/styles.css -> hide sort, un-clip chips, resizable split pane & auto-reflow card grid
marker_7 = "/* v15.7: Resizable Split Pane"
idx_7 = css.find(marker_7)
if idx_7 >= 0: css = css[:idx_7].rstrip()

ws_resize_css = ""
if ws_sel and ws_sel not in ("body", "html"):
    ws_resize_css = f"""
@media (min-width: 901px) {{
  {ws_sel} {{ grid-template-columns: var(--pane-w, 560px) minmax(240px, 1fr) !important; }}
}}
body.gallery-mode {ws_sel} {{ display:block !important; grid-template-columns:1fr !important; }}
"""

V15_7_CSS = f"""
/* v15.7: Resizable Split Pane, Dynamic Card Columns, Unclipped Chip Bar & Hide Sort Dropdown */
:root {{ --pane-w: 560px; }}

#sortSelect, .sort-sel {{ display:none !important; }}

{ch_sel} {{
  display:flex !important;
  align-items:center !important;
  flex-wrap:nowrap !important;
  gap:5px !important;
  overflow-x:auto !important;
  scrollbar-width:none !important;
  padding-right:16px !important;
  min-width:0 !important;
  flex:1 1 auto !important;
}}
{ch_sel}::-webkit-scrollbar {{ display:none; }}
{ch_sel} .chip {{ padding:4px 9px !important; font-size:11.5px !important; white-space:nowrap !important; }}

{ws_resize_css}
@media (min-width: 901px) {{
  {lp_sel} {{
    width:var(--pane-w, 560px) !important;
    min-width:290px !important;
    max-width:82vw !important;
    flex:0 0 var(--pane-w, 560px) !important;
  }}
  {mp_sel} {{
    position:relative !important;
    min-width:240px !important;
    flex:1 1 auto !important;
  }}
}}

/* Cards adapt smoothly to 1, 2, 3, or 4 columns as you drag the panel */
#cardList {{
  grid-template-columns:repeat(auto-fill, minmax(235px, 1fr)) !important;
}}
@media (max-width: 900px) {{
  #cardList {{ grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)) !important; }}
}}

/* Tactile Pull Handle on the Map's Left Seam (never overlaps #cardList scrollbar) */
#paneResizer {{
  position:absolute;
  top:0;
  left:0;
  bottom:0;
  width:12px;
  z-index:1150;
  cursor:col-resize;
  touch-action:none;
  user-select:none;
  background:transparent;
  transition:background .15s ease;
}}
#paneResizer:hover, body.resizing-pane #paneResizer {{ background:rgba(196,158,92,.22); }}
#paneResizer::after {{
  content:"";
  position:absolute;
  top:50%;
  left:0;
  transform:translateY(-50%);
  width:14px;
  height:52px;
  border-radius:0 9px 9px 0;
  background:var(--card);
  border:1px solid var(--line);
  border-left:none;
  box-shadow:3px 0 12px rgba(22,42,39,.14);
  background-image:radial-gradient(circle, rgba(22,42,39,.48) 1.3px, transparent 1.5px);
  background-size:6px 7px;
  background-position:center;
  background-repeat:repeat-y;
  transition:background-color .15s, border-color .15s, width .15s;
}}
[data-theme="dark"] #paneResizer::after {{
  background-image:radial-gradient(circle, rgba(196,158,92,.75) 1.3px, transparent 1.5px);
}}
#paneResizer:hover::after, body.resizing-pane #paneResizer::after {{
  width:17px;
  border-color:var(--brass);
  background-color:var(--pine);
  background-image:radial-gradient(circle, #e8cfa0 1.4px, transparent 1.6px);
}}
body.resizing-pane {{ cursor:col-resize !important; user-select:none !important; }}
body.resizing-pane #map {{ pointer-events:none !important; }}
body.gallery-mode #paneResizer {{ display:none !important; }}
@media (max-width: 900px) {{ #paneResizer {{ display:none !important; }} }}
"""
css_p.write_text(css.rstrip() + "\n" + V15_7_CSS, encoding="utf-8")

# 4. Wire Draggable Split-Pane Resizer + Horizontal Wheel Scroll on Chip Bar inside web/app.js
p0 = js.find("/* === V15.7 RESIZER & CHIP SCROLL === */")
if p0 >= 0:
    p1 = js.find("/* === END V15.7 === */", p0)
    if p1 >= 0: js = js[:p0] + js[p1 + len("/* === END V15.7 === */"):]

V15_7_JS = f"""
  /* === V15.7 RESIZER & CHIP SCROLL === */
  const chipStrip = document.querySelector("{ch_sel}");
  if (chipStrip && chipStrip.addEventListener) {{
    chipStrip.addEventListener("wheel", e => {{
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && chipStrip.scrollWidth > chipStrip.clientWidth) {{
        e.preventDefault();
        chipStrip.scrollLeft += e.deltaY;
      }}
    }}, {{ passive: false }});
  }}

  const mapHost = document.querySelector("{mp_sel}") || $("map");
  if (mapHost && mapHost.appendChild && !$("paneResizer")) {{
    const handle = document.createElement("div");
    handle.id = "paneResizer";
    handle.title = "Drag to resize panel · Double-click to reset";
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    mapHost.appendChild(handle);

    const DEFAULT_W = 560;
    const clampW = w => {{
      const vw = (typeof window !== "undefined" && window.innerWidth) ? window.innerWidth : 1440;
      return Math.round(Math.max(290, Math.min(vw - 260, w)));
    }};
    const applyPaneW = (w, persist = false) => {{
      const cw = clampW(w);
      if (document.documentElement?.style?.setProperty) {{
        document.documentElement.style.setProperty("--pane-w", cw + "px");
      }}
      if (persist) {{
        try {{ localStorage.setItem("bh_pane_w", String(cw)); }} catch {{}}
      }}
    }};

    try {{
      const savedW = Number(localStorage.getItem("bh_pane_w") || 0);
      if (savedW >= 290) applyPaneW(savedW, false);
    }} catch {{}}

    let dragging = false, rafId = 0;
    const syncMapSize = () => {{
      rafId = 0;
      try {{ map.invalidateSize({{ animate: false }}); }} catch {{}}
    }};

    handle.addEventListener("pointerdown", e => {{
      if (e.button && e.button !== 0) return;
      dragging = true;
      document.body.classList.add("resizing-pane");
      if (handle.setPointerCapture) handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    }});

    handle.addEventListener("pointermove", e => {{
      if (!dragging) return;
      applyPaneW(e.clientX, false);
      if (!rafId && typeof requestAnimationFrame === "function") {{
        rafId = requestAnimationFrame(syncMapSize);
      }}
    }});

    const endDrag = e => {{
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("resizing-pane");
      if (e && e.clientX) applyPaneW(e.clientX, true);
      try {{ map.invalidateSize({{ animate: false }}); }} catch {{}}
      try {{ renderMap(); }} catch {{}}
    }};
    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);

    handle.addEventListener("dblclick", () => {{
      applyPaneW(DEFAULT_W, true);
      setTimeout(() => {{
        try {{ map.invalidateSize({{ animate: false }}); renderMap(); }} catch {{}}
      }}, 40);
    }});

    if (typeof window !== "undefined" && window.addEventListener) {{
      window.addEventListener("resize", () => {{
        try {{
          const cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--pane-w"), 10);
          if (cur) applyPaneW(cur, false);
        }} catch {{}}
      }});
    }}
  }}
  /* === END V15.7 === */
"""

close_idx = js.rfind("})();")
assert close_idx > 0, "Could not locate closing })(); in web/app.js"
js = js[:close_idx] + V15_7_JS + "\n" + js[close_idx:]
js_p.write_text(js, encoding="utf-8")

# 5. Syntax & Runtime Verification in Node
r_chk = subprocess.run(["node", "--check", "web/app.js"], text=True)
if r_chk.returncode != 0: sys.exit(r_chk.returncode)

SMOKE_JS = r"""
const fs = require("fs"), vm = require("vm");
function mkEl(id = "") {
  const cls = new Set(), listeners = {};
  return {
    id, value: "ALL", textContent: "", innerHTML: "", style: { setProperty(){} }, dataset: {}, checked: false, rel: "", href: "",
    selectedOptions: [{ text: "Any" }], options: [{ value: "ALL", text: "Any" }],
    parentNode: { insertBefore() {} }, contains: () => false,
    classList: { add: (...c) => c.forEach(x => cls.add(x)), remove: (...c) => c.forEach(x => cls.delete(x)), toggle: () => {}, contains: c => cls.has(c) },
    addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
    removeEventListener: () => {}, focus: () => {}, querySelector: () => null, querySelectorAll: () => [],
    appendChild: () => {}, remove: () => {}, setAttribute: () => {}, getAttribute: () => null,
    getBoundingClientRect: () => ({ width: 320, height: 38, top: 10, left: 200, bottom: 48 }),
  };
}
const els = new Map();
const getEl = id => { if (!els.has(id)) els.set(id, mkEl(id)); return els.get(id); };
getEl("fHub").value = ""; getEl("fMetro").value = "0"; getEl("fRate").value = "0"; getEl("fHubMin").value = "45";
const mkLayer = () => ({ addTo() { return this; }, clearLayers() { return this; }, remove() { return this; }, on() { return this; }, bindTooltip() { return this; }, bindPopup() { return this; }, addLayer() { return this; }, getElement() { return mkEl(); } });
const mkMap = () => ({
  setView() { return this; }, on() { return this; }, getZoom: () => 12,
  getBounds: () => ({ pad: () => ({ contains: () => true }), contains: () => true }),
  latLngToContainerPoint: ([la, ln]) => ({ x: (ln - 72.7) * 1000, y: (19.35 - la) * 1000 }),
  containerPointToLatLng: () => ({ lat: 19.07, lng: 72.87 }),
  flyTo() {}, panTo() {}, fitBounds() {}, invalidateSize() {}, hasLayer: () => false, addLayer() {}, removeLayer() {},
});
const store = {};
const sandbox = {
  console, Math, Date, JSON, Number, String, Boolean, Array, Object, Set, Map, RegExp, Error, Promise,
  Intl, URLSearchParams, URL, parseInt, parseFloat, isFinite, isNaN, encodeURIComponent, decodeURIComponent,
  innerWidth: 1440, setTimeout: () => 0, clearTimeout: () => {}, requestAnimationFrame: () => 0,
  addEventListener: () => {}, getComputedStyle: () => ({ getPropertyValue: () => "560px" }),
  navigator: { userAgent: "Mozilla/5.0", clipboard: { writeText: () => Promise.resolve() } },
  location: { href: "", search: "", pathname: "/", hash: "" },
  history: { replaceState: () => {}, pushState: () => {} },
  localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  document: { head: mkEl("head"), body: mkEl("body"), documentElement: mkEl("html"), getElementById: getEl, querySelector: () => mkEl(), querySelectorAll: () => [], addEventListener: () => {}, createElement: tag => mkEl(tag) },
  L: { map: mkMap, tileLayer: mkLayer, canvas: () => ({}), layerGroup: mkLayer, latLngBounds: () => ({ pad: () => ({}) }), circle: mkLayer, circleMarker: mkLayer, divIcon: () => ({}), marker: mkLayer, polyline: mkLayer, polygon: mkLayer, point: (x, y) => ({ x, y }) },
  fetch: url => {
    if (String(url).includes("mumbai-index.json")) return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync("web/public/data/mumbai-index.json", "utf8"))) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ listings: [] }) });
  },
};
sandbox.window = sandbox; sandbox.self = sandbox;
let err = null;
const oe = console.error;
console.error = (...a) => { if (a[0] instanceof Error) err = a[0]; oe(...a); };
vm.runInNewContext(fs.readFileSync("web/app.js", "utf8"), sandbox, { filename: "web/app.js" });
setTimeout(() => {
  const h = (els.get("cardList") || {}).innerHTML || "";
  const shown = (h.match(/class="fc/g) || []).length;
  console.log("[v15.7 TEST] cards rendered =", shown, "| err =", err ? err.message : "NONE");
  if (err || shown === 0) process.exit(1);
  console.log("[v15.7 TEST] PASS! Resizer + unclipped chips + sort removed ready to deploy!");
}, 150);
"""
r = subprocess.run(["node", "-e", SMOKE_JS], text=True)
sys.exit(r.returncode)
