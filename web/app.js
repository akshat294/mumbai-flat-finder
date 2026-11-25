function bhPointInPoly(lat, lng, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1];
    const xj = poly[j][0], yj = poly[j][1];
    const intersect = ((yi > lng) !== (yj > lng)) && (lat < (xj - xi) * (lng - yi) / ((yj - yi) || 1e-12) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}
function bhProxySy(u) {
  return (typeof u === "string" && /^https:\/\/static\.squareyards\.com\//i.test(u))
    ? ("/api/img?u=" + encodeURIComponent(u)) : u;
}
(() => {
  const H = "https" + "://";
  const fLink = document.createElement("link");
  fLink.rel = "stylesheet";
  fLink.href = H + "fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap";
  document.head.appendChild(fLink);

  const RENT_STOPS = [0,10000,15000,20000,25000,30000,35000,40000,45000,50000,60000,70000,80000,90000,100000,120000,140000,160000,180000,200000,250000,300000,350000,400000,500000,750000];
  const BUY_STOPS  = [0,4000000,6000000,8000000,10000000,12500000,15000000,17500000,20000000,25000000,30000000,35000000,40000000,50000000,60000000,75000000,100000000,125000000,150000000];
  const SQFT_MAX = 4000;
  const HUB_LABELS = { bkc:"BKC", lower_parel:"Lower Parel", andheri_seepz:"Andheri", powai:"Powai", goregaon_nesco:"Goregaon", nariman_point:"Nariman Pt" };
const PORTAL_NAMES = { magicbricks:"MagicBricks", nobroker:"NoBroker", squareyards:"Square Yards", commonfloor:"CommonFloor", makaan:"Makaan", nobrokerage:"NoBrokerage", community:"Flatmates", reddit:"Reddit", "99acres":"99acres", housing:"Housing.com", owner:"Direct Owner", nextflat:"NextFlat", dwelo:"Dwelo", nestaway:"NestAway", zolostays:"ZoloStays", telegram:"Telegram Direct", stanza:"Stanza Living", flatmate:"FlatMate.in", settl:"Settl.", other:"Direct" };

  function readJSON(k, fb) { try { return JSON.parse(localStorage.getItem(k) || "null") || fb; } catch { return fb; } }
  const savedInit = readJSON("mhf_s3", { ids:[], notes:{} });
  if (!Array.isArray(savedInit.ids)) savedInit.ids = [];
  if (!savedInit.notes) savedInit.notes = {};

  const st = {
    mode: "rent", theme: localStorage.getItem("mhf_t_v9") || "light", mapStyle: "street",
    bhks: new Set(), zero: false, dealOnly: false, flood: false, exactOnly: false, showEst: false, mapBounds: false, lasso: null, /* BH_V62_LASSO */
    showMetro: true, showFlood: false, page: 36, sel: null,
    pLo: 0, pHi: RENT_STOPS[RENT_STOPS.length - 1], sLo: 0, sHi: SQFT_MAX,
    saved: savedInit, clipped: readJSON("mhf_clipped_v7", [])
  };

  let baseSocieties = [], societies = [], filtered = [];
  const pillEls = new Map();
  let renderTimer = null;

  const $ = id => document.getElementById(id);
  const pStops = () => st.mode === "buy" ? BUY_STOPS : RENT_STOPS;
  const priceMax = () => pStops()[pStops().length - 1];
  const scheduleRender = () => { clearTimeout(renderTimer); renderTimer = setTimeout(renderAll, 70); };

  const esc = s => { const d = document.createElement("div"); d.textContent = String(s ?? ""); return d.innerHTML.replace(/"/g, String.fromCharCode(38) + "quot;"); };
  const fmt = (v, buy) => !v ? "On request" : (buy ? (v >= 1e7 ? `₹${(v / 1e7).toFixed(2)} Cr` : `₹${(v / 1e5).toFixed(1)} L`) : (v >= 1e5 ? `₹${(v / 1e5).toFixed(2)} L/mo` : `₹${Math.round(v).toLocaleString("en-IN")}/mo`));
  const fmtPill = (v, buy) => !v ? "—" : (buy ? (v >= 1e7 ? `₹${+(v / 1e7).toFixed(1)}Cr` : `₹${Math.round(v / 1e5)}L`) : (v >= 1e5 ? `₹${+(v / 1e5).toFixed(1)}L` : `₹${Math.round(v / 1e3)}k`));
  const fmtS = (v, buy, ceil) => v <= 0 ? "₹0" : fmtPill(v, buy) + (v >= ceil ? "+" : "");
  const fmtDist = m => !m ? "—" : (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`);
  const fmtBhk = b => b === 0 ? "1 RK" : `${b} BHK`;

  function matchingUnits(s) {
    const isBuy = st.mode === "buy";
    const raw = (isBuy ? s.units_buy : s.units_rent) || [];
    const ceil = (typeof priceMax === "function") ? priceMax() : Infinity;
    const pLo = Number(st.pLo || 0);
    const pHi = (st.pHi !== undefined && st.pHi < ceil) ? Number(st.pHi) : Infinity;
    const sLo = Number(st.sLo || 0);
    const sHi = (st.sHi !== undefined && typeof SQFT_MAX !== "undefined" && st.sHi < SQFT_MAX) ? Number(st.sHi) : Infinity;
    const wantFurn = ($("fFurn")?.value || st.furn || "ALL");
    const wantSrc = ($("fSource")?.value || st.source || "ALL");
    const wantLister = st.lister || "ALL";

    return raw.filter(u => {
      if (!u || !u.p) return false;
      if (pLo > 0 && u.p < pLo) return false;
      if (pHi < Infinity && u.p > pHi) return false;
      if (u.sq) {
        if (sLo > 0 && u.sq < sLo) return false;
        if (sHi < Infinity && u.sq > sHi) return false;
      }

      if (st.bhks instanceof Set && st.bhks.size > 0) {
        if (u.b === null || u.b === undefined) return false;
        const ub = Number(u.b);
        let ok = false;
        for (const w of st.bhks) {
          if ((w === "4+" || Number(w) === 4) ? ub >= 4 : Math.abs(ub - Number(w)) <= 0.05) { ok = true; break; }
        }
        if (!ok) return false;
      }

      if (wantFurn && wantFurn !== "ALL" && u.f && String(u.f).toLowerCase() !== String(wantFurn).toLowerCase()) return false;
      const uLt = u.lt || ((u.s === "community" || u.s === "reddit") ? "shared" : ((u.zb || u.s === "nobroker" || u.s === "owner") ? "owner" : "broker"));
      if (wantSrc && wantSrc !== "ALL") {
        if (wantSrc === "community") { if (u.s !== "community" && u.s !== "reddit" && uLt !== "shared") return false; }
        else if (u.s !== wantSrc) return false;
      }
      if (st.zero && uLt !== "owner" && !u.zb) return false;
      if ((st.community || ($("fSource")?.value === "community")) && uLt !== "shared") return false;
      if (wantLister !== "ALL" && uLt !== wantLister) return false;
      return true;
    });
  }

  function passesV15SocietyFilter(s) {
    const _tq = (document.getElementById("searchBox")?.value || "").trim().toLowerCase();
    if (_tq && (!Array.isArray(st.multiLocs) || !st.multiLocs.length)) {
      const _ns = v => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");
      const _rawHay = ((s.name || "") + " " + (s.locality || "") + " " + ((s.features?.tags || []).join(" ").replace(/_/g, " ")) + " " + ((s.bhks || []).map(b => b === 0 ? "1 rk studio" : (b + " bhk")).join(" "))).toLowerCase();
      const _normHay = _ns(s.name) + " " + _ns(s.locality) + " " + _ns((s.features?.tags || []).join(" "));
      const _toks = _tq.split(/\s+/).filter(Boolean);
      if (!_toks.every(tok => _rawHay.includes(tok) || _normHay.includes(_ns(tok)))) return false;
    } /* v16_strict_search */
    if (Array.isArray(st.multiLocs) && st.multiLocs.length && !st.multiLocs.includes(s.locality)) return false;
    if (!matchingUnits(s).length) return false;
    const ftags = s.features?.tags || [];
    if (st.seaview && !ftags.includes("sea_view")) return false;
    if (st.balcony && !ftags.includes("balcony")) return false;
    if (st.terrace && !(ftags.includes("terrace") || ftags.includes("garden"))) return false;
    if (st.drop && !(s.price_drop && s.price_drop[st.mode])) return false;
    if (st.hub && st.hub !== "ALL" && HUB_META[st.hub]) {
      const cm = s.commutes?.[st.hub];
      if (!cm || cm > st.hubMin) return false;
    }
    if (st.brightOnly) {
      if (s.vr || (Number(s.vs) || 0) < 97) return false;
    }
    if (st.reraOnly) {
      const _hasRera = !!(s.rera || s.rera_id || (Array.isArray(s.rera_ids) && s.rera_ids.length) || (s.units_buy || []).some(u => u && u.rera));
      if (!_hasRera) return false;
    }
    if (Array.isArray(st.lasso) && st.lasso.length >= 3) {
      if (typeof s.lat !== "number" || typeof s.lng !== "number" || !bhPointInPoly(s.lat, s.lng, st.lasso)) return false;
    }
    return true;
  }

  function getP(s) {
    const us = matchingUnits(s);
    if (us.length) return Math.min(...us.map(u => u.p));
    return st.mode === "rent" ? (s.pricing?.rent_monthly_inr?.median || 0) : (s.pricing?.buy_inr?.median || 0);
  }
  function getPriceLabel(s) {
    const us = matchingUnits(s);
    if (us.length >= 2) {
      const ps = us.map(u => u.p); const lo = Math.min(...ps), hi = Math.max(...ps);
      if (hi > lo * 1.12) return `${fmtPill(lo, st.mode === "buy")} – ${fmtPill(hi, st.mode === "buy")}${st.mode === "rent" ? "/mo" : ""}`;
    }
    return fmt(getP(s), st.mode === "buy");
  }
  function hasRealListing(s) {
    const us = st.mode === "rent" ? (s.units_rent || []) : (s.units_buy || []);
    if (us.length > 0) return true;
    const pinfo = st.mode === "rent" ? s.pricing?.rent_monthly_inr : s.pricing?.buy_inr;
    return !!(pinfo?.median && !pinfo?.is_estimate);
  }
  const getDeal = s => st.mode === "rent" ? s.deal?.rent : s.deal?.buy;
  const getSources = s => {
    const set = new Set([...Object.keys(s.sources || {}), ...Object.keys(s.pricing?.by_portal || {})]);
    for (const u of (s.units_rent || []).concat(s.units_buy || [])) if (u.s) set.add(u.s);
    return [...set];
  };

  function toast(msg) {
    const el = $("toast"); el.textContent = msg; el.classList.add("show");
    clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("show"), 2500);
  }

  const MMR_BOUNDS = L.latLngBounds([18.84, 72.72], [19.36, 73.22]);
  const map = L.map("map", { preferCanvas: true, zoomControl: true, minZoom: 11, maxZoom: 20, maxBounds: MMR_BOUNDS, maxBoundsViscosity: 0.92 }).setView([19.088, 72.885], 11);
  const osmStreet = L.tileLayer(H + "tile.openstreetmap.org/{z}/{x}/{y}.png", { maxNativeZoom: 19, maxZoom: 20, attribution: "OpenStreetMap" });
  const esriSat = L.layerGroup([
    L.tileLayer(H + "server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxNativeZoom: 18, maxZoom: 20, attribution: "Esri" }),
    L.tileLayer(H + "server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", { maxNativeZoom: 18, maxZoom: 20 })
  ]);
  let activeBase = null;

  function setMapStyle(style) {
    st.mapStyle = style;
    if (activeBase) map.removeLayer(activeBase);
    activeBase = style === "sat" ? esriSat : osmStreet;
    activeBase.addTo(map);
    const mapEl = $("map");
    mapEl.classList.remove("map-street", "map-dark", "map-sat");
    mapEl.classList.add(style === "dark" ? "map-dark" : (style === "sat" ? "map-sat" : "map-street"));
    ["msStreet","msDark","msSat"].forEach(id => $(id).classList.remove("active"));
    $(style === "dark" ? "msDark" : (style === "sat" ? "msSat" : "msStreet")).classList.add("active");
  }

  const cv = L.canvas({ padding: 0.5 });
  const mLayer = L.layerGroup().addTo(map);
  const hubLayer = L.layerGroup().addTo(map);
  const HUB_META = {
    bkc: { name: "BKC", ll: [19.0653, 72.8681] },
    lower_parel: { name: "Lower Parel", ll: [18.9985, 72.8295] },
    nariman_point: { name: "Nariman Pt", ll: [18.9281, 72.8235] },
    seepz: { name: "SEEPZ", ll: [19.1242, 72.8742] },
    powai: { name: "Powai", ll: [19.1197, 72.9051] },
    mindspace: { name: "Mindspace", ll: [19.1802, 72.8334] }
  };
  function drawHubRing() {
    hubLayer.clearLayers();
    const hm = HUB_META[st.hub];
    if (!hm) return;
    const radM = Math.max(1500, ((st.hubMin - 4) / 60) * 19500 / 1.28);
    L.circle(hm.ll, { radius: radM, color: "#c49e5c", weight: 1.6, dashArray: "5 5", fillColor: "#c49e5c", fillOpacity: 0.08, interactive: false }).addTo(hubLayer);
    L.circleMarker(hm.ll, { radius: 6, color: "#162a27", weight: 2, fillColor: "#c49e5c", fillOpacity: 1 }).bindTooltip(`${hm.name} · ≤${st.hubMin} min`, { direction: "top" }).addTo(hubLayer);
  }

  const metroL = L.layerGroup().addTo(map);
  const floodL = L.layerGroup();

  [
    { n:"Aqua Line 3", c:"#0891b2", p:[[19.1365,72.8748],[19.1082,72.8800],[19.0817,72.8482],[19.0653,72.8644],[19.0218,72.8414],[19.0074,72.8195],[18.9696,72.8193],[18.9352,72.8273],[18.9142,72.8213]] },
    { n:"Blue Line 1", c:"#2563eb", p:[[19.1307,72.8213],[19.1207,72.8481],[19.1082,72.8800],[19.0867,72.9082]] },
    { n:"Lines 2A / 7", c:"#d97706", p:[[19.2288,72.8468],[19.1862,72.8358],[19.1469,72.8347],[19.1301,72.8306],[19.1190,72.8559],[19.1665,72.8576]] },
    { n:"Navi Mumbai Line 1", c:"#7c3aed", p:[[19.0185,73.0394],[19.0359,73.0631],[19.0548,73.0686],[19.0620,73.0715],[19.0772,73.0977]] }
  ].forEach(l => L.polyline(l.p, { color: l.c, weight: 2.5, opacity: 0.68, renderer: cv }).bindTooltip(l.n).addTo(metroL));

  [
    { n:"Hindmata", la:19.0079, ln:72.8423, r:650 }, { n:"Sion Gandhi Market", la:19.0322, ln:72.8576, r:700 },
    { n:"Milan Subway", la:19.0853, ln:72.8439, r:550 }, { n:"Andheri Subway", la:19.1157, ln:72.8442, r:550 },
    { n:"Kurla LBS", la:19.0764, ln:72.8832, r:800 }, { n:"Malad Subway", la:19.1846, ln:72.8468, r:500 }
  ].forEach(s => L.circle([s.la, s.ln], { radius: s.r, color: "#b91c1c", fillColor: "#b91c1c", fillOpacity: 0.14, weight: 1, renderer: cv }).bindTooltip("Flood Zone: " + s.n).addTo(floodL));

  function syncPriceSliders(iLo, iHi) {
    const stops = pStops(), maxI = stops.length - 1, ceil = stops[maxI];
    if (iLo > iHi) { const t = iLo; iLo = iHi; iHi = t; }
    st.pLo = stops[iLo]; st.pHi = stops[iHi];
    $("mpMin").value = iLo; $("mpMax").value = iHi;
    $("mPriceFill").style.left = `${(iLo / maxI) * 100}%`;
    $("mPriceFill").style.width = `${((iHi - iLo) / maxI) * 100}%`;
    $("mPriceVal").textContent = (iLo === 0 && iHi === maxI) ? "Any Price" : `${fmtS(st.pLo, st.mode === "buy", ceil)} – ${fmtS(st.pHi, st.mode === "buy", ceil)}`;
  }
  function resetPriceScale() {
    const maxI = pStops().length - 1;
    ["mpMin","mpMax"].forEach(id => { $(id).min = 0; $(id).max = maxI; $(id).step = 1; });
    $("mPriceLbl").textContent = st.mode === "buy" ? "Purchase Budget" : "Monthly Rent";
    syncPriceSliders(0, maxI);
  }
  function syncSqftSlider() {
    let lo = Number($("sMin").value), hi = Number($("sMax").value);
    if (lo > hi) { const t = lo; lo = hi; hi = t; $("sMin").value = lo; $("sMax").value = hi; }
    st.sLo = lo; st.sHi = hi;
    $("sqftFill").style.left = `${(lo / SQFT_MAX) * 100}%`;
    $("sqftFill").style.width = `${((hi - lo) / SQFT_MAX) * 100}%`;
    $("sqftVal").textContent = (lo === 0 && hi === SQFT_MAX) ? "Any Size" : `${lo} – ${hi >= SQFT_MAX ? SQFT_MAX + "+" : hi} sq ft`;
  }

  function applyTheme(t) {
    st.theme = t; localStorage.setItem("mhf_t_v9", t);
    document.documentElement.setAttribute("data-theme", t);
    $("themeIcon").innerHTML = t === "dark"
      ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>'
      : '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>';
    setMapStyle(t === "dark" ? "dark" : "street");
  }

  function syncCounts() {
    localStorage.setItem("mhf_s3", JSON.stringify(st.saved));
    localStorage.setItem("mhf_clipped_v7", JSON.stringify(st.clipped));
    const sc = st.saved.ids.length;
    $("savedCount").textContent = sc; $("savedCount").style.display = sc ? "inline-block" : "none";
  }

  function rebuildSocietyList() { societies = [...directSocieties, ...st.clipped, ...baseSocieties]; }

  function populateLocalities() {
    const z = $("fZone").value, prev = $("fLoc").value;
    const locs = [...new Set(societies.filter(s => z === "ALL" || s.zone === z).map(s => s.locality).filter(Boolean))].sort();
    $("fLoc").innerHTML = `<option value="ALL">All Localities (${locs.length})</option>` + locs.map(l => `<option value="${esc(l)}">${esc(l)}</option>`).join("");
    if (locs.includes(prev)) $("fLoc").value = prev;
  }

  function populateSources() {
    const counts = {};
    for (const s of societies) {
      for (const k of getSources(s)) {
        const key = k === "reddit" ? "community" : k;
        counts[key] = (counts[key] || 0) + 1;
      }
    }
    const sel = $("fSource"), prev = sel.value;
    const ordered = Object.entries(counts).filter(([_, n]) => n > 0).sort((a, b) => b[1] - a[1]);
    sel.innerHTML = '<option value="ALL">All Sources</option>' + ordered.map(([k, n]) => `<option value="${esc(k)}">${esc(PORTAL_NAMES[k] || k)} (${n.toLocaleString("en-IN")})</option>`).join("");
    if (ordered.some(([k]) => k === prev)) sel.value = prev;
    const commChip = document.querySelector('.chip[data-q="community"]');
    if (commChip) commChip.style.display = (counts.community || 0) > 0 ? "" : "none";
  }

  function renderMap() {
    mLayer.clearLayers(); pillEls.clear(); drawHubRing();
    const z = map.getZoom(), bounds = map.getBounds().pad(0.12);
    const inView = filtered.filter(s => s.lat && s.lng && bounds.contains([s.lat, s.lng]));
    if (!inView.length) return;

    const exact = inView.filter(s => !s.coords_approx), approx = inView.filter(s => s.coords_approx);
    const _mob = window.innerWidth <= 820;
    const cellW = _mob ? (z <= 11 ? 84 : (z <= 13 ? 74 : (z >= 17 ? 50 : 62))) : (z <= 11 ? 124 : (z <= 13 ? 104 : (z >= 17 ? 66 : 84)));
    const cellH = _mob ? (z <= 11 ? 46 : (z <= 13 ? 40 : (z >= 17 ? 28 : 34))) : (z <= 11 ? 54 : (z <= 13 ? 48 : (z >= 17 ? 34 : 40)));
    const buckets = new Map();
    const occupied = [];

    for (const s of exact) {
      const pt = map.project([s.lat, s.lng], z);
      const key = `${Math.floor(pt.x / cellW)}:${Math.floor(pt.y / cellH)}`;
      let b = buckets.get(key);
      if (!b) { b = { items: [], lat: 0, lng: 0, minP: Infinity, maxP: 0 }; buckets.set(key, b); }
      b.items.push(s); b.lat += s.lat; b.lng += s.lng;
      const pv = getP(s); if (pv > 0) { if (pv < b.minP) b.minP = pv; if (pv > b.maxP) b.maxP = pv; }
    }

    for (const b of buckets.values()) {
      const cla = b.lat / b.items.length, cln = b.lng / b.items.length;
      occupied.push(map.latLngToContainerPoint([cla, cln]));
      if (b.items.length === 1) { addPricePill(b.items[0]); }
      else {
        const ps = b.items.map(x => getP(x)).filter(v => v > 0).sort((a, c) => a - c);
        const medP = ps.length ? ps[Math.floor(ps.length / 2)] : 0;
        const medS = medP ? fmtPill(medP, st.mode === "buy") : "";
        const pillHtml = `<div class="cluster-pill${z <= 11 ? " cluster-hero" : ""}"><span>${medS || "Homes"}</span><span class="cluster-cnt">\u00b7 ${b.items.length}</span></div>`;
        const ic = L.divIcon({ className: "cluster-wrap", html: pillHtml, iconSize: [0, 0] });
        L.marker([cla, cln], { icon: ic }).on("click", () => {
          const lats = b.items.map(x => x.lat), lngs = b.items.map(x => x.lng);
          const span = Math.max(Math.max(...lats) - Math.min(...lats), Math.max(...lngs) - Math.min(...lngs));
          if (z >= 17 || span < 0.0005) openClusterSheet(`${b.items.length} verified buildings`, b.items[0]?.locality || "Mumbai", b.items);
          else map.setView([cla, cln], Math.min(18, z + 2), { animate: true });
        }).addTo(mLayer);
      }
    }

    if (!st.exactOnly && z >= 13 && approx.length) {
      const byLoc = new Map();
      for (const s of approx) {
        let g = byLoc.get(s.locality);
        if (!g) { g = { loc: s.locality, items: [], lat: 0, lng: 0 }; byLoc.set(s.locality, g); }
        g.items.push(s); g.lat += s.lat; g.lng += s.lng;
      }
      const offsets = [[0,0],[0,-40],[0,40],[96,0],[-96,0],[76,-36],[-76,-36],[76,36],[-76,36],[0,-76],[0,76]];
      for (const g of byLoc.values()) {
        const basePt = map.latLngToContainerPoint([g.lat / g.items.length, g.lng / g.items.length]);
        let placed = basePt;
        for (const [dx, dy] of offsets) {
          const cand = L.point(basePt.x + dx, basePt.y + dy);
          if (!occupied.some(o => Math.abs(o.x - cand.x) < 92 && Math.abs(o.y - cand.y) < 34)) { placed = cand; break; }
        }
        occupied.push(placed);
        const ll = map.containerPointToLatLng(placed);
        const ic = L.divIcon({ className: "cluster-wrap", html: `<div class="area-pill">${esc(g.loc)} · +${g.items.length}</div>`, iconSize: [0, 0] });
        L.marker([ll.lat, ll.lng], { icon: ic, zIndexOffset: -100 })
          .on("click", () => openClusterSheet(`${g.loc} — Area Listings`, `${g.items.length} homes in ${g.loc}`, g.items))
          .addTo(mLayer);
      }
    }
  }

  function addPricePill(s) {
    const deal = getDeal(s), isSel = s.id === st.sel;
    const cls = ["price-pill", isSel ? "sel" : "", deal?.label === "Great Value" ? "val" : ""].filter(Boolean).join(" ");
    const ic = L.divIcon({ className: "pill-wrap", html: `<div class="${cls}" data-pid="${esc(s.id)}">${fmtPill(getP(s), st.mode === "buy")}</div>`, iconSize: [0, 0] });
    const mk = L.marker([s.lat, s.lng], { icon: ic, zIndexOffset: isSel ? 900 : 0 });
    mk.on("click", () => onPinClick(s)); mk.addTo(mLayer); pillEls.set(s.id, mk);
  }

  function openClusterSheet(title, sub, items) {
    const sorted = [...items].sort((a, b) => (getP(a) || 9e12) - (getP(b) || 9e12));
    $("clTitle").textContent = title; $("clSub").textContent = sub;
    $("clBody").innerHTML = sorted.slice(0, 60).map(s => renderCardHtml(s, $("fHub").value)).join("");
    bindCardEvents($("clBody"));
    $("clusterBackdrop").style.display = "block"; $("clusterSheet").style.display = "flex";
  }
  const closeCluster = () => { $("clusterBackdrop").style.display = "none"; $("clusterSheet").style.display = "none"; };

  function onPinClick(s) {
    st.sel = s.id; filtered = filtered.filter(passesV15SocietyFilter); /* v15_filter_hook */
    renderMap();
    openDetail(s);
  }

  function showMapPreview(s) {
    const box = $("mapPreview"), ctx = s.mumbai_context || {}, deal = getDeal(s);
    box.innerHTML = `<div class="mp-top"><div style="min-width:0;"><div class="mp-name">${esc(s.name)}</div><div class="mp-loc">${esc(s.locality)}</div></div><button class="btn icon xs" id="closeMp" aria-label="Close">✕</button></div>
      <div class="mp-row"><strong class="mp-price">${getPriceLabel(s)}</strong>${deal?.label === "Great Value" ? `<span class="tag good">${Math.abs(deal.pct)}% below avg</span>` : ""}</div>
      <div class="mp-foot"><span class="mp-meta">${(s.bhks || []).map(fmtBhk).join(", ") || "Home"}${ctx.nearest_metro ? ` · ${ctx.nearest_metro.walk_min}m Metro` : ""}</span><button class="btn pri xs" id="openMpDetail">View</button></div>`;
    box.style.display = "flex";
    if ($("closeMp")) $("closeMp").onclick = () => { box.style.display = "none"; };
    if ($("openMpDetail")) $("openMpDetail").onclick = () => { box.style.display = "none"; openDetail(s); };
  }

  function renderActiveBar() {
    const bar = $("activeBar"), tags = [];
    const z = $("fZone").value, loc = $("fLoc").value, srcF = $("fSource").value, ceil = priceMax();
    if (z !== "ALL") tags.push(z);
    if (loc !== "ALL") tags.push(loc);
    if (srcF !== "ALL") tags.push(PORTAL_NAMES[srcF] || srcF);
    if (st.bhks.size) tags.push([...st.bhks].sort((a, b) => a - b).map(x => Number(x) === 4 ? "4+ BHK" : (Number(x) === 0 ? "1 RK" : `${x} BHK`)).join(", "));
    if (st.pLo > 0 || st.pHi < ceil) tags.push(`${fmtS(st.pLo, st.mode === "buy", ceil)}–${fmtS(st.pHi, st.mode === "buy", ceil)}`);
    if (st.sLo > 0 || st.sHi < SQFT_MAX) tags.push(`${st.sLo}–${st.sHi} sq ft`);
    if (Number($("fMetro").value)) tags.push(`Metro ≤${$("fMetro").value}m`);
    if ($("fHub") && $("fHub").value && $("fHub").value !== "ALL") tags.push((HUB_LABELS[$("fHub").value] || $("fHub").value) + (Number($("fHubMin").value) ? ` ≤${$("fHubMin").value}m` : ""));
    if ($("fFurn") && $("fFurn").value && $("fFurn").value !== "ALL") tags.push($("fFurn").selectedOptions?.[0]?.text || $("fFurn").value);
    if ($("fTen") && $("fTen").value && $("fTen").value !== "ALL") tags.push($("fTen").selectedOptions?.[0]?.text || $("fTen").value);
    if (Number($("fRate").value)) tags.push(`${$("fRate").value}★+`);
    if (st.exactOnly) tags.push("Exact Pins");
    if (st.mapBounds) tags.push("Map Area"); if (Array.isArray(st.lasso) && st.lasso.length >= 3) tags.push("Drawn Area");

    $("filterCount").textContent = tags.length; $("filterCount").style.display = tags.length ? "inline-block" : "none";
    $("resetMiniBtn").style.display = (tags.length > 0 || st.zero || st.dealOnly || st.flood) ? "inline-block" : "none";
    if (!tags.length) { bar.style.display = "none"; return; }
    bar.style.display = "flex";
    bar.innerHTML = tags.map(t => `<span class="af-pill">${esc(t)}</span>`).join("");
  }

  function renderAll() {
    const q = $("searchBox").value.trim().toLowerCase();
    const z = $("fZone").value, loc = $("fLoc").value, srcF = $("fSource").value, ceil = priceMax();
    const maxM = Number($("fMetro").value || 0), hub = $("fHub").value, hubMax = Number($("fHubMin").value || 0);
    const furn = $("fFurn").value, ten = $("fTen").value, minRate = Number($("fRate").value || 0), srt = ($("sortSelect")?.value || "rec");
    const bounds = st.mapBounds ? map.getBounds() : null;

    filtered = societies.filter(s => {
      if (!st.showEst && !hasRealListing(s)) return false;
      if (st.exactOnly && s.coords_approx) return false;
      if (z !== "ALL" && s.zone !== z) return false;
      if (loc !== "ALL" && s.locality !== loc) return false;
      if (srcF !== "ALL") {
        const srcs = getSources(s);
        if (srcF === "community") { const _hasSh = srcs.includes("community") || srcs.includes("reddit") || (s.units_rent || []).some(u => (u.lt || ((u.s === "community" || u.s === "reddit") ? "shared" : "")) === "shared"); if (!_hasSh) return false; }
        else if (!srcs.includes(srcF)) return false;
      }
      if (q && (!((s.name + " " + s.locality + " " + (s.zone || "") + " " + ((s.features?.tags || []).join(" "))).toLowerCase().replace(/[^a-z0-9]/g, "").includes(q.replace(/[^a-z0-9]/g, ""))))) return false;
      if (st.bhks.size) {
        const bs = s.bhks || [];
        if (!bs.length || ![...st.bhks].some(b => b === 4 ? bs.some(x => x >= 4) : bs.includes(b))) return false;
      }
      const p = getP(s);
      if (st.pLo > 0 && (!p || p < st.pLo)) return false;
      if (st.pHi < ceil && (!p || p > st.pHi)) return false;
      if (st.sLo > 0 && (!s.rera_carpet_sqft || s.rera_carpet_sqft < st.sLo)) return false;
      if (st.sHi < SQFT_MAX && (!s.rera_carpet_sqft || s.rera_carpet_sqft > st.sHi)) return false;
      if (maxM > 0 && (s.mumbai_context?.nearest_metro?.walk_min || 999) > maxM) return false;
      if (hub && hubMax > 0 && (s.mumbai_context?.commute_hubs_min?.[hub] || 999) > hubMax) return false;
      if (furn !== "ALL" && !(s.furnishing || []).includes(furn)) return false;
      if (ten !== "ALL" && !(s.tenant || []).includes(ten)) return false;
      if (minRate > 0 && (s.google?.rating || 0) < minRate) return false;
      if (st.zero && !s.pricing?.has_zero_brokerage && !matchingUnits(s).some(u => u.zb)) return false;
      if (st.dealOnly && getDeal(s)?.label !== "Great Value") return false;
      if (st.flood && s.mumbai_context?.monsoon_flood_risk === "high") return false;
      if (bounds && !bounds.contains([s.lat, s.lng])) return false;
      return true;
    });

    filtered.sort((a, b) => {
      if (srt === "p_asc") return (getP(a) || 9e12) - (getP(b) || 9e12);
      if (srt === "p_desc") return (getP(b) || 0) - (getP(a) || 0);
      if (srt === "deal") return (getDeal(a)?.pct ?? 999) - (getDeal(b)?.pct ?? 999);
      if (srt === "metro") return (a.mumbai_context?.nearest_metro?.walk_min || 999) - (b.mumbai_context?.nearest_metro?.walk_min || 999);
      if (srt === "rate") return (b.google?.rating || 0) - (a.google?.rating || 0);
      if (hub) {
        const ca = a.mumbai_context?.commute_hubs_min?.[hub] || 999, cb = b.mumbai_context?.commute_hubs_min?.[hub] || 999;
        if (Math.abs(ca - cb) >= 5) return ca - cb;
      }
      const sc = x => (x._clipped ? 25 : 0) + (x.thumb || (x.photos && x.photos.length) ? 18 : -16) + ((st.lister === "ALL" && !(x.units_rent || []).some(u => u.lt !== "shared") && st.mode === "rent") ? -14 : 0) + (!x.coords_approx ? 10 : 0) + (getDeal(x)?.label === "Great Value" ? 8 : 0) + (x.google?.rating || 0) * 3 + (x.pricing?.has_zero_brokerage ? 6 : 0) + Math.min(8, matchingUnits(x).length * 2) - Math.min(20, (x.mumbai_context?.nearest_metro?.walk_min || 20) * 0.25);
      return sc(b) - sc(a);
    });

    filtered = filtered.filter(passesV15SocietyFilter); /* v15_filter_hook */
    const exactCnt = filtered.filter(s => !s.coords_approx).length;
    // BH_V59_SMOOTH_BUY: show smooth loading text while Buy/Rent shards download
    if (window.__bhModeLoading && window.__bhModeLoading === st.mode && filtered.length === 0) {
      $("resSum").textContent = st.mode === "buy" ? "Loading homes for sale..." : "Loading homes for rent...";
    } else {
      $("resSum").textContent = `${filtered.length.toLocaleString("en-IN")} homes \u00b7 ${exactCnt.toLocaleString("en-IN")} exact pins`;
    }
    $("applyFiltersBtn").textContent = `Show ${filtered.length.toLocaleString("en-IN")} Homes`;
    renderActiveBar();
    renderMap(); renderList();
  }

  function renderCardHtml(s, hub) {
    const ctx = s.mumbai_context || {}, g = s.google, deal = getDeal(s), us = matchingUnits(s), isS = st.saved.ids.includes(s.id);
    const meta = [];
    if (s.bhks?.length) meta.push(s.bhks.slice(0, 2).map(fmtBhk).join(", "));
    if (s.rera_carpet_sqft) meta.push(`${s.rera_carpet_sqft} sq ft`);
    if (hub && ctx.commute_hubs_min?.[hub]) meta.push(`${ctx.commute_hubs_min[hub]}m to ${HUB_LABELS[hub]}`);
    else if (ctx.nearest_metro) meta.push(`${ctx.nearest_metro.walk_min}m Metro`);

    return `<article class="hc ${s.id === st.sel ? "sel" : ""}" data-id="${esc(s.id)}">
      ${s.thumb ? `<img referrerpolicy="no-referrer" class="hc-thumb" src="${esc(s.thumb)}" referrerpolicy="no-referrer" alt="" loading="lazy" onerror="this.remove()" />` : ""}
      <div class="hc-main">
        <div class="hc-row1">
          <div style="min-width:0;"><div class="hc-name">${esc(s.name)}</div><div class="hc-loc">${esc(s.locality)}${g?.rating ? ` · <span class="hc-star">★ ${g.rating}</span>` : ""}</div></div>
          <button class="heart-btn ${isS ? "sv" : ""}" data-sv="1" aria-label="Save"><svg class="ic" viewBox="0 0 24 24"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg></button>
        </div>
        <div class="hc-row2">
          <strong class="hc-price">${getPriceLabel(s)}</strong>
          <div class="hc-tags">
            ${deal?.label === "Great Value" ? `<span class="tag good">${Math.abs(deal.pct)}% below avg</span>` : ""}
            ${(s.pricing?.has_zero_brokerage || us.some(u => u.zb)) ? `<span class="tag zb-brass">Zero Brok</span>` : ""}
          </div>
        </div>
        <div class="hc-row3">
          <span>${esc(meta.join(" · ") || s.zone)}</span>
          ${us.length > 1 ? `<span class="hc-u">${us.length} units</span>` : ""}
        </div>
      </div>
    </article>`;
  }

  function bindCardEvents(container) {
    container.querySelectorAll(".hc").forEach(el => {
      const id = el.dataset.id;
      el.onmouseenter = () => highlightPin(id, true);
      el.onmouseleave = () => highlightPin(id, false);
      el.onclick = e => {
        if (e.target.closest("[data-sv]")) { e.stopPropagation(); toggleSave(id); return; }
        const s = societies.find(x => x.id === id);
        if (s) {
          closeCluster();
          if (!s.coords_approx && s.lat && s.lng) map.flyTo([s.lat, s.lng], Math.max(map.getZoom(), 15), { duration: 0.4 });
          openDetail(s);
        }
      };
    });
  }

  function renderList() {
  if (!window.__bhById) window.__bhById = new Map();
  if (Array.isArray(filtered)) { for (const _s of filtered) { if (_s && _s.id) window.__bhById.set(_s.id, _s); } }
    const isBuy = st.mode === "buy";
    const PORTALS = {
      magicbricks:"MagicBricks", nobroker:"NoBroker", squareyards:"Square Yards",
      makaan:"Makaan", commonfloor:"CommonFloor", community:"Flatmates",
      reddit:"Flatmates", "99acres":"99acres", housing:"Housing.com", owner:"Direct Owner"
    };
    const socMap = new Map();
    const flats = [];
    const flagsMap = window.__v17Flags || {};
    for (const s of filtered) {
      socMap.set(s.id, s);
      const rawUs = matchingUnits(s);
      const deduped = [];
      for (const u of rawUs) {
        const isClone = deduped.some(x =>
          x.bhk === u.bhk &&
          Math.abs((x.p || 0) - (u.p || 0)) <= Math.max(1500, (x.p || 0) * 0.05) &&
          (!x.sq || !u.sq || Math.abs(x.sq - u.sq) <= Math.max(40, x.sq * 0.05))
        );
        if (!isClone) deduped.push(u);
      }
      const liveDeduped = deduped.filter(u => ((flagsMap[u.u || u.url]?.total) || 0) < 2);
      if (!liveDeduped.length) continue;
      deduped.length = 0; deduped.push(...liveDeduped);
      deduped.sort((a, b) => {
        const fA = (flagsMap[a.url]?.total || 0) > 0 ? 1 : 0;
        const fB = (flagsMap[b.url]?.total || 0) > 0 ? 1 : 0;
        if (fA !== fB) return fA - fB;
        const iA = a.img ? 1 : 0, iB = b.img ? 1 : 0;
        if (iB !== iA) return iB - iA;
        return (a.p || 9e9) - (b.p || 9e9);
      });
      const best = deduped[0];
      best._v17MoreCount = Math.max(0, deduped.length - 1); window.__v18MoreMap = window.__v18MoreMap || new Map(); window.__v18MoreMap.set(s.id, best._v17MoreCount);
      flats.push({ s, u: best, idx: 0 });
    }

    if (st.sort === "price_asc") flats.sort((a, b) => a.u.p - b.u.p);
    else if (st.sort === "savings") flats.sort((a, b) => ((b.s.price_drop_pct || 0) + (b.s.deal_score || 0)) - ((a.s.price_drop_pct || 0) + (a.s.deal_score || 0)));
    else if (st.sort === "price_desc") flats.sort((a, b) => b.u.p - a.u.p);
    else if (st.sort === "metro") flats.sort((a, b) => (a.s.mumbai_context?.nearest_metro?.walk_min ?? 99) - (b.s.mumbai_context?.nearest_metro?.walk_min ?? 99));
    else if (st.sort === "rating") flats.sort((a, b) => (b.s.google?.rating || 0) - (a.s.google?.rating || 0));
    else {
      flats.sort((a, b) => {
        const imgA = (a.u.img || a.s.thumb) ? 1 : 0, imgB = (b.u.img || b.s.thumb) ? 1 : 0;
        if (imgB !== imgA) return imgB - imgA;
        const exA = a.s.coords_approx ? 0 : 1, exB = b.s.coords_approx ? 0 : 1;
        if (exB !== exA) return exB - exA;
        const rA = a.s.google?.rating || 0, rB = b.s.google?.rating || 0;
        if (rB !== rA) return rB - rA;
        return a.u.p - b.u.p;
      });
    }

    const exSocs = filtered.filter(s => !s.coords_approx).length;
    const sumTxt = `${flats.length.toLocaleString("en-IN")} flats · ${filtered.length.toLocaleString("en-IN")} buildings (${exSocs.toLocaleString("en-IN")} exact pins)`;
    const sumEl = $("resSummary") || $("resCount") || document.querySelector(".res-meta");
    if (sumEl) sumEl.textContent = sumTxt;

    const listEl = $("cardList");
    if (!flats.length) {
      listEl.innerHTML = `<div class="empty" style="grid-column:1/-1;text-align:center;padding:42px 16px;color:var(--mut);">No flats match these filters. Try widening budget or resetting chips.</div>`;
      return;
    }

    // v18SourceDiversify: interleave portals on Best Match so Grid shows all sources
    if (!st.sort || st.sort === "rec") {
      const buckets = new Map();
      for (const f of flats) {
        const k = String(f.u.src || f.u.s || f.u.source || "other").toLowerCase();
        if (!buckets.has(k)) buckets.set(k, []);
        buckets.get(k).push(f);
      }
      if (buckets.size > 1) {
        const mixed = [];
        const keys = [...buckets.keys()];
        let more = true;
        while (more) {
          more = false;
          for (const k of keys) {
            const arr = buckets.get(k);
            if (arr && arr.length) {
              mixed.push(arr.shift());
              if (arr.length && k === "magicbricks") mixed.push(arr.shift());
              more = true;
            }
          }
        }
        flats.length = 0;
        flats.push(...mixed);
      }
    }
    const slice = flats.slice(0, st.page);
    const archSvg = `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20V11a8 8 0 0 1 16 0v9"/><path d="M8 20v-7a4 4 0 0 1 8 0v7"/><path d="M2 20h20"/></svg>`;

    listEl.innerHTML = slice.map(({ s, u }) => {
      const _rawImg = u.img || s.thumb || "";
      const _m99 = _rawImg.match(/imagecdn\.99acres\.com\/.*\/(\d+)T-\d+\./i);
      const _hi99 = _m99 ? (s.photos || []).find(p => typeof p === "string" && new RegExp("/" + _m99[1] + "[MLO]-\\d+\\.", "i").test(p)) : null;
      const img = _hi99 || _rawImg;
      const bhkTxt = u.b === 0 ? "1 RK" : (u.b ? `${u.b} BHK` : "");
      const sq = u.sq || s.rera_carpet_sqft;
      const specTxt = [bhkTxt, sq ? `${sq} sq ft` : ""].filter(Boolean).join(" · ");
      const psf = (u.p && sq) ? Math.round(u.p / sq) : 0;
      const psfTxt = psf ? `₹${psf >= 1000 ? (psf / 1000).toFixed(1) + "k" : psf}/sf` : "";
      const metroMin = s.mumbai_context?.nearest_metro?.walk_min;
      const subTxt = [s.locality, metroMin && metroMin <= 25 ? `${metroMin}m Metro` : "", s.google?.rating ? `★ ${s.google.rating}` : ""].filter(Boolean).join(" · ");
      const portal = PORTALS[u.s] || u.s || "Portal";
      const saved = st.saved instanceof Set ? st.saved.has(s.id) : (Array.isArray(st.saved) ? st.saved.includes(s.id) : Boolean(st.saved && st.saved[s.id]));
      const sel = st.selectedId === s.id;

      const topPills = [];
      const dr = s.price_drop?.[st.mode];
      if (dr) topPills.push(`<span class="fc-pill dr">↓${dr.pct}% Drop</span>`);
      else {
        const uLt = u.lt || ((u.s === "community" || u.s === "reddit") ? "shared" : ((u.zb || u.s === "nobroker" || u.s === "owner") ? "owner" : "broker"));
        if (uLt === "owner") topPills.push(`<span class="fc-pill zb">Owner</span>`);
        else if (uLt === "shared") topPills.push(`<span class="fc-pill sh">Shared</span>`);
        else topPills.push(`<span class="fc-pill br">Broker</span>`);
      }
      const ft = s.features?.tags || [], vt = s.features?.vision_tags || [];
      if (ft.includes("sea_view")) topPills.push(`<span class="fc-pill sea">Sea View</span>`);

      const tags = [];
      const deal = getDeal(s);
      if (deal?.label === "Great Value") tags.push(`<span class="tag good">${Math.abs(deal.pct)}% below avg</span>`);
      if (ft.includes("balcony")) tags.push(`<span class="tag out">Balcony${vt.includes("balcony") ? " · Photo" : ""}</span>`);
      else if (ft.includes("terrace")) tags.push(`<span class="tag out">Terrace</span>`);
      else if (ft.includes("garden")) tags.push(`<span class="tag out">Garden</span>`);
      if (st.hub !== "ALL" && s.commutes?.[st.hub]) tags.push(`<span class="tag ai-v">~${s.commutes[st.hub]}m ${HUB_META[st.hub]?.name}</span>`);
      else if (u.f) tags.push(`<span class="tag">${esc(u.f)}</span>`);

      const directHref = u.u || (isBuy ? (s.sources_buy || {}) : (s.sources_rent || {}))[u.s] || (s.sources || {})[u.s] || "";

      return `
        <article class="fc${sel ? " sel" : ""}" data-id="${esc(s.id)}" data-url="${esc(directHref)}" data-img="${esc(img)}">
          <div class="fc-media">${(s.videos && s.videos.length) ? '<span class="bh-vid-pill">\u25b6 Video</span>' : ""}
            <div class="fc-ph">${archSvg}<span>${esc(s.locality)}</span></div>
            ${img ? `<img referrerpolicy="no-referrer" class="fc-img" src="${esc(img)}" referrerpolicy="no-referrer" loading="lazy" alt="" onerror="this.remove()" />` : ""}
            ${topPills.length ? `<div class="fc-badges-top">${topPills.slice(0, 2).join("")}</div>` : ""}
            <button class="fc-heart${saved ? " on" : ""}" data-save="${esc(s.id)}" aria-label="Save flat">${saved ? "♥" : "♡"}</button>
            ${img || directHref ? `<button type="button" class="fc-nav prev" data-pdir="-1" aria-label="Previous photo">‹</button><button type="button" class="fc-nav next" data-pdir="1" aria-label="Next photo">›</button><span class="fc-pcount">${Array.isArray(u.imgs) && u.imgs.length > 1 ? `1 / ${u.imgs.length}` : "1 / +"}</span>` : ""}
          </div>
          <div class="fc-body">
            <div class="fc-price-row">
              <div class="fc-price">${fmt(u.p, isBuy)}${psfTxt ? `<span class="fc-psf">${psfTxt}</span>` : ""}</div>
              <div class="fc-bhk">${esc(specTxt)}</div>
            </div>
            <div class="fc-title" title="${esc(s.name)}">${esc(s.name)}</div>
            <div class="fc-sub">${esc(subTxt)}</div>
            <div class="fc-foot">
              <div class="fc-tags">${tags.slice(0, 2).join("")}</div>
              ${directHref ? `<a class="fc-src" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" href="${esc(directHref)}" onclick="event.stopPropagation()">${esc(portal)} ↗</a>` : `<span class="fc-src">${esc(portal)}</span>`}
            </div>
          </div>
        </article>`;
    }).join("") + (flats.length > st.page ? `<div class="load-more-wrap"><button id="loadMoreBtn" class="btn">Show more flats (${(flats.length - st.page).toLocaleString("en-IN")} left)</button></div>` : "");

    listEl.querySelectorAll(".fc").forEach(el => {
      const s = socMap.get(el.dataset.id);
      if (!s) return;
      el.onclick = () => {
        st.selectedId = s.id;
        if (!s.coords_approx && s.lat && s.lng) map.panTo([s.lat, s.lng], { animate: true });
        if (typeof openDetail === "function") openDetail(s);
        else if (typeof onPinClick === "function") onPinClick(s);
      };
      el.onmouseenter = () => pillEls.get(s.id)?.classList.add("hi");
      el.onmouseleave = () => pillEls.get(s.id)?.classList.remove("hi");
    });
    listEl.querySelectorAll("[data-save]").forEach(btn => {
      btn.onclick = e => {
        e.stopPropagation();
        if (typeof toggleSave === "function") toggleSave(btn.dataset.save);
      };
    });
    const lm = $("loadMoreBtn");
    if (lm) lm.onclick = () => { st.page += 36; renderList(); };
  }

  function highlightPin(id, on) {
    const mk = pillEls.get(id); if (!mk) return;
    mk.setZIndexOffset(on ? 1200 : (id === st.sel ? 900 : 0));
    const el = mk.getElement()?.querySelector(".price-pill");
    if (el) el.classList.toggle("hov", on);
  }

  function toggleSave(id) {
    const i = st.saved.ids.indexOf(id);
    if (i >= 0) { st.saved.ids.splice(i, 1); toast("Removed from shortlist"); }
    else { st.saved.ids.push(id); toast("Saved to shortlist"); }
    syncCounts(); renderList();
    if (st.sel === id && $("detailSheet").style.display === "flex") { const s = societies.find(x => x.id === id); if (s) openDetail(s); }
    if ($("savedSheet").style.display === "flex") renderSavedSheet();
  }

  function openDetail(s) {
    st.sel = s.id;
    const ctx = s.mumbai_context || {}, g = s.google || {}, civ = s.civic || {}, deal = getDeal(s), isS = st.saved.ids.includes(s.id);
    const units = matchingUnits(s), isBuy = st.mode === "buy";
    const mapsUrl = g.url || (H + "www.google.com/maps/search/?api=1&query=" + encodeURIComponent(`${s.name} ${s.locality} Mumbai`));
    const share = `${location.origin}${location.pathname}?open=${encodeURIComponent(s.id)}`;
    const wa = encodeURIComponent(`${s.name} (${s.locality})\n${getPriceLabel(s)}\nMetro: ${ctx.nearest_metro?.walk_min || "?"}m to ${ctx.nearest_metro?.name || "Metro"}\n${share}`);

    let unitsHtml = "";
    if (units.length) {
      unitsHtml = `<div class="unit-list">${units.map(u => {
        const specs = [u.b !== null && u.b !== undefined ? fmtBhk(u.b) : null, u.sq ? `${u.sq} sq ft` : null, u.f || null, u.flr ? `Flr ${u.flr}` : null, u.fac || null].filter(Boolean).join(" \u00b7 ");
        const portal = PORTAL_NAMES[u.s] || u.s;
        const inner = `<div class="u-left"><div class="u-price">${fmt(u.p, isBuy)}</div><div class="u-meta">${esc(specs || "Verified listing")}</div></div><div class="u-right">${u.zb ? '<span class="zb-dot" title="Zero Brokerage"></span>' : ""}${esc(portal)}${u.u ? " ↗" : ""}</div>`;
        const fbU = (isBuy ? (s.sources_buy || {}) : (s.sources_rent || {}))[u.s] || (s.sources || {})[u.s] || (H + "www.google.com/search?q=" + encodeURIComponent(`${s.name} ${s.locality} Mumbai ${portal} ${isBuy ? "sale" : "rent"}`));
        const href = u.u || fbU;
        const innerLink = `<div class="u-left"><div class="u-price">${fmt(u.p, isBuy)}</div><div class="u-meta">${esc(specs || "Verified listing")}</div></div><div class="u-right">${u.zb ? '<span class="zb-dot" title="Zero Brokerage"></span>' : ""}${esc(portal)} ↗</div>`;
        return `<a class="unit-row" target="_blank" href="${esc(href)}">${innerLink}</a>`;
      }).join("")}</div>`;
    } else {
      const modeSrc = isBuy ? (s.sources_buy || {}) : (s.sources_rent || {});
      const fallbackSrc = Object.keys(modeSrc).length ? modeSrc : (s.sources || {});
      const btns = Object.entries(fallbackSrc).map(([k, u]) => `<a class="unit-row" target="_blank" href="${esc(u)}"><div class="u-left"><div class="u-price">${fmt(getP(s), isBuy)}</div><div class="u-meta">Open on ${esc(PORTAL_NAMES[k] || k)}</div></div><div class="u-right">View ↗</div></a>`).join("");
      unitsHtml = btns ? `<div class="unit-list">${btns}</div>` : `<div class="info-strip">Estimated pricing based on locality trends.</div>`;
    }

    let costHtml = "";
    const pv = getP(s);
    const realDep = units.map(u => u.dep).find(d => d && d >= 5000);
    if (!isBuy && pv && realDep) {
      costHtml = `<div class="info-strip"><strong>Upfront Move-In (Rent):</strong> Deposit <b>${fmt(realDep, true)}</b> \u00b7 Direct <b>${fmt(realDep + pv, true)}</b> \u00b7 Broker ~<b>${fmt(realDep + pv * 2, true)}</b><small>Verified portal security deposit + 1st month rent</small></div>`;
    } else if (!isBuy && pv) {
      costHtml = `<div class="info-strip"><strong>Upfront Move-In (Rent):</strong> Direct ~<b>${fmt(pv * 4, true)}</b> · Broker ~<b>${fmt(pv * 5, true)}</b><small>Standard 3 months deposit + 1st month rent</small></div>`;
    } else if (isBuy && pv) {
      const isTN = s.zone === "Thane" || s.zone === "Navi Mumbai", stdPct = isTN ? 7 : 6, womPct = stdPct - 1, reg = Math.min(30000, Math.round(pv * 0.01));
      costHtml = `<div class="info-strip"><strong>Stamp Duty & Reg (${isTN ? "Thane/Navi Mumbai" : "Mumbai"}):</strong> <b>${fmt(Math.round(pv * stdPct / 100) + reg, true)}</b> (${stdPct}%) · Sole woman buyer: <b>${fmt(Math.round(pv * womPct / 100) + reg, true)}</b> (${womPct}%)<small>Includes ₹30k registration cap (Maharashtra 2026 rates)</small></div>`;
    }

    const igrSearch = H + "www.google.com/search?q=" + encodeURIComponent(`site:zapkey.com OR site:indextap.com "${s.name}" "${s.locality}" Mumbai`);

    $("dName").textContent = s.name;
    $("dSub").textContent = `${s.locality} · ${s.coords_approx ? "Locality Area Pin" : "Verified Building Pin"}${g.rating ? ` · ★ ${g.rating}` : ""}`;
    $("dBody").innerHTML = `
      <div class="d-hero-slot">${s.thumb ? `<img referrerpolicy="no-referrer" class="d-hero" src="${esc(s.thumb)}" referrerpolicy="no-referrer" alt="" onerror="this.remove()" />` : ""}</div>
      <div class="d-actions">
        <button class="btn ${isS ? "active" : ""}" id="dSv">${isS ? "Saved" : "Save"}</button>
        <a class="btn" target="_blank" href="${mapsUrl}">Google Maps ↗</a>
        <a class="btn wa" target="_blank" href="${H}wa.me/?text=${wa}">WhatsApp</a>
      </div>
      <div><div class="sec-lbl">Available ${isBuy ? "For Sale" : "For Rent"} (${units.length || 1}) ${deal?.label === "Great Value" ? `· ${Math.abs(deal.pct)}% below ${esc(s.locality)} median` : ""}</div>${unitsHtml}</div>
      ${costHtml}
      <div>
        <div class="sec-lbl">Essentials</div>
        <div class="g2">
          <div class="met"><small>Nearest Metro</small><strong>${esc(ctx.nearest_metro?.name || "—")}</strong><small>${ctx.nearest_metro?.walk_min || "—"} min walk</small></div>
          <div class="met"><small>Local Train</small><strong>${esc(ctx.nearest_local?.name || "—")}</strong><small>${ctx.nearest_local?.walk_min || "—"} min walk</small></div>
          <div class="met"><small>Monsoon Safety</small><strong class="risk-${ctx.monsoon_flood_risk || "low"}">${(ctx.monsoon_flood_risk || "low").toUpperCase()} RISK</strong></div>
          <div class="met"><small>${civ.hospital ? `Hospital (${fmtDist(civ.hospital.dist_m)})` : "Commute to BKC"}</small><strong>${civ.hospital ? esc(civ.hospital.name) : `~${ctx.commute_hubs_min?.bkc || "—"} min`}</strong></div>
        </div>
      </div>
      ${g.reviews?.length ? `<div><div class="sec-lbl">Resident Reviews</div>${g.reviews.map(r => `<div class="rev"><b>★ ${r.rating || ""}</b> — ${esc(r.text)}</div>`).join("")}</div>` : ""}
      <div><div class="sec-lbl">Your Notes</div><textarea id="dNote" rows="2" placeholder="Floor, sunlight, water supply, broker contact...">${esc(st.saved.notes[s.id] || "")}</textarea></div>
      <div class="quiet-links">
        ${s.rera_ids?.length ? `<a target="_blank" href="${H}maharera.maharashtra.gov.in/projects-search-result?project_name=${encodeURIComponent(s.rera_ids[0])}"><span>MahaRERA ${esc(s.rera_ids[0])}</span><span>↗</span></a>` : ""}
        <a target="_blank" href="${igrSearch}"><span>Check Registered Sale Prices (Zapkey / IndexTap)</span><span>↗</span></a>
      </div>`;

    $("detailBackdrop").style.display = "block"; $("detailSheet").style.display = "flex";
    if ($("dSv")) $("dSv").onclick = () => toggleSave(s.id);
    if ($("dNote")) $("dNote").oninput = e => { st.saved.notes[s.id] = e.target.value; syncCounts(); };
    renderMap();
  }

  function renderSavedSheet() {
    const items = st.saved.ids.map(id => societies.find(x => x.id === id)).filter(Boolean);
    $("svSub").textContent = items.length ? `${items.length} shortlisted homes` : "Save homes to compare or plan visits";
    $("svFoot").style.display = items.length ? "flex" : "none";
    $("svBody").innerHTML = !items.length
      ? `<div class="empty"><p>Tap the heart on any home to build your shortlist, compare side-by-side, or generate a 1-tap Weekend Visit Route.</p><button class="btn" id="svAddExt">+ Add Housing.com / 99acres URL</button></div>`
      : items.map(s => renderCardHtml(s, $("fHub").value)).join("") + `<button class="btn" id="svAddExt" style="width:100%;margin-top:4px;">+ Add External Listing (Housing / 99acres)</button>`;
    bindCardEvents($("svBody"));
    const addBtn = $("svAddExt"); if (addBtn) addBtn.onclick = () => { closeSaved(); $("clipModal").style.display = "grid"; };
  }

  function planVisitRoute() {
    const items = st.saved.ids.map(id => societies.find(x => x.id === id)).filter(Boolean);
    if (!items.length) return toast("Save homes first");
    const ordered = [...items].sort((a, b) => (b.lat || 0) - (a.lat || 0)).slice(0, 8);
    const pts = ordered.map(s => encodeURIComponent(s.coords_approx ? `${s.name}, ${s.locality}, Mumbai` : `${s.lat},${s.lng}`));
    const dest = pts[pts.length - 1], mid = pts.slice(0, -1).join("|");
    window.open(`${H}www.google.com/maps/dir/?api=1&destination=${dest}${mid ? `&waypoints=${mid}` : ""}&travelmode=driving`, "_blank");
  }

  function openCmp(overrideIds) {
    const ids = overrideIds || st.saved.ids.slice(0, 4);
    const items = ids.map(id => societies.find(x => x.id === id)).filter(Boolean);
    const row = (l, fn) => `<tr><th>${l}</th>${items.map(s => `<td>${fn(s)}</td>`).join("")}</tr>`;
    $("cmpBody").innerHTML = !items.length
      ? `<div class="empty"><p>Save up to 4 homes to compare them side-by-side.</p></div>`
      : `<div style="overflow-x:auto;"><table class="ctbl">
          <tr><th>Feature</th>${items.map(s => `<th>${esc(s.name)}<br/><small>${esc(s.locality)}</small></th>`).join("")}</tr>
          ${row("Price", s => getPriceLabel(s))}
          ${row("Value", s => { const d = getDeal(s); return d ? `${d.label} (${d.pct > 0 ? "+" : ""}${d.pct}%)` : "—"; })}
          ${row("Size", s => s.bhks?.length ? s.bhks.map(fmtBhk).join(", ") : "—")}
          ${row("Carpet", s => s.rera_carpet_sqft ? s.rera_carpet_sqft + " sq ft" : "—")}
          ${row("Metro", s => s.mumbai_context?.nearest_metro ? `${esc(s.mumbai_context.nearest_metro.name)} (${s.mumbai_context.nearest_metro.walk_min}m)` : "—")}
          ${row("Monsoon", s => (s.mumbai_context?.monsoon_flood_risk || "low").toUpperCase())}
          ${row("Rating", s => s.google?.rating ? `★ ${s.google.rating}` : "—")}
        </table></div>`;
    const shareLink = `${location.origin}${location.pathname}?list=${encodeURIComponent(items.map(x => x.id).join(","))}`;
    $("copyCmpLink").onclick = () => navigator.clipboard?.writeText(shareLink).then(() => toast("Shortlist link copied"));
    $("shareCmpWa").onclick = () => {
      const msg = `Bombay Homes Shortlist (${items.length} homes):\n` + items.map((s, i) => `${i + 1}. ${s.name} (${s.locality}) — ${getPriceLabel(s)}`).join("\n") + `\n\nCompare: ${shareLink}`;
      window.open(H + "wa.me/?text=" + encodeURIComponent(msg), "_blank");
    };
    $("cmpModal").style.display = "grid";
  }

  function addClippedHome(obj) {
    const name = (obj.name || "External Flat").trim().slice(0, 80), url = (obj.url || "").trim(), price = Number(obj.price || 0), isBuy = price >= 2000000;
    const portal = obj.portal || (url.includes("housing.com") ? "housing" : (url.includes("99acres") ? "99acres" : "other")), id = "clip-" + Date.now().toString(36);
    const unit = price ? [{ p: price, b: null, sq: Number(obj.sqft || 0) || null, s: portal, u: url || null, zb: false, f: null }] : [];
    st.clipped.unshift({
      id, name, _clipped: true, locality: (obj.locality || "Mumbai").trim(), zone: "Mumbai",
      lat: 19.076, lng: 72.8777, coords_approx: true, bhks: [], furnishing: [], tenant: [], rera_ids: [],
      rera_carpet_sqft: Number(obj.sqft || 0) || null,
      pricing: { rent_monthly_inr: { median: isBuy ? null : (price || null), is_estimate: false }, buy_inr: { median: isBuy ? price : null, is_estimate: false }, has_zero_brokerage: false, by_portal: {} },
      units_rent: isBuy ? [] : unit, units_buy: isBuy ? unit : [],
      mumbai_context: { monsoon_flood_risk: "low" }, sources: url ? { [portal]: url } : {}
    });
    if (!st.saved.ids.includes(id)) st.saved.ids.unshift(id);
    rebuildSocietyList(); syncCounts(); renderAll(); toast(`Saved "${name}"`);
  }

  function resetAll() {
    $("searchBox").value = ""; ["fZone","fLoc","fSource","fFurn","fTen"].forEach(id => $(id).value = "ALL");
    $("fHub").value = ""; ["fHubMin","fMetro","fRate"].forEach(id => $(id).value = "0"); if ($("sortSelect")) $("sortSelect").value = "rec";
    $("sMin").value = 0; $("sMax").value = SQFT_MAX; syncSqftSlider(); resetPriceScale();
    st.bhks.clear(); document.querySelectorAll(".bhk-opt").forEach(b => b.classList.remove("active"));
    st.zero = st.dealOnly = st.flood = st.exactOnly = st.showEst = st.mapBounds = false; st.lasso = null; st.multiLocs = []; st.brightOnly = false; st.reraOnly = false; st.lister = "ALL"; st.page = 36; if (window.__bhClearLasso) window.__bhClearLasso(true); if (window.__bhResetAiUiOnly) window.__bhResetAiUiOnly();
    document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
    document.querySelectorAll(".n-chip").forEach(c => c.classList.toggle("active", c.dataset.nb === "ALL"));
    ["fExactOnly","fShowEst","mapAreaBtn"].forEach(id => $(id).classList.remove("active"));
    populateLocalities(); renderAll();
  }

  const closeDetail = () => { $("detailBackdrop").style.display = "none"; $("detailSheet").style.display = "none"; };
  const openFilters = () => { $("filterBackdrop").style.display = "block"; $("filterSheet").style.display = "flex"; };
  const closeFilters = () => { $("filterBackdrop").style.display = "none"; $("filterSheet").style.display = "none"; };
  const openSaved = () => { renderSavedSheet(); $("savedBackdrop").style.display = "block"; $("savedSheet").style.display = "flex"; };
  const closeSaved = () => { $("savedBackdrop").style.display = "none"; $("savedSheet").style.display = "none"; };

  function setMobView(v) {
    document.body.className = "view-" + v;
    $("mobTogTxt").textContent = v === "map" ? "List" : "Map";
    $("mobTogIc").innerHTML = v === "map"
      ? '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>'
      : '<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>';
    $("mapPreview").style.display = "none";
    setTimeout(() => { map.invalidateSize(); renderMap(); }, 90);
  }

  $("modeRent").onclick = () => { st.mode = "rent"; $("modeRent").classList.add("active"); $("modeBuy").classList.remove("active"); resetPriceScale(); renderAll(); };
  $("modeBuy").onclick = () => { if (!window.__bhBuyDone) window.__bhModeLoading = "buy"; st.mode = "buy"; $("modeBuy").classList.add("active"); $("modeRent").classList.remove("active"); resetPriceScale(); renderAll(); ensureBuyShardsLoaded(); };
  $("themeBtn").onclick = () => applyTheme(st.theme === "dark" ? "light" : "dark");
  $("openFilterBtn").onclick = openFilters; $("closeFilterBtn").onclick = closeFilters; $("filterBackdrop").onclick = closeFilters; $("applyFiltersBtn").onclick = closeFilters;
  $("clearFiltersBtn").onclick = resetAll; $("resetMiniBtn").onclick = resetAll;
  $("savedBtn").onclick = openSaved; $("closeSavedBtn").onclick = closeSaved; $("savedBackdrop").onclick = closeSaved;
  $("closeDetailBtn").onclick = closeDetail; $("detailBackdrop").onclick = closeDetail;
  $("closeClusterBtn").onclick = closeCluster; $("clusterBackdrop").onclick = closeCluster;
  $("planRouteBtn").onclick = planVisitRoute; $("openCmpBtn").onclick = () => { closeSaved(); openCmp(); };
  $("closeCmp").onclick = () => $("cmpModal").style.display = "none"; $("closeClip").onclick = () => $("clipModal").style.display = "none";
  $("saveClipBtn").onclick = () => {
    const name = $("cName").value.trim(); if (!name) return toast("Enter society or flat name");
    addClippedHome({ name, locality: $("cLoc").value, price: $("cPrice").value, portal: $("cPortal").value, sqft: $("cSqft").value, url: $("cUrl").value });
    ["cName","cLoc","cPrice","cSqft","cUrl"].forEach(id => $(id).value = ""); $("clipModal").style.display = "none";
  };

  $("mobToggle").onclick = () => setMobView(document.body.classList.contains("view-map") ? "list" : "map");
  $("msStreet").onclick = () => setMapStyle("street"); $("msDark").onclick = () => setMapStyle("dark"); $("msSat").onclick = () => setMapStyle("sat");
  $("togMetro").onclick = e => { st.showMetro = !st.showMetro; e.currentTarget.classList.toggle("active", st.showMetro); if (st.showMetro) metroL.addTo(map); else map.removeLayer(metroL); };
  $("togFlood").onclick = e => { st.showFlood = !st.showFlood; e.currentTarget.classList.toggle("active", st.showFlood); if (st.showFlood) floodL.addTo(map); else map.removeLayer(floodL); };
  $("mapAreaBtn").onclick = e => { st.mapBounds = !st.mapBounds; if (st.mapBounds && st.lasso) { st.lasso = null; if (window.__bhClearLasso) window.__bhClearLasso(true); } e.currentTarget.classList.toggle("active", st.mapBounds); st.page = 36; renderAll(); };

  document.querySelectorAll(".chip").forEach(btn => {
    btn.onclick = () => {
      const k = btn.dataset.q;
      if (k === "zero") { st.zero = !st.zero; btn.classList.toggle("active", st.zero); }
      else if (k === "deal") { st.dealOnly = !st.dealOnly; btn.classList.toggle("active", st.dealOnly); }
      else if (k === "flood") { st.flood = !st.flood; btn.classList.toggle("active", st.flood); }
      else if (k === "metro") { const on = $("fMetro").value !== "10"; $("fMetro").value = on ? "10" : "0"; btn.classList.toggle("active", on); }
      else if (k === "community") { const on = $("fSource").value !== "community"; $("fSource").value = on ? "community" : "ALL"; btn.classList.toggle("active", on); }
      else if (k === "rated") { const on = $("fRate").value !== "4.0"; $("fRate").value = on ? "4.0" : "0"; btn.classList.toggle("active", on); }
      st.page = 36; renderAll();
    };
  });


  const NB_VIEWS = {
    "ALL": [19.088, 72.885, 11],
    "South Mumbai": [18.972, 72.820, 13],
    "Bandra-Santacruz": [19.064, 72.838, 14],
    "Andheri-Juhu": [19.124, 72.838, 13],
    "Powai-Central": [19.118, 72.908, 13],
    "Thane": [19.222, 72.974, 13],
    "Navi Mumbai": [19.048, 73.035, 12]
  };
  document.querySelectorAll(".n-chip").forEach(btn => {
    btn.onclick = () => {
      const nb = btn.dataset.nb;
      $("fZone").value = nb;
      populateLocalities();
      document.querySelectorAll(".n-chip").forEach(x => x.classList.toggle("active", x.dataset.nb === nb));
      const v = NB_VIEWS[nb];
      if (v) map.flyTo([v[0], v[1]], v[2], { duration: 0.55 });
      st.page = 36; renderAll();
    };
  });

  $("fZone").addEventListener("change", () => { document.querySelectorAll(".n-chip").forEach(x => x.classList.toggle("active", x.dataset.nb === $("fZone").value)); populateLocalities(); st.page = 36; renderAll(); });
  $("sortSelect")?.addEventListener("change", () => { st.page = 36; renderAll(); });
  ["mpMin","mpMax"].forEach(id => $(id).addEventListener("input", () => { syncPriceSliders(Number($("mpMin").value), Number($("mpMax").value)); st.page = 36; scheduleRender(); }));
  ["sMin","sMax"].forEach(id => $(id).addEventListener("input", () => { syncSqftSlider(); st.page = 36; scheduleRender(); }));
  document.querySelectorAll(".bhk-opt").forEach(btn => {
    btn.onclick = () => { const v = Number(btn.dataset.bhk); if (st.bhks.has(v)) st.bhks.delete(v); else st.bhks.add(v); btn.classList.toggle("active", st.bhks.has(v)); st.page = 36; renderAll(); };
  });
  $("fExactOnly").onclick = e => { st.exactOnly = !st.exactOnly; e.currentTarget.classList.toggle("active", st.exactOnly); st.page = 36; renderAll(); };
  $("fShowEst").onclick = e => { st.showEst = !st.showEst; e.currentTarget.classList.toggle("active", st.showEst); st.page = 36; renderAll(); };
  ["searchBox","fLoc","fSource","fMetro","fHub","fHubMin","fFurn","fTen","fRate"].forEach(id => $(id).addEventListener("input", () => { st.page = 36; scheduleRender(); }));

  map.on("moveend zoomend", () => { if (st.mapBounds) renderAll(); else renderMap(); });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeDetail(); closeFilters(); closeCluster(); closeSaved(); $("cmpModal").style.display = "none"; $("clipModal").style.display = "none"; $("mapPreview").style.display = "none"; }
    if (e.key === "/" && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)) { e.preventDefault(); $("searchBox").focus(); }
  });

  applyTheme(st.theme); resetPriceScale(); syncSqftSlider(); syncCounts();
  if (window.innerWidth <= 1024) setMobView("list");


  let directSocieties = [];
  function mapDirectRow(r) {
    const isBuy = r.mode === "buy";
    const unit = [{ p: r.price_inr, b: r.bhk, sq: r.carpet_sqft || null, s: r.source || "owner", u: r.url || null, zb: !!r.zero_brokerage, f: r.furnishing || null }];
    return {
      id: r.id, name: r.name, locality: r.locality || "Mumbai", zone: r.zone || "Mumbai",
      lat: r.lat || 19.076, lng: r.lng || 72.8777, coords_approx: !(r.lat && r.lng),
      bhks: r.bhk !== null && r.bhk !== undefined ? [r.bhk] : [],
      furnishing: r.furnishing ? [r.furnishing] : [], tenant: [], rera_ids: [],
      rera_carpet_sqft: r.carpet_sqft || null,
      pricing: {
        rent_monthly_inr: { median: isBuy ? null : r.price_inr, is_estimate: false },
        buy_inr: { median: isBuy ? r.price_inr : null, is_estimate: false },
        has_zero_brokerage: !!r.zero_brokerage, by_portal: {}
      },
      units_rent: isBuy ? [] : unit, units_buy: isBuy ? unit : [],
      mumbai_context: { monsoon_flood_risk: "low" },
      sources: r.url ? { [r.source || "owner"]: r.url } : {},
      _direct: true, _contact: r.contact || null
    };
  }
  function loadDirectListings() {
    fetch("./api/listings", { cache: "no-store" })
      .then(r => r.ok ? r.json() : { listings: [] })
      .then(d => {
        directSocieties = (d.listings || []).map(mapDirectRow);
        if (directSocieties.length) { rebuildSocietyList(); populateLocalities(); populateSources(); renderAll(); }
      })
      .catch(() => {});
  }
  if ($("listFlatBtn")) $("listFlatBtn").onclick = () => { $("postModal").style.display = "grid"; };
  if ($("closePost")) $("closePost").onclick = () => { $("postModal").style.display = "none"; };
  if ($("submitPostBtn")) $("submitPostBtn").onclick = () => {
    const name = $("pName").value.trim(), price = Number($("pPrice").value || 0);
    if (!name || price < 5000) return toast("Enter society name and valid price");
    const payload = {
      name, locality: $("pLoc").value.trim() || "Mumbai", mode: $("pMode").value,
      price_inr: price, bhk: Number($("pBhk").value), carpet_sqft: Number($("pSqft").value || 0) || null,
      contact: $("pContact").value.trim() || null, zero_brokerage: true, source: "owner"
    };
    fetch("./api/listings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          toast("Listing published live!");
          ["pName","pLoc","pPrice","pSqft","pContact"].forEach(id => $(id).value = "");
          $("postModal").style.display = "none";
        
    document.querySelectorAll("#listerToggle button").forEach(b => {
    b.onclick = () => {
      st.lister = b.dataset.lt || "ALL";
      document.querySelectorAll("#listerToggle button").forEach(x => x.classList.toggle("active", x.dataset.lt === st.lister));
      st.page = 36; renderAll();
    };
  });
  document.querySelectorAll("#viewToggle button").forEach(b => {
    b.onclick = () => {
      st.view = b.dataset.v;
      document.querySelectorAll("#viewToggle button").forEach(x => x.classList.toggle("active", x.dataset.v === st.view));
      document.body.classList.toggle("gallery-mode", st.view === "gallery");
      if (st.view === "split") setTimeout(() => map.invalidateSize(), 120);
      st.page = 48; renderAll();
    };
  });
  if ($("fHub")) {
    const syncHubUI = () => {
      st.hub = ($("fHub").value || "ALL");
      st.hubMin = Number($("fHubMin").value || 45);
      if ($("hubVal")) $("hubVal").textContent = st.hub === "ALL" ? "Any" : `≤ ${st.hubMin} min to ${HUB_META[st.hub]?.name || st.hub}`;
      if (st.hub !== "ALL" && HUB_META[st.hub]) map.flyTo(HUB_META[st.hub].ll, 12, { duration: 0.5 });
      st.page = 36; renderAll();
    };
    $("fHub").addEventListener("change", syncHubUI);
    $("fHubMin").addEventListener("input", syncHubUI);
  }
  document.addEventListener("keydown", e => {
    if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") {
      e.preventDefault(); $("searchBox")?.focus();
    } else if (e.key === "Escape") {
      if ($("detailSheet")) $("detailSheet").classList.remove("open");
      if ($("filterSheet")) $("filterSheet").classList.remove("open");
      if ($("savedModal")) $("savedModal").style.display = "none";
      if ($("postModal")) $("postModal").style.display = "none";
    }
  });

  loadDirectListings();
        } else {
          toast(res.error || "Bind D1 database in Cloudflare first");
        }
      })
      .catch(() => toast("Could not reach /api/listings"));
  };

  loadDirectListings();
  let _bhManifest = null, _bhBuyLoaded = false, _bhBuyPromise = null;
  function _mergeShardSocieties(existing, incoming) {
    const mapById = new Map(existing.map(s => [s.id, s]));
    for (const s of incoming) {
      const prev = mapById.get(s.id);
      if (!prev) {
        mapById.set(s.id, s);
      } else {
        if (s.units_buy && s.units_buy.length) prev.units_buy = s.units_buy;
        if (s.units_rent && s.units_rent.length) prev.units_rent = s.units_rent;
        if (s.pricing) prev.pricing = Object.assign({}, prev.pricing || {}, s.pricing);
        if (s.sources_buy) prev.sources_buy = s.sources_buy;
        if (s.sources_rent) prev.sources_rent = s.sources_rent;
      }
    }
    return [...mapById.values()];
  }
  async function _loadShardList(relPaths) {
    const parts = await Promise.all(
      (relPaths || []).map(rel =>
        fetch("./public/data/" + rel, { cache: "default" }).then(r => {
          if (!r.ok) throw new Error("Shard HTTP " + r.status);
          return r.json();
        })
      )
    );
    const out = [];
    for (const arr of parts) {
      if (!Array.isArray(arr)) continue;
      for (const _s of arr) {
        if (!_s) continue;
        if (_s.thumb) _s.thumb = bhProxySy(_s.thumb);
        if (Array.isArray(_s.photos)) _s.photos = _s.photos.map(bhProxySy);
        for (const _uk of ["units_rent", "units_buy"]) {
          if (Array.isArray(_s[_uk])) {
            for (const _u of _s[_uk]) {
              if (_u.img) _u.img = bhProxySy(_u.img);
              if (Array.isArray(_u.imgs)) _u.imgs = _u.imgs.map(bhProxySy);
            }
          }
        }
        out.push(_s);
      }
    }
    return out;
  }
  async function ensureBuyShardsLoaded() {
    // BH_V59B_BUY_SMOOTH
    if (!window.__bhBuyDone) window.__bhModeLoading = "buy";
    if (_bhBuyLoaded || !_bhManifest) return;
    if (!_bhBuyPromise) {
      _bhBuyPromise = _loadShardList(_bhManifest.buy_shards).then(buyRows => { window.__bhBuyDone = true; window.__bhModeLoading = null;
        baseSocieties = _mergeShardSocieties(baseSocieties, buyRows);
        _bhBuyLoaded = true;
        rebuildSocietyList(); populateLocalities(); populateSources(); renderAll();
      }).catch(err => { console.error("Buy shard load failed:", err); _bhBuyPromise = null; });
    }
    return _bhBuyPromise;
  }
  window.__bhEnsureBuy = ensureBuyShardsLoaded;
  // BH_V59B_PREFETCH: quietly pre-load Buy shards after Rent renders so Rent->Buy is instant
  setTimeout(() => { try { if (typeof ensureBuyShardsLoaded === 'function') ensureBuyShardsLoaded(); } catch {} }, 2200);

  fetch("./public/data/manifest.json", { cache: "no-store" })
    .then(r => { if (!r.ok) throw new Error("Manifest HTTP " + r.status); return r.json(); })
    .then(async man => {
      _bhManifest = man;
      const rentRows = await _loadShardList(man.rent_shards);
      return { societies: rentRows, generated_at: man.generated_at, count: man.count };
    })
    .then(d => {
      baseSocieties = d.societies || []; rebuildSocietyList(); populateLocalities(); populateSources();
      if (st.mode === "buy") ensureBuyShardsLoaded();
      $("freshBadge").textContent = `${baseSocieties.length.toLocaleString("en-IN")} homes · ${d.generated_at}`;
      renderAll();
      const params = new URLSearchParams(location.search);
      const listRaw = params.get("list"); if (listRaw) { const ids = listRaw.split(",").filter(Boolean); if (ids.length) openCmp(ids); }
      const oid = params.get("open"); if (oid) { const t = societies.find(s => s.id === oid); if (t) { map.setView([t.lat, t.lng], 15); openDetail(t); } }
    })
    .catch(err => { $("freshBadge").textContent = "Load error: " + (err?.message || "retry"); });

  


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
  const sInput = $("searchBox");
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
    if ("search" in st) st.search = "";
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
    const normS = v => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const normQ = normS(q);
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
    if (normQ) locList = locList.filter(x => normS(x.loc).includes(normQ));
    locList.sort((a, b) => {
      const aPre = normQ && normS(a.loc).startsWith(normQ) ? 1 : 0;
      const bPre = normQ && normS(b.loc).startsWith(normQ) ? 1 : 0;
      return (bPre - aPre) || (b.flats - a.flats);
    });
    locList = locList.slice(0, q ? 6 : 7);

    let socList = [];
    if (q.length >= 2) {
      socList = societies.filter(s => {
        const uLen = ((isBuy ? s.units_buy : s.units_rent) || []).length;
        return uLen > 0 && (normS(s.name).includes(normQ) || normS(s.locality).includes(normQ));
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
      e.preventDefault(); $("searchBox")?.focus();
    } else if (e.key === "Escape") {
      if (ssBox) ssBox.style.display = "none";
      ["detailSheet","filterSheet"].forEach(id => $(id)?.classList.remove("open"));
      ["savedModal","postModal"].forEach(id => { if ($(id)) $(id).style.display = "none"; });
    }
  });
  /* === END V15.6 CONTROLS === */


  


  /* === V16 GALLERY, SEARCH & RESIZER === */
  const realSearchEl = $("searchBox");
  if (realSearchEl) {
    let _sTimer = 0;
    realSearchEl.addEventListener("input", () => {
      clearTimeout(_sTimer);
      _sTimer = setTimeout(() => {
        const tv = (realSearchEl.value || "").trim().toLowerCase();
        if (tv.length >= 3) {
          const hitOtherZone = societies.some(s => (s.locality || "").toLowerCase().includes(tv) && $("fZone") && $("fZone").value !== "ALL" && s.zone !== $("fZone").value);
          if (hitOtherZone) {
            if ($("fZone")) $("fZone").value = "ALL";
            if ($("fLoc")) $("fLoc").value = "ALL";
            if (st.zone && st.zone !== "ALL") st.zone = "ALL";
            document.querySelectorAll(".zone-pill, [data-zone]").forEach(z => z.classList.toggle("active", z.dataset.zone === "ALL"));
          }
        }
        st.page = 36;
        renderAll();
      }, 80);
    });
  }

  const PHOTO_CACHE = new Map();

  function collectLocalPhotos(socId, unitUrl, primaryImg) {
    const out = [], seen = new Set();
    const pushImg = u => {
      if (!u || typeof u !== "string" || !u.startsWith("http")) return;
      const k = u.split("?")[0].toLowerCase();
      if (seen.has(k)) return;
      seen.add(k); out.push(u);
    };
    pushImg(primaryImg);
    const s = societies.find(x => x.id === socId);
    if (s) {
      const allU = [...(s.units_rent || []), ...(s.units_buy || [])];
      const exactU = unitUrl ? allU.find(u => u.u === unitUrl) : null;
      if (exactU && Array.isArray(exactU.imgs)) exactU.imgs.forEach(pushImg);
      pushImg(s.thumb);
      for (const u of allU) {
        if (u.img) pushImg(u.img);
        if (Array.isArray(u.imgs)) u.imgs.forEach(pushImg);
        if (out.length >= 10) break;
      }
    }
    return out;
  }

  async function fetchFullGallery(socId, unitUrl, primaryImg) {
    const key = unitUrl || socId;
    if (PHOTO_CACHE.has(key)) return PHOTO_CACHE.get(key);
    const local = collectLocalPhotos(socId, unitUrl, primaryImg);
    if (!unitUrl || !unitUrl.startsWith("http")) { PHOTO_CACHE.set(key, local); return local; }
    try {
      const r = await fetch(`/api/photos?url=${encodeURIComponent(unitUrl)}`);
      if (r.ok) {
        const d = await r.json();
        const remote = Array.isArray(d.photos) ? d.photos : [];
        const merged = [], seen = new Set();
        for (const u of [...remote, ...local]) {
          if (!u || typeof u !== "string") continue;
          const dk = u.split("?")[0].toLowerCase();
          if (seen.has(dk)) continue;
          seen.add(dk); merged.push(u);
        }
        const finalList = merged.slice(0, 12);
        PHOTO_CACHE.set(key, finalList);
        return finalList;
      }
    } catch {}
    PHOTO_CACHE.set(key, local);
    return local;
  }

  const clNode = $("cardList");
  if (clNode && clNode.addEventListener) {
    clNode.addEventListener("click", async e => {
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
      if (!photos) {
        if (cntEl) cntEl.textContent = "…";
        photos = await fetchFullGallery(socId, unitUrl, baseImg);
        card._photos = photos; card._pIdx = 0;
      }
      if (!photos.length) { if (cntEl) cntEl.textContent = "No photos"; return; }
      if (photos.length === 1) { if (cntEl) cntEl.textContent = "1 / 1"; return; }
      const nextIdx = ((card._pIdx || 0) + dir + photos.length) % photos.length;
      card._pIdx = nextIdx;

      let imgEl = media.querySelector("img.fc-img");
      if (!imgEl) {
        imgEl = document.createElement("img");
        imgEl.className = "fc-img"; imgEl.referrerPolicy = "no-referrer"; imgEl.alt = "";
        media.insertBefore(imgEl, media.firstChild?.nextSibling || null);
      }
      imgEl.src = photos[nextIdx];
      if (cntEl) cntEl.textContent = `${nextIdx + 1} / ${photos.length}`;
    }, true);
  }

  const dsNode = $("detailSheet");
  if (dsNode && typeof MutationObserver !== "undefined") {
    const upgradeDetailGallery = () => {
      if (!dsNode.classList.contains("open") || dsNode.querySelector(".d-gal-wrap")) return;
      const soc = societies.find(x => x.id === st.selectedId);
      if (!soc) return;
      const us = ((st.mode === "buy") ? soc.units_buy : soc.units_rent) || [];
      const topU = us[0] || {};
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
      const paint = () => {
        if (!dPhotos.length) { wrap.style.display = "none"; return; }
        img.src = dPhotos[dIdx];
        cnt.textContent = `${dIdx + 1} / ${dPhotos.length}`;
        prev.style.display = next.style.display = dPhotos.length > 1 ? "grid" : "none";
      };
      paint();
      prev.onclick = () => { dIdx = (dIdx - 1 + dPhotos.length) % dPhotos.length; paint(); };
      next.onclick = () => { dIdx = (dIdx + 1) % dPhotos.length; paint(); };
      fetchFullGallery(soc.id, topU.u, img.src).then(full => {
        if (full && full.length) { dPhotos = full; dIdx = Math.min(dIdx, dPhotos.length - 1); paint(); }
      });
    };
    new MutationObserver(upgradeDetailGallery).observe(dsNode, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  }

  const chipStrip = document.querySelector(".chips");
  if (chipStrip && chipStrip.addEventListener) {
    chipStrip.addEventListener("wheel", e => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && chipStrip.scrollWidth > chipStrip.clientWidth) {
        e.preventDefault(); chipStrip.scrollLeft += e.deltaY;
      }
    }, { passive: false });
  }

  const mapHost = document.querySelector("#mapPane") || $("map");
  if (mapHost && mapHost.appendChild && !$("paneResizer")) {
    const handle = document.createElement("div");
    handle.id = "paneResizer"; handle.title = "Drag to resize panel · Double-click to reset";
    handle.setAttribute("role", "separator"); handle.setAttribute("aria-orientation", "vertical");
    mapHost.appendChild(handle);

    const DEFAULT_W = 560;
    const clampW = w => Math.round(Math.max(290, Math.min(((typeof window !== "undefined" && window.innerWidth) ? window.innerWidth : 1440) - 260, w)));
    const applyPaneW = (w, persist = false) => {
      const cw = clampW(w);
      if (document.documentElement?.style?.setProperty) document.documentElement.style.setProperty("--pane-w", cw + "px");
      if (persist) { try { localStorage.setItem("bh_pane_w", String(cw)); } catch {} }
    };
    try { const savedW = Number(localStorage.getItem("bh_pane_w") || 0); if (savedW >= 290) applyPaneW(savedW, false); } catch {}

    let dragging = false, rafId = 0;
    const syncMapSize = () => { rafId = 0; try { map.invalidateSize({ animate: false }); } catch {} };
    handle.addEventListener("pointerdown", e => {
      if (e.button && e.button !== 0) return;
      dragging = true; document.body.classList.add("resizing-pane");
      if (handle.setPointerCapture) handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    handle.addEventListener("pointermove", e => {
      if (!dragging) return;
      applyPaneW(e.clientX, false);
      if (!rafId && typeof requestAnimationFrame === "function") rafId = requestAnimationFrame(syncMapSize);
    });
    const endDrag = e => {
      if (!dragging) return;
      dragging = false; document.body.classList.remove("resizing-pane");
      if (e && e.clientX) applyPaneW(e.clientX, true);
      try { map.invalidateSize({ animate: false }); renderMap(); } catch {}
    };
    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
    handle.addEventListener("dblclick", () => {
      applyPaneW(DEFAULT_W, true);
      setTimeout(() => { try { map.invalidateSize({ animate: false }); renderMap(); } catch {} }, 40);
    });
  }
  /* === END V16 === */
  // v36 Full Bridge for web/js/enhancements.js (Ask Map AI + Bright & Modern)
  window.__bh = () => ({
    map: typeof map !== "undefined" ? map : null,
    st: typeof st !== "undefined" ? st : null,
    societies: typeof societies !== "undefined" ? societies : (typeof baseSocieties !== "undefined" ? baseSocieties : []),
    filtered: typeof filtered !== "undefined" ? filtered : [],
    matchingUnits: typeof matchingUnits === "function" ? matchingUnits : null,
    renderList: typeof renderList === "function" ? renderList : null,
    renderAll: typeof renderAll === "function" ? renderAll : null,
    applyFilters: typeof renderAll === "function" ? renderAll : null,
    renderMap: typeof renderMap === "function" ? renderMap : null,
    renderLocChips: typeof renderLocChips === "function" ? renderLocChips : null,
    fitToSelectedLocalities: typeof fitToSelectedLocalities === "function" ? fitToSelectedLocalities : null,
    ensureBuy: typeof ensureBuyShardsLoaded === "function" ? ensureBuyShardsLoaded : null,
    openDetail: typeof openDetail === "function" ? openDetail : null,
    priceMax: typeof priceMax === "function" ? priceMax : null,
    setMode: async (want) => {
      const target = want === "buy" ? "buy" : "rent";
      if (st.mode !== target) {
        const btn = document.querySelector(`[data-mode="${target}"]`) || document.getElementById(target === "buy" ? "modeBuy" : "modeRent");
        if (btn) {
          btn.click();
        } else {
          st.mode = target;
          st.pLo = 0;
          st.pHi = priceMax();
        }
      }
      if (target === "buy" && typeof ensureBuyShardsLoaded === "function") {
        await ensureBuyShardsLoaded();
      }
    },
    resetAskFilters: () => {
      if (st.bhks && st.bhks.clear) st.bhks.clear();
      st.pLo = 0;
      st.pHi = priceMax();
      st.sLo = 0;
      st.sHi = SQFT_MAX;
      st.zero = false;
      st.community = false;
      st.lister = "ALL";
      st.balcony = false;
      st.seaview = false;
      st.terrace = false;
      st.drop = false;
      st.flood = false;
      st.dealOnly = false;
      st.brightOnly = false;
      st.reraOnly = false;
      st.hub = "ALL";
      st.hubMin = 45;
      st.multiLocs = [];
      st.mapBounds = false;
      st.page = 36;
      for (const [id, val] of [["searchBox", ""], ["fZone", "ALL"], ["fLoc", "ALL"], ["fSource", "ALL"], ["fFurn", "ALL"], ["fTen", "ALL"], ["fMetro", "0"], ["fHub", ""], ["fHubMin", "0"], ["fRate", "0"], ["sortSelect", "rec"]]) {
        const el = document.getElementById(id);
        if (el) el.value = val;
      }
      document.querySelectorAll(".bhk-btn, [data-bhk], #bhBrightBtn").forEach(b => b.classList.remove("active"));
      if (typeof renderLocChips === "function") renderLocChips();
    }
  });


})();
