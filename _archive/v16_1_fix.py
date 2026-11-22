import json, re, subprocess, sys
from pathlib import Path

# 1. Inspect real localities in mumbai-index.json
idx_data = json.loads(Path("web/public/data/mumbai-index.json").read_text(encoding="utf-8"))
socs_all = idx_data.get("societies") or []
all_locs = sorted({s.get("locality", "") for s in socs_all if s.get("locality")})
santa_locs = [l for l in all_locs if "santa" in l.lower() or "cruz" in l.lower()]
print(f"[v16.1] Localities in index: {len(all_locs)} | Santa/Cruz matches: {santa_locs}", flush=True)

js_p = Path("web/app.js")
js = js_p.read_text(encoding="utf-8")
html = Path("web/index.html").read_text(encoding="utf-8")

search_id = "searchBox" if 'id="searchBox"' in html else "searchInput"
for m in re.finditer(r'<input\b([^>]+)>', html, re.I):
    attrs = m.group(1)
    id_m = re.search(r'\bid=["\']([^"\']+)["\']', attrs)
    ph_m = re.search(r'\bplaceholder=["\']([^"\']+)["\']', attrs)
    if id_m and ph_m and any(k in ph_m.group(1).lower() for k in ("search", "bandra", "localit")):
        search_id = id_m.group(1)
        break

m_soc_arr = re.search(r'\b(societies|ALL|DATA|allSocieties|homes)\s*=\s*(?:d|data|res|json)\.societies', js)
soc_var = m_soc_arr.group(1) if m_soc_arr else "societies"
print(f"[v16.1] searchId='{search_id}' | societiesVar='{soc_var}'", flush=True)

# 2. Align societiesVar & add space/hyphen-insensitive matching inside autocomplete + gallery blocks
for sm, em in (
    ("/* === V15.6 INTERACTIVE CONTROLS === */", "/* === END V15.6 CONTROLS === */"),
    ("/* === V16 GALLERY, SEARCH & RESIZER === */", "/* === END V16 === */"),
):
    p0 = js.find(sm)
    if p0 >= 0:
        p1 = js.find(em, p0)
        if p1 >= 0:
            block = js[p0:p1 + len(em)]
            if soc_var != "societies":
                block = re.sub(r'\bsocieties\b', soc_var, block)
            if "const normQ =" not in block and "function buildSuggestions(rawQ)" in block:
                block = block.replace(
                    'const q = (rawQ || "").trim().toLowerCase();',
                    'const q = (rawQ || "").trim().toLowerCase();\n    const normS = v => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");\n    const normQ = normS(q);',
                )
                block = block.replace(
                    'if (q) locList = locList.filter(x => x.loc.toLowerCase().includes(q) || x.zone.toLowerCase().includes(q));',
                    'if (normQ) locList = locList.filter(x => normS(x.loc).includes(normQ));',
                )
                block = block.replace(
                    'const aPre = q && a.loc.toLowerCase().startsWith(q) ? 1 : 0;\n      const bPre = q && b.loc.toLowerCase().startsWith(q) ? 1 : 0;',
                    'const aPre = normQ && normS(a.loc).startsWith(normQ) ? 1 : 0;\n      const bPre = normQ && normS(b.loc).startsWith(normQ) ? 1 : 0;',
                )
                block = block.replace(
                    'return uLen > 0 && (s.name || "").toLowerCase().includes(q);',
                    'return uLen > 0 && (normS(s.name).includes(normQ) || normS(s.locality).includes(normQ));',
                )
            js = js[:p0] + block + js[p1 + len(em):]

# 3. Space/hyphen-insensitive strict search inside passesV15SocietyFilter(s) + original filter
old_strict = re.search(r'[ \t]*const _tq =[\s\S]*?/\* v16_strict_search \*/\n?', js)
new_strict = (
    f'    const _tq = (document.getElementById("{search_id}")?.value || "").trim().toLowerCase();\n'
    '    if (_tq && (!Array.isArray(st.multiLocs) || !st.multiLocs.length)) {\n'
    '      const _ns = v => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");\n'
    '      const _rawHay = ((s.name || "") + " " + (s.locality || "") + " " + ((s.features?.tags || []).join(" ").replace(/_/g, " ")) + " " + ((s.bhks || []).map(b => b === 0 ? "1 rk studio" : (b + " bhk")).join(" "))).toLowerCase();\n'
    '      const _normHay = _ns(s.name) + " " + _ns(s.locality) + " " + _ns((s.features?.tags || []).join(" "));\n'
    '      const _toks = _tq.split(/\\s+/).filter(Boolean);\n'
    '      if (!_toks.every(tok => _rawHay.includes(tok) || _normHay.includes(_ns(tok)))) return false;\n'
    '    } /* v16_strict_search */\n'
)
if old_strict:
    js = js[:old_strict.start()] + new_strict + js[old_strict.end():]

js = re.sub(
    r'(!\s*\(?[^;\n]*?\.toLowerCase\(\)\)?\.includes\(\s*q\s*\))',
    r'(!((s.name + " " + s.locality + " " + (s.zone || "") + " " + ((s.features?.tags || []).join(" "))).toLowerCase().replace(/[^a-z0-9]/g, "").includes(q.replace(/[^a-z0-9]/g, ""))))',
    js,
    count=1,
)
js = js.replace(
    'if (sInput) sInput.value = "";\n    if ("q" in st) st.q = "";',
    'if (sInput) sInput.value = "";\n    if ("q" in st) st.q = "";\n    if ("search" in st) st.search = "";',
)

js_p.write_text(js, encoding="utf-8")

# 4. Syntax & Real Node.js Verification
for f_chk in ("web/app.js", "functions/api/photos.js"):
    r_chk = subprocess.run(["node", "--check", f_chk], text=True)
    if r_chk.returncode != 0: sys.exit(r_chk.returncode)

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

SMOKE_TEMPLATE = r"""
const fs = require("fs"), vm = require("vm");
const DEFAULTS = __DEFAULTS__;
const SEARCH_ID = __SEARCH_ID__;
const els = new Map();
function mkEl(id = "", dataset = {}) {
  const cls = new Set(), listeners = {};
  const defVal = Object.prototype.hasOwnProperty.call(DEFAULTS, id) ? DEFAULTS[id] : "";
  const el = {
    _id: id, value: defVal, textContent: "", innerHTML: "", style: { setProperty(){} }, dataset, checked: false, rel: "", href: "",
    selectedOptions: [{ text: defVal || "Any" }], options: [{ value: defVal, text: defVal || "Any" }],
    parentNode: { insertBefore() {} }, contains: () => false,
    classList: {
      add: (...cs) => cs.forEach(c => cls.add(c)), remove: (...cs) => cs.forEach(c => cls.delete(c)),
      toggle: (c, f) => f === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : (f ? cls.add(c) : cls.delete(c)),
      contains: c => cls.has(c),
    },
    addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
    dispatch(ev) {
      if (ev === "input" && typeof this.oninput === "function") this.oninput({ target: this });
      (listeners[ev] || []).forEach(fn => fn({ target: this, preventDefault(){}, stopPropagation(){} }));
    },
    removeEventListener: () => {}, focus: () => {}, querySelector: () => null, querySelectorAll: () => [],
    appendChild: () => {}, remove: () => {}, setAttribute: () => {}, getAttribute: () => null,
    getBoundingClientRect: () => ({ width: 320, height: 38, top: 10, left: 200, bottom: 48 }),
  };
  Object.defineProperty(el, "id", {
    get() { return this._id; },
    set(v) { this._id = v; if (v) els.set(v, this); },
  });
  if (id) els.set(id, el);
  return el;
}
const getEl = id => { if (!els.has(id)) mkEl(id); return els.get(id); };
const bodyEl = mkEl("body");
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
  innerWidth: 1440, setTimeout: fn => { fn(); return 0; }, clearTimeout: () => {}, requestAnimationFrame: () => 0,
  addEventListener: () => {}, getComputedStyle: () => ({ getPropertyValue: () => "560px" }),
  navigator: { userAgent: "Mozilla/5.0", clipboard: { writeText: () => Promise.resolve() } },
  location: { href: "", search: "", pathname: "/", hash: "" },
  history: { replaceState: () => {}, pushState: () => {} },
  localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  document: { head: mkEl("head"), body: bodyEl, documentElement: mkEl("html"), getElementById: getEl, querySelector: () => mkEl(), querySelectorAll: () => [], addEventListener: () => {}, createElement: () => mkEl("") },
  L: { map: mkMap, tileLayer: mkLayer, canvas: () => ({}), layerGroup: mkLayer, latLngBounds: () => ({ pad: () => ({}) }), circle: mkLayer, circleMarker: mkLayer, divIcon: () => ({}), marker: mkLayer, polyline: mkLayer, polygon: mkLayer, point: (x, y) => ({ x, y }) },
  fetch: url => {
    if (String(url).includes("mumbai-index.json")) return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync("web/public/data/mumbai-index.json", "utf8"))) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ listings: [], photos: [] }) });
  },
};
sandbox.window = sandbox; sandbox.self = sandbox;
let err = null;
const oe = console.error;
console.error = (...a) => { if (a[0] instanceof Error) err = a[0]; oe(...a); };
vm.runInNewContext(fs.readFileSync("web/app.js", "utf8"), sandbox, { filename: "web/app.js" });

setTimeout(() => {
  const h0 = (els.get("cardList") || {}).innerHTML || "";
  const cards0 = (h0.match(/<article class="fc/g) || []).length;
  const navs0 = (h0.match(/fc-nav next/g) || []).length;

  const sEl = getEl(SEARCH_ID);
  sEl.value = "santacruz";
  sEl.dispatch("input");
  const hS = (els.get("cardList") || {}).innerHTML || "";
  const cardsS = (hS.match(/<article class="fc/g) || []).length;
  const hasSanta = /santa\s*cruz/i.test(hS);
  const hasBandraLeak = /Bandra East/i.test(hS);
  const suggestHtml = (els.get("searchSuggest") || {}).innerHTML || "";
  const hasSuggest = /santa\s*cruz/i.test(suggestHtml);

  sEl.value = ""; sEl.dispatch("input");
  sandbox.__BH_ADD_LOC("Bandra West");
  const m1 = ((els.get("cardList") || {}).innerHTML || "").match(/<article class="fc/g)?.length || 0;
  sandbox.__BH_ADD_LOC("Khar West");
  sandbox.__BH_ADD_LOC("Powai");
  const m3 = ((els.get("cardList") || {}).innerHTML || "").match(/<article class="fc/g)?.length || 0;

  console.log("[v16.1 TEST] cards=" + cards0 + " | carouselArrows=" + navs0 + " | santacruzCards=" + cardsS + " | santaMatch=" + hasSanta + " | bandraLeak=" + hasBandraLeak + " | autocomplete=" + hasSuggest + " | multiLoc3=" + m3 + " | err=" + (err ? err.message : "NONE"));
  if (!hasSuggest) console.log("[v16.1 DEBUG] suggestHtml:", suggestHtml.slice(0, 260));
  if (!hasSanta) console.log("[v16.1 DEBUG] cardList on santacruz:", hS.slice(0, 260));
  if (err || cards0 === 0 || navs0 === 0 || !hasSanta || hasBandraLeak || !hasSuggest || m1 === 0 || m3 === 0) {
    console.error("[v16.1 TEST] FAILED!");
    process.exit(1);
  }
  console.log("[v16.1 TEST] PASS! Search, Autocomplete, 3-Locality Multi-Select & Photo Carousel verified!");
}, 180);
"""
smoke_js = SMOKE_TEMPLATE.replace("__DEFAULTS__", json.dumps(dom_defaults)).replace("__SEARCH_ID__", json.dumps(search_id))
r = subprocess.run(["node", "-e", smoke_js], text=True)
sys.exit(r.returncode)
