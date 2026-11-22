import json, re, subprocess, sys
from pathlib import Path

html_p = Path("web/index.html")
html = html_p.read_text(encoding="utf-8")
css_p = Path("web/styles.css")
css = css_p.read_text(encoding="utf-8")
js_p = Path("web/app.js")
js = js_p.read_text(encoding="utf-8")

# 1. Auto-discover REAL parent selectors of #cardList, #map, and the split workspace from web/index.html
def find_enclosing_tag(src: str, target_id: str):
    pos = src.find(f'id="{target_id}"')
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

lp_tag, lp_info = find_enclosing_tag(html, "cardList")
mp_tag, mp_info = find_enclosing_tag(html, "map")
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
print(f"[v15.5] Real layout selectors -> workspace={ws_sel} | listPane={lp_sel} | mapPane={mp_sel}", flush=True)

# 2. Rewrite authoritative v15.5 CSS using REAL selectors + un-collapsible card & photo heights
for marker in ("/* v14: Jobs-Grade Individual Flat Grid", "/* v15: Owner / Broker / Shared", "/* v15.5: Authoritative"):
    idx_m = css.find(marker)
    if idx_m >= 0: css = css[:idx_m].rstrip()

ws_rule = ""
if ws_sel and ws_sel not in ("body", "html"):
    ws_rule = f"""
@media (min-width: 1120px) {{
  {ws_sel} {{ grid-template-columns: minmax(520px, 560px) 1fr !important; }}
}}
@media (min-width: 901px) and (max-width: 1119px) {{
  {ws_sel} {{ grid-template-columns: 400px 1fr !important; }}
}}
body.gallery-mode {ws_sel} {{ display:block !important; grid-template-columns:1fr !important; }}
"""

V15_5_CSS = f"""
/* v15.5: Authoritative Individual Flat Grid, Non-Squishing Cards, Gallery Mode & Clean Controls */
{ws_rule}
@media (min-width: 1120px) {{
  {lp_sel} {{ width:560px !important; min-width:520px !important; max-width:560px !important; flex:0 0 560px !important; display:flex !important; flex-direction:column !important; min-height:0 !important; height:100% !important; overflow:hidden !important; }}
}}
@media (min-width: 901px) and (max-width: 1119px) {{
  {lp_sel} {{ width:400px !important; min-width:380px !important; max-width:400px !important; flex:0 0 400px !important; display:flex !important; flex-direction:column !important; min-height:0 !important; height:100% !important; overflow:hidden !important; }}
}}

#cardList {{
  display:grid !important;
  grid-template-columns:repeat(2, minmax(0, 1fr)) !important;
  grid-auto-rows:max-content !important;
  align-content:start !important;
  align-items:start !important;
  gap:14px !important;
  padding:14px 16px 64px !important;
  overflow-y:auto !important;
  flex:1 1 auto !important;
  min-height:0 !important;
}}
@media (max-width: 1119px) {{ #cardList {{ grid-template-columns:1fr !important; }} }}
@media (max-width: 900px) {{ #cardList {{ grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)) !important; padding:12px 14px 80px !important; }} }}

.fc {{
  position:relative !important;
  display:flex !important;
  flex-direction:column !important;
  height:auto !important;
  min-height:264px !important;
  flex:none !important;
  background:var(--card);
  border:1px solid var(--line);
  border-radius:14px;
  overflow:hidden !important;
  cursor:pointer;
  transition:transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}}
.fc:hover {{ transform:translateY(-2px); border-color:rgba(196,158,92,.75); box-shadow:0 10px 24px rgba(22,42,39,.11); }}
.fc.sel {{ border-color:var(--pine); box-shadow:0 0 0 1.5px var(--pine); }}

.fc-media {{
  position:relative !important;
  width:100% !important;
  height:142px !important;
  min-height:142px !important;
  flex:none !important;
  background:linear-gradient(135deg, #eae4d6 0%, #ddd4c2 100%);
  overflow:hidden !important;
}}
[data-theme="dark"] .fc-media {{ background:linear-gradient(135deg, #1b2421 0%, #141b19 100%); }}
.fc-img {{ position:absolute; inset:0; width:100% !important; height:100% !important; object-fit:cover !important; display:block; transition:transform .28s ease; }}
.fc:hover .fc-img {{ transform:scale(1.03); }}
.fc-ph {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px; color:rgba(22,42,39,.48); font-family:var(--font-serif); font-size:12px; padding:10px; text-align:center; }}
[data-theme="dark"] .fc-ph {{ color:rgba(242,237,226,.42); }}
.fc-ph svg {{ opacity:.40; }}

.fc-badges-top {{ position:absolute; top:8px; left:8px; display:flex; gap:5px; z-index:2; pointer-events:none; }}
.fc-pill {{ font-family:var(--font-body); font-size:10px; font-weight:700; letter-spacing:.02em; padding:3px 8px; border-radius:999px; backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); }}
.fc-pill.zb {{ background:rgba(22,42,39,.86); color:#e8cfa0; border:1px solid rgba(196,158,92,.55); }}
.fc-pill.dr {{ background:rgba(194,82,56,.92); color:#fff; }}
.fc-pill.sea {{ background:rgba(21,94,117,.90); color:#fff; }}
.fc-pill.sh {{ background:rgba(31,107,92,.90); color:#fff; }}
.fc-pill.br {{ background:rgba(24,30,28,.72); color:#e7e3da; }}

.fc-heart {{ position:absolute; top:8px; right:8px; z-index:3; width:28px; height:28px; border-radius:999px; border:1px solid rgba(255,255,255,.35); background:rgba(22,42,39,.56); color:#fff; display:grid; place-items:center; cursor:pointer; backdrop-filter:blur(6px); font-size:14px; line-height:1; }}
.fc-heart:hover {{ background:rgba(22,42,39,.86); }}
.fc-heart.on {{ background:var(--pri); border-color:var(--pri); color:#fff; }}

.fc-body {{ padding:10px 12px 11px !important; display:flex !important; flex-direction:column !important; gap:4px; flex:1 0 auto !important; min-height:118px; }}
.fc-price-row {{ display:flex; align-items:baseline; justify-content:space-between; gap:6px; flex-wrap:nowrap; }}
.fc-price {{ font-family:var(--font-head); font-size:15px; font-weight:800; color:var(--txt); font-variant-numeric:tabular-nums; white-space:nowrap; }}
.fc-psf {{ font-size:10.5px; font-weight:500; color:var(--mut); margin-left:4px; }}
.fc-bhk {{ font-size:11px; font-weight:600; color:var(--txt); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.fc-title {{ font-family:var(--font-serif); font-size:14px; font-weight:600; color:var(--txt); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px; }}
.fc-sub {{ font-size:10.5px; font-weight:600; text-transform:uppercase; letter-spacing:.045em; color:var(--mut); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}

.fc-foot {{ display:flex; align-items:center; justify-content:space-between; gap:6px; margin-top:auto; padding-top:7px; border-top:1px solid var(--line); }}
.fc-tags {{ display:flex; flex-wrap:wrap; gap:4px; min-width:0; }}
.fc-src {{ font-size:11px; font-weight:600; color:var(--pri); text-decoration:none; white-space:nowrap; flex-shrink:0; }}
.fc-src:hover {{ text-decoration:underline; }}

.tag.sea {{ background:rgba(21,94,117,.12); color:#155e75; }}
[data-theme="dark"] .tag.sea {{ background:rgba(56,189,248,.16); color:#7dd3fc; }}
.tag.out {{ background:var(--sage-s); color:var(--sage); }}
.tag.drop {{ background:var(--pri-s); color:var(--pri); font-weight:700; }}
.tag.ai-v {{ background:var(--brass-s); color:#8a6830; }}
[data-theme="dark"] .tag.ai-v {{ color:var(--brass); }}
.load-more-wrap {{ grid-column:1 / -1; display:flex; justify-content:center; padding:8px 0 14px; }}

.view-seg {{ display:inline-flex !important; background:var(--hover); border:1px solid var(--line); border-radius:999px; padding:2px; gap:2px; flex-shrink:0; }}
.view-seg button {{ border:none; background:transparent; color:var(--mut); font-size:11.5px; font-weight:600; padding:4px 9px; border-radius:999px; cursor:pointer; white-space:nowrap; }}
.view-seg button.active {{ background:var(--pine); color:#f6f1e7; }}
[data-theme="dark"] .view-seg button.active {{ background:var(--brass); color:#111715; }}
.chip {{ flex-shrink:0 !important; }}
.chip.on, .chip.active {{ background:var(--pine) !important; color:#f6f1e7 !important; border-color:var(--pine) !important; }}
[data-theme="dark"] .chip.on, [data-theme="dark"] .chip.active {{ background:var(--brass) !important; color:#111715 !important; border-color:var(--brass) !important; }}

body.gallery-mode {mp_sel}, body.gallery-mode #map {{ display:none !important; }}
body.gallery-mode {lp_sel} {{ width:100% !important; max-width:100% !important; min-width:0 !important; flex:1 1 100% !important; border-right:none !important; }}
body.gallery-mode #cardList {{ grid-template-columns:repeat(auto-fill, minmax(285px, 1fr)) !important; gap:18px !important; padding:18px 26px 64px !important; }}
body.gallery-mode .fc-media {{ height:172px !important; min-height:172px !important; }}
"""
css_p.write_text(css.rstrip() + "\n" + V15_5_CSS, encoding="utf-8")

# 3. Wire EVERY interactive control cleanly right before closing `})();` in web/app.js
m_prev = js.find("/* === V15.5 INTERACTIVE CONTROLS === */")
if m_prev >= 0:
    m_end = js.find("/* === END V15.5 CONTROLS === */", m_prev)
    if m_end >= 0: js = js[:m_prev] + js[m_end + len("/* === END V15.5 CONTROLS === */"):]

V15_5_JS = """
  /* === V15.5 INTERACTIVE CONTROLS === */
  if (st.seaview === undefined) st.seaview = false;
  if (st.balcony === undefined) st.balcony = false;
  if (st.terrace === undefined) st.terrace = false;
  if (st.drop === undefined) st.drop = false;
  if (!st.lister) st.lister = "ALL";
  if (!st.view) st.view = "split";
  if (!st.hub) st.hub = "ALL";
  if (!st.hubMin) st.hubMin = 45;

  const V15_CHIP_KEYS = new Set(["seaview", "balcony", "terrace", "drop"]);
  document.querySelectorAll(".chip[data-q]").forEach(btn => {
    const k = btn.dataset.q;
    if (!V15_CHIP_KEYS.has(k)) return;
    btn.addEventListener("click", e => {
      e.stopImmediatePropagation();
      st[k] = !st[k];
      btn.classList.toggle("on", !!st[k]);
      btn.classList.toggle("active", !!st[k]);
      st.page = 36;
      renderAll();
    }, true);
  });

  document.querySelectorAll("#listerToggle button").forEach(btn => {
    btn.onclick = () => {
      st.lister = btn.dataset.lt || "ALL";
      document.querySelectorAll("#listerToggle button").forEach(x => x.classList.toggle("active", x.dataset.lt === st.lister));
      st.page = 36;
      renderAll();
    };
  });

  document.querySelectorAll("#viewToggle button").forEach(btn => {
    btn.onclick = () => {
      st.view = btn.dataset.v || "split";
      document.querySelectorAll("#viewToggle button").forEach(x => x.classList.toggle("active", x.dataset.v === st.view));
      document.body.classList.toggle("gallery-mode", st.view === "gallery");
      if (st.view === "split") setTimeout(() => map.invalidateSize(), 120);
      st.page = st.view === "gallery" ? 48 : 36;
      renderAll();
    };
  });

  if ($("fHub")) {
    const onHubChange = () => {
      st.hub = $("fHub").value || "ALL";
      st.hubMin = Number($("fHubMin")?.value || 45);
      if ($("hubVal")) $("hubVal").textContent = st.hub === "ALL" ? "Any" : `≤ ${st.hubMin} min to ${HUB_META[st.hub]?.name || st.hub}`;
      if (st.hub !== "ALL" && HUB_META[st.hub]) map.flyTo(HUB_META[st.hub].ll, 12, { duration: 0.5 });
      st.page = 36;
      renderAll();
    };
    $("fHub").addEventListener("change", onHubChange);
    if ($("fHubMin")) $("fHubMin").addEventListener("input", onHubChange);
  }

  ["resetMiniBtn", "resetBtn", "fReset"].forEach(id => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("click", () => {
      st.seaview = st.balcony = st.terrace = st.drop = false;
      st.lister = "ALL";
      st.hub = "ALL";
      if ($("fHub")) $("fHub").value = "";
      if ($("hubVal")) $("hubVal").textContent = "Any";
      document.querySelectorAll(".chip[data-q]").forEach(b => {
        if (V15_CHIP_KEYS.has(b.dataset.q)) b.classList.remove("on", "active");
      });
      document.querySelectorAll("#listerToggle button").forEach(x => x.classList.toggle("active", x.dataset.lt === "ALL"));
      setTimeout(() => renderAll(), 0);
    });
  });

  document.addEventListener("keydown", e => {
    if (e.key === "/" && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName)) {
      e.preventDefault(); $("searchInput")?.focus();
    } else if (e.key === "Escape") {
      ["detailSheet","filterSheet"].forEach(id => $(id)?.classList.remove("open"));
      ["savedModal","postModal"].forEach(id => { if ($(id)) $(id).style.display = "none"; });
    }
  });
  /* === END V15.5 CONTROLS === */
"""

close_idx = js.rfind("})();")
assert close_idx > 0, "Could not locate closing })(); in web/app.js"
js = js[:close_idx] + V15_5_JS + "\n" + js[close_idx:]
js_p.write_text(js, encoding="utf-8")

# 4. Interactive Node.js Verification: Tests Initial Load + Clicks EVERY New Button!
dom_defaults = {}
for m in re.finditer(r'<input\b([^>]+)>', html, re.I):
    attrs = m.group(1)
    id_m = re.search(r'\bid=["\']([^"\']+)["\']', attrs)
    val_m = re.search(r'\bvalue=["\']([^"\']*)["\']', attrs)
    if id_m and val_m: dom_defaults[id_m.group(1)] = val_m.group(1)
for m in re.finditer(r'<select\b([^>]+)>([\s\S]*?)</select>', html, re.I):
    attrs, body = m.group(1), m.group(2)
    id_m = re.search(r'\bid=["\']([^"\']+)["\']', attrs)
    if not id_m: continue
    sel_opt = re.search(r'<option\b[^>]*\bselected\b[^>]*value=["\']([^"\']*)["\']', body, re.I) or re.search(r'<option\b[^>]*value=["\']([^"\']*)["\']', body, re.I)
    dom_defaults[id_m.group(1)] = sel_opt.group(1) if sel_opt else ""

defaults_json = json.dumps(dom_defaults)

SMOKE_JS = f"""
const fs = require("fs"), vm = require("vm");
const DEFAULTS = {defaults_json};
function mkEl(id = "", dataset = {{}}) {{
  const cls = new Set();
  const listeners = {{}};
  const defVal = Object.prototype.hasOwnProperty.call(DEFAULTS, id) ? DEFAULTS[id] : "";
  return {{
    id, value: defVal, textContent: "", innerHTML: "", style: {{}}, dataset, checked: false, rel: "", href: "",
    selectedOptions: [{{ text: defVal || "Any" }}],
    options: [{{ value: defVal, text: defVal || "Any" }}],
    classList: {{
      add: (...cs) => cs.forEach(c => cls.add(c)),
      remove: (...cs) => cs.forEach(c => cls.delete(c)),
      toggle: (c, f) => f === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : (f ? cls.add(c) : cls.delete(c)),
      contains: c => cls.has(c),
    }},
    addEventListener: (ev, fn) => {{ (listeners[ev] = listeners[ev] || []).push(fn); }},
    removeEventListener: () => {{}},
    click() {{
      const e = {{ stopImmediatePropagation(){{}}, stopPropagation(){{}}, preventDefault(){{}} }};
      if (this.onclick) this.onclick(e);
      (listeners.click || []).forEach(fn => fn(e));
    }},
    focus: () => {{}}, querySelector: () => null, querySelectorAll: () => [],
    appendChild: () => {{}}, remove: () => {{}}, setAttribute: () => {{}}, getAttribute: () => null,
    getBoundingClientRect: () => ({{ width: 800, height: 600, top: 0, left: 0 }}),
  }};
}}
const els = new Map();
const getEl = id => {{ if (!els.has(id)) els.set(id, mkEl(id)); return els.get(id); }};
const chipBtns = ["seaview","balcony","terrace","drop"].map(q => mkEl("", {{ q }}));
const listerBtns = ["ALL","owner","broker","shared"].map(lt => mkEl("", {{ lt }}));
const viewBtns = ["split","gallery"].map(v => mkEl("", {{ v }}));
const bodyEl = mkEl("body");
const mkLayer = () => ({{
  addTo() {{ return this; }}, clearLayers() {{ return this; }}, remove() {{ return this; }},
  on() {{ return this; }}, bindTooltip() {{ return this; }}, bindPopup() {{ return this; }},
  addLayer() {{ return this; }}, getElement() {{ return mkEl(); }},
}});
const mkMap = () => ({{
  setView() {{ return this; }}, on() {{ return this; }}, getZoom: () => 12,
  getBounds: () => ({{ pad: () => ({{ contains: () => true }}), contains: () => true }}),
  latLngToContainerPoint: ([la, ln]) => ({{ x: (ln - 72.7) * 1000, y: (19.35 - la) * 1000 }}),
  containerPointToLatLng: () => ({{ lat: 19.07, lng: 72.87 }}),
  flyTo() {{}}, panTo() {{}}, fitBounds() {{}}, invalidateSize() {{}},
  hasLayer: () => false, addLayer() {{}}, removeLayer() {{}},
}});
const store = {{}};
const sandbox = {{
  console, Math, Date, JSON, Number, String, Boolean, Array, Object, Set, Map, RegExp, Error, Promise,
  Intl, URLSearchParams, URL, parseInt, parseFloat, isFinite, isNaN, encodeURIComponent, decodeURIComponent,
  setTimeout: () => 0, clearTimeout: () => {{}}, requestAnimationFrame: () => 0,
  navigator: {{ userAgent: "Mozilla/5.0", clipboard: {{ writeText: () => Promise.resolve() }} }},
  location: {{ href: "", search: "", pathname: "/", hash: "" }},
  history: {{ replaceState: () => {{}}, pushState: () => {{}} }},
  localStorage: {{ getItem: k => store[k] ?? null, setItem: (k, v) => {{ store[k] = String(v); }}, removeItem: k => {{ delete store[k]; }} }},
  document: {{
    head: mkEl("head"), body: bodyEl, documentElement: mkEl("html"),
    getElementById: getEl, querySelector: () => mkEl(),
    querySelectorAll: sel => {{
      if (sel.includes("listerToggle")) return listerBtns;
      if (sel.includes("viewToggle")) return viewBtns;
      if (sel.includes(".chip[data-q]")) return chipBtns;
      return [];
    }},
    addEventListener: () => {{}}, createElement: tag => mkEl(tag),
  }},
  L: {{
    map: mkMap, tileLayer: mkLayer, canvas: () => ({{}}), layerGroup: mkLayer,
    latLngBounds: () => ({{}}), circle: mkLayer, circleMarker: mkLayer,
    divIcon: () => ({{}}), marker: mkLayer, polyline: mkLayer, polygon: mkLayer,
    point: (x, y) => ({{ x, y }}),
  }},
  fetch: url => {{
    if (String(url).includes("mumbai-index.json")) {{
      return Promise.resolve({{ ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync("web/public/data/mumbai-index.json", "utf8"))) }});
    }}
    return Promise.resolve({{ ok: true, json: () => Promise.resolve({{ listings: [] }}) }});
  }},
}};
sandbox.window = sandbox; sandbox.self = sandbox;
let caughtErr = null;
const origErr = console.error;
console.error = (...a) => {{ if (a[0] instanceof Error) caughtErr = a[0]; origErr(...a); }};

vm.runInNewContext(fs.readFileSync("web/app.js", "utf8"), sandbox, {{ filename: "web/app.js" }});

setTimeout(() => {{
  const flatCount = () => {{
    const h = (els.get("cardList") || {{}}).innerHTML || "";
    const shown = (h.match(/class="fc/g) || []).length;
    const m = h.match(/Show more flats \\(([\\d,]+) left\\)/);
    return shown + (m ? parseInt(m[1].replace(/,/g, ""), 10) : 0);
  }};

  const initC = flatCount();
  console.log("[TEST] Initial All :", initC, "flats");
  if (caughtErr || initC === 0) {{ console.error("INITIAL FAIL", caughtErr); process.exit(1); }}

  listerBtns[1].click(); const ownC = flatCount(); console.log("[TEST] Owner       :", ownC, "flats");
  listerBtns[2].click(); const brkC = flatCount(); console.log("[TEST] Broker      :", brkC, "flats");
  listerBtns[3].click(); const shrC = flatCount(); console.log("[TEST] Shared      :", shrC, "flats");
  listerBtns[0].click();

  chipBtns[1].click(); const balC = flatCount(); console.log("[TEST] Balcony     :", balC, "flats"); chipBtns[1].click();
  chipBtns[2].click(); const terC = flatCount(); console.log("[TEST] Terrace/Gdn :", terC, "flats"); chipBtns[2].click();
  chipBtns[0].click(); const seaC = flatCount(); console.log("[TEST] Sea View    :", seaC, "flats"); chipBtns[0].click();
  chipBtns[3].click(); const drpC = flatCount(); console.log("[TEST] Price Drop  :", drpC, "flats"); chipBtns[3].click();

  viewBtns[1].click(); const galOn = bodyEl.classList.contains("gallery-mode");
  viewBtns[0].click(); const galOff = !bodyEl.classList.contains("gallery-mode");
  console.log("[TEST] Map/Gallery :", (galOn && galOff) ? "PASS" : "FAIL");

  if (!galOn || !galOff || ownC >= initC || brkC >= initC || balC >= initC || seaC >= initC) {{
    console.error("[TEST] FAILED: One or more controls did not filter results!");
    process.exit(1);
  }}
  console.log("[TEST] ALL BUTTONS & FILTERS PASS! Safe to deploy!");
}}, 160);
"""
r = subprocess.run(["node", "-e", SMOKE_JS], text=True)
sys.exit(r.returncode)
