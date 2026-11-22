import json, re, subprocess, sys
from pathlib import Path

def write(rel: str, txt: str):
    p = Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt.lstrip("\n"), encoding="utf-8")

# 1. Cloudflare Pages Edge Photo Gallery API: functions/api/photos.js (24h edge-cached)
write("functions/api/photos.js", r"""
const ALLOWED_HOSTS = new Set([
  "www.magicbricks.com", "magicbricks.com",
  "www.nobroker.in", "nobroker.in",
  "www.squareyards.com", "squareyards.com",
  "www.makaan.com", "makaan.com",
  "www.commonfloor.com", "commonfloor.com",
  "www.99acres.com", "99acres.com",
  "housing.com", "www.housing.com",
]);

const BAD_IMG = /(logo|icon|avatar|placeholder|default|spinner|loader|blank|pixel|badge|sprite|banner|ads|verified|watermark|brochure|map|qrcode|playstore|appstore|whatsapp|facebook|twitter|instagram|youtube|no[-_]?image|no[-_]?photo|agent|broker|owner[-_]?img|profile|user[-_]?pic|1x1|\.svg(?:\?|$)|\.gif(?:\?|$))/i;
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

function cleanUrl(raw) {
  if (!raw || typeof raw !== "string") return null;
  let u = raw.trim().replace(/\\u002F/gi, "/").replace(/\\\//g, "/").replace(/&/g, "&");
  if (u.startsWith("//")) u = "https:" + u;
  if (!u.startsWith("http://") && !u.startsWith("https://")) return null;
  if (u.length < 24 || u.length > 500) return null;
  if (BAD_IMG.test(u)) return null;
  return u;
}

function dedupeKey(u) {
  return u
    .split("?")[0]
    .replace(/\/(thumb|medium|small|large|original|cropped|resized)\//gi, "/")
    .replace(/_\d+x\d+(?=\.[a-z]+$)/i, "")
    .replace(/-(?:small|medium|large|thumb|original)(?=\.[a-z]+$)/i, "")
    .toLowerCase();
}

function upgradeRes(u) {
  if (u.includes("img.staticmb.com/mbphoto/property")) return u.replace(/_\d+_\d+\./, "_600_800.");
  if (u.includes("images.nobroker.in/images/")) return u.replace(/_thumbnail\./i, "_medium.").replace(/_small\./i, "_medium.");
  return u;
}

function extractPhotos(html, host, targetUrl) {
  const out = [], seen = new Set();
  const add = raw => {
    const u = cleanUrl(raw);
    if (!u) return;
    const up = upgradeRes(u);
    const dk = dedupeKey(up);
    if (seen.has(dk)) return;
    seen.add(dk); out.push(up);
  };

  if (host.includes("magicbricks")) {
    for (const m of html.matchAll(/https?:\/\/img\.staticmb\.com\/mbphoto\/property\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
    for (const m of html.matchAll(/https?:\/\/img\.staticmb\.com\/mbimages\/project\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
  }
  if (host.includes("nobroker")) {
    for (const m of html.matchAll(/https?:\/\/images\.nobroker\.in\/images\/[a-f0-9]{16,32}\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
    const idM = targetUrl.match(/([a-f0-9]{24,32})/i) || html.match(/"propertyId"\s*:\s*"([a-f0-9]{20,32})"/i) || html.match(/"id"\s*:\s*"([a-f0-9]{24,32})"/i);
    if (idM) {
      const pid = idM[1];
      for (const m of html.matchAll(/"(?:large|medium|original)"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp))"/gi)) {
        const fn = m[1];
        add(fn.startsWith("http") ? fn : ("https:" + "//images.nobroker.in/images/" + pid + "/" + fn));
      }
    }
  }
  if (host.includes("squareyards")) {
    for (const m of html.matchAll(/https?:\/\/(?:img|static)\.squareyards\.com\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) {
      if (/\/secondaryPortal\/|\/project\/|\/property\/|\/cdn-cgi\//i.test(m[0])) add(m[0]);
    }
  }
  if (host.includes("makaan") || host.includes("housing")) {
    for (const m of html.matchAll(/https?:\/\/(?:im\.proptiger\.com|housing-images\.n7net\.in|is1-\d+\.housingcdn\.com)\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
  }
  if (host.includes("commonfloor")) {
    for (const m of html.matchAll(/https?:\/\/[^\s"'<>\\]*commonfloor\.com\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
  }
  if (host.includes("99acres")) {
    for (const m of html.matchAll(/https?:\/\/(?:imagecdn\.99acres\.com|mediacdn\.99acres\.com)\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
  }

  for (const m of html.matchAll(/"(?:image|imageUrl|photoUrl|originalUrl)"\s*:\s*"(https?:\/\/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"/gi)) add(m[1]);
  for (const m of html.matchAll(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/gi)) add(m[1]);

  return out.slice(0, 12);
}

export async function onRequestGet(context) {
  const reqUrl = new URL(context.request.url);
  const target = reqUrl.searchParams.get("url") || "";
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "public, max-age=86400",
    "access-control-allow-origin": "*",
  };

  let parsed;
  try { parsed = new URL(target); }
  catch { return new Response(JSON.stringify({ photos: [], error: "invalid url" }), { status: 400, headers }); }

  if (!ALLOWED_HOSTS.has(parsed.hostname.toLowerCase())) {
    return new Response(JSON.stringify({ photos: [], error: "host not allowed" }), { status: 403, headers });
  }

  const cache = caches.default;
  const cacheKey = new Request(reqUrl.toString(), { method: "GET" });
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  try {
    const resp = await fetch(parsed.toString(), {
      headers: {
        "user-agent": UA,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-IN,en;q=0.9",
        "referer": parsed.origin + "/",
      },
      redirect: "follow",
    });
    if (!resp.ok) return new Response(JSON.stringify({ photos: [], status: resp.status }), { status: 200, headers });
    const html = await resp.text();
    const photos = extractPhotos(html, parsed.hostname.toLowerCase(), parsed.toString());
    const outResp = new Response(JSON.stringify({ photos }), { status: 200, headers });
    if (photos.length > 0) context.waitUntil(cache.put(cacheKey, outResp.clone()));
    return outResp;
  } catch (err) {
    return new Response(JSON.stringify({ photos: [], error: String(err) }), { status: 200, headers });
  }
}
""")

# 2. Auto-discover REAL Search Input ID & Layout Selectors from web/index.html
html_p = Path("web/index.html")
html = html_p.read_text(encoding="utf-8")
css_p = Path("web/styles.css")
css = css_p.read_text(encoding="utf-8")
js_p = Path("web/app.js")
js = js_p.read_text(encoding="utf-8")

search_id = None
for m in re.finditer(r'<input\b([^>]+)>', html, re.I):
    attrs = m.group(1)
    id_m = re.search(r'\bid=["\']([^"\']+)["\']', attrs)
    ph_m = re.search(r'\bplaceholder=["\']([^"\']+)["\']', attrs)
    tp_m = re.search(r'\btype=["\']([^"\']+)["\']', attrs)
    tp = (tp_m.group(1) if tp_m else "text").lower()
    if tp in ("range", "checkbox", "radio", "number", "hidden"): continue
    ph = (ph_m.group(1) if ph_m else "").lower()
    iid = id_m.group(1) if id_m else ""
    if ("search" in ph or "bandra" in ph or "locality" in ph or "society" in ph or "search" in iid.lower() or iid.lower() in ("q", "query")):
        search_id = iid
        print(f"[v16] Discovered REAL search input -> id='{search_id}' | placeholder='{ph_m.group(1) if ph_m else ''}'", flush=True)
        break

assert search_id, "Could not discover search <input> in web/index.html!"

html = re.sub(
    rf'(id="{re.escape(search_id)}"[^>]*placeholder=")[^"]*(")',
    r'\1Search up to 5 localities (Bandra, Khar, Santacruz) or society…\2',
    html,
    count=1,
)
html = re.sub(
    r'(<select\b[^>]*id="sortSelect"[^>]*)(>)',
    lambda m: m.group(0) if 'display:none' in m.group(1) else m.group(1) + ' style="display:none"' + m.group(2),
    html,
    count=1,
)
html_p.write_text(html, encoding="utf-8")

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

# 3. Upgrade web/styles.css -> Photo Carousel + Resizable Split Pane + Unclipped Chips + Hide Sort
for marker in ("/* v15.7: Resizable Split Pane", "/* v16: Photo Carousel"):
    idx_m = css.find(marker)
    if idx_m >= 0: css = css[:idx_m].rstrip()

ws_resize_css = ""
if ws_sel and ws_sel not in ("body", "html"):
    ws_resize_css = f"""
@media (min-width: 901px) {{
  {ws_sel} {{ grid-template-columns: var(--pane-w, 560px) minmax(240px, 1fr) !important; }}
}}
body.gallery-mode {ws_sel} {{ display:block !important; grid-template-columns:1fr !important; }}
"""

V16_CSS = f"""
/* v16: Photo Carousel (Cards + Detail Sheet), Resizable Split Pane, Unclipped Chips & Hide Sort */
:root {{ --pane-w: 560px; }}
#sortSelect, .sort-sel {{ display:none !important; }}

{ch_sel} {{
  display:flex !important; align-items:center !important; flex-wrap:nowrap !important;
  gap:5px !important; overflow-x:auto !important; scrollbar-width:none !important;
  padding-right:16px !important; min-width:0 !important; flex:1 1 auto !important;
}}
{ch_sel}::-webkit-scrollbar {{ display:none; }}
{ch_sel} .chip {{ padding:4px 9px !important; font-size:11.5px !important; white-space:nowrap !important; }}

{ws_resize_css}
@media (min-width: 901px) {{
  {lp_sel} {{ width:var(--pane-w, 560px) !important; min-width:290px !important; max-width:82vw !important; flex:0 0 var(--pane-w, 560px) !important; }}
  {mp_sel} {{ position:relative !important; min-width:240px !important; flex:1 1 auto !important; }}
}}
#cardList {{ grid-template-columns:repeat(auto-fill, minmax(235px, 1fr)) !important; }}
@media (max-width: 900px) {{ #cardList {{ grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)) !important; }} }}

.fc-nav {{
  position:absolute; top:50%; transform:translateY(-50%); z-index:4;
  width:28px; height:28px; border-radius:999px;
  border:1px solid rgba(255,255,255,.42); background:rgba(16,28,25,.66); color:#fff;
  display:grid; place-items:center; cursor:pointer; font-size:17px; line-height:1; padding:0 0 2px 0;
  backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  opacity:.82; transition:opacity .15s, background .15s, transform .15s;
}}
.fc-nav.prev {{ left:7px; }}
.fc-nav.next {{ right:7px; }}
.fc-nav:hover {{ opacity:1; background:rgba(16,28,25,.92); border-color:var(--brass); transform:translateY(-50%) scale(1.06); }}
.fc-pcount {{
  position:absolute; bottom:7px; right:8px; z-index:4;
  font-family:var(--font-body); font-size:10px; font-weight:700; font-variant-numeric:tabular-nums;
  padding:2px 7px; border-radius:999px; background:rgba(16,28,25,.72); color:#f6f1e7;
  border:1px solid rgba(255,255,255,.22); backdrop-filter:blur(6px); pointer-events:none;
}}
.d-gal-wrap {{
  position:relative; width:100%; height:220px; border-radius:13px; overflow:hidden;
  border:1px solid var(--line); background:var(--hover); margin-bottom:10px;
}}
.d-gal-wrap .d-hero {{ width:100% !important; height:100% !important; object-fit:cover !important; border:none !important; border-radius:0 !important; display:block; }}
.d-gal-wrap .fc-nav {{ width:34px; height:34px; font-size:20px; opacity:.92; }}

#paneResizer {{ position:absolute; top:0; left:0; bottom:0; width:12px; z-index:1150; cursor:col-resize; touch-action:none; user-select:none; background:transparent; transition:background .15s ease; }}
#paneResizer:hover, body.resizing-pane #paneResizer {{ background:rgba(196,158,92,.22); }}
#paneResizer::after {{
  content:""; position:absolute; top:50%; left:0; transform:translateY(-50%); width:14px; height:52px;
  border-radius:0 9px 9px 0; background:var(--card); border:1px solid var(--line); border-left:none;
  box-shadow:3px 0 12px rgba(22,42,39,.14);
  background-image:radial-gradient(circle, rgba(22,42,39,.48) 1.3px, transparent 1.5px);
  background-size:6px 7px; background-position:center; background-repeat:repeat-y;
  transition:background-color .15s, border-color .15s, width .15s;
}}
[data-theme="dark"] #paneResizer::after {{ background-image:radial-gradient(circle, rgba(196,158,92,.75) 1.3px, transparent 1.5px); }}
#paneResizer:hover::after, body.resizing-pane #paneResizer::after {{ width:17px; border-color:var(--brass); background-color:var(--pine); background-image:radial-gradient(circle, #e8cfa0 1.4px, transparent 1.6px); }}
body.resizing-pane {{ cursor:col-resize !important; user-select:none !important; }}
body.resizing-pane #map {{ pointer-events:none !important; }}
body.gallery-mode #paneResizer {{ display:none !important; }}
@media (max-width: 900px) {{ #paneResizer {{ display:none !important; }} }}
"""
css_p.write_text(css.rstrip() + "\n" + V16_CSS, encoding="utf-8")

# 4. Upgrade web/app.js -> REAL search input ID, strict relevance, Next/Prev Photo Carousel & Resizer
js = js.replace('const sInput = $("searchInput");', f'const sInput = $("{search_id}");')
js = js.replace('$("searchInput")?.focus();', f'$("{search_id}")?.focus();')

if "/* v16_strict_search */" not in js:
    strict_search_line = (
        f'    const _tq = (document.getElementById("{search_id}")?.value || "").trim().toLowerCase();\n'
        '    if (_tq && (!Array.isArray(st.multiLocs) || !st.multiLocs.length)) {\n'
        '      const _relHay = ((s.name || "") + " " + (s.locality || "") + " " + ((s.features?.tags || []).join(" ").replace(/_/g, " ")) + " " + ((s.bhks || []).map(b => b === 0 ? "1 rk studio" : (b + " bhk")).join(" "))).toLowerCase();\n'
        '      if (!_tq.split(/\\s+/).every(tok => _relHay.includes(tok))) return false;\n'
        '    } /* v16_strict_search */\n'
    )
    js = js.replace("  function passesV15SocietyFilter(s) {\n", "  function passesV15SocietyFilter(s) {\n" + strict_search_line, 1)

if "fc-nav next" not in js:
    old_media_close = '<button class="fc-heart${saved ? " on" : ""}" data-save="${esc(s.id)}" aria-label="Save flat">${saved ? "♥" : "♡"}</button>\n          </div>'
    new_media_close = (
        '<button class="fc-heart${saved ? " on" : ""}" data-save="${esc(s.id)}" aria-label="Save flat">${saved ? "♥" : "♡"}</button>\n'
        '            ${img || directHref ? `<button type="button" class="fc-nav prev" data-pdir="-1" aria-label="Previous photo">‹</button><button type="button" class="fc-nav next" data-pdir="1" aria-label="Next photo">›</button><span class="fc-pcount">${Array.isArray(u.imgs) && u.imgs.length > 1 ? `1 / ${u.imgs.length}` : "1 / +"}</span>` : ""}\n'
        '          </div>'
    )
    assert old_media_close in js, "Could not locate .fc-media closing block in web/app.js"
    js = js.replace(old_media_close, new_media_close, 1)

    old_art = '<article class="fc${sel ? " sel" : ""}" data-id="${esc(s.id)}">'
    new_art = '<article class="fc${sel ? " sel" : ""}" data-id="${esc(s.id)}" data-url="${esc(directHref)}" data-img="${esc(img)}">'
    assert old_art in js, "Could not locate <article class=fc> in web/app.js"
    js = js.replace(old_art, new_art, 1)

for sm, em in (
    ("/* === V15.7 RESIZER & CHIP SCROLL === */", "/* === END V15.7 === */"),
    ("/* === V16 GALLERY, SEARCH & RESIZER === */", "/* === END V16 === */"),
):
    p0 = js.find(sm)
    if p0 >= 0:
        p1 = js.find(em, p0)
        if p1 >= 0: js = js[:p0] + js[p1 + len(em):]

V16_JS = f"""
  /* === V16 GALLERY, SEARCH & RESIZER === */
  const realSearchEl = $("{search_id}");
  if (realSearchEl) {{
    let _sTimer = 0;
    realSearchEl.addEventListener("input", () => {{
      clearTimeout(_sTimer);
      _sTimer = setTimeout(() => {{
        const tv = (realSearchEl.value || "").trim().toLowerCase();
        if (tv.length >= 3) {{
          const hitOtherZone = societies.some(s => (s.locality || "").toLowerCase().includes(tv) && $("fZone") && $("fZone").value !== "ALL" && s.zone !== $("fZone").value);
          if (hitOtherZone) {{
            if ($("fZone")) $("fZone").value = "ALL";
            if ($("fLoc")) $("fLoc").value = "ALL";
            if (st.zone && st.zone !== "ALL") st.zone = "ALL";
            document.querySelectorAll(".zone-pill, [data-zone]").forEach(z => z.classList.toggle("active", z.dataset.zone === "ALL"));
          }}
        }}
        st.page = 36;
        renderAll();
      }}, 80);
    }});
  }}

  const PHOTO_CACHE = new Map();

  function collectLocalPhotos(socId, unitUrl, primaryImg) {{
    const out = [], seen = new Set();
    const pushImg = u => {{
      if (!u || typeof u !== "string" || !u.startsWith("http")) return;
      const k = u.split("?")[0].toLowerCase();
      if (seen.has(k)) return;
      seen.add(k); out.push(u);
    }};
    pushImg(primaryImg);
    const s = societies.find(x => x.id === socId);
    if (s) {{
      const allU = [...(s.units_rent || []), ...(s.units_buy || [])];
      const exactU = unitUrl ? allU.find(u => u.u === unitUrl) : null;
      if (exactU && Array.isArray(exactU.imgs)) exactU.imgs.forEach(pushImg);
      pushImg(s.thumb);
      for (const u of allU) {{
        if (u.img) pushImg(u.img);
        if (Array.isArray(u.imgs)) u.imgs.forEach(pushImg);
        if (out.length >= 10) break;
      }}
    }}
    return out;
  }}

  async function fetchFullGallery(socId, unitUrl, primaryImg) {{
    const key = unitUrl || socId;
    if (PHOTO_CACHE.has(key)) return PHOTO_CACHE.get(key);
    const local = collectLocalPhotos(socId, unitUrl, primaryImg);
    if (!unitUrl || !unitUrl.startsWith("http")) {{ PHOTO_CACHE.set(key, local); return local; }}
    try {{
      const r = await fetch(`/api/photos?url=${{encodeURIComponent(unitUrl)}}`);
      if (r.ok) {{
        const d = await r.json();
        const remote = Array.isArray(d.photos) ? d.photos : [];
        const merged = [], seen = new Set();
        for (const u of [...remote, ...local]) {{
          if (!u || typeof u !== "string") continue;
          const dk = u.split("?")[0].toLowerCase();
          if (seen.has(dk)) continue;
          seen.add(dk); merged.push(u);
        }}
        const finalList = merged.slice(0, 12);
        PHOTO_CACHE.set(key, finalList);
        return finalList;
      }}
    }} catch {{}}
    PHOTO_CACHE.set(key, local);
    return local;
  }}

  const clNode = $("cardList");
  if (clNode && clNode.addEventListener) {{
    clNode.addEventListener("click", async e => {{
      const btn = e.target?.closest ? e.target.closest(".fc-nav") : null;
      if (!btn) return;
      e.preventDefault(); e.stopPropagation();
      const card = btn.closest(".fc");
      if (!card) return;
      const dir = Number(btn.dataset.pdir || 1);
      const socId = card.dataset.id || "";
      const unitUrl = card.dataset.url || "";
      const baseImg = card.dataset.img || "";
      const media = card.querySelector(".fc-media");
      const cntEl = card.querySelector(".fc-pcount");
      if (!media) return;

      let photos = card._photos;
      if (!photos) {{
        if (cntEl) cntEl.textContent = "…";
        photos = await fetchFullGallery(socId, unitUrl, baseImg);
        card._photos = photos; card._pIdx = 0;
      }}
      if (!photos.length) {{ if (cntEl) cntEl.textContent = "No photos"; return; }}
      if (photos.length === 1) {{ if (cntEl) cntEl.textContent = "1 / 1"; return; }}
      const nextIdx = ((card._pIdx || 0) + dir + photos.length) % photos.length;
      card._pIdx = nextIdx;

      let imgEl = media.querySelector("img.fc-img");
      if (!imgEl) {{
        imgEl = document.createElement("img");
        imgEl.className = "fc-img"; imgEl.referrerPolicy = "no-referrer"; imgEl.alt = "";
        media.insertBefore(imgEl, media.firstChild?.nextSibling || null);
      }}
      imgEl.src = photos[nextIdx];
      if (cntEl) cntEl.textContent = `${{nextIdx + 1}} / ${{photos.length}}`;
    }}, true);
  }}

  const dsNode = $("detailSheet");
  if (dsNode && typeof MutationObserver !== "undefined") {{
    const upgradeDetailGallery = () => {{
      if (!dsNode.classList.contains("open") || dsNode.querySelector(".d-gal-wrap")) return;
      const soc = societies.find(x => x.id === st.selectedId);
      if (!soc) return;
      const us = ((st.mode === "buy") ? soc.units_buy : soc.units_rent) || [];
      const topU = us[0] || {{}};
      const hero = dsNode.querySelector("img.d-hero");
      const bodyHost = hero ? hero.parentNode : dsNode.querySelector(".d-body, .sheet-body");
      if (!bodyHost) return;

      const wrap = document.createElement("div"); wrap.className = "d-gal-wrap";
      const img = document.createElement("img"); img.className = "d-hero"; img.referrerPolicy = "no-referrer";
      img.src = (hero && hero.src) || topU.img || soc.thumb || "";
      const prev = document.createElement("button"); prev.type = "button"; prev.className = "fc-nav prev"; prev.textContent = "‹";
      const next = document.createElement("button"); next.type = "button"; next.className = "fc-nav next"; next.textContent = "›";
      const cnt = document.createElement("span"); cnt.className = "fc-pcount"; cnt.textContent = "Loading…";
      wrap.appendChild(img); wrap.appendChild(prev); wrap.appendChild(next); wrap.appendChild(cnt);

      if (hero) bodyHost.replaceChild(wrap, hero);
      else if (img.src) bodyHost.insertBefore(wrap, bodyHost.firstChild);
      else return;

      let dPhotos = collectLocalPhotos(soc.id, topU.u, img.src), dIdx = 0;
      const paint = () => {{
        if (!dPhotos.length) {{ wrap.style.display = "none"; return; }}
        img.src = dPhotos[dIdx];
        cnt.textContent = `${{dIdx + 1}} / ${{dPhotos.length}}`;
        prev.style.display = next.style.display = dPhotos.length > 1 ? "grid" : "none";
      }};
      paint();
      prev.onclick = () => {{ dIdx = (dIdx - 1 + dPhotos.length) % dPhotos.length; paint(); }};
      next.onclick = () => {{ dIdx = (dIdx + 1) % dPhotos.length; paint(); }};
      fetchFullGallery(soc.id, topU.u, img.src).then(full => {{
        if (full && full.length) {{ dPhotos = full; dIdx = Math.min(dIdx, dPhotos.length - 1); paint(); }}
      }});
    }};
    new MutationObserver(upgradeDetailGallery).observe(dsNode, {{ childList: true, subtree: true, attributes: true, attributeFilter: ["class"] }});
  }}

  const chipStrip = document.querySelector("{ch_sel}");
  if (chipStrip && chipStrip.addEventListener) {{
    chipStrip.addEventListener("wheel", e => {{
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && chipStrip.scrollWidth > chipStrip.clientWidth) {{
        e.preventDefault(); chipStrip.scrollLeft += e.deltaY;
      }}
    }}, {{ passive: false }});
  }}

  const mapHost = document.querySelector("{mp_sel}") || $("map");
  if (mapHost && mapHost.appendChild && !$("paneResizer")) {{
    const handle = document.createElement("div");
    handle.id = "paneResizer"; handle.title = "Drag to resize panel · Double-click to reset";
    handle.setAttribute("role", "separator"); handle.setAttribute("aria-orientation", "vertical");
    mapHost.appendChild(handle);

    const DEFAULT_W = 560;
    const clampW = w => Math.round(Math.max(290, Math.min(((typeof window !== "undefined" && window.innerWidth) ? window.innerWidth : 1440) - 260, w)));
    const applyPaneW = (w, persist = false) => {{
      const cw = clampW(w);
      if (document.documentElement?.style?.setProperty) document.documentElement.style.setProperty("--pane-w", cw + "px");
      if (persist) {{ try {{ localStorage.setItem("bh_pane_w", String(cw)); }} catch {{}} }}
    }};
    try {{ const savedW = Number(localStorage.getItem("bh_pane_w") || 0); if (savedW >= 290) applyPaneW(savedW, false); }} catch {{}}

    let dragging = false, rafId = 0;
    const syncMapSize = () => {{ rafId = 0; try {{ map.invalidateSize({{ animate: false }}); }} catch {{}} }};
    handle.addEventListener("pointerdown", e => {{
      if (e.button && e.button !== 0) return;
      dragging = true; document.body.classList.add("resizing-pane");
      if (handle.setPointerCapture) handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    }});
    handle.addEventListener("pointermove", e => {{
      if (!dragging) return;
      applyPaneW(e.clientX, false);
      if (!rafId && typeof requestAnimationFrame === "function") rafId = requestAnimationFrame(syncMapSize);
    }});
    const endDrag = e => {{
      if (!dragging) return;
      dragging = false; document.body.classList.remove("resizing-pane");
      if (e && e.clientX) applyPaneW(e.clientX, true);
      try {{ map.invalidateSize({{ animate: false }}); renderMap(); }} catch {{}}
    }};
    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
    handle.addEventListener("dblclick", () => {{
      applyPaneW(DEFAULT_W, true);
      setTimeout(() => {{ try {{ map.invalidateSize({{ animate: false }}); renderMap(); }} catch {{}} }}, 40);
    }});
  }}
  /* === END V16 === */
"""

close_idx = js.rfind("})();")
assert close_idx > 0, "Could not locate closing })(); in web/app.js"
js = js[:close_idx] + V16_JS + "\n" + js[close_idx:]
js_p.write_text(js, encoding="utf-8")

# 5. Syntax & Interactive Node.js Verification (Tests Real Search Bar + Santacruz Accuracy + Carousel Arrows!)
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
    dispatch(ev) { (listeners[ev] || []).forEach(fn => fn({ target: this, preventDefault(){}, stopPropagation(){} })); },
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
  const cards0 = (h0.match(/class="fc/g) || []).length;
  const navs0 = (h0.match(/fc-nav next/g) || []).length;

  const sEl = getEl(SEARCH_ID);
  sEl.value = "santacruz";
  sEl.dispatch("input");
  const hS = (els.get("cardList") || {}).innerHTML || "";
  const hasSantacruz = /santacruz/i.test(hS);
  const hasBandraLeak = /Bandra East/i.test(hS);
  const suggestHtml = (els.get("searchSuggest") || {}).innerHTML || "";
  const hasSuggest = /Santacruz West|Santacruz East/i.test(suggestHtml);

  console.log("[v16 TEST] searchId=" + SEARCH_ID + " | cards=" + cards0 + " | carouselArrows=" + navs0 + " | santacruzMatch=" + hasSantacruz + " | bandraLeak=" + hasBandraLeak + " | autocomplete=" + hasSuggest + " | err=" + (err ? err.message : "NONE"));
  if (err || cards0 === 0 || navs0 === 0 || !hasSantacruz || hasBandraLeak || !hasSuggest) {
    console.error("[v16 TEST] FAILED!");
    process.exit(1);
  }
  console.log("[v16 TEST] PASS! Real search bar + Autocomplete + Santacruz accuracy + Multi-Photo Carousel verified!");
}, 150);
"""
smoke_js = SMOKE_TEMPLATE.replace("__DEFAULTS__", json.dumps(dom_defaults)).replace("__SEARCH_ID__", json.dumps(search_id))
r = subprocess.run(["node", "-e", smoke_js], text=True)
sys.exit(r.returncode)
