(() => {
  const H = "https" + "://";
  const fLink = document.createElement("link");
  fLink.rel = "stylesheet";
  fLink.href = H + "fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap";
  document.head.appendChild(fLink);

  const RENT_STOPS = [0,10000,15000,20000,25000,30000,35000,40000,45000,50000,60000,70000,80000,90000,100000,120000,140000,160000,180000,200000,250000,300000,350000,400000,500000,750000];
  const BUY_STOPS  = [0,4000000,6000000,8000000,10000000,12500000,15000000,17500000,20000000,25000000,30000000,35000000,40000000,50000000,60000000,75000000,100000000,125000000,150000000];
  const SQFT_MAX = 4000;
  const HUB_LABELS = { bkc:"BKC", lower_parel:"Lower Parel", andheri_seepz:"Andheri/SEEPZ", powai:"Powai", goregaon_nesco:"Goregaon", nariman_point:"Nariman Pt" };
  const PORTAL_NAMES = {
    magicbricks:"MagicBricks", nobroker:"NoBroker", squareyards:"Square Yards",
    commonfloor:"CommonFloor", makaan:"Makaan", nobrokerage:"NoBrokerage",
    community:"Flatmates / Reddit", reddit:"Reddit Owner", "99acres":"99acres",
    housing:"Housing.com", other:"Saved Link"
  };

  window.addEventListener("error", e => {
    const b = document.getElementById("freshBadge");
    if (b) b.textContent = "Error: " + (e.message || "script error");
  });

  function readJSON(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || "null") || fallback; }
    catch { return fallback; }
  }

  const savedInit = readJSON("mhf_s3", { ids:[], notes:{} });
  if (!Array.isArray(savedInit.ids)) savedInit.ids = [];
  if (!savedInit.notes) savedInit.notes = {};

  const st = {
    mode: "rent", theme: localStorage.getItem("mhf_t_v8") || "light", mapStyle: "street",
    bhks: new Set(), realOnly: true, zero: false, dealOnly: false, flood: false, mapBounds: false, savedOnly: false,
    mission: null, showMetro: true, showFlood: false, page: 36, sel: null, cmp: [],
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
  const getP = s => st.mode === "rent" ? (s.pricing?.rent_monthly_inr?.median || 0) : (s.pricing?.buy_inr?.median || 0);
  const isEst = s => st.mode === "rent" ? !!s.pricing?.rent_monthly_inr?.is_estimate : !!s.pricing?.buy_inr?.is_estimate;
  const getDeal = s => st.mode === "rent" ? s.deal?.rent : s.deal?.buy;
  const getSources = s => [...new Set([...Object.keys(s.sources || {}), ...Object.keys(s.pricing?.by_portal || {})])];

  function toast(msg) {
    const el = $("toast"); el.textContent = msg; el.classList.add("show");
    clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("show"), 2600);
  }

  const map = L.map("map", { preferCanvas: true, zoomControl: true, maxZoom: 20 }).setView([19.085, 72.905], 11);
  const osmStreet = L.tileLayer(H + "tile.openstreetmap.org/{z}/{x}/{y}.png", { maxNativeZoom: 19, maxZoom: 20, attribution: "OpenStreetMap" });
  const esriFallback = L.tileLayer(H + "server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", { maxNativeZoom: 16, maxZoom: 20, attribution: "Esri" });
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
    ["msStreet", "msDark", "msSat"].forEach(id => $(id).classList.remove("active"));
    $(style === "dark" ? "msDark" : (style === "sat" ? "msSat" : "msStreet")).classList.add("active");
  }
  osmStreet.on("tileerror", () => { if (activeBase === osmStreet) { map.removeLayer(osmStreet); activeBase = esriFallback.addTo(map); } });

  const cv = L.canvas({ padding: 0.5 });
  const mLayer = L.layerGroup().addTo(map);
  const metroL = L.layerGroup().addTo(map);
  const floodL = L.layerGroup();

  [
    { n:"Aqua Line 3", c:"#0891b2", p:[[19.1365,72.8748],[19.1082,72.8800],[19.0817,72.8482],[19.0653,72.8644],[19.0218,72.8414],[19.0074,72.8195],[18.9696,72.8193],[18.9352,72.8273],[18.9142,72.8213]] },
    { n:"Blue Line 1", c:"#2563eb", p:[[19.1307,72.8213],[19.1207,72.8481],[19.1082,72.8800],[19.0867,72.9082]] },
    { n:"Yellow/Red Lines 2A/7", c:"#d97706", p:[[19.2288,72.8468],[19.1862,72.8358],[19.1469,72.8347],[19.1301,72.8306],[19.1190,72.8559],[19.1665,72.8576]] },
    { n:"Navi Mumbai Line 1", c:"#7c3aed", p:[[19.0185,73.0394],[19.0359,73.0631],[19.0548,73.0686],[19.0620,73.0715],[19.0772,73.0977]] }
  ].forEach(l => L.polyline(l.p, { color: l.c, weight: 2.8, opacity: 0.72, renderer: cv }).bindTooltip(l.n).addTo(metroL));

  [
    { n:"Hindmata", la:19.0079, ln:72.8423, r:650 }, { n:"Sion Gandhi Market", la:19.0322, ln:72.8576, r:700 },
    { n:"Milan Subway", la:19.0853, ln:72.8439, r:550 }, { n:"Andheri Subway", la:19.1157, ln:72.8442, r:550 },
    { n:"Kurla LBS", la:19.0764, ln:72.8832, r:800 }, { n:"Malad Subway", la:19.1846, ln:72.8468, r:500 }
  ].forEach(s => L.circle([s.la, s.ln], { radius: s.r, color: "#b91c1c", fillColor: "#b91c1c", fillOpacity: 0.13, weight: 1, renderer: cv }).bindTooltip("Flood Zone: " + s.n).addTo(floodL));

  function syncPriceSliders(iLo, iHi) {
    const stops = pStops(), maxI = stops.length - 1, ceil = stops[maxI];
    if (iLo > iHi) { const t = iLo; iLo = iHi; iHi = t; }
    st.pLo = stops[iLo]; st.pHi = stops[iHi];
    [["dpMin","dpMax","dPriceFill","dPriceVal"],["mpMin","mpMax","mPriceFill","mPriceVal"]].forEach(([a,b,f,l]) => {
      $(a).value = iLo; $(b).value = iHi;
      const fill = $(f);
      fill.style.left = `${(iLo / maxI) * 100}%`; fill.style.width = `${((iHi - iLo) / maxI) * 100}%`;
      $(l).textContent = (iLo === 0 && iHi === maxI) ? "Any Price" : `${fmtS(st.pLo, st.mode === "buy", ceil)} – ${fmtS(st.pHi, st.mode === "buy", ceil)}`;
    });
  }
  function resetPriceScale() {
    const maxI = pStops().length - 1;
    ["dpMin","dpMax","mpMin","mpMax"].forEach(id => { const el = $(id); el.min = 0; el.max = maxI; el.step = 1; });
    $("dPriceLbl").textContent = st.mode === "buy" ? "Buy" : "Rent";
    $("mPriceLbl").textContent = st.mode === "buy" ? "Purchase Budget" : "Monthly Rent";
    syncPriceSliders(0, maxI);
  }
  function syncSqftSlider() {
    let lo = Number($("sMin").value), hi = Number($("sMax").value);
    if (lo > hi) { const t = lo; lo = hi; hi = t; $("sMin").value = lo; $("sMax").value = hi; }
    st.sLo = lo; st.sHi = hi;
    const fill = $("sqftFill");
    fill.style.left = `${(lo / SQFT_MAX) * 100}%`; fill.style.width = `${((hi - lo) / SQFT_MAX) * 100}%`;
    $("sqftVal").textContent = (lo === 0 && hi === SQFT_MAX) ? "Any Size" : `${lo} – ${hi >= SQFT_MAX ? SQFT_MAX + "+" : hi} sq ft`;
  }

  function applyTheme(t) {
    st.theme = t; localStorage.setItem("mhf_t_v8", t);
    document.documentElement.setAttribute("data-theme", t);
    $("themeIcon").innerHTML = t === "dark"
      ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>'
      : '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>';
    setMapStyle(t === "dark" ? "dark" : "street");
  }

  function syncCounts() {
    localStorage.setItem("mhf_s3", JSON.stringify(st.saved));
    localStorage.setItem("mhf_clipped_v7", JSON.stringify(st.clipped));
    const sc = st.saved.ids.length, cc = st.cmp.length;
    $("savedCount").textContent = sc; $("cmpCount").textContent = cc;
    $("mSavedLbl").textContent = sc ? `Saved (${sc})` : "Saved";
    $("mCmpLbl").textContent = cc ? `Compare (${cc})` : "Compare";
    $("shareShortlistBtn").style.display = (st.savedOnly && sc > 0) ? "inline-flex" : "none";
  }

  function rebuildSocietyList() { societies = [...st.clipped, ...baseSocieties]; }

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
    sel.innerHTML = '<option value="ALL">All Available Sources</option>' + ordered.map(([k, n]) => `<option value="${esc(k)}">${esc(PORTAL_NAMES[k] || k)} (${n.toLocaleString("en-IN")})</option>`).join("");
    if (ordered.some(([k]) => k === prev)) sel.value = prev;
    const commChip = document.querySelector('.m-chip[data-mission="community"]');
    if (commChip) commChip.style.display = (counts.community || 0) > 0 ? "" : "none";
  }

  function populateLocalities() {
    const z = $("fZone").value, prev = $("fLoc").value;
    const locs = [...new Set(societies.filter(s => z === "ALL" || s.zone === z).map(s => s.locality).filter(Boolean))].sort();
    $("fLoc").innerHTML = `<option value="ALL">All Localities (${locs.length})</option>` + locs.map(l => `<option value="${esc(l)}">${esc(l)}</option>`).join("");
    if (locs.includes(prev)) $("fLoc").value = prev;
  }

  function renderMap() {
    mLayer.clearLayers();
    pillEls.clear();
    const z = map.getZoom();
    const bounds = map.getBounds().pad(0.12);
    const inView = filtered.filter(s => s.lat && s.lng && bounds.contains([s.lat, s.lng]));
    if (!inView.length) return;

    const cellW = z >= 17 ? 64 : (z >= 15 ? 76 : 88);
    const cellH = z >= 17 ? 34 : (z >= 15 ? 38 : 44);
    const buckets = new Map();

    for (const s of inView) {
      const pt = map.latLngToContainerPoint([s.lat, s.lng]);
      const key = `${Math.floor(pt.x / cellW)}:${Math.floor(pt.y / cellH)}`;
      let b = buckets.get(key);
      if (!b) { b = { items: [], lat: 0, lng: 0, minP: Infinity }; buckets.set(key, b); }
      b.items.push(s); b.lat += s.lat; b.lng += s.lng;
      const pv = getP(s);
      if (pv > 0 && pv < b.minP) b.minP = pv;
    }

    for (const b of buckets.values()) {
      if (b.items.length === 1) {
        addPricePill(b.items[0]);
      } else {
        const cla = b.lat / b.items.length, cln = b.lng / b.items.length;
        const label = b.minP < Infinity ? `${fmtPill(b.minP, st.mode === "buy")}+` : "Homes";
        const ic = L.divIcon({
          className: "cluster-wrap",
          html: `<div class="cluster-pill"><span>${label}</span><span class="cluster-cnt">${b.items.length}</span></div>`,
          iconSize: [0, 0]
        });
        L.marker([cla, cln], { icon: ic }).on("click", () => {
          const lats = b.items.map(x => x.lat), lngs = b.items.map(x => x.lng);
          const span = Math.max(Math.max(...lats) - Math.min(...lats), Math.max(...lngs) - Math.min(...lngs));
          if (z >= 17 || span < 0.0005) openClusterSheet(b.items);
          else map.setView([cla, cln], Math.min(18, z + 2), { animate: true });
        }).addTo(mLayer);
      }
    }
  }

  function addPricePill(s) {
    const deal = getDeal(s), isSel = s.id === st.sel;
    const cls = ["price-pill", isSel ? "sel" : "", s.pricing?.has_zero_brokerage ? "zb" : "", deal?.label === "Great Value" ? "val" : "", s.coords_approx ? "approx" : ""].filter(Boolean).join(" ");
    const ic = L.divIcon({ className: "pill-wrap", html: `<div class="${cls}" data-pid="${esc(s.id)}">${fmtPill(getP(s), st.mode === "buy")}</div>`, iconSize: [0, 0] });
    const mk = L.marker([s.lat, s.lng], { icon: ic, zIndexOffset: isSel ? 900 : 0 });
    mk.on("click", () => onPinClick(s));
    mk.addTo(mLayer);
    pillEls.set(s.id, mk);
  }

  function openClusterSheet(items) {
    const sorted = [...items].sort((a, b) => (getP(a) || 9e12) - (getP(b) || 9e12));
    $("clTitle").textContent = `${sorted.length} homes in this spot`;
    $("clSub").textContent = `${sorted[0]?.locality || "Mumbai"} · sorted lowest price first`;
    $("clBody").innerHTML = sorted.map(s => renderCardHtml(s, $("fHub").value)).join("");
    bindCardEvents($("clBody"));
    $("clusterBackdrop").style.display = "block";
    $("clusterSheet").style.display = "flex";
  }
  const closeCluster = () => { $("clusterBackdrop").style.display = "none"; $("clusterSheet").style.display = "none"; };

  function onPinClick(s) {
    st.sel = s.id; renderMap();
    if (window.innerWidth <= 1120 || document.body.classList.contains("view-map")) showMapPreview(s);
    else openDetail(s);
  }

  function showMapPreview(s) {
    const box = $("mapPreview"), ctx = s.mumbai_context || {}, deal = getDeal(s), hub = $("fHub").value;
    const commuteTxt = hub && ctx.commute_hubs_min?.[hub] ? `${ctx.commute_hubs_min[hub]}m to ${HUB_LABELS[hub]}` : (ctx.nearest_metro ? `${ctx.nearest_metro.walk_min}m to ${ctx.nearest_metro.name}` : "");
    box.innerHTML = `
      <div class="mp-top">
        <div style="min-width:0;"><div class="mp-name">${esc(s.name)}</div><div class="mp-loc">${esc(s.locality)} · ${esc(s.zone)}</div></div>
        <button class="btn icon xs" id="closeMp" aria-label="Close preview">✕</button>
      </div>
      <div class="mp-row">
        <strong class="mp-price">${fmt(getP(s), st.mode === "buy")}</strong>
        ${deal?.label === "Great Value" ? `<span class="tag deal">${Math.abs(deal.pct)}% below avg</span>` : ""}
        ${s.pricing?.has_zero_brokerage ? `<span class="tag zb">Zero Brokerage</span>` : ""}
      </div>
      <div class="mp-foot">
        <span class="mp-meta">${(s.bhks || []).map(fmtBhk).join(", ") || "Residential"}${commuteTxt ? " · " + esc(commuteTxt) : ""}</span>
        <button class="btn pri xs" id="openMpDetail">View Home</button>
      </div>`;
    box.style.display = "flex";
    $("closeMp").onclick = () => { box.style.display = "none"; };
    $("openMpDetail").onclick = () => { box.style.display = "none"; openDetail(s); };
  }

  function renderActivePills() {
    const bar = $("activeBar"), tags = [];
    const z = $("fZone").value, loc = $("fLoc").value, srcF = $("fSource").value, ceil = priceMax();
    if (z !== "ALL") tags.push(z);
    if (loc !== "ALL") tags.push(loc);
    if (srcF !== "ALL") tags.push(PORTAL_NAMES[srcF] || srcF);
    if (st.bhks.size) tags.push([...st.bhks].sort((a, b) => a - b).map(x => x === 4 ? "4+ BHK" : fmtBhk(x)).join(", "));
    if (st.pLo > 0 || st.pHi < ceil) tags.push(`${fmtS(st.pLo, st.mode === "buy", ceil)}–${fmtS(st.pHi, st.mode === "buy", ceil)}`);
    if (st.sLo > 0 || st.sHi < SQFT_MAX) tags.push(`${st.sLo}–${st.sHi} sq ft`);
    if (st.zero) tags.push("Zero Brokerage");
    if (st.dealOnly) tags.push("Great Value");
    if (st.flood) tags.push("Monsoon Safe");
    if (Number($("fMetro").value)) tags.push(`Metro ≤${$("fMetro").value}m`);
    if ($("fHub").value && Number($("fHubMin").value)) tags.push(`${HUB_LABELS[$("fHub").value]} ≤${$("fHubMin").value}m`);
    if ($("fFurn").value !== "ALL") tags.push($("fFurn").selectedOptions[0].text);
    if ($("fTen").value !== "ALL") tags.push($("fTen").selectedOptions[0].text);
    if (Number($("fRate").value)) tags.push(`${$("fRate").value}★+`);
    if (st.savedOnly) tags.push("Saved Shortlist");
    if (st.mapBounds) tags.push("This Map Area");

    const fc = $("filterCount");
    fc.textContent = tags.length; fc.style.visibility = tags.length ? "visible" : "hidden";
    if (!tags.length) { bar.style.display = "none"; return; }
    bar.style.display = "flex";
    bar.innerHTML = tags.map(t => `<span class="af-pill">${esc(t)}</span>`).join("") + `<button class="af-clear" id="clearBarBtn">Reset</button>`;
    $("clearBarBtn").onclick = () => resetAll();
  }

  function renderAll() {
    const q = $("searchBox").value.trim().toLowerCase();
    const z = $("fZone").value, loc = $("fLoc").value, srcF = $("fSource").value, ceil = priceMax();
    const maxM = Number($("fMetro").value || 0);
    const hub = $("fHub").value, hubMax = Number($("fHubMin").value || 0);
    const furn = $("fFurn").value, ten = $("fTen").value;
    const minRate = Number($("fRate").value || 0);
    const srt = $("fSort").value;
    const bounds = st.mapBounds ? map.getBounds() : null;

    filtered = societies.filter(s => {
      if (z !== "ALL" && s.zone !== z) return false;
      if (loc !== "ALL" && s.locality !== loc) return false;
      if (srcF !== "ALL") {
        const srcs = getSources(s);
        if (srcF === "community") { if (!srcs.includes("community") && !srcs.includes("reddit")) return false; }
        else if (!srcs.includes(srcF)) return false;
      }
      if (q && !`${s.name} ${s.locality} ${s.zone} ${(s.rera_ids || []).join(" ")}`.toLowerCase().includes(q)) return false;
      if (st.bhks.size) {
        const bs = s.bhks || [];
        if (!bs.length || ![...st.bhks].some(b => b === 4 ? bs.some(x => x >= 4) : bs.includes(b))) return false;
      }
      const p = getP(s);
      if (st.realOnly && (!p || isEst(s))) return false;
      if (st.pLo > 0 && (!p || p < st.pLo)) return false;
      if (st.pHi < ceil && (!p || p > st.pHi)) return false;
      if (st.sLo > 0 && (!s.rera_carpet_sqft || s.rera_carpet_sqft < st.sLo)) return false;
      if (st.sHi < SQFT_MAX && (!s.rera_carpet_sqft || s.rera_carpet_sqft > st.sHi)) return false;
      if (maxM > 0 && (s.mumbai_context?.nearest_metro?.walk_min || 999) > maxM) return false;
      if (hub && hubMax > 0 && (s.mumbai_context?.commute_hubs_min?.[hub] || 999) > hubMax) return false;
      if (furn !== "ALL" && !(s.furnishing || []).includes(furn)) return false;
      if (ten !== "ALL" && !(s.tenant || []).includes(ten)) return false;
      if (minRate > 0 && (s.google?.rating || 0) < minRate) return false;
      if (st.zero && !s.pricing?.has_zero_brokerage) return false;
      if (st.dealOnly && getDeal(s)?.label !== "Great Value") return false;
      if (st.flood && s.mumbai_context?.monsoon_flood_risk === "high") return false;
      if (st.savedOnly && !st.saved.ids.includes(s.id)) return false;
      if (bounds && !bounds.contains([s.lat, s.lng])) return false;
      return true;
    });

    filtered.sort((a, b) => {
      if (srt === "p_asc") return (getP(a) || 9e12) - (getP(b) || 9e12);
      if (srt === "p_desc") return (getP(b) || 0) - (getP(a) || 0);
      if (srt === "deal") return (getDeal(a)?.pct ?? 999) - (getDeal(b)?.pct ?? 999);
      if (srt === "sqft") return (b.rera_carpet_sqft || 0) - (a.rera_carpet_sqft || 0);
      if (srt === "metro") return (a.mumbai_context?.nearest_metro?.walk_min || 999) - (b.mumbai_context?.nearest_metro?.walk_min || 999);
      if (srt === "rate") return (b.google?.rating || 0) - (a.google?.rating || 0);
      if (hub) {
        const ca = a.mumbai_context?.commute_hubs_min?.[hub] || 999;
        const cb = b.mumbai_context?.commute_hubs_min?.[hub] || 999;
        if (Math.abs(ca - cb) >= 5) return ca - cb;
      }
      const sc = x => (x._clipped ? 25 : 0) + (isEst(x) ? 0 : 14) + (getDeal(x)?.label === "Great Value" ? 10 : 0) + (x.google?.rating || 0) * 3 + (x.pricing?.has_zero_brokerage ? 7 : 0) + getSources(x).length * 4 - Math.min(20, (x.mumbai_context?.nearest_metro?.walk_min || 20) * 0.3);
      return sc(b) - sc(a);
    });

    $("resSum").textContent = `${filtered.length.toLocaleString("en-IN")} homes`;
    $("applyFiltersBtn").textContent = `Show ${filtered.length.toLocaleString("en-IN")} Homes`;
    $("shareShortlistBtn").style.display = (st.savedOnly && st.saved.ids.length > 0) ? "inline-flex" : "none";
    renderActivePills(); renderMap(); renderList();
  }

  function renderCardHtml(s, hub) {
    const ctx = s.mumbai_context || {}, g = s.google, fl = ctx.monsoon_flood_risk || "low", deal = getDeal(s);
    const isS = st.saved.ids.includes(s.id), isC = st.cmp.includes(s.id);
    const specs = [];
    if (s.bhks?.length) specs.push(s.bhks.map(fmtBhk).join(", "));
    if (s.rera_carpet_sqft) specs.push(`${s.rera_carpet_sqft} sq ft`);
    if (g?.rating) specs.push(`★ ${g.rating}`);
    const srcs = getSources(s).slice(0, 2).map(k => PORTAL_NAMES[k] || k);
    const transit = hub && ctx.commute_hubs_min?.[hub]
      ? `${ctx.commute_hubs_min[hub]}m to ${HUB_LABELS[hub]}${ctx.nearest_metro ? ` · ${ctx.nearest_metro.walk_min}m Metro` : ""}`
      : (ctx.nearest_metro ? `${ctx.nearest_metro.walk_min}m walk to ${ctx.nearest_metro.name}` : (ctx.nearest_local?.name || ""));

    return `<article class="hc ${s.id === st.sel ? "sel" : ""}" data-id="${esc(s.id)}">
      <div class="hc-top">
        <div style="min-width:0;"><div class="hc-name">${esc(s.name)}</div><div class="hc-loc">${esc(s.locality)} · ${esc(s.zone)}</div></div>
        <button class="heart-btn ${isS ? "sv" : ""}" data-a="sv" aria-label="Save home"><svg class="ic" viewBox="0 0 24 24"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg></button>
      </div>
      <div class="hc-price-row">
        <div class="hc-price"><strong>${fmt(getP(s), st.mode === "buy")}</strong><span>${isEst(s) ? "est." : ""}</span></div>
        <div class="tags">
          ${deal?.label === "Great Value" ? `<span class="tag deal">${Math.abs(deal.pct)}% below avg</span>` : ""}
          ${s.pricing?.has_zero_brokerage ? `<span class="tag zb">Zero Brok</span>` : ""}
          ${(s.sources?.community || s.sources?.reddit) ? `<span class="tag comm">Community</span>` : ""}
          ${fl === "high" ? `<span class="tag warn">Flood Zone</span>` : ""}
        </div>
      </div>
      <div class="hc-specs">
        <span>${specs.join(" · ") || "Residential"}</span>
        ${srcs.length ? `<span class="tag src">${esc(srcs.join(" + "))}</span>` : ""}
      </div>
      <div class="hc-foot">
        <span class="hc-transit">${esc(transit)}</span>
        <button class="cmp-link ${isC ? "cm" : ""}" data-a="cm">${isC ? "✓ Comparing" : "+ Compare"}</button>
      </div>
    </article>`;
  }

  function bindCardEvents(container) {
    container.querySelectorAll(".hc").forEach(el => {
      const id = el.dataset.id;
      el.onmouseenter = () => highlightPin(id, true);
      el.onmouseleave = () => highlightPin(id, false);
      el.onclick = e => {
        const b = e.target.closest("[data-a]");
        if (b) { e.stopPropagation(); if (b.dataset.a === "sv") toggleSave(id); else toggleCmp(id); return; }
        const s = societies.find(x => x.id === id);
        if (s) {
          closeCluster();
          if (s.lat && s.lng) map.flyTo([s.lat, s.lng], Math.max(map.getZoom(), 15), { duration: 0.45 });
          openDetail(s);
        }
      };
    });
  }

  function renderList() {
    const box = $("cardList");
    if (!filtered.length) {
      box.innerHTML = `<div class="empty"><p>No homes match these filters.</p><button class="btn pri" id="emptyReset">Reset Filters</button></div>`;
      $("emptyReset").onclick = () => resetAll();
      return;
    }
    const hub = $("fHub").value;
    box.innerHTML = filtered.slice(0, st.page).map(s => renderCardHtml(s, hub)).join("") +
      (filtered.length > st.page ? `<button class="btn" id="moreBtn" style="grid-column:1/-1;width:100%;">Show More (${filtered.length - st.page} remaining)</button>` : "");
    bindCardEvents(box);
    const mb = $("moreBtn");
    if (mb) mb.onclick = () => { st.page += 36; renderList(); };
  }

  function highlightPin(id, on) {
    const mk = pillEls.get(id);
    if (!mk) return;
    mk.setZIndexOffset(on ? 1200 : (id === st.sel ? 900 : 0));
    const el = mk.getElement()?.querySelector(".price-pill");
    if (el) el.classList.toggle("hov", on);
  }

  function toggleSave(id) {
    const i = st.saved.ids.indexOf(id);
    if (i >= 0) st.saved.ids.splice(i, 1); else st.saved.ids.push(id);
    syncCounts(); renderAll();
    if (st.sel === id && $("detailSheet").style.display === "flex") {
      const s = societies.find(x => x.id === id); if (s) openDetail(s);
    }
  }
  function toggleCmp(id) {
    const i = st.cmp.indexOf(id);
    if (i >= 0) st.cmp.splice(i, 1);
    else if (st.cmp.length < 4) st.cmp.push(id);
    else toast("Compare up to 4 homes at once");
    syncCounts(); renderList();
  }

  function openDetail(s) {
    st.sel = s.id;
    const p = s.pricing || {}, ctx = s.mumbai_context || {}, g = s.google || {}, pr = p.by_portal || {}, civ = s.civic || {};
    const modeSrc = st.mode === "rent" ? (s.sources_rent || {}) : (s.sources_buy || {});
    const src = Object.keys(modeSrc).length ? modeSrc : (s.sources || {});
    const deal = getDeal(s);
    const qMaps = encodeURIComponent(`${s.name} ${s.locality} Mumbai`);
    const isS = st.saved.ids.includes(s.id), isC = st.cmp.includes(s.id);
    const rent = p.rent_monthly_inr?.median, buy = p.buy_inr?.median;
    const share = `${location.origin}${location.pathname}?open=${encodeURIComponent(s.id)}`;
    const wa = encodeURIComponent(`${s.name} (${s.locality}, ${s.zone})\nRent: ${fmt(rent, false)} | Buy: ${fmt(buy, true)}\n${deal ? `Market Verdict: ${deal.label} (${deal.pct > 0 ? "+" : ""}${deal.pct}% vs area median)\n` : ""}Metro: ${ctx.nearest_metro?.walk_min || "?"}m to ${ctx.nearest_metro?.name || "Metro"}\nMonsoon Risk: ${(ctx.monsoon_flood_risk || "low").toUpperCase()}\n${share}`);

    const activePortals = Object.entries(pr).filter(([_, info]) => info && (st.mode === "rent" ? info.rent_median : info.buy_median));
    const linkBtns = [];
    Object.entries(src).forEach(([k, url]) => {
      if (url) linkBtns.push(`<a class="primary-link" target="_blank" href="${esc(url)}">${esc(PORTAL_NAMES[k] || k)} ↗<span>Verified ${st.mode === "rent" ? "Rent" : "Sale"} Listing</span></a>`);
    });
    linkBtns.push(`<a target="_blank" href="${g.url || (H + "www.google.com/maps/search/?api=1&query=" + qMaps)}">Google Maps ↗<span>Gate Directions and Reviews</span></a>`);
    if (s.rera_ids?.length) {
      linkBtns.push(`<a target="_blank" href="${H}maharera.maharashtra.gov.in/projects-search-result?project_name=${encodeURIComponent(s.rera_ids[0])}">MahaRERA ${esc(s.rera_ids[0])} ↗<span>Official RERA Record</span></a>`);
    }
    const crossSearch = H + "www.google.com/search?q=" + encodeURIComponent(`"${s.name}" "${s.locality}" Mumbai flat ${st.mode}`);
    const igrSearch = H + "www.google.com/search?q=" + encodeURIComponent(`site:zapkey.com OR site:indextap.com "${s.name}" "${s.locality}" Mumbai`);
    const fbSearch = H + "www.google.com/search?q=" + encodeURIComponent(`site:facebook.com "flats and flatmates" mumbai "${s.locality}"`);

    let dealHtml = "";
    if (deal && deal.loc_median) {
      const pos = Math.max(8, Math.min(92, 50 + (deal.pct * 0.6)));
      const dCls = deal.label === "Great Value" ? "deal" : (deal.label === "Premium" ? "warn" : "src");
      dealHtml = `<div class="deal-box">
        <div class="deal-head"><span class="tag ${dCls}">${esc(deal.label)} (${deal.pct > 0 ? "+" : ""}${deal.pct}% vs ${esc(s.locality)} median)</span><small>Area median: ${fmt(deal.loc_median, st.mode === "buy")}</small></div>
        <div class="deal-bar"><div class="deal-mid"></div><div class="deal-dot" style="left:${pos}%;"></div></div>
      </div>`;
    }

    $("dName").textContent = s.name;
    $("dSub").textContent = `${s.locality} · ${s.zone}${g.rating ? ` · ★ ${g.rating} (${g.review_count || 0})` : ""}`;
    $("dBody").innerHTML = `
      <div class="d-actions">
        <button class="btn ${isS ? "active" : ""}" id="dSv">${isS ? "Saved" : "Save Home"}</button>
        <button class="btn ${isC ? "active" : ""}" id="dCm">${isC ? "In Compare" : "Compare"}</button>
        <a class="btn wa" target="_blank" href="${H}wa.me/?text=${wa}">Share WhatsApp</a>
      </div>
      <div class="card-box">
        <h3>Price and Value</h3>
        ${dealHtml}
        <div class="g2">
          <div class="met"><small>Monthly Rent ${p.rent_monthly_inr?.is_estimate ? "(Est.)" : ""}</small><strong>${fmt(rent, false)}</strong></div>
          <div class="met"><small>Purchase Price ${p.buy_inr?.is_estimate ? "(Est.)" : ""}</small><strong>${fmt(buy, true)}</strong></div>
          <div class="met"><small>Home Size / Furnishing</small><strong>${s.bhks?.length ? s.bhks.map(fmtBhk).join(", ") : "—"}</strong><small>${(s.furnishing || []).join(", ") || "Check listing"}</small></div>
          <div class="met"><small>Carpet Area / Rate</small><strong>${s.rera_carpet_sqft ? s.rera_carpet_sqft + " sq ft" : "—"}</strong><small>${p.price_per_carpet_sqft ? `₹${p.price_per_carpet_sqft.toLocaleString("en-IN")}/sq ft` : ""}</small></div>
        </div>
        ${p.move_in_cash_nobroker ? `<div class="cash-note"><strong>Upfront Move-In Cash (Rent):</strong> Direct <b>${fmt(p.move_in_cash_nobroker, true)}</b> · Broker <b>${fmt(p.move_in_cash_broker, true)}</b></div>` : ""}
      </div>
      <div class="card-box">
        <h3>Verified Direct Links</h3>
        <div class="plinks">${linkBtns.join("")}</div>
        <div class="sub-links">
          <a target="_blank" href="${crossSearch}">Check Housing.com / 99acres via Google ↗</a>
          <a target="_blank" href="${igrSearch}">Registered Sale Prices (Zapkey / IndexTap) ↗</a>
          <a target="_blank" href="${fbSearch}">Search Flats & Flatmates Mumbai (${esc(s.locality)}) ↗</a>
        </div>
      </div>
      ${activePortals.length ? `<div class="card-box"><h3>Active Portal Breakdown (${activePortals.length})</h3><div class="g2">${activePortals.map(([k, info]) => `<div class="met"><small>${esc(PORTAL_NAMES[k] || k)} (${info.count || 1})</small><strong>${st.mode === "rent" ? fmt(info.rent_median, false) : fmt(info.buy_median, true)}</strong>${info.deposit_median ? `<small>Deposit: ${fmt(info.deposit_median, true)}</small>` : ""}</div>`).join("")}</div></div>` : ""}
      <div class="card-box">
        <h3>Transit, Commute and Monsoon</h3>
        <div class="g2">
          <div class="met"><small>Nearest Metro (2026)</small><strong>${esc(ctx.nearest_metro?.name || "—")}</strong><small>${ctx.nearest_metro?.walk_min || "—"} min walk</small></div>
          <div class="met"><small>Local Train</small><strong>${esc(ctx.nearest_local?.name || "—")}</strong><small>${ctx.nearest_local?.walk_min || "—"} min walk</small></div>
          <div class="met"><small>Monsoon Flood Risk</small><strong class="risk-${ctx.monsoon_flood_risk || "low"}">${(ctx.monsoon_flood_risk || "low").toUpperCase()}</strong></div>
          <div class="met"><small>Pin Precision</small><strong>${s.coords_approx ? "Locality Area" : "Verified Building"}</strong></div>
        </div>
        ${ctx.commute_hubs_min ? `<div class="commute-strip">BKC ~${ctx.commute_hubs_min.bkc}m · Lower Parel ~${ctx.commute_hubs_min.lower_parel}m · Andheri ~${ctx.commute_hubs_min.andheri_seepz}m · Powai ~${ctx.commute_hubs_min.powai}m</div>` : ""}
      </div>
      ${(civ.hospital || civ.park || civ.supermarket || civ.school) ? `<div class="card-box">
        <h3>Nearby Essentials</h3>
        <div class="g2">
          ${civ.hospital ? `<div class="met"><small>Hospital (${fmtDist(civ.hospital.dist_m)})</small><strong>${esc(civ.hospital.name)}</strong></div>` : ""}
          ${civ.supermarket ? `<div class="met"><small>Supermarket (${fmtDist(civ.supermarket.dist_m)})</small><strong>${esc(civ.supermarket.name)}</strong></div>` : ""}
          ${civ.park ? `<div class="met"><small>Park / Walk (${fmtDist(civ.park.dist_m)})</small><strong>${esc(civ.park.name)}</strong></div>` : ""}
          ${civ.school ? `<div class="met"><small>School (${fmtDist(civ.school.dist_m)})</small><strong>${esc(civ.school.name)}</strong></div>` : ""}
        </div>
      </div>` : ""}
      ${g.reviews?.length ? `<div class="card-box"><h3>Google Resident Reviews</h3>${g.reviews.map(r => `<div class="rev"><b>★ ${r.rating || ""}</b> — ${esc(r.text)}</div>`).join("")}</div>` : ""}
      <div class="card-box">
        <h3>Your Visit and Broker Notes</h3>
        <textarea id="dNote" rows="3" placeholder="Broker contact, floor, sunlight, water supply, society rules...">${esc(st.saved.notes[s.id] || "")}</textarea>
      </div>`;

    $("detailBackdrop").style.display = "block";
    $("detailSheet").style.display = "flex";
    $("dSv").onclick = () => toggleSave(s.id);
    $("dCm").onclick = () => { toggleCmp(s.id); openDetail(s); };
    $("dNote").oninput = e => { st.saved.notes[s.id] = e.target.value; syncCounts(); };
    renderMap();
  }

  const closeDetail = () => { $("detailBackdrop").style.display = "none"; $("detailSheet").style.display = "none"; };
  const openFilters = () => { $("filterBackdrop").style.display = "block"; $("filterSheet").style.display = "flex"; };
  const closeFilters = () => { $("filterBackdrop").style.display = "none"; $("filterSheet").style.display = "none"; };
  function buildShortlistUrl(ids) { return `${location.origin}${location.pathname}?list=${encodeURIComponent(ids.join(","))}`; }

  function openCmp(overrideIds) {
    const ids = overrideIds || (st.cmp.length ? st.cmp : st.saved.ids.slice(0, 4));
    const items = ids.map(id => societies.find(x => x.id === id)).filter(Boolean);
    const row = (l, fn) => `<tr><th>${l}</th>${items.map(s => `<td>${fn(s)}</td>`).join("")}</tr>`;
    $("cmpBody").innerHTML = !items.length
      ? `<div class="empty"><p>Tap <b>+ Compare</b> on up to 4 homes (or add a Housing.com / 99acres listing) to compare side-by-side.</p></div>`
      : `<div style="overflow-x:auto;"><table class="ctbl">
          <tr><th>Feature</th>${items.map(s => `<th>${esc(s.name)}<br/><small>${esc(s.locality)}</small></th>`).join("")}</tr>
          ${row("Monthly Rent", s => fmt(s.pricing?.rent_monthly_inr?.median, false))}
          ${row("Buy Price", s => fmt(s.pricing?.buy_inr?.median, true))}
          ${row("Value Verdict", s => { const d = getDeal(s); return d ? `${d.label} (${d.pct > 0 ? "+" : ""}${d.pct}%)` : "—"; })}
          ${row("Move-In (Direct)", s => fmt(s.pricing?.move_in_cash_nobroker, true))}
          ${row("Home Size", s => s.bhks?.length ? s.bhks.map(fmtBhk).join(", ") : "—")}
          ${row("Carpet Area", s => s.rera_carpet_sqft ? s.rera_carpet_sqft + " sq ft" : "—")}
          ${row("Sources", s => getSources(s).map(k => PORTAL_NAMES[k] || k).join(", ") || "—")}
          ${row("Nearest Metro", s => s.mumbai_context?.nearest_metro ? `${esc(s.mumbai_context.nearest_metro.name)} (${s.mumbai_context.nearest_metro.walk_min}m)` : "—")}
          ${row("Hospital", s => s.civic?.hospital ? `${esc(s.civic.hospital.name)} (${fmtDist(s.civic.hospital.dist_m)})` : "—")}
          ${row("Monsoon Risk", s => (s.mumbai_context?.monsoon_flood_risk || "low").toUpperCase())}
          ${row("Google Rating", s => s.google?.rating ? `★ ${s.google.rating}` : "—")}
        </table></div>`;

    const shareLink = buildShortlistUrl(items.map(x => x.id));
    $("copyCmpLink").onclick = () => { if (!items.length) return toast("Add homes first"); navigator.clipboard?.writeText(shareLink).then(() => toast("Shortlist link copied!")); };
    $("shareCmpWa").onclick = () => {
      if (!items.length) return toast("Add homes first");
      const msg = `Shortlisted ${items.length} Mumbai homes to compare:\n` + items.map((s, i) => `${i + 1}. ${s.name} (${s.locality}) — ${fmt(getP(s), st.mode === "buy")}`).join("\n") + `\n\nCompare side-by-side: ${shareLink}`;
      window.open(H + "wa.me/?text=" + encodeURIComponent(msg), "_blank");
    };
    $("cmpModal").style.display = "grid";
  }

  function initBookmarklet() {
    const base = location.origin + location.pathname;
    const code = "javascript:(()=>{const t=document.title.replace(/\\s*[|\\-].*$/,'').slice(0,80);const b=document.body.innerText.slice(0,4000);const pm=b.match(/(?:₹|Rs\\.?)\\s*([0-9,.]+)\\s*(Cr|Crore|Lac|Lakh|L|k)?/i);let p=0;if(pm){const v=parseFloat(pm[1].replace(/,/g,''));const u=(pm[2]||'').toLowerCase();p=u.startsWith('cr')?v*1e7:(u.startsWith('l')?v*1e5:(u==='k'?v*1e3:v));}const sm=b.match(/(\\d{3,4})\\s*(?:sq\\.?\\s*ft|sqft)/i);const s=sm?parseInt(sm[1]):0;const u=location.href;window.open('" + base + "?clip='+encodeURIComponent(JSON.stringify({name:t,price:Math.round(p),sqft:s,url:u})),'_blank');})();";
    $("bookmarkletLink").setAttribute("href", code);
  }

  function addClippedHome(obj) {
    const name = (obj.name || "External Listing").trim().slice(0, 80);
    const url = (obj.url || "").trim();
    const price = Number(obj.price || 0);
    const isBuy = price >= 2000000;
    const portal = obj.portal || (url.includes("housing.com") ? "housing" : (url.includes("99acres") ? "99acres" : "other"));
    const id = "clip-" + Date.now().toString(36);
    const item = {
      id, name, _clipped: true, locality: (obj.locality || "Mumbai").trim(), zone: "Mumbai",
      lat: 19.076, lng: 72.8777, coords_approx: true, bhks: [], furnishing: [], tenant: [], rera_ids: [],
      rera_carpet_sqft: Number(obj.sqft || 0) || null,
      pricing: {
        rent_monthly_inr: { median: isBuy ? null : (price || null), is_estimate: false },
        buy_inr: { median: isBuy ? price : null, is_estimate: false },
        has_zero_brokerage: false,
        by_portal: { [portal]: { count: 1, rent_median: isBuy ? null : (price || null), buy_median: isBuy ? price : null } }
      },
      mumbai_context: { monsoon_flood_risk: "low" },
      sources: url ? { [portal]: url } : {}
    };
    st.clipped.unshift(item);
    if (!st.saved.ids.includes(id)) st.saved.ids.unshift(id);
    if (st.cmp.length < 4 && !st.cmp.includes(id)) st.cmp.push(id);
    rebuildSocietyList(); syncCounts(); renderAll();
    toast(`Added "${name}" to Saved & Compare`);
  }

  function applyMission(key) {
    const same = st.mission === key;
    resetAll(true);
    if (same) return;
    st.mission = key;
    document.querySelectorAll(".m-chip").forEach(c => c.classList.toggle("active", c.dataset.mission === key));
    if (key === "zerobrok60") {
      st.mode = "rent"; $("modeRent").classList.add("active"); $("modeBuy").classList.remove("active");
      resetPriceScale();
      const idx60 = RENT_STOPS.indexOf(60000);
      syncPriceSliders(0, idx60 > 0 ? idx60 : 10);
      st.zero = true; $("fZero").classList.add("active");
    } else if (key === "deals") {
      st.dealOnly = true; $("fDealOnly").classList.add("active");
      $("sortSelect").value = $("fSort").value = "deal";
    } else if (key === "metro10") {
      $("fMetro").value = "10"; $("sortSelect").value = $("fSort").value = "metro";
    } else if (key === "family") {
      st.flood = true; $("fFlood").classList.add("active");
      [2, 3].forEach(b => st.bhks.add(b));
      document.querySelectorAll(".bhk-opt").forEach(b => b.classList.toggle("active", st.bhks.has(Number(b.dataset.bhk))));
    } else if (key === "community") {
      $("fSource").value = "community";
    } else if (key === "rated") {
      $("fRate").value = "4.0"; $("sortSelect").value = $("fSort").value = "rate";
    }
    renderAll();
  }

  function resetAll(silent) {
    st.mission = null;
    document.querySelectorAll(".m-chip").forEach(c => c.classList.remove("active"));
    $("searchBox").value = "";
    ["fZone","fLoc","fSource","fFurn","fTen"].forEach(id => $(id).value = "ALL");
    $("fHub").value = $("commuteQuick").value = "";
    ["fHubMin","fMetro","fRate"].forEach(id => $(id).value = "0");
    $("sortSelect").value = $("fSort").value = "rec";
    $("sMin").value = 0; $("sMax").value = SQFT_MAX; syncSqftSlider();
    resetPriceScale();
    st.bhks.clear(); document.querySelectorAll(".bhk-opt").forEach(b => b.classList.remove("active"));
    st.realOnly = true; st.zero = st.dealOnly = st.flood = st.mapBounds = st.savedOnly = false;
    st.page = 36;
    ["fZero","fDealOnly","fFlood","savedBtn","mapAreaBtn"].forEach(id => $(id).classList.remove("active"));
    $("fRealOnly").classList.add("active");
    populateLocalities();
    if (!silent) renderAll();
  }

  function setView(v) {
    document.body.className = "view-" + v;
    ["viewSplit","viewList","viewMap"].forEach(id => $(id).classList.remove("active"));
    const btn = $("view" + v[0].toUpperCase() + v.slice(1));
    if (btn) btn.classList.add("active");
    ["mTabList","mTabMap","mTabSaved","mTabCmp"].forEach(id => $(id).classList.remove("active"));
    if (st.savedOnly) $("mTabSaved").classList.add("active");
    else $(v === "map" ? "mTabMap" : "mTabList").classList.add("active");
    $("mapPreview").style.display = "none";
    setTimeout(() => { map.invalidateSize(); renderMap(); }, 90);
  }

  $("modeRent").onclick = () => { st.mode = "rent"; $("modeRent").classList.add("active"); $("modeBuy").classList.remove("active"); resetPriceScale(); renderAll(); };
  $("modeBuy").onclick = () => { st.mode = "buy"; $("modeBuy").classList.add("active"); $("modeRent").classList.remove("active"); resetPriceScale(); renderAll(); };
  $("viewSplit").onclick = () => { st.savedOnly = false; $("savedBtn").classList.remove("active"); setView("split"); renderAll(); };
  $("viewList").onclick = () => { st.savedOnly = false; $("savedBtn").classList.remove("active"); setView("list"); renderAll(); };
  $("viewMap").onclick = () => setView("map");
  $("mTabList").onclick = () => { st.savedOnly = false; $("savedBtn").classList.remove("active"); setView("list"); renderAll(); };
  $("mTabMap").onclick = () => setView("map");
  $("mTabSaved").onclick = () => { st.savedOnly = !st.savedOnly; $("savedBtn").classList.toggle("active", st.savedOnly); setView("list"); renderAll(); };
  $("mTabCmp").onclick = () => openCmp();

  $("themeBtn").onclick = () => applyTheme(st.theme === "dark" ? "light" : "dark");
  $("savedBtn").onclick = e => { st.savedOnly = !st.savedOnly; e.currentTarget.classList.toggle("active", st.savedOnly); renderAll(); };
  $("compareBtn").onclick = () => openCmp();
  $("shareShortlistBtn").onclick = () => openCmp(st.saved.ids.slice(0, 4));
  $("closeCmp").onclick = () => $("cmpModal").style.display = "none";
  $("clearCmp").onclick = () => { st.cmp = []; syncCounts(); openCmp(); renderList(); };

  const openClipModal = () => { initBookmarklet(); $("clipModal").style.display = "grid"; };
  $("openClipFromFilter").onclick = () => { closeFilters(); openClipModal(); };
  $("openClipFromCmp").onclick = () => { $("cmpModal").style.display = "none"; openClipModal(); };
  $("closeClip").onclick = () => $("clipModal").style.display = "none";
  $("saveClipBtn").onclick = () => {
    const name = $("cName").value.trim();
    if (!name) return toast("Enter a society or flat name");
    addClippedHome({ name, locality: $("cLoc").value, price: $("cPrice").value, portal: $("cPortal").value, sqft: $("cSqft").value, url: $("cUrl").value });
    ["cName","cLoc","cPrice","cSqft","cUrl"].forEach(id => $(id).value = "");
    $("clipModal").style.display = "none";
  };

  $("openFilterBtn").onclick = openFilters;
  $("mobSortBtn").onclick = openFilters;
  $("closeFilterBtn").onclick = closeFilters;
  $("filterBackdrop").onclick = closeFilters;
  $("applyFiltersBtn").onclick = closeFilters;
  $("clearFiltersBtn").onclick = () => resetAll();
  $("closeDetailBtn").onclick = closeDetail;
  $("detailBackdrop").onclick = closeDetail;
  $("closeClusterBtn").onclick = closeCluster;
  $("clusterBackdrop").onclick = closeCluster;

  $("msStreet").onclick = () => setMapStyle("street");
  $("msDark").onclick = () => setMapStyle("dark");
  $("msSat").onclick = () => setMapStyle("sat");
  $("togMetro").onclick = e => { st.showMetro = !st.showMetro; e.currentTarget.classList.toggle("active", st.showMetro); if (st.showMetro) metroL.addTo(map); else map.removeLayer(metroL); };
  $("togFlood").onclick = e => { st.showFlood = !st.showFlood; e.currentTarget.classList.toggle("active", st.showFlood); if (st.showFlood) floodL.addTo(map); else map.removeLayer(floodL); };
  $("mapAreaBtn").onclick = e => { st.mapBounds = !st.mapBounds; e.currentTarget.classList.toggle("active", st.mapBounds); st.page = 36; renderAll(); };

  document.querySelectorAll(".m-chip").forEach(btn => { btn.onclick = () => applyMission(btn.dataset.mission); });
  $("commuteQuick").addEventListener("change", e => { $("fHub").value = e.target.value; st.page = 36; renderAll(); });
  $("fHub").addEventListener("change", e => { $("commuteQuick").value = e.target.value; st.page = 36; renderAll(); });
  $("fZone").addEventListener("change", () => { populateLocalities(); st.page = 36; renderAll(); });
  $("sortSelect").addEventListener("change", e => { $("fSort").value = e.target.value; st.page = 36; renderAll(); });
  $("fSort").addEventListener("change", e => { $("sortSelect").value = e.target.value; st.page = 36; renderAll(); });

  ["dpMin","dpMax"].forEach(id => $(id).addEventListener("input", () => { syncPriceSliders(Number($("dpMin").value), Number($("dpMax").value)); st.page = 36; scheduleRender(); }));
  ["mpMin","mpMax"].forEach(id => $(id).addEventListener("input", () => { syncPriceSliders(Number($("mpMin").value), Number($("mpMax").value)); st.page = 36; scheduleRender(); }));
  ["sMin","sMax"].forEach(id => $(id).addEventListener("input", () => { syncSqftSlider(); st.page = 36; scheduleRender(); }));

  document.querySelectorAll(".bhk-opt").forEach(btn => {
    btn.onclick = () => { const v = Number(btn.dataset.bhk); if (st.bhks.has(v)) st.bhks.delete(v); else st.bhks.add(v); btn.classList.toggle("active", st.bhks.has(v)); st.page = 36; renderAll(); };
  });
  [["fRealOnly","realOnly"],["fZero","zero"],["fDealOnly","dealOnly"],["fFlood","flood"]].forEach(([id, k]) => {
    $(id).onclick = e => { st[k] = !st[k]; e.currentTarget.classList.toggle("active", st[k]); st.page = 36; renderAll(); };
  });
  ["searchBox","fLoc","fSource","fMetro","fHubMin","fFurn","fTen","fRate"].forEach(id => {
    $(id).addEventListener("input", () => { st.page = 36; scheduleRender(); });
  });

  map.on("moveend zoomend", () => { if (st.mapBounds) renderAll(); else renderMap(); });

  $("exportBtn").onclick = () => {
    const rows = [["Society","Zone","Locality","BHKs","Carpet","Rent_INR","Buy_INR","Deal_Pct","Sources","Google","Metro","Walk_Min","Flood"]];
    filtered.forEach(s => rows.push([
      `"${(s.name || "").replace(/"/g, '""')}"`, `"${s.zone || ""}"`, `"${s.locality || ""}"`,
      `"${(s.bhks || []).map(fmtBhk).join("/")}"`, s.rera_carpet_sqft || "",
      s.pricing?.rent_monthly_inr?.median || "", s.pricing?.buy_inr?.median || "",
      getDeal(s)?.pct ?? "", `"${getSources(s).join("/")}"`, s.google?.rating || "",
      `"${s.mumbai_context?.nearest_metro?.name || ""}"`, s.mumbai_context?.nearest_metro?.walk_min || "",
      s.mumbai_context?.monsoon_flood_risk || ""
    ]));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([rows.map(r => r.join(",")).join("\n")], { type: "text/csv" }));
    a.download = "mumbai-homes.csv";
    a.click();
  };

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeDetail(); closeFilters(); closeCluster(); $("cmpModal").style.display = "none"; $("clipModal").style.display = "none"; $("mapPreview").style.display = "none"; }
    if (e.key === "/" && !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)) { e.preventDefault(); $("searchBox").focus(); }
  });

  applyTheme(st.theme);
  $("fRealOnly").classList.add("active");
  resetPriceScale();
  syncSqftSlider();
  syncCounts();
  if (window.innerWidth <= 1120) setView("list");

  fetch("./public/data/mumbai-index.json", { cache: "no-store" })
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(d => {
      baseSocieties = d.societies || [];
      rebuildSocietyList();
      populateLocalities();
      populateSources();
      $("freshBadge").textContent = `${baseSocieties.length.toLocaleString("en-IN")} homes · ${d.generated_at}`;
      renderAll();

      const params = new URLSearchParams(location.search);
      const clipRaw = params.get("clip");
      if (clipRaw) { try { addClippedHome(JSON.parse(clipRaw)); openCmp(); } catch {} }
      const listRaw = params.get("list");
      if (listRaw) { const ids = listRaw.split(",").filter(Boolean); if (ids.length) openCmp(ids); }
      const oid = params.get("open");
      if (oid) { const t = societies.find(s => s.id === oid); if (t) { map.setView([t.lat, t.lng], 15); openDetail(t); } }
    })
    .catch(err => { $("freshBadge").textContent = "Load failed: " + (err?.message || "refresh to retry"); });
})();
