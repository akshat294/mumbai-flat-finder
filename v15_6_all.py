import json, re, subprocess, sys
from pathlib import Path

html_p = Path("web/index.html")
html = html_p.read_text(encoding="utf-8")
css_p = Path("web/styles.css")
css = css_p.read_text(encoding="utf-8")
js_p = Path("web/app.js")
js = js_p.read_text(encoding="utf-8")

# 1. Auto-discover REAL parent selectors of #cardList, #map & workspace from web/index.html
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
print(f"[v15.6] Layout selectors -> workspace={ws_sel} | listPane={lp_sel} | mapPane={mp_sel}", flush=True)

# 2. Fix web/index.html: exact BHK pill class on 1.5/2.5/3.5, hide obsolete Price Estimates button, update search placeholder
m_bhk1 = re.search(r'<button\b([^>]*data-bhk="1"[^>]*)>', html)
if m_bhk1:
    cls_m = re.search(r'class=["\']([^"\']+)["\']', m_bhk1.group(1))
    real_bhk_cls = cls_m.group(1) if cls_m else "bhk-btn"
    print(f"[v15.6] Real BHK button class: '{real_bhk_cls}'", flush=True)
    for frac in ("1.5", "2.5", "3.5"):
        html = re.sub(
            rf'<button\b[^>]*data-bhk="{re.escape(frac)}"[^>]*>.*?</button>',
            f'<button class="{real_bhk_cls}" data-bhk="{frac}">{frac} BHK</button>',
            html,
        )

html = re.sub(
    r'(<button\b[^>]*)(>\s*Include Price Estimates\s*</button>)',
    lambda m: m.group(0) if 'display:none' in m.group(1) else m.group(1) + ' style="display:none"' + m.group(2),
    html,
    flags=re.I,
)
html = re.sub(
    r'(id="searchInput"[^>]*placeholder=")[^"]*(")',
    r'\1Search up to 5 localities (Bandra, Khar, Powai) or society…\2',
    html,
)
html_p.write_text(html, encoding="utf-8")

# 3. Authoritative web/styles.css (un-squished 2-col cards, sheet z-index, smart search dropdown, locality chips, gallery mode)
for marker in ("/* v14: Jobs-Grade Individual Flat Grid", "/* v15: Owner / Broker / Shared", "/* v15.5: Authoritative", "/* v15.6: Authoritative"):
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

V15_6_CSS = f"""
/* v15.6: Authoritative Individual Flat Grid, Smart Multi-Locality Search, Sheet Z-Index & Gallery Mode */
{ws_rule}
@media (min-width: 1120px) {{
  {lp_sel} {{ width:560px !important; min-width:520px !important; max-width:560px !important; flex:0 0 560px !important; display:flex !important; flex-direction:column !important; min-height:0 !important; height:100% !important; overflow:hidden !important; }}
}}
@media (min-width: 901px) and (max-width: 1119px) {{
  {lp_sel} {{ width:400px !important; min-width:380px !important; max-width:400px !important; flex:0 0 400px !important; display:flex !important; flex-direction:column !important; min-height:0 !important; height:100% !important; overflow:hidden !important; }}
}}

#filterSheet, #detailSheet, .sheet, .drawer, .modal {{ z-index:2500 !important; }}
.leaflet-control-attribution {{ z-index:400 !important; }}

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

#searchSuggest {{
  position:fixed;
  z-index:3200;
  background:var(--card);
  border:1px solid rgba(196,158,92,.55);
  border-radius:14px;
  box-shadow:0 16px 40px rgba(14,24,22,.26);
  max-height:380px;
  overflow-y:auto;
  padding:6px;
  display:none;
}}
.ss-hdr {{ font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--mut); padding:6px 10px 4px; display:flex; justify-content:space-between; }}
.ss-item {{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 10px; border-radius:10px; cursor:pointer; font-size:13px; color:var(--txt); }}
.ss-item:hover, .ss-item.hi {{ background:var(--hover); }}
.ss-item.picked {{ opacity:.55; }}
.ss-main {{ min-width:0; display:flex; flex-direction:column; gap:1px; }}
.ss-title {{ font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ss-sub {{ font-size:11px; color:var(--mut); }}
.ss-badge {{ font-size:10.5px; font-weight:700; padding:2px 8px; border-radius:999px; background:var(--hover); color:var(--pine); border:1px solid var(--line); white-space:nowrap; flex-shrink:0; }}
[data-theme="dark"] .ss-badge {{ color:var(--brass); }}
.ss-item.picked .ss-badge {{ background:var(--pine); color:#f6f1e7; border-color:var(--pine); }}

#locChipsBar {{
  display:none;
  flex-wrap:wrap;
  align-items:center;
  gap:6px;
  padding:7px 14px;
  background:var(--card);
  border-bottom:1px solid var(--line);
}}
.loc-chip {{
  display:inline-flex;
  align-items:center;
  gap:6px;
  background:var(--pine);
  color:#f6f1e7;
  border:1px solid rgba(196,158,92,.65);
  border-radius:999px;
  padding:3px 10px 3px 11px;
  font-size:12px;
  font-weight:600;
}}
[data-theme="dark"] .loc-chip {{ background:var(--brass); color:#111715; }}
.loc-chip button {{ background:none; border:none; color:inherit; font-size:14px; line-height:1; cursor:pointer; padding:0; opacity:.85; }}
.loc-chip button:hover {{ opacity:1; }}
.loc-chip-hint {{ font-size:11px; color:var(--mut); margin-left:4px; }}
.loc-chip-clr {{ margin-left:auto; background:none; border:none; color:var(--pri); font-size:11.5px; font-weight:600; cursor:pointer; }}

body.gallery-mode {mp_sel}, body.gallery-mode #map {{ display:none !important; }}
body.gallery-mode {lp_sel} {{ width:100% !important; max-width:100% !important; min-width:0 !important; flex:1 1 100% !important; border-right:none !important; }}
body.gallery-mode #cardList {{ grid-template-columns:repeat(auto-fill, minmax(285px, 1fr)) !important; gap:18px !important; padding:18px 26px 64px !important; }}
body.gallery-mode .fc-media {{ height:172px !important; min-height:172px !important; }}
"""
css_p.write_text(css.rstrip() + "\n" + V15_6_CSS, encoding="utf-8")

# 4. Upgrade web/app.js -> Clear Cluster Price Ranges (₹16k–2L · 3), Multi-Locality Search (up to 5) & All Controls
js = js.replace(
    'if (!b) { b = { items: [], lat: 0, lng: 0, minP: Infinity }; buckets.set(key, b); }',
    'if (!b) { b = { items: [], lat: 0, lng: 0, minP: Infinity, maxP: 0 }; buckets.set(key, b); }',
)
js = js.replace(
    'const pv = getP(s); if (pv > 0 && pv < b.minP) b.minP = pv;',
    'const pv = getP(s); if (pv > 0) { if (pv < b.minP) b.minP = pv; if (pv > b.maxP) b.maxP = pv; }',
)
js = js.replace(
    'const label = b.minP < Infinity ? `${fmtPill(b.minP, st.mode === "buy")}+` : "Homes";',
    'const loS = b.minP < Infinity ? fmtPill(b.minP, st.mode === "buy") : "";\n        const hiS = b.maxP > 0 ? fmtPill(b.maxP, st.mode === "buy").replace(/^₹/, "") : "";\n        const label = !loS ? "Homes" : (hiS && b.maxP > b.minP * 1.15 ? `${loS}–${hiS}` : loS);',
)

if "st.multiLocs" not in js:
    js = js.replace(
        "  function passesV15SocietyFilter(s) {\n    if (!matchingUnits(s).length) return false;",
        "  function passesV15SocietyFilter(s) {\n    if (Array.isArray(st.multiLocs) && st.multiLocs.length && !st.multiLocs.includes(s.locality)) return false;\n    if (!matchingUnits(s).length) return false;",
        1,
    )

for start_m, end_m in (
    ("/* === V15.5 INTERACTIVE CONTROLS === */", "/* === END V15.5 CONTROLS === */"),
    ("/* === V15.6 INTERACTIVE CONTROLS === */", "/* === END V15.6 CONTROLS === */"),
):
    p0 = js.find(start_m)
    if p0 >= 0:
        p1 = js.find(end_m, p0)
        if p1 >= 0: js = js[:p0] + js[p1 + len(end_m):]

V15_6_JS = """
  /* === V15.6 INTERACTIVE CONTROLS === */
  if (st.seaview === undefined) st.seaview = false;
  if (st.balcony === undefined) st.balcony = false;
  if (st.terrace === undefined) st.terrace = false;
  if (st.drop === undefined) st.drop = false;
  if (!st.lister) st.lister = "ALL";
  if (!st.view) st.view = "split";
  if (!st.hub) st.hub = "ALL";
  if (!st.hubMin) st.hubMin = 45;
  if (!Array.isArray(st.multiLocs)) st.multiLocs = [];

  const MAX_MULTI_LOCS = 5;
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

  // Smart Search Autocomplete + Multi-Locality Picker (pick up to 5 localities at once!)
  const sInput = $("searchInput");
  let ssBox = $("searchSuggest");
  if (!ssBox && document.body && document.body.appendChild) {
    ssBox = document.createElement("div");
    ssBox.id = "searchSuggest";
    document.body.appendChild(ssBox);
  }
  let locBar = $("locChipsBar");
  const cardListEl = $("cardList");
  if (!locBar && cardListEl && cardListEl.parentNode && cardListEl.parentNode.insertBefore) {
    locBar = document.createElement("div");
    locBar.id = "locChipsBar";
    cardListEl.parentNode.insertBefore(locBar, cardListEl);
  }

  function fitToSelectedLocalities() {
    if (!st.multiLocs.length || typeof L === "undefined") return;
    const pts = societies.filter(s => st.multiLocs.includes(s.locality) && s.lat && s.lng).map(s => [s.lat, s.lng]);
    if (pts.length >= 2 && typeof map.fitBounds === "function") {
      try { map.fitBounds(L.latLngBounds(pts).pad(0.18), { maxZoom: 14, animate: true }); } catch {}
    } else if (pts.length === 1) {
      map.flyTo(pts[0], 14, { duration: 0.5 });
    }
  }

  function renderLocChips() {
    if (!locBar) return;
    if (!st.multiLocs.length) { locBar.style.display = "none"; locBar.innerHTML = ""; return; }
    locBar.style.display = "flex";
    const rem = MAX_MULTI_LOCS - st.multiLocs.length;
    locBar.innerHTML = st.multiLocs.map(loc =>
      `<span class="loc-chip">${esc(loc)}<button type="button" data-rmloc="${esc(loc)}" aria-label="Remove ${esc(loc)}">×</button></span>`
    ).join("") +
      (rem > 0 ? `<span class="loc-chip-hint">+ Add up to ${rem} more in search</span>` : `<span class="loc-chip-hint">Max ${MAX_MULTI_LOCS} localities</span>`) +
      `<button type="button" class="loc-chip-clr" id="clearLocChips">Clear</button>`;
    locBar.querySelectorAll("[data-rmloc]").forEach(b => {
      b.onclick = () => {
        st.multiLocs = st.multiLocs.filter(x => x !== b.dataset.rmloc);
        renderLocChips(); st.page = 36; renderAll();
      };
    });
    const clr = $("clearLocChips");
    if (clr) clr.onclick = () => { st.multiLocs = []; renderLocChips(); st.page = 36; renderAll(); };
  }

  function addMultiLocality(loc) {
    if (!loc) return;
    if (st.multiLocs.includes(loc)) {
      st.multiLocs = st.multiLocs.filter(x => x !== loc);
    } else {
      if (st.multiLocs.length >= MAX_MULTI_LOCS) st.multiLocs.shift();
      st.multiLocs.push(loc);
    }
    if ($("fZone") && $("fZone").value !== "ALL") $("fZone").value = "ALL";
    if ($("fLoc") && $("fLoc").value !== "ALL") $("fLoc").value = "ALL";
    if (st.zone && st.zone !== "ALL") st.zone = "ALL";
    document.querySelectorAll(".zone-pill, [data-zone]").forEach(z => z.classList.toggle("active", z.dataset.zone === "ALL"));
    if (sInput) sInput.value = "";
    if ("q" in st) st.q = "";
    renderLocChips();
    st.page = 36;
    renderAll();
    fitToSelectedLocalities();
  }

  let ssHi = -1;
  function positionSuggest() {
    if (!ssBox || !sInput || !sInput.getBoundingClientRect) return;
    const r = sInput.getBoundingClientRect();
    ssBox.style.left = Math.max(12, r.left - 18) + "px";
    ssBox.style.top  = (r.bottom + 8) + "px";
    ssBox.style.width = Math.max(340, Math.min(480, r.width + 80)) + "px";
  }

  function buildSuggestions(rawQ) {
    if (!ssBox) return;
    const q = (rawQ || "").trim().toLowerCase();
    const isBuy = st.mode === "buy";

    const locMap = new Map();
    for (const s of societies) {
      if (!s.locality) continue;
      const uLen = ((isBuy ? s.units_buy : s.units_rent) || []).length;
      if (!uLen) continue;
      let g = locMap.get(s.locality);
      if (!g) { g = { loc: s.locality, zone: s.zone || "", flats: 0, socs: 0 }; locMap.set(s.locality, g); }
      g.flats += uLen; g.socs += 1;
    }

    let locList = [...locMap.values()];
    if (q) locList = locList.filter(x => x.loc.toLowerCase().includes(q) || x.zone.toLowerCase().includes(q));
    locList.sort((a, b) => {
      const aPre = q && a.loc.toLowerCase().startsWith(q) ? 1 : 0;
      const bPre = q && b.loc.toLowerCase().startsWith(q) ? 1 : 0;
      return (bPre - aPre) || (b.flats - a.flats);
    });
    locList = locList.slice(0, q ? 6 : 7);

    let socList = [];
    if (q.length >= 2) {
      socList = societies.filter(s => {
        const uLen = ((isBuy ? s.units_buy : s.units_rent) || []).length;
        return uLen > 0 && (s.name || "").toLowerCase().includes(q);
      }).sort((a, b) => ((b.coords_approx ? 0 : 1) - (a.coords_approx ? 0 : 1)) || ((b.google?.rating || 0) - (a.google?.rating || 0))).slice(0, 5);
    }

    const featHints = [
      { k: "balcony", lbl: "Balcony flats", kw: "balcony sitout verandah" },
      { k: "terrace", lbl: "Terrace / Garden flats", kw: "terrace garden lawn deck patio" },
      { k: "seaview", lbl: "Sea View flats (Coast verified)", kw: "sea view ocean arabian beach waterfront" },
      { k: "drop", lbl: "Recent Price Drops", kw: "price drop discount deal" },
    ].filter(f => q.length >= 2 && f.kw.includes(q));

    if (!locList.length && !socList.length && !featHints.length) {
      ssBox.style.display = "none"; return;
    }

    let h = "";
    if (locList.length) {
      h += `<div class="ss-hdr"><span>Localities (pick up to ${MAX_MULTI_LOCS})</span><span>${st.multiLocs.length}/${MAX_MULTI_LOCS} selected</span></div>`;
      h += locList.map(x => {
        const picked = st.multiLocs.includes(x.loc);
        return `<div class="ss-item${picked ? " picked" : ""}" data-ss-type="loc" data-ss-val="${esc(x.loc)}">
          <div class="ss-main"><div class="ss-title">${esc(x.loc)}</div><div class="ss-sub">${esc(x.zone)} · ${x.flats.toLocaleString("en-IN")} flats</div></div>
          <span class="ss-badge">${picked ? "✓ Added" : "+ Add"}</span>
        </div>`;
      }).join("");
    }
    if (socList.length) {
      h += `<div class="ss-hdr"><span>Buildings & Societies</span><span>Jump to flat</span></div>`;
      h += socList.map(s => {
        const us = (isBuy ? s.units_buy : s.units_rent) || [];
        const pTxt = us.length ? fmt(us[0].p, isBuy) : "";
        return `<div class="ss-item" data-ss-type="soc" data-ss-val="${esc(s.id)}">
          <div class="ss-main"><div class="ss-title">${esc(s.name)}</div><div class="ss-sub">${esc(s.locality)} · ${us.length} unit${us.length > 1 ? "s" : ""}</div></div>
          <span class="ss-badge">${esc(pTxt)}</span>
        </div>`;
      }).join("");
    }
    if (featHints.length) {
      h += `<div class="ss-hdr"><span>Feature Filters</span><span>1-click</span></div>`;
      h += featHints.map(f =>
        `<div class="ss-item" data-ss-type="feat" data-ss-val="${f.k}">
          <div class="ss-main"><div class="ss-title">${esc(f.lbl)}</div><div class="ss-sub">Toggle quick filter</div></div>
          <span class="ss-badge">${st[f.k] ? "Active" : "Apply"}</span>
        </div>`
      ).join("");
    }

    ssBox.innerHTML = h;
    ssHi = -1;
    positionSuggest();
    ssBox.style.display = "block";

    ssBox.querySelectorAll(".ss-item").forEach(el => {
      el.onmousedown = e => {
        e.preventDefault();
        const tp = el.dataset.ssType, val = el.dataset.ssVal;
        if (tp === "loc") {
          addMultiLocality(val);
          buildSuggestions("");
        } else if (tp === "soc") {
          ssBox.style.display = "none";
          const soc = societies.find(x => x.id === val);
          if (soc) {
            if (sInput) sInput.value = soc.name;
            if (soc.lat && soc.lng) map.flyTo([soc.lat, soc.lng], 16, { duration: 0.5 });
            if (typeof openDetail === "function") openDetail(soc);
          }
        } else if (tp === "feat") {
          ssBox.style.display = "none";
          if (sInput) sInput.value = "";
          st[val] = true;
          document.querySelectorAll(`.chip[data-q="${val}"]`).forEach(c => { c.classList.add("on", "active"); });
          st.page = 36; renderAll();
        }
      };
    });
  }

  if (sInput && ssBox) {
    sInput.addEventListener("focus", () => buildSuggestions(sInput.value));
    sInput.addEventListener("input", () => buildSuggestions(sInput.value));
    sInput.addEventListener("keydown", e => {
      const items = [...ssBox.querySelectorAll(".ss-item")];
      if (e.key === "Backspace" && !sInput.value && st.multiLocs.length) {
        st.multiLocs.pop(); renderLocChips(); st.page = 36; renderAll(); return;
      }
      if (!items.length || ssBox.style.display === "none") return;
      if (e.key === "ArrowDown") { e.preventDefault(); ssHi = (ssHi + 1) % items.length; items.forEach((x, i) => x.classList.toggle("hi", i === ssHi)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); ssHi = (ssHi - 1 + items.length) % items.length; items.forEach((x, i) => x.classList.toggle("hi", i === ssHi)); }
      else if (e.key === "Enter" && ssHi >= 0) { e.preventDefault(); items[ssHi].onmousedown({ preventDefault(){} }); }
      else if (e.key === "Escape") { ssBox.style.display = "none"; }
    });
    document.addEventListener("click", e => {
      if (e.target !== sInput && !ssBox.contains(e.target)) ssBox.style.display = "none";
    });
  }

  window.__BH_ADD_LOC = addMultiLocality;

  ["resetMiniBtn", "resetBtn", "fReset"].forEach(id => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("click", () => {
      st.seaview = st.balcony = st.terrace = st.drop = false;
      st.lister = "ALL"; st.hub = "ALL"; st.multiLocs = [];
      if ($("fHub")) $("fHub").value = "";
      if ($("hubVal")) $("hubVal").textContent = "Any";
      document.querySelectorAll(".chip[data-q]").forEach(b => {
        if (V15_CHIP_KEYS.has(b.dataset.q)) b.classList.remove("on", "active");
      });
      document.querySelectorAll("#listerToggle button").forEach(x => x.classList.toggle("active", x.dataset.lt === "ALL"));
      renderLocChips();
      setTimeout(() => renderAll(), 0);
    });
  });

  document.addEventListener("keydown", e => {
    if (e.key === "/" && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName)) {
      e.preventDefault(); $("searchInput")?.focus();
    } else if (e.key === "Escape") {
      if (ssBox) ssBox.style.display = "none";
      ["detailSheet","filterSheet"].forEach(id => $(id)?.classList.remove("open"));
      ["savedModal","postModal"].forEach(id => { if ($(id)) $(id).style.display = "none"; });
    }
  });
  /* === END V15.6 CONTROLS === */
"""

close_idx = js.rfind("})();")
assert close_idx > 0, "Could not locate closing })(); in web/app.js"
js = js[:close_idx] + V15_6_JS + "\n" + js[close_idx:]
js_p.write_text(js, encoding="utf-8")

# 5. Interactive Node.js Verification Suite: Initial Load + 3-Locality Picker + Every New Button!
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
  const cls = new Set(), listeners = {{}};
  const defVal = Object.prototype.hasOwnProperty.call(DEFAULTS, id) ? DEFAULTS[id] : "";
  return {{
    id, value: defVal, textContent: "", innerHTML: "", style: {{}}, dataset, checked: false, rel: "", href: "",
    selectedOptions: [{{ text: defVal || "Any" }}],
    options: [{{ value: defVal, text: defVal || "Any" }}],
    parentNode: {{ insertBefore() {{}} }},
    contains: () => false,
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
    getBoundingClientRect: () => ({{ width: 320, height: 38, top: 10, left: 200, bottom: 48 }}),
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
    latLngBounds: () => ({{ pad: () => ({{}}) }}), circle: mkLayer, circleMarker: mkLayer,
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
  console.log("[TEST] Initial All   :", initC, "flats");
  if (caughtErr || initC === 0) {{ console.error("INITIAL FAIL", caughtErr); process.exit(1); }}

  sandbox.__BH_ADD_LOC("Bandra West"); const c1 = flatCount();
  sandbox.__BH_ADD_LOC("Khar West"); const c2 = flatCount();
  sandbox.__BH_ADD_LOC("Santacruz West"); const c3 = flatCount();
  console.log("[TEST] Multi-Locs    : Bandra W=" + c1 + " | +Khar W=" + c2 + " | +Santacruz W=" + c3);
  sandbox.__BH_ADD_LOC("Bandra West"); sandbox.__BH_ADD_LOC("Khar West"); sandbox.__BH_ADD_LOC("Santacruz West");

  listerBtns[1].click(); const ownC = flatCount(); console.log("[TEST] Owner         :", ownC, "flats");
  listerBtns[2].click(); const brkC = flatCount(); console.log("[TEST] Broker        :", brkC, "flats");
  listerBtns[3].click(); const shrC = flatCount(); console.log("[TEST] Shared        :", shrC, "flats");
  listerBtns[0].click();

  chipBtns[1].click(); const balC = flatCount(); console.log("[TEST] Balcony       :", balC, "flats"); chipBtns[1].click();
  chipBtns[2].click(); const terC = flatCount(); console.log("[TEST] Terrace/Gdn   :", terC, "flats"); chipBtns[2].click();
  chipBtns[0].click(); const seaC = flatCount(); console.log("[TEST] Sea View      :", seaC, "flats"); chipBtns[0].click();
  chipBtns[3].click(); const drpC = flatCount(); console.log("[TEST] Price Drop    :", drpC, "flats"); chipBtns[3].click();

  viewBtns[1].click(); const galOn = bodyEl.classList.contains("gallery-mode");
  viewBtns[0].click(); const galOff = !bodyEl.classList.contains("gallery-mode");
  console.log("[TEST] Map/Gallery   :", (galOn && galOff) ? "PASS" : "FAIL");

  if (!galOn || !galOff || !(c1 > 0 && c2 > c1 && c3 > c2) || ownC >= initC || brkC >= initC || balC >= initC || seaC >= initC) {{
    console.error("[TEST] FAILED: One or more controls did not filter results!");
    process.exit(1);
  }}
  console.log("[TEST] ALL CONTROLS + 3-LOCALITY SEARCH PASS! Safe to deploy!");
}}, 180);
"""
r = subprocess.run(["node", "-e", SMOKE_JS], text=True)
sys.exit(r.returncode)
