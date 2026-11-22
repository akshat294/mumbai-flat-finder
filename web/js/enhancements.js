/* Bombay Homes - Unified Enhancements Module (v24 Clean & Hardened) */
(function initBombayHomesEnhancements() {
  "use strict";

  window.__v17Flags = window.__v17Flags || {};
  window.__v18MoreMap = window.__v18MoreMap || new Map();

  function escHtml(val) {
    return String(val == null ? "" : val)
      .replace(/&/g, "\x26amp;")
      .replace(/</g, "\x26lt;")
      .replace(/>/g, "\x26gt;")
      .replace(/"/g, "\x26quot;")
      .replace(/'/g, "\x26#39;");
  }

  function safeUrl(raw) {
    if (typeof raw !== "string") return "";
    const trimmed = raw.trim();
    if (!/^https?:\/\//i.test(trimmed)) return "";
    try {
      const u = new URL(trimmed);
      return (u.protocol === "https:" || u.protocol === "http:") ? u.toString() : "";
    } catch {
      return "";
    }
  }

  function rafDebounce(fn) {
    let scheduled = false;
    return () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; fn(); });
    };
  }

  fetch("/api/flags")
    .then(r => (r.ok ? r.json() : null))
    .then(d => {
      if (d && d.flags) {
        window.__v17Flags = d.flags;
        try { if (typeof renderList === "function") renderList(); } catch {}
      }
    })
    .catch(() => {});

  const freshEl = document.getElementById("freshBadge");
  const resSumEl = document.getElementById("resSum");

  function updateHeaderLabels() {
    if (freshEl) {
      const raw = freshEl.textContent || "";
      const mDate = raw.match(/(\d{1,2}\s+[A-Za-z]{3}\s+\d{4},\s*\d{1,2}:\d{2}\s*[AP]M)/);
      let rel = "Updated today";
      if (mDate) {
        const parsed = Date.parse(mDate[1] + " GMT+0530");
        if (isFinite(parsed)) {
          const hrs = Math.max(0, Math.round((Date.now() - parsed) / 3600000));
          rel = hrs < 1 ? "Updated just now" : (hrs < 24 ? ("Updated " + hrs + "h ago") : ("Updated " + Math.round(hrs / 24) + "d ago"));
        }
      }
      const modeLbl = (typeof st !== "undefined" && st.mode === "buy") ? "For Sale" : "For Rent";
      const target = "Mumbai " + modeLbl + " \u00b7 " + rel;
      if (freshEl.textContent !== target) freshEl.textContent = target;
    }

    if (resSumEl) {
      const txt = resSumEl.textContent || "";
      if (txt.includes("exact pin") || txt.includes("homes")) {
        const nMatch = txt.match(/([\d,]+)/);
        const bldgs = nMatch ? nMatch[1] : (typeof filtered !== "undefined" ? filtered.length.toLocaleString("en-IN") : "0");
        let totalFlats = 0;
        if (typeof filtered !== "undefined" && typeof matchingUnits === "function") {
          for (const s of filtered) totalFlats += matchingUnits(s).length;
        }
        const modeWord = (typeof st !== "undefined" && st.mode === "buy") ? "for sale" : "for rent";
        const out = totalFlats > 0
          ? (bldgs + " buildings \u00b7 " + totalFlats.toLocaleString("en-IN") + " flats " + modeWord)
          : (bldgs + " buildings " + modeWord);
        if (resSumEl.textContent !== out) resSumEl.textContent = out;
      }
    }
  }

  const debouncedHeader = rafDebounce(updateHeaderLabels);
  if (freshEl) new MutationObserver(debouncedHeader).observe(freshEl, { childList: true, characterData: true, subtree: true });
  if (resSumEl) new MutationObserver(debouncedHeader).observe(resSumEl, { childList: true, characterData: true, subtree: true });
  setTimeout(updateHeaderLabels, 500);

  const sortEl = document.getElementById("v17Sort");
  const shareBtn = document.getElementById("v17ShareBtn");

  function syncUrlFromState() {
    try {
      if (typeof st === "undefined") return;
      const p = new URLSearchParams();
      if (st.mode && st.mode !== "rent") p.set("mode", st.mode);
      if (st.sort && st.sort !== "rec") p.set("sort", st.sort);
      if (st.lister && st.lister !== "all") p.set("lister", st.lister);
      const locs = (window.__v16Locs && window.__v16Locs.size) ? [...window.__v16Locs] : (st.locality ? [st.locality] : []);
      if (locs.length) p.set("locs", locs.join(","));
      if (st.bhk && st.bhk.size) p.set("bhk", [...st.bhk].join(","));
      if (st.balcony) p.set("balcony", "1");
      if (st.seaview) p.set("seaview", "1");
      if (st.zb) p.set("zb", "1");
      const qs = p.toString();
      history.replaceState(null, "", qs ? ("?" + qs) : location.pathname);
    } catch {}
  }

  function applyUrlStateOnBoot() {
    try {
      const p = new URLSearchParams(location.search);
      if (![...p.keys()].length || typeof st === "undefined") return;
      if (p.get("mode") === "buy") { st.mode = "buy"; document.getElementById("modeBuy")?.click(); }
      if (p.get("sort")) { st.sort = p.get("sort"); if (sortEl) sortEl.value = st.sort; }
      if (p.get("lister")) {
        st.lister = p.get("lister");
        document.querySelector('[data-lt="' + p.get("lister").replace(/"/g, "") + '"]')?.click();
      }
      if (p.get("balcony") === "1") st.balcony = true;
      if (p.get("seaview") === "1") st.seaview = true;
      if (p.get("zb") === "1") st.zb = true;
      if (p.get("bhk") && st.bhk && st.bhk.add) {
        p.get("bhk").split(",").forEach(v => { const n = parseFloat(v); if (isFinite(n)) st.bhk.add(n); });
      }
      if (p.get("locs")) {
        const arr = p.get("locs").split(",").map(x => x.trim()).filter(Boolean).slice(0, 5);
        if (arr.length) {
          if (window.__v16Locs && window.__v16Locs.add) arr.forEach(l => window.__v16Locs.add(l));
          else st.locality = arr[0];
        }
      }
      setTimeout(() => { try { if (typeof applyFilters === "function") applyFilters(); } catch {} }, 450);
    } catch {}
  }

  if (sortEl) {
    sortEl.addEventListener("change", () => {
      if (typeof st !== "undefined") st.sort = sortEl.value;
      try { if (typeof renderList === "function") renderList(); } catch {}
      syncUrlFromState();
    });
  }

  if (shareBtn) {
    shareBtn.addEventListener("click", async () => {
      syncUrlFromState();
      try {
        await navigator.clipboard.writeText(location.href);
        shareBtn.textContent = "Copied!";
        setTimeout(() => { shareBtn.textContent = "Share"; }, 1600);
      } catch { prompt("Copy link:", location.href); }
    });
  }

  const cardList = document.getElementById("cardList");
  if (cardList) {
    const decorateCards = rafDebounce(() => {
      const socById = new Map((typeof societies !== "undefined" ? societies : []).map(s => [s.id, s]));
      cardList.querySelectorAll("article.fc").forEach(card => {
        if (card.dataset.bhDone) return;
        card.dataset.bhDone = "1";

        const imgEl = card.querySelector("img");
        if (imgEl) { imgEl.loading = "lazy"; imgEl.decoding = "async"; }

        const sid = card.dataset.id;
        const url = card.dataset.url || "";
        const soc = socById.get(sid);
        const body = card.querySelector(".fc-body") || card;
        const metaRow = card.querySelector(".fc-price, .fc-top") || body;

        const cnt = card.querySelector(".fc-cnt");
        if (cnt && /^\s*1\s*\/\s*(?:\+|1)\s*$/.test(cnt.textContent || "")) cnt.dataset.single = "1";

        if (soc) {
          const extra = window.__v18MoreMap.get(sid) || 0;
          if (extra > 0 && !card.querySelector(".bh-more-pill")) {
            const pill = document.createElement("span");
            pill.className = "bh-more-pill";
            pill.textContent = "+" + extra + " more in " + String(soc.name || "building").slice(0, 24);
            body.appendChild(pill);
          }

          if (!card.querySelector(".bh-fresh") && typeof soc.age_days === "number") {
            const fp = document.createElement("span");
            fp.className = "bh-fresh " + (soc.age_days === 0 ? "new" : "act");
            fp.textContent = soc.age_days === 0 ? "New today" : ("Active " + soc.age_days + "d");
            metaRow.appendChild(fp);
          }

          if (typeof st !== "undefined" && st.mode === "buy" && Array.isArray(soc.rera_ids) && soc.rera_ids.length && !card.querySelector(".bh-rera-chip")) {
            const rc = document.createElement("span");
            rc.className = "bh-rera-chip";
            rc.textContent = "RERA";
            metaRow.appendChild(rc);
          }

          const photos = [];
          const addP = u => { const su = safeUrl(u); if (su && !photos.includes(su)) photos.push(su); };
          if (imgEl) addP(imgEl.src);
          addP(soc.thumb);
          (soc.photos || []).forEach(addP);
          const us = (typeof st !== "undefined" && st.mode === "buy" ? soc.units_buy : soc.units_rent) || [];
          us.forEach(u => { addP(u.img); (u.imgs || []).forEach(addP); });

          if (imgEl && photos.length > 1) {
            let idx = 0;
            const show = () => {
              idx = (idx + photos.length) % photos.length;
              imgEl.src = photos[idx];
              if (cnt) { delete cnt.dataset.single; cnt.textContent = (idx + 1) + "/" + photos.length; }
            };
            if (cnt) { delete cnt.dataset.single; cnt.textContent = "1/" + photos.length; }

            const mediaBox = imgEl.parentElement || card;
            mediaBox.querySelectorAll("button").forEach(btn => {
              const t = (btn.textContent || "").trim();
              const al = (btn.getAttribute("aria-label") || "").toLowerCase();
              if (t === "<" || t === "\u2039" || al.includes("prev")) {
                btn.addEventListener("click", e => { e.preventDefault(); e.stopImmediatePropagation(); idx--; show(); }, true);
              } else if (t === ">" || t === "\u203a" || al.includes("next")) {
                btn.addEventListener("click", e => { e.preventDefault(); e.stopImmediatePropagation(); idx++; show(); }, true);
              }
            });

            let sx = null;
            mediaBox.addEventListener("pointerdown", e => { if (!e.target.closest("button")) sx = e.clientX; }, { passive: true });
            mediaBox.addEventListener("pointerup", e => {
              if (sx === null) return;
              const dx = e.clientX - sx;
              sx = null;
              if (Math.abs(dx) > 32) { e.stopPropagation(); idx += (dx < 0 ? 1 : -1); show(); }
            });
          }
        }

        const fl = window.__v17Flags?.[url] || window.__v17Flags?.[sid];
        if (fl && fl.total > 0 && !card.querySelector(".bh-flag-pill")) {
          const b = document.createElement("span");
          b.className = "bh-flag-pill";
          b.textContent = "Reported (" + fl.total + ")";
          metaRow.appendChild(b);
        }
      });
      updateHeaderLabels();
      syncUrlFromState();
    });
    new MutationObserver(decorateCards).observe(cardList, { childList: true });
    setTimeout(decorateCards, 600);
  }

  const dBody = document.getElementById("dBody");
  if (dBody) {
    let galPhotos = [];
    let galIdx = 0;

    function updateGalView(wrap) {
      const img = wrap.querySelector("img");
      const cnt = wrap.querySelector(".bh-dgal-cnt");
      const dots = wrap.querySelector(".bh-dgal-dots");
      if (!img || !galPhotos.length) return;
      galIdx = (galIdx + galPhotos.length) % galPhotos.length;
      img.src = galPhotos[galIdx];
      if (cnt) {
        cnt.style.display = galPhotos.length > 1 ? "" : "none";
        cnt.textContent = (galIdx + 1) + " / " + galPhotos.length;
      }
      wrap.querySelectorAll(".bh-dgal-btn").forEach(b => { b.style.display = galPhotos.length > 1 ? "flex" : "none"; });
      if (dots) {
        dots.innerHTML = galPhotos.length > 1
          ? galPhotos.slice(0, 8).map((_, i) => '<span class="bh-dgal-dot' + (i === galIdx ? ' on' : '') + '"></span>').join("")
          : "";
      }
    }

    document.addEventListener("keydown", e => {
      const wrap = dBody.querySelector(".bh-dgal");
      if (!wrap || galPhotos.length < 2) return;
      if (e.key === "ArrowLeft") { galIdx--; updateGalView(wrap); }
      else if (e.key === "ArrowRight") { galIdx++; updateGalView(wrap); }
    });

    new MutationObserver(() => {
      if (dBody.dataset.bhRendering || !dBody.innerHTML.trim()) return;
      dBody.dataset.bhRendering = "1";
      try {
        dBody.querySelectorAll("button").forEach(b => {
          if (/^\s*sav(e|ed)\s*$/i.test(b.textContent || "")) b.style.display = "none";
        });

        const socId = (typeof st !== "undefined" && st.sel) || "";
        const soc = (typeof societies !== "undefined" ? societies : []).find(x => x.id === socId);

        const firstImg = dBody.querySelector("img");
        if (firstImg && !dBody.querySelector(".bh-dgal")) {
          const seed = [];
          const addUrl = u => { const su = safeUrl(u); if (su && !seed.includes(su)) seed.push(su); };
          addUrl(firstImg.src);
          if (soc) {
            addUrl(soc.thumb);
            (soc.photos || []).forEach(addUrl);
            const us = typeof matchingUnits === "function" ? matchingUnits(soc) : (soc.units_rent || []);
            us.forEach(u => { addUrl(u.img); (u.imgs || []).forEach(addUrl); });
          }
          galPhotos = seed;
          galIdx = 0;

          const wrap = document.createElement("div");
          wrap.className = "bh-dgal";
          wrap.innerHTML =
            '<img src="' + escHtml(galPhotos[0] || "") + '" alt="Property photo" decoding="async" />' +
            '<button type="button" class="bh-dgal-btn bh-dgal-prev" aria-label="Previous photo">\u2039</button>' +
            '<button type="button" class="bh-dgal-btn bh-dgal-next" aria-label="Next photo">\u203a</button>' +
            '<span class="bh-dgal-cnt"></span>' +
            '<div class="bh-dgal-dots"></div>';

          const oldWrap = firstImg.closest(".d-hero, .d-gal, .gallery, .hero-wrap") || firstImg;
          oldWrap.replaceWith(wrap);
          updateGalView(wrap);

          wrap.querySelector(".bh-dgal-prev").addEventListener("click", () => { galIdx--; updateGalView(wrap); });
          wrap.querySelector(".bh-dgal-next").addEventListener("click", () => { galIdx++; updateGalView(wrap); });

          let startX = null;
          wrap.addEventListener("pointerdown", e => { if (!e.target.closest("button")) startX = e.clientX; });
          wrap.addEventListener("pointerup", e => {
            if (startX === null) return;
            const dx = e.clientX - startX;
            startX = null;
            if (Math.abs(dx) > 35 && galPhotos.length > 1) { galIdx += (dx < 0 ? 1 : -1); updateGalView(wrap); }
          });

          const portalLink = dBody.querySelector('a[href*="magicbricks"], a[href*="nobroker"], a[href*="squareyards"], a[href*="makaan"], a[href*="commonfloor"], a[href*="99acres"], a[href*="housing.com"]')?.href;
          if (portalLink && galPhotos.length < 5) {
            fetch("/api/photos?url=" + encodeURIComponent(portalLink))
              .then(r => (r.ok ? r.json() : null))
              .then(d => {
                if (d && Array.isArray(d.photos)) {
                  let changed = false;
                  d.photos.forEach(p => { const su = safeUrl(p); if (su && !galPhotos.includes(su)) { galPhotos.push(su); changed = true; } });
                  if (changed) updateGalView(wrap);
                }
              })
              .catch(() => {});
          }
        }

        if (soc && !dBody.querySelector(".bh-rera-card")) {
          const hasRera = Array.isArray(soc.rera_ids) && soc.rera_ids.length > 0;
          const isBuy = (typeof st !== "undefined" && st.mode === "buy");
          if (hasRera || isBuy) {
            const card = document.createElement("div");
            card.className = "bh-rera-card";
            if (hasRera) {
              const metaParts = [];
              if (soc.rera_developer) metaParts.push("<span>Developer: <strong>" + escHtml(soc.rera_developer) + "</strong></span>");
              if (soc.rera_carpet_sqft) metaParts.push("<span>Carpet: <strong>" + escHtml(soc.rera_carpet_sqft) + " sq ft</strong></span>");
              if (soc.rera_possession) metaParts.push("<span>Possession: <strong>" + escHtml(soc.rera_possession) + "</strong></span>");
              card.innerHTML =
                '<div class="bh-rera-hdr"><span class="bh-rera-title">MahaRERA Verified Registry</span><span style="font-size:11px;opacity:.7;">Click ID to copy</span></div>' +
                '<div class="bh-rera-ids">' + soc.rera_ids.map(r => '<button type="button" class="bh-rera-id" data-copy="' + escHtml(r) + '">' + escHtml(r) + '</button>').join("") + '</div>' +
                (metaParts.length ? '<div class="bh-rera-meta">' + metaParts.join("") + '</div>' : '') +
                '<a class="bh-rera-link" href="https://maharera.maharashtra.gov.in/" target="_blank" rel="noopener noreferrer">Verify project on official MahaRERA portal \u2197</a>';
            } else {
              card.innerHTML =
                '<div class="bh-rera-hdr"><span class="bh-rera-title">MahaRERA Check</span></div>' +
                '<div class="bh-rera-meta"><span>RERA ID not listed on portal ad. Verify registration before paying a booking token.</span></div>' +
                '<a class="bh-rera-link" href="https://maharera.maharashtra.gov.in/" target="_blank" rel="noopener noreferrer">Search "' + escHtml(soc.name || "project") + '" on MahaRERA \u2197</a>';
            }
            card.addEventListener("click", async e => {
              const btn = e.target.closest(".bh-rera-id");
              if (!btn) return;
              const val = btn.dataset.copy || "";
              try {
                await navigator.clipboard.writeText(val);
                btn.textContent = val + " (Copied)";
                setTimeout(() => { btn.textContent = val; }, 1400);
              } catch {}
            });
            dBody.appendChild(card);
          }
        }

        if (!dBody.querySelector(".bh-flag-bar")) {
          const bar = document.createElement("div");
          bar.className = "bh-flag-bar";
          bar.innerHTML =
            '<span>Issue with this listing or map pin?</span>' +
            '<div class="bh-flag-btns">' +
            '<button type="button" class="bh-flag-btn" data-r="rented">Report Rented</button>' +
            '<button type="button" class="bh-flag-btn" data-r="wrong_pin">Wrong Pin</button>' +
            '<button type="button" class="bh-flag-btn" data-r="broker_bait">Fake / Bait</button>' +
            '</div>';
          bar.addEventListener("click", async e => {
            const btn = e.target.closest(".bh-flag-btn");
            if (!btn) return;
            const unitUrl = dBody.querySelector('a[href^="http"]:not([href*="google.com/maps"]):not([href*="wa.me"]):not([href*="maharera"])')?.href || null;
            btn.textContent = "Saving...";
            try {
              const r = await fetch("/api/flags", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ society_id: socId || "unknown", unit_url: unitUrl, reason: btn.dataset.r })
              });
              if (r.ok) bar.innerHTML = '<span style="color:#16a34a;font-weight:600;">Logged! Thank you for keeping Bombay Homes accurate.</span>';
              else if (r.status === 429) btn.textContent = "Slow down";
              else btn.textContent = "Retry";
            } catch { btn.textContent = "Retry"; }
          });
          dBody.appendChild(bar);
        }
      } finally {
        setTimeout(() => { delete dBody.dataset.bhRendering; }, 30);
      }
    }).observe(dBody, { childList: true });
  }

  const waBtn = document.getElementById("v17WaParseBtn");
  const waTxt = document.getElementById("v17WaPaste");
  if (waBtn && waTxt) {
    const LOC_LIST = [
      "Bandra West","Bandra East","Pali Hill","Khar West","Khar East","Santacruz West","Santacruz East",
      "Vile Parle West","Vile Parle East","Juhu","Versova","Lokhandwala","Andheri West","Andheri East",
      "Goregaon West","Goregaon East","Malad West","Malad East","Kandivali West","Borivali West",
      "Colaba","Cuffe Parade","Malabar Hill","Worli","Lower Parel","Prabhadevi","Dadar West","Dadar East",
      "Mahim","Matunga West","Sion","Byculla","Parel","Tardeo","Wadala","Powai","Chandivali",
      "Ghatkopar West","Vikhroli","Kanjurmarg","Mulund West","Chembur","Kurla West","Thane West",
      "Vashi","Nerul","Seawoods","Kharghar","CBD Belapur","Airoli","Panvel"
    ];
    waBtn.addEventListener("click", () => {
      const t = waTxt.value.trim();
      if (!t) return;
      const low = t.toLowerCase();
      const hitLoc = LOC_LIST.find(l => low.includes(l.toLowerCase())) || "";
      if (hitLoc && document.getElementById("pLoc")) document.getElementById("pLoc").value = hitLoc;
      const bhkEl = document.getElementById("pBhk");
      if (bhkEl) {
        if (/\b1\s*rk\b|\bstudio\b/i.test(t)) bhkEl.value = "0";
        else { const bm = t.match(/\b([1-4](?:\.5)?)\s*[-]?\s*bhk\b/i); if (bm) bhkEl.value = bm[1]; }
      }
      const pm = t.match(/(?:\u20b9|rs\.?|rent[:\s]*|price[:\s]*)\s*([\d,.]+)\s*(cr|crore|l|lac|lakh|k)?/i) || t.match(/\b(\d{2,3})\s*k\b/i);
      if (pm && document.getElementById("pPrice")) {
        let v = parseFloat(pm[1].replace(/,/g, ""));
        const u = (pm[2] || (pm[0].toLowerCase().includes("k") ? "k" : "")).toLowerCase();
        if (u.startsWith("cr")) v *= 1e7;
        else if (u.startsWith("l")) v *= 1e5;
        else if (u === "k") v *= 1e3;
        if (isFinite(v) && v >= 5000) {
          document.getElementById("pPrice").value = Math.round(v);
          const modeEl = document.getElementById("pMode");
          if (modeEl) modeEl.value = v >= 2000000 ? "buy" : "rent";
        }
      }
      const nm = t.match(/(?:in|at|building|society|tower)[:\s]+([A-Z][A-Za-z0-9\s&'-]{3,38})/);
      if (nm && document.getElementById("pName") && !document.getElementById("pName").value) {
        document.getElementById("pName").value = nm[1].trim();
      }
      waBtn.textContent = "Auto-Filled!";
      setTimeout(() => { waBtn.textContent = "Auto-Fill Form"; }, 1500);
    });
  }

  function hookMapUpgrades() {
    const m = (typeof map !== "undefined" && map && map.createPane) ? map : null;
    if (!m || m._bhUpgraded) return;
    m._bhUpgraded = true;

    if (!m.getPane("bhOverlayPane")) {
      const op = m.createPane("bhOverlayPane");
      op.style.zIndex = 520;
      op.style.pointerEvents = "none";
    }
    if (!m.getPane("bhAreaPane")) {
      const ap = m.createPane("bhAreaPane");
      ap.style.zIndex = 690;
      ap.style.pointerEvents = "none";
    }

    const AREA_LABELS = [
      ["Colaba",18.9067,72.8147],["Malabar Hill",18.9548,72.8017],["Worli",19.0176,72.8162],
      ["Lower Parel",18.9977,72.8290],["Dadar",19.0213,72.8424],["Wadala",19.0169,72.8636],
      ["Bandra West",19.0596,72.8295],["Bandra East / BKC",19.0658,72.8620],["Khar West",19.0715,72.8339],
      ["Santacruz",19.0825,72.8410],["Juhu",19.1075,72.8263],["Versova",19.1314,72.8152],
      ["Andheri West",19.1364,72.8296],["Andheri East",19.1136,72.8697],["Powai",19.1197,72.9051],
      ["Chembur",19.0522,72.9005],["Ghatkopar",19.0860,72.9080],["Goregaon West",19.1663,72.8426],
      ["Goregaon East",19.1653,72.8645],["Malad West",19.1864,72.8358],["Malad East",19.1872,72.8582],
      ["Kandivali",19.2084,72.8490],["Borivali",19.2288,72.8520],["Mulund",19.1726,72.9425],
      ["Thane West",19.2183,72.9781],["Vashi",19.0771,72.9986],["Nerul",19.0330,73.0297],
      ["Kharghar",19.0473,73.0699],["Airoli",19.1590,72.9986]
    ];
    const lblLayer = L.layerGroup();
    AREA_LABELS.forEach(([name, lat, lng]) => {
      L.marker([lat, lng], {
        pane: "bhAreaPane", interactive: false,
        icon: L.divIcon({ className: "", html: '<div class="bh-area-lbl">' + escHtml(name) + '</div>', iconSize: [0, 0] })
      }).addTo(lblLayer);
    });
    lblLayer.addTo(m);

    const METRO_LINES = [
      { color: "#38bdf8", pts: [[19.1314,72.8213],[19.1243,72.8315],[19.1197,72.8464],[19.1155,72.8562],[19.1103,72.8750],[19.1079,72.8834],[19.1045,72.8886],[19.0868,72.9082]] },
      { color: "#facc15", pts: [[19.2502,72.8593],[19.2292,72.8452],[19.2059,72.8364],[19.1864,72.8360],[19.1665,72.8366],[19.1415,72.8330],[19.1243,72.8315]] },
      { color: "#fb7185", pts: [[19.2502,72.8593],[19.2296,72.8631],[19.2050,72.8650],[19.1865,72.8615],[19.1650,72.8565],[19.1370,72.8560],[19.1155,72.8562]] },
      { color: "#2dd4bf", pts: [[18.9128,72.8214],[18.9322,72.8264],[18.9520,72.8220],[18.9830,72.8210],[19.0055,72.8235],[19.0215,72.8390],[19.0655,72.8655],[19.0890,72.8680],[19.1100,72.8760],[19.1410,72.8780]] }
    ];
    const boldMetro = L.layerGroup();
    METRO_LINES.forEach(line => {
      L.polyline(line.pts, { pane: "bhOverlayPane", color: "#000000", weight: 8, opacity: 0.55 }).addTo(boldMetro);
      L.polyline(line.pts, { pane: "bhOverlayPane", color: line.color, weight: 4.5, opacity: 0.96 }).addTo(boldMetro);
      line.pts.forEach(pt => L.circleMarker(pt, { pane: "bhOverlayPane", radius: 4.5, color: "#000", weight: 1.5, fillColor: line.color, fillOpacity: 1 }).addTo(boldMetro));
    });

    const FLOOD_ZONES = [
      [19.0075, 72.8422, 650],[19.0385, 72.8605, 750],[19.0725, 72.8790, 800],[19.0885, 72.8435, 600],
      [19.1180, 72.8440, 620],[19.1865, 72.8475, 620],[18.9990, 72.8330, 580],[19.0480, 72.8880, 700],
      [19.1390, 72.9330, 750],[19.2420, 72.8580, 620]
    ];
    const boldFlood = L.layerGroup();
    FLOOD_ZONES.forEach(([lat, lng, rad]) => {
      L.circle([lat, lng], {
        pane: "bhOverlayPane", radius: rad, color: "#ef4444", weight: 2.5,
        dashArray: "6 4", fillColor: "#dc2626", fillOpacity: 0.36
      }).addTo(boldFlood);
    });

    const syncOverlayButtons = () => {
      const mBtn = [...document.querySelectorAll("button")].find(b => /^\s*metro\s*$/i.test(b.textContent || ""));
      const fBtn = [...document.querySelectorAll("button")].find(b => /^\s*flood\s*$/i.test(b.textContent || ""));
      if (mBtn) {
        const on = mBtn.classList.contains("active") || mBtn.classList.contains("on");
        if (on && !m.hasLayer(boldMetro)) boldMetro.addTo(m);
        else if (!on && m.hasLayer(boldMetro)) m.removeLayer(boldMetro);
      }
      if (fBtn) {
        const on = fBtn.classList.contains("active") || fBtn.classList.contains("on");
        if (on && !m.hasLayer(boldFlood)) boldFlood.addTo(m);
        else if (!on && m.hasLayer(boldFlood)) m.removeLayer(boldFlood);
      }
    };
    document.addEventListener("click", e => {
      if (e.target.closest("button") && /^\s*(metro|flood)\s*$/i.test(e.target.closest("button").textContent || "")) {
        setTimeout(syncOverlayButtons, 40);
      }
    });
    setTimeout(syncOverlayButtons, 500);
  }

  const mobBtn = document.getElementById("v20MobToggle");
  if (mobBtn) {
    mobBtn.addEventListener("click", () => {
      const showingMap = document.body.classList.toggle("bh-mob-map");
      mobBtn.textContent = showingMap ? "Show List" : "Show Map";
      if (showingMap && typeof map !== "undefined" && map && map.invalidateSize) {
        setTimeout(() => map.invalidateSize(), 120);
      }
    });
  }

  setTimeout(hookMapUpgrades, 650);
  applyUrlStateOnBoot();
})();
