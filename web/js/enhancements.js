/* Bombay Homes - Unified Enhancements Module (v24 Clean & Hardened) */
(function initBombayHomesEnhancements() {
  "use strict";

  function bh() { return (typeof window.__bh === "function" ? window.__bh() : {}) || {}; }

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

  const BH_BAD_IMG_RE = /(floor[-_]?plan|master[-_]?plan|site[-_]?plan|unit[-_]?plan|location[-_]?map|3d[-_]?plan|3d[-_]?render|layout|blueprint|brochure|elevation|under_screening|secondaryPortal\/optImages|fbshare|static\.99acres\.com|assets\.nobroker\.in|no[-_]?image|no[-_]?photo|placeholder|default[-_]?img|avatar|logo)/i;

  function bhMediaInfo(raw) {
    const su = safeUrl(raw);
    if (!su || BH_BAD_IMG_RE.test(su)) return null;
    let url = su;
    if (url.includes("img.staticmb.com/mbphoto/property/") && url.includes("Photo_h180_w240")) {
      url = url.replace("Photo_h180_w240", "Photo_h600_w900").replace("_180_240.", "_600_900.");
    } else if (url.includes("housingcdn.com/") || url.includes("housing-images.n7net.in/")) {
      url = url.replace(/\/v(\d+)\/(?:version|fs_medium|medium|small|thumb)\//i, "/v$1/fs/");
    } else if (url.includes("img.staticmb.com/mbimages/project/Photo_h310_w462/")) {
      url = url.replace("Photo_h310_w462/", "").replace("_310_462.", ".");
    } else if (url.includes("images.nobroker.in/images/")) {
      url = url.replace(/_(?:thumbnail|small|medium)\./i, "_large.");
    }
    const clean = url.split("?")[0];
    const m99 = clean.match(/imagecdn\.99acres\.com\/.*\/(\d+)([A-Z])-\d+\./i);
    if (m99) {
      const c = m99[2].toUpperCase();
      const rank = c === "O" ? 5 : (c === "L" ? 4 : (c === "M" ? 3 : (c === "F" ? 2 : 1)));
      return { url, key: "99:" + m99[1], rank };
    }
    if (clean.includes("images.nobroker.in/images/")) {
      const k = clean.replace(/_(?:thumbnail|small|medium|large|original|enhance_large|enhance_medium)(?=\.[a-z]+$)/i, "").toLowerCase();
      const rank = /_original\./i.test(clean) ? 4 : (/_large\./i.test(clean) ? 3 : (/_medium\./i.test(clean) ? 2 : 1));
      return { url, key: "nb:" + k, rank };
    }
    if (clean.includes("housingcdn.com") || clean.includes("n7net.in")) {
      const mH = clean.match(/\/([a-f0-9]{16,40})\/v\d+\/([^/]+)\//i);
      if (mH) {
        const vn = mH[2].toLowerCase();
        const rank = vn === "fs" ? 4 : (vn.includes("large") ? 3 : 2);
        return { url, key: "hs:" + mH[1].toLowerCase(), rank };
      }
    }
    const k = clean
      .replace(/\/(thumb|medium|small|large|original|cropped|resized|fs|fs_medium|version)\//gi, "/")
      .replace(/[_\-]\d+x\d+(?=\.[a-z]+$)/i, "")
      .replace(/[_\-](?:small|medium|large|thumb|thumbnail|original)(?=\.[a-z]+$)/i, "")
      .toLowerCase();
    return { url, key: k, rank: 2 };
  }

  function bhBuildCleanPhotos(urls) {
    const byKey = new Map();
    const order = [];
    for (const raw of (urls || [])) {
      const info = bhMediaInfo(raw);
      if (!info) continue;
      const prev = byKey.get(info.key);
      if (!prev) {
        byKey.set(info.key, info);
        order.push(info.key);
      } else if (info.rank > prev.rank) {
        byKey.set(info.key, info);
      }
    }
    return order.map(k => byKey.get(k).url);
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
        try { if (bh().renderList) bh().renderList(); } catch {}
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
      const modeLbl = (bh().st && bh().st.mode === "buy") ? "For Sale" : "For Rent";
      const target = "Mumbai " + modeLbl + " \u00b7 " + rel;
      if (freshEl.textContent !== target) freshEl.textContent = target;
    }

    if (resSumEl) {
      const txt = resSumEl.textContent || "";
      if (txt.includes("exact pin") || txt.includes("homes")) {
        const nMatch = txt.match(/([\d,]+)/);
        const bldgs = nMatch ? nMatch[1] : (bh().filtered ? bh().filtered.length.toLocaleString("en-IN") : "0");
        let totalFlats = 0;
        if (bh().filtered && bh().matchingUnits) {
          for (const s of bh().filtered) totalFlats += bh().matchingUnits(s).length;
        }
        const modeWord = (bh().st && bh().st.mode === "buy") ? "for sale" : "for rent";
        const out = totalFlats > 0
          ? (bldgs + " buildings \u00b7 " + totalFlats.toLocaleString("en-IN") + " flats " + modeWord)
          : (bldgs + " buildings " + modeWord);
        if (window.__bhModeLoading === "buy" && /^0\s+buildings\s+for\s+sale/i.test(out)) out = "Loading homes for sale..."; if (resSumEl.textContent !== out) resSumEl.textContent = out;
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
      const api = bh();
      const st = api.st; if (!st) return;
      const p = new URLSearchParams();
      if (st.mode && st.mode !== "rent") p.set("mode", st.mode);
      const sortVal = (sortEl && sortEl.value) || st.sort || "rec";
      if (sortVal && sortVal !== "rec") p.set("sort", sortVal);
      if (st.lister && String(st.lister).toUpperCase() !== "ALL") p.set("lister", st.lister);
      const fLocVal = (document.getElementById("fLoc")?.value || "ALL");
      const locs = (Array.isArray(st.multiLocs) && st.multiLocs.length)
        ? st.multiLocs
        : (fLocVal && fLocVal !== "ALL" ? [fLocVal] : []);
      if (locs.length) p.set("locs", locs.join(","));
      if (st.bhks && st.bhks.size) p.set("bhk", [...st.bhks].join(","));
      if (st.balcony) p.set("balcony", "1");
      if (st.seaview) p.set("seaview", "1");
      if (st.terrace) p.set("terrace", "1");
      if (st.zero) p.set("zb", "1");
      if (st.brightOnly) p.set("bright", "1");
      if (st.reraOnly) p.set("rera", "1");
      const qs = p.toString();
      history.replaceState(null, "", qs ? ("?" + qs) : location.pathname);
    } catch {}
  }

  function applyUrlStateOnBoot() {
    try {
      const p = new URLSearchParams(location.search);
      const api = bh();
      const st = api.st; if (![...p.keys()].length || !st) return;
      if (p.get("mode") === "buy") {
        st.mode = "buy";
        document.getElementById("modeBuy")?.click();
      }
      if (p.get("sort")) {
        st.sort = p.get("sort");
        if (sortEl) sortEl.value = st.sort;
      }
      if (p.get("lister")) {
        st.lister = p.get("lister");
        document.querySelector('[data-lt="' + p.get("lister").replace(/"/g, "") + '"]')?.click();
      }
      if (p.get("balcony") === "1") st.balcony = true;
      if (p.get("seaview") === "1") st.seaview = true;
      if (p.get("terrace") === "1") st.terrace = true;
      if (p.get("zb") === "1") st.zero = true;
      if (p.get("bright") === "1") st.brightOnly = true;
      if (p.get("rera") === "1") st.reraOnly = true;
      if (p.get("bhk") && st.bhks && st.bhks.add) {
        p.get("bhk").split(",").forEach(v => { const n = parseFloat(v); if (isFinite(n)) st.bhks.add(n); });
      }
      const rawLocs = p.get("locs") || p.get("loc") || "";
      if (rawLocs) {
        const arr = rawLocs.split(",").map(x => x.trim()).filter(Boolean).slice(0, 5);
        if (arr.length) {
          st.multiLocs = arr;
          const fl = document.getElementById("fLoc");
          if (fl && arr.length === 1 && [...fl.options].some(o => o.value === arr[0])) {
            fl.value = arr[0];
          }
        }
      }
      const triggerRender = () => {
        try {
          const cur = bh();
          if (cur.renderAll) cur.renderAll();
          else if (cur.renderList) cur.renderList();
        } catch {}
      };
      triggerRender();
      setTimeout(triggerRender, 500);
      setTimeout(triggerRender, 1500);
    } catch {}
  }

  if (sortEl) {
    sortEl.addEventListener("change", () => {
      if (bh().st) bh().st.sort = sortEl.value;
      try { if (bh().renderList) bh().renderList(); } catch {}
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
      const socById = new Map((bh().societies || []).map(s => [s.id, s]));
      cardList.querySelectorAll("article.fc").forEach(card => {
        if (card.dataset.bhDone) return;
        card.dataset.bhDone = "1";

        const imgEl = card.querySelector("img");
        if (imgEl) { imgEl.loading = "lazy"; imgEl.decoding = "async"; }

        const sid = card.dataset.id;
        const url = card.dataset.url || "";
        const soc = socById.get(sid);
        const body = card.querySelector(".fc-body") || card;
        let metaRow = card.querySelector(".bh-badge-row");
        if (!metaRow) { metaRow = document.createElement("div"); metaRow.className = "bh-badge-row"; const anchor = card.querySelector(".fc-price, .fc-top"); if (anchor) anchor.insertAdjacentElement("afterend", metaRow); else body.appendChild(metaRow); }

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
          const _rawP = [];
          const addP = u => { if (u) _rawP.push(u); };
          if (imgEl) addP(imgEl.src);
          addP(soc.thumb);
          (soc.photos || []).forEach(addP);
          const us = (typeof st !== "undefined" && st.mode === "buy" ? soc.units_buy : soc.units_rent) || [];
          us.forEach(u => { addP(u.img); (u.imgs || []).forEach(addP); });

          bhBuildCleanPhotos(_rawP).forEach(u => photos.push(u));
          if (imgEl && photos.length && imgEl.src !== photos[0]) imgEl.src = photos[0];
          if (cnt) { if (photos.length > 1) { delete cnt.dataset.single; cnt.textContent = "1/" + photos.length; } else { cnt.dataset.single = "1"; cnt.textContent = ""; } }
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
      if (!wrap || !wrap._bhNav) return;
      if (e.key === "ArrowLeft") wrap._bhNav(-1);
      else if (e.key === "ArrowRight") wrap._bhNav(1);
    });

    new MutationObserver(() => {
      if (dBody.dataset.bhRendering || !dBody.innerHTML.trim()) return;
      dBody.dataset.bhRendering = "1";
      try {
        dBody.querySelectorAll("button").forEach(b => {
          if (/^\s*sav(e|ed)\s*$/i.test(b.textContent || "")) b.style.display = "none";
        });

        const socId = (bh().st && bh().st.sel) || "";
        const soc = (bh().societies || []).find(x => x.id === socId);

        const heroSlot = dBody.querySelector(".d-hero-slot");
        const firstImg = dBody.querySelector("img");
        const mountTarget = heroSlot || firstImg;
        if (mountTarget && !dBody.querySelector(".bh-dgal")) {
          const openedSocId = socId;
          const _mkMedia = (rawUrls, rawVids) => {
            const imgs = bhBuildCleanPhotos(rawUrls).filter(u => !(rawVids && rawVids.length && u.includes("i.ytimg.com/vi/")));
            const vids = [], seenV = new Set();
            for (const v of (rawVids || [])) {
              if (!v || !v.url || seenV.has(v.url)) continue;
              seenV.add(v.url);
              vids.push({ type: v.kind === "youtube" ? "youtube" : "video", url: v.url });
            }
            const out = [];
            if (imgs.length) out.push({ type: "img", url: imgs[0] });
            vids.forEach(v => out.push(v));
            imgs.slice(1).forEach(url => out.push({ type: "img", url }));
            return out;
          };
          const _fmtTabP = (p, isB) => {
            if (!p) return "";
            if (isB) return p >= 1e7 ? ("\u20b9" + (p / 1e7).toFixed(1).replace(/\.0$/, "") + "Cr") : ("\u20b9" + Math.round(p / 1e5) + "L");
            return p >= 1e5 ? ("\u20b9" + (p / 1e5).toFixed(1).replace(/\.0$/, "") + "L") : ("\u20b9" + Math.round(p / 1e3) + "k");
          };
          const rawSeed = [], rawVids = [];
          const unitTabs = [];
          const isBuyMode = !!(bh().st && bh().st.mode === "buy");
          if (firstImg && firstImg.getAttribute("src")) rawSeed.push(firstImg.getAttribute("src"));
          if (soc) {
            if (soc.thumb) rawSeed.push(soc.thumb);
            (soc.photos || []).forEach(p => rawSeed.push(p));
            (soc.videos || []).forEach(v => rawVids.push(v));
            const us = bh().matchingUnits ? bh().matchingUnits(soc) : (soc.units_rent || []);
            us.forEach((u, ui) => {
              const uUrls = [];
              if (u.img) { rawSeed.push(u.img); uUrls.push(u.img); }
              (u.imgs || []).forEach(p => { rawSeed.push(p); uUrls.push(p); });
              const uVids = Array.isArray(u.vids) ? u.vids : [];
              uVids.forEach(v => rawVids.push(v));
              const uMedia = _mkMedia(uUrls, uVids);
              if (uMedia.length) {
                const bLbl = u.b === 0 ? "1RK" : (u.b ? (u.b + "BHK") : "");
                const lbl = [_fmtTabP(u.p, isBuyMode), bLbl].filter(Boolean).join(" ") || ("Flat " + (ui + 1));
                unitTabs.push({ label: lbl, items: uMedia });
              }
            });
          }

          let allMediaItems = _mkMedia(rawSeed, rawVids);
          let mediaItems = allMediaItems.slice();
          let mIdx = 0;
          galPhotos = mediaItems.map(x => x.url);
          galIdx = 0;

          const wrap = document.createElement("div");
          wrap.className = "bh-dgal" + (mediaItems.length ? "" : " is-empty");
          wrap.innerHTML =
            '<div class="bh-dgal-stage"></div>' +
            '<button type="button" class="bh-dgal-btn bh-dgal-prev" aria-label="Previous media">\u2039</button>' +
            '<button type="button" class="bh-dgal-btn bh-dgal-next" aria-label="Next media">\u203a</button>' +
            '<span class="bh-dgal-cnt"></span>' +
            '<div class="bh-dgal-dots"></div>';

          const oldWrap = heroSlot || firstImg.closest(".d-hero, .d-gal, .gallery, .hero-wrap") || firstImg;
          oldWrap.replaceWith(wrap);

          const renderSlide = () => {
            const stage = wrap.querySelector(".bh-dgal-stage");
            const prevB = wrap.querySelector(".bh-dgal-prev");
            const nextB = wrap.querySelector(".bh-dgal-next");
            const cntEl = wrap.querySelector(".bh-dgal-cnt");
            const dotsEl = wrap.querySelector(".bh-dgal-dots");
            if (!mediaItems.length) {
              wrap.classList.add("is-empty");
              return;
            }
            wrap.classList.remove("is-empty");
            mIdx = ((mIdx % mediaItems.length) + mediaItems.length) % mediaItems.length;
            const cur = mediaItems[mIdx];
            if (cur.type === "video") {
              stage.innerHTML =
                '<video class="bh-dgal-vid" controls playsinline preload="metadata" src="' + escHtml(cur.url) + '"></video>' +
                '<span class="bh-dgal-vidtag">Video Tour</span>';
            } else if (cur.type === "youtube") {
              stage.innerHTML =
                '<iframe class="bh-dgal-yt" src="' + escHtml(cur.url) + '" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>' +
                '<span class="bh-dgal-vidtag">Video Tour</span>';
            } else {
              stage.innerHTML = '<img referrerpolicy="no-referrer" src="' + escHtml(cur.url) + '" referrerpolicy="no-referrer" alt="Property photo" decoding="async" />';
              const im = stage.querySelector("img");
              if (im) {
                im.addEventListener("error", () => {
                  mediaItems.splice(mIdx, 1);
                  if (mIdx >= mediaItems.length) mIdx = 0;
                  renderSlide();
                }, { once: true });
              }
            }
            const multi = mediaItems.length > 1;
            if (prevB) prevB.style.display = multi ? "" : "none";
            if (nextB) nextB.style.display = multi ? "" : "none";
            if (cntEl) {
              cntEl.style.display = multi ? "" : "none";
              cntEl.textContent = (mIdx + 1) + "/" + mediaItems.length + (cur.type !== "img" ? " \u00b7 Video" : "");
            }
            if (dotsEl) {
              dotsEl.style.display = multi ? "flex" : "none";
              const dotCap = Math.min(mediaItems.length, 10);
              dotsEl.innerHTML = Array.from({ length: dotCap }, (_, i) =>
                '<span class="bh-dgal-dot' + (i === (mIdx % dotCap) ? " on" : "") + '"></span>'
              ).join("");
            }
          };

          renderSlide();
          wrap._bhNav = d => { mIdx += d; renderSlide(); };
          if (unitTabs.length >= 2) {
            const tabBar = document.createElement("div");
            tabBar.className = "bh-utabs";
            const mkBtn = (txt, isOn, fn) => {
              const b = document.createElement("button");
              b.type = "button";
              b.className = "bh-utab" + (isOn ? " on" : "");
              b.textContent = txt;
              b.addEventListener("click", () => {
                tabBar.querySelectorAll(".bh-utab").forEach(x => x.classList.remove("on"));
                b.classList.add("on");
                fn();
              });
              return b;
            };
            tabBar.appendChild(mkBtn("All (" + allMediaItems.length + ")", true, () => {
              mediaItems = allMediaItems.slice(); mIdx = 0; renderSlide();
            }));
            unitTabs.slice(0, 6).forEach(t => {
              tabBar.appendChild(mkBtn(t.label + " (" + t.items.length + ")", false, () => {
                mediaItems = t.items.slice(); mIdx = 0; renderSlide();
              }));
            });
            wrap.insertAdjacentElement("afterend", tabBar);
          }
          wrap.querySelector(".bh-dgal-prev").addEventListener("click", () => { mIdx--; renderSlide(); });
          wrap.querySelector(".bh-dgal-next").addEventListener("click", () => { mIdx++; renderSlide(); });

          let startX = null;
          wrap.addEventListener("pointerdown", e => { if (!e.target.closest("button, video, iframe")) startX = e.clientX; });
          wrap.addEventListener("pointerup", e => {
            if (startX === null) return;
            const dx = e.clientX - startX;
            startX = null;
            if (Math.abs(dx) > 35 && mediaItems.length > 1) { mIdx += (dx < 0 ? 1 : -1); renderSlide(); }
          });

          const portalLinks = [...dBody.querySelectorAll('a[href*="magicbricks"], a[href*="nobroker"], a[href*="squareyards"], a[href*="makaan"], a[href*="commonfloor"], a[href*="99acres"], a[href*="housing.com"]')].map(a => a.href);
          const portalLink = portalLinks[0];
          const shouldFetch = !!portalLink && /squareyards\.com|makaan\.com|commonfloor\.com/i.test(portalLink) && mediaItems.length < 6;
          if (shouldFetch) {
            fetch("/api/photos?url=" + encodeURIComponent(portalLink))
              .then(r => (r.ok ? r.json() : null))
              .then(d => {
                if (!d || !wrap.isConnected || ((bh().st && bh().st.sel) !== openedSocId)) return;
                const existingImgs = mediaItems.filter(x => x.type === "img").map(x => x.url);
                const mergedImgs = bhBuildCleanPhotos(existingImgs.concat(Array.isArray(d.photos) ? d.photos : []));
                const vids = Array.isArray(d.videos) ? d.videos.filter(v => v && v.url).map(v => ({ type: v.kind === "youtube" ? "youtube" : "video", url: v.url })) : [];
                const nextItems = [];
                if (mergedImgs.length) nextItems.push({ type: "img", url: mergedImgs[0] });
                vids.forEach(v => nextItems.push(v));
                mergedImgs.slice(1).forEach(u => nextItems.push({ type: "img", url: u }));
                if (nextItems.length > mediaItems.length || (vids.length && !mediaItems.some(x => x.type !== "img"))) {
                  mediaItems = nextItems;
                  galPhotos = mediaItems.map(x => x.url);
                  renderSlide();
                }
              })
              .catch(() => {});
          }
        }

        if (soc && !dBody.querySelector(".bh-rera-card")) {
          const hasRera = Array.isArray(soc.rera_ids) && soc.rera_ids.length > 0;
          const isBuy = (bh().st && bh().st.mode === "buy");
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
    const m = (bh().map && bh().map.createPane) ? bh().map : null;
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
    const MAJOR_NAMES = new Set(["Colaba", "Worli", "Dadar", "Bandra West", "Andheri West", "Powai", "Goregaon West", "Borivali", "Thane West", "Vashi"]);
    const majorLbls = L.layerGroup();
    const detailLbls = L.layerGroup();
    AREA_LABELS.forEach(([name, lat, lng]) => {
      const mk = L.marker([lat, lng], {
        pane: "bhAreaPane", interactive: true,
        icon: L.divIcon({ className: "", html: '<div class="bh-area-lbl bh-area-tap">' + escHtml(name) + '</div>', iconSize: [0, 0] })
      });
      mk.on("click", () => { try { m.flyTo([lat, lng], 14, { duration: 0.65 }); } catch {} });
      if (MAJOR_NAMES.has(name)) mk.addTo(majorLbls);
      else mk.addTo(detailLbls);
    });
    const syncZoomLabels = () => {
      const z = m.getZoom ? m.getZoom() : 11;
      if (!m.hasLayer(majorLbls)) majorLbls.addTo(m);
      if (z >= 12 && !m.hasLayer(detailLbls)) detailLbls.addTo(m);
      else if (z < 12 && m.hasLayer(detailLbls)) m.removeLayer(detailLbls);
    };
    m.on("zoomend", syncZoomLabels);
    syncZoomLabels();

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

  function syncMobTopOffset() {
    const h1 = document.querySelector("header.topbar")?.getBoundingClientRect().height || 0;
    const h2 = document.getElementById("bhAiBar")?.getBoundingClientRect().height || 0;
    const tot = Math.round(h1 + h2);
    if (tot > 40) document.documentElement.style.setProperty("--bh-mob-top", tot + "px");
  }
  window.addEventListener("resize", syncMobTopOffset);
  const mobBtn = document.getElementById("v20MobToggle");
  if (mobBtn) {
    mobBtn.addEventListener("click", () => {
      syncMobTopOffset();
      const showingMap = document.body.classList.toggle("bh-mob-map");
      mobBtn.textContent = showingMap ? "Show List" : "Show Map";
      if (showingMap && bh().map && bh().map.invalidateSize) {
        setTimeout(() => { syncMobTopOffset(); bh().map.invalidateSize(); }, 120);
      }
    });
  }

  let _mapTries = 0; const _mapIv = setInterval(() => { hookMapUpgrades(); if ((bh().map && bh().map._bhUpgraded) || ++_mapTries > 15) clearInterval(_mapIv); }, 300);
  applyUrlStateOnBoot();
})();


// === V38 AI VIBE (BRIGHT & MODERN) & JOBS-MINIMAL ASK-THE-MAP ===
(function initV38Features() {
  "use strict";
  function bh() { return (typeof window.__bh === "function" ? window.__bh() : {}) || {}; }

  function stampVibeBadgesOnDom() {
    const cl = document.getElementById("cardList");
    if (!cl) return;
    const socById = new Map((bh().societies || []).map(s => [s.id, s]));
    cl.querySelectorAll("article.fc, .fc[data-id]").forEach(card => {
      const soc = socById.get(card.dataset.id);
      if (!soc) return;
      const vs = typeof soc.vs === "number" ? soc.vs : 50;
      const isRender = !!soc.vr;
      let metaRow = card.querySelector(".bh-badge-row");
      if (!metaRow) {
        metaRow = document.createElement("div");
        metaRow.className = "bh-badge-row";
        const anchor = card.querySelector(".fc-price, .fc-top");
        if (anchor) anchor.insertAdjacentElement("afterend", metaRow);
        else (card.querySelector(".fc-body") || card).appendChild(metaRow);
      }
      if (vs >= 78 && !isRender && !card.querySelector(".bh-vibe-badge")) {
        const vb = document.createElement("span");
        vb.className = "bh-vibe-badge";
        vb.textContent = "Sunlit";
        metaRow.appendChild(vb);
      } else if (isRender && !card.querySelector(".bh-render-badge")) {
        const rb = document.createElement("span");
        rb.className = "bh-render-badge";
        rb.textContent = "3D Render";
        metaRow.appendChild(rb);
      }
    });
  }

  function syncBrightBtnUi() {
    const btn = document.getElementById("bhBrightBtn");
    const st = bh().st;
    if (btn && st) btn.classList.toggle("active", !!st.brightOnly);
  }

  function injectBrightChip() {
    if (document.getElementById("bhBrightBtn")) return;
    const anchor = [...document.querySelectorAll("button")].find(b => /Zero Brokerage|Sea View|Balcony/i.test(b.textContent || ""));
    if (!anchor || !anchor.parentElement) return;
    const btn = document.createElement("button");
    btn.id = "bhBrightBtn";
    btn.type = "button";
    btn.className = "bh-vibe-chip";
    btn.textContent = "Bright & Modern";
    btn.title = "Filter for sunlit, modern flats (ONNX vibe >= 74, hides dark & 3D render ads)";
    btn.addEventListener("click", () => {
      const api = bh();
      if (!api.st) return;
      api.st.brightOnly = !api.st.brightOnly;
      api.st.page = 36;
      syncBrightBtnUi();
      if (api.renderAll) api.renderAll();
      setTimeout(stampVibeBadgesOnDom, 90);
    });
    anchor.parentElement.insertBefore(btn, anchor);
    syncBrightBtnUi();
  }

  const LOC_ALIASES = {
    "sobo": ["Worli", "Lower Parel", "Prabhadevi", "Colaba", "Malabar Hill"],
    "south mumbai": ["Worli", "Lower Parel", "Prabhadevi", "Colaba", "Malabar Hill"],
    "south bombay": ["Worli", "Lower Parel", "Prabhadevi", "Colaba", "Malabar Hill"],
    "bandra": ["Bandra West"],
    "bkc": ["Bandra East", "Bandra West", "Santacruz East"],
    "khar": ["Khar West"],
    "santacruz": ["Santacruz West"],
    "andheri": ["Andheri West", "Andheri East"],
    "dadar": ["Dadar West"],
    "goregaon": ["Goregaon West", "Goregaon East"],
    "malad": ["Malad West"],
    "kandivali": ["Kandivali West"],
    "borivali": ["Borivali West"],
    "thane": ["Thane West"],
    "mulund": ["Mulund West"],
    "ghatkopar": ["Ghatkopar West"],
    "navi mumbai": ["Vashi", "Kharghar", "Nerul", "Seawoods", "Airoli"],
    "aqua line": ["Worli", "Lower Parel", "Dadar West", "Bandra East", "Santacruz East"]
  };

  function getKnownLocalities() {
    const set = new Set();
    (bh().societies || []).forEach(s => { if (s && s.locality) set.add(s.locality); });
    if (set.size < 5) {
      [
        "Bandra West","Bandra East","Khar West","Khar East","Santacruz West","Santacruz East",
        "Vile Parle West","Juhu","Versova","Andheri West","Andheri East","Powai","Chandivali",
        "Colaba","Malabar Hill","Worli","Lower Parel","Prabhadevi","Dadar West","Mahim","Wadala",
        "Chembur","Ghatkopar West","Vikhroli","Mulund West","Goregaon West","Goregaon East",
        "Malad West","Kandivali West","Borivali West","Mira Road","Thane West","Ghodbunder Road",
        "Vashi","Nerul","Seawoods","Kharghar","Airoli","Panvel"
      ].forEach(l => set.add(l));
    }
    return [...set].sort();
  }

  function localFallbackParse(query, knownLocs) {
    const low = String(query || "").toLowerCase();
    const f = {};
    if (/\b(buy|sale|purchase|invest|resale|cr\b|crore)\b/i.test(low)) f.mode = "buy";
    else if (/\b(rent|lease|flatmate|sharing|pg|k\b|\/mo)\b/i.test(low)) f.mode = "rent";

    const bhks = [];
    if (/\b1\s*rk\b|\bstudio\b/i.test(low)) bhks.push(0);
    for (const m of low.matchAll(/\b([1-4])\s*[-]?\s*bhk\b/gi)) {
      const n = Number(m[1]);
      if (!bhks.includes(n)) bhks.push(n);
    }
    if (bhks.length) f.bhks = bhks;

    const pm = low.match(/(?:under|below|max|upto|up to|<)\s*(?:\u20b9|rs\.?)?\s*([\d,.]+)\s*(cr|crore|l|lac|lakh|k)?/i);
    if (pm) {
      let val = parseFloat(pm[1].replace(/,/g, ""));
      const u = (pm[2] || "").toLowerCase();
      if (u.startsWith("cr")) val *= 1e7;
      else if (u.startsWith("l")) val *= 1e5;
      else if (u === "k") val *= 1e3;
      else if (val > 0 && val < 500 && f.mode !== "buy") val *= 1e3;
      if (isFinite(val) && val >= 5000) f.maxPrice = Math.round(val);
    }

    const pmin = low.match(/(?:above|over|min|from|>)\s*(?:\u20b9|rs\.?)?\s*([\d,.]+)\s*(cr|crore|l|lac|lakh|k)?/i);
    if (pmin) {
      let val = parseFloat(pmin[1].replace(/,/g, ""));
      const u = (pmin[2] || "").toLowerCase();
      if (u.startsWith("cr")) val *= 1e7;
      else if (u.startsWith("l")) val *= 1e5;
      else if (u === "k") val *= 1e3;
      if (isFinite(val) && val >= 5000) f.minPrice = Math.round(val);
    }

    const locs = [];
    for (const loc of knownLocs) {
      if (low.includes(loc.toLowerCase()) && !locs.includes(loc)) locs.push(loc);
    }
    if (!locs.length) {
      for (const [al, arr] of Object.entries(LOC_ALIASES)) {
        if (new RegExp("\\b" + al + "\\b", "i").test(low)) {
          arr.forEach(t => { if (knownLocs.includes(t) && !locs.includes(t)) locs.push(t); });
        }
      }
    }
    if (locs.length) f.localities = locs.slice(0, 5);

    if (/\b(zero brokerage|no broker|no brokerage|owner|direct)\b/i.test(low)) f.zero = true;
    if (/\b(flatmate|roommate|shared|sharing|\bpg\b)\b/i.test(low)) f.lister = "shared";
    if (/\bsemi[\s-]*furnished\b/i.test(low)) f.furn = "Semi-Furnished";
    else if (/\bunfurnished\b/i.test(low)) f.furn = "Unfurnished";
    else if (/\bfurnished\b/i.test(low)) f.furn = "Furnished";
    if (/\bbalcony\b/i.test(low)) f.balcony = true;
    if (/\b(sea view|ocean|seaview)\b/i.test(low)) f.seaview = true;
    if (/\b(terrace|garden)\b/i.test(low)) f.terrace = true;
    if (/\b(price drop|dropped|discount|reduced)\b/i.test(low)) f.drop = true;
    if (/\b(monsoon|flood[\s-]*safe|no flood|no waterlogging|low flood)\b/i.test(low)) f.floodSafe = true;
    if (/\b(bright|sunlit|modern|daylight|good interior|airy)\b/i.test(low)) f.brightOnly = true;
    if (/\b(rera|maharera)\b/i.test(low)) f.reraOnly = true;
    if (/\b(aqua line|near metro|walk to metro|metro)\b/i.test(low)) f.maxMetroWalk = 15;
    if (/\bcheapest|lowest price|budget\b/i.test(low)) f.sort = "p_asc";
    else if (/\bbest deal|great value|value\b/i.test(low)) f.sort = "deal";
    else if (/\bclosest metro|nearest metro\b/i.test(low)) f.sort = "metro";
    return f;
  }

  let _askSeq = 0;
  let _aiActive = false;

  window.__bhIsAiActive = () => !!_aiActive;
  window.__bhResetAiUiOnly = () => {
    _askSeq++; _aiActive = false;
    const inp = document.getElementById('bhAiInput'); if (inp) inp.value = '';
    const stEl = document.getElementById('bhAiStatus'); if (stEl) stEl.textContent = '';
    const clrB = document.getElementById('bhAiClear'); if (clrB) clrB.style.display = 'none';
    syncBrightBtnUi();
  };
  function resetAskMapAll() {
    _askSeq++;
    _aiActive = false;
    const api = bh();
    const statusEl = document.getElementById("bhAiStatus");
    const clrBtn = document.getElementById("bhAiClear");
    if (statusEl) statusEl.textContent = "";
    if (clrBtn) clrBtn.style.display = "none";
    if (api.resetAskFilters) api.resetAskFilters();
    syncBrightBtnUi();
    if (api.renderAll) api.renderAll();
  }
  window.__bhResetAskMapAll = resetAskMapAll;

  async function runTalkToMap(query) {
    const q = String(query || "").trim();
    const api = bh();
    const statusEl = document.getElementById("bhAiStatus");
    const goBtn = document.getElementById("bhAiGo");
    if (!q) {
      if (_aiActive) resetAskMapAll();
      return;
    }
    if (!api.st) return;

    const mySeq = ++_askSeq;
    _aiActive = true;
    if (goBtn) { goBtn.disabled = true; goBtn.textContent = "..."; }
    if (statusEl) statusEl.textContent = "Filtering...";

    const knownLocs = getKnownLocalities();
    const localF = localFallbackParse(q, knownLocs);
    let llmF = {};

    try {
      const r = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "parse",
          query: q,
          currentMode: api.st.mode || "rent",
          knownLocalities: knownLocs,
        }),
      });
      if (r.ok) {
        const d = await r.json();
        if (d && d.ok && d.filters && typeof d.filters === "object") llmF = d.filters;
      }
    } catch {}

    if (mySeq !== _askSeq) return;

    const f = Object.assign({}, localF, llmF);
    if ((!f.localities || !f.localities.length) && localF.localities) f.localities = localF.localities;
    if ((!f.bhks || !f.bhks.length) && localF.bhks) f.bhks = localF.bhks;

    const targetMode = f.mode || api.st.mode || "rent";
    if (api.setMode) await api.setMode(targetMode);
    if (mySeq !== _askSeq) return;

    const api2 = bh();
    const st = api2.st;
    if (api2.resetAskFilters) api2.resetAskFilters();

    const applied = [];
    if (Array.isArray(f.bhks) && f.bhks.length && st.bhks && st.bhks.add) {
      f.bhks.forEach(b => {
        st.bhks.add(Number(b));
        applied.push(Number(b) === 0 ? "1RK" : (Number(b) === 4 ? "4+BHK" : (b + "BHK")));
      });
    }
    if (f.minPrice && isFinite(f.minPrice)) st.pLo = Number(f.minPrice);
    if (f.maxPrice && isFinite(f.maxPrice)) st.pHi = Number(f.maxPrice);
    if (Array.isArray(f.localities) && f.localities.length) {
      st.multiLocs = f.localities.slice(0, 5);
      if (api2.renderLocChips) api2.renderLocChips();
      applied.push(st.multiLocs.slice(0, 2).join(" + "));
    }
    if (f.zero) { st.zero = true; applied.push("Zero Brok"); }
    if (f.lister === "shared") { st.lister = "shared"; applied.push("Shared"); }
    else if (f.lister === "owner") { st.lister = "owner"; st.zero = true; }

    function setSelectSmart(id, wanted, numericCeil) {
      const el = document.getElementById(id);
      if (!el) return false;
      const opts = [...(el.options || [])];
      if (!opts.length) { el.value = String(wanted); return true; }
      if (numericCeil) {
        const num = Number(wanted);
        const nums = opts.map(o => ({ v: o.value, n: Number(o.value) })).filter(x => isFinite(x.n) && x.n > 0).sort((a, b) => a.n - b.n);
        if (!nums.length) return false;
        const pick = nums.find(x => x.n >= num) || nums[nums.length - 1];
        el.value = pick.v;
        return true;
      }
      const lowW = String(wanted).toLowerCase();
      const exact = opts.find(o => o.value.toLowerCase() === lowW || (o.textContent || "").toLowerCase().includes(lowW));
      if (exact) { el.value = exact.value; return true; }
      return false;
    }

    if (f.furn) setSelectSmart("fFurn", f.furn, false);
    if (f.balcony) st.balcony = true;
    if (f.seaview) st.seaview = true;
    if (f.terrace) st.terrace = true;
    if (f.drop) st.drop = true;
    if (f.floodSafe) st.flood = true;
    if (f.brightOnly) { st.brightOnly = true; applied.push("Bright"); }
    if (f.reraOnly) st.reraOnly = true;
    if (f.maxMetroWalk) setSelectSmart("fMetro", f.maxMetroWalk, true);
    if (f.hub && setSelectSmart("fHub", f.hub, false) && f.maxHubMin) setSelectSmart("fHubMin", f.maxHubMin, true);
    if (f.sort) {
      const se = document.getElementById("sortSelect");
      if (se) se.value = f.sort;
    }
    if (f.keywords && !st.multiLocs.length) {
      const sb = document.getElementById("searchBox");
      if (sb) sb.value = f.keywords;
    }

    syncBrightBtnUi();
    if (api2.renderAll) api2.renderAll();

    const api3 = bh();
    const matchedSocs = api3.filtered || [];
    const pts = matchedSocs.filter(s => s && s.lat && s.lng).slice(0, 120).map(s => [s.lat, s.lng]);
    if (api3.map && typeof L !== "undefined" && pts.length) {
      try {
        if (pts.length >= 2) api3.map.fitBounds(L.latLngBounds(pts).pad(0.18), { maxZoom: 14, animate: true });
        else api3.map.flyTo(pts[0], 15, { duration: 0.6 });
      } catch {}
    } else if (api3.fitToSelectedLocalities) {
      try { api3.fitToSelectedLocalities(); } catch {}
    }

    setTimeout(stampVibeBadgesOnDom, 100);
    if (statusEl) {
      statusEl.textContent = matchedSocs.length
        ? `${matchedSocs.length.toLocaleString("en-IN")} matches` + (applied.length ? (" \u00b7 " + applied.slice(0, 3).join(" \u00b7 ")) : "")
        : "No exact matches";
    }
    if (goBtn) { goBtn.disabled = false; goBtn.textContent = "Ask Map"; }
  }

  function injectTalkToMapBar() {
    if (document.getElementById("bhAiBar")) return;
    const header = document.querySelector("header.topbar");
    if (!header || !header.parentElement) return;
    const bar = document.createElement("div");
    bar.id = "bhAiBar";
    bar.className = "bh-ai-bar";
    bar.innerHTML =
      '<div class="bh-ai-wrap">' +
        '<input id="bhAiInput" class="bh-ai-input" type="text" placeholder="Ask Map AI: e.g. Sunlit 2BHK under 85k Bandra or Khar zero brokerage" />' +
        '<button id="bhAiClear" class="bh-ai-clear" type="button" aria-label="Clear search" style="display:none">\u00d7</button>' +
      '</div>' +
      '<button id="bhAiGo" class="bh-ai-go" type="button">Ask Map</button>' +
      '<span id="bhAiStatus" class="bh-ai-status"></span>';

    header.insertAdjacentElement("afterend", bar);

    const inp = document.getElementById("bhAiInput");
    const clr = document.getElementById("bhAiClear");
    document.getElementById("bhAiGo").addEventListener("click", () => runTalkToMap(inp.value));
    clr.addEventListener("click", () => { inp.value = ""; resetAskMapAll(); inp.focus(); });
    inp.addEventListener("input", () => {
      const empty = !inp.value.trim();
      clr.style.display = empty ? "none" : "inline-flex";
      const stTxt = (document.getElementById("bhAiStatus")?.textContent || "").trim();
      if (empty && (_aiActive || stTxt)) {
        const sb = document.getElementById("searchBox");
        if (sb && sb.value.trim()) sb.value = "";
        resetAskMapAll();
      }
    });
    inp.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); runTalkToMap(inp.value); } });
  }

  const cl = document.getElementById("cardList");
  if (cl) new MutationObserver(() => requestAnimationFrame(stampVibeBadgesOnDom)).observe(cl, { childList: true });

  setTimeout(() => { injectBrightChip(); injectTalkToMapBar(); stampVibeBadgesOnDom(); }, 450);
})();

/* === BH_V45_UNIFIED_SEARCH === */
(function initUnifiedSearchV48() {
  const NL_RE = /(?:\b(?:under|below|above|over|max|min|upto|within|near|walk|metro|aqua|bkc|sunlit|bright|modern|zero|no\s*brok|owner|flatmate|sharing|pg|sea\s*view|balcony|terrace|flood|monsoon|rera|furnished|semi|unfurnished|cheapest|budget|deal|sobo)\b|\b\d+\s*(?:bhk|rk|k|l|lac|lakh|cr|crore)\b)/i;
  function wire() {
    const sb = document.getElementById("searchBox");
    if (!sb || sb.dataset.bhV48) return;
    sb.dataset.bhV48 = "1";
    sb.placeholder = "Bandra, society, or '2BHK under 85k near metro'";

    const runUnifiedAsk = (rawQ) => {
      const q = String(rawQ || "").trim();
      if (!q) return false;
      const inp = document.getElementById("bhAiInput");
      const btn = document.getElementById("bhAiGo");
      if (!inp) return false;
      inp.value = q;
      inp.dispatchEvent(new Event("input", { bubbles: true }));
      if (btn) btn.click();
      else inp.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      const ac = document.getElementById("ac");
      if (ac) ac.style.display = "none";
      const _ss = document.getElementById("searchSuggest"); if (_ss) { _ss.style.display = "none"; _ss.classList.remove("open", "show"); }
      return true;
    };

    const wrap = sb.closest(".search-wrap");
    if (wrap) {
      let aiBtn = wrap.querySelector(".bh-uni-ai");
      if (!aiBtn) {
        aiBtn = document.createElement("button");
        aiBtn.type = "button";
        aiBtn.className = "bh-uni-ai";
        aiBtn.title = "Ask Map AI";
        aiBtn.textContent = "\u2726 AI";
        wrap.appendChild(aiBtn);
      }
      aiBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (sb.value.trim()) runUnifiedAsk(sb.value);
        else {
          sb.focus();
          sb.placeholder = "Try: Sunlit 2BHK under 85k Bandra zero brokerage";
        }
      };
      const syncBtn = () => {
        const v = sb.value.trim();
        aiBtn.classList.toggle("hot", NL_RE.test(v) || v.split(/\s+/).length >= 3);
        if (!v) {
          const _ss = document.getElementById("searchSuggest"); if (_ss) { _ss.style.display = "none"; _ss.classList.remove("open", "show"); }
          if (window.__bhIsAiActive && window.__bhIsAiActive()) {
            const aiInp = document.getElementById("bhAiInput");
            if (aiInp) aiInp.value = "";
            if (window.__bhResetAskMapAll) window.__bhResetAskMapAll();
          }
        }
      };
      sb.addEventListener("input", syncBtn);
      syncBtn();
    }

    sb.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const v = sb.value.trim();
      if (!v) return;
      if (NL_RE.test(v) || v.split(/\s+/).length >= 3) {
        if (runUnifiedAsk(v)) {
          e.preventDefault();
          e.stopPropagation();
        }
      }
    }, true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(wire, 220));
  else setTimeout(wire, 220);
})();

/* === BH_V50_IMG_GUARD === */
(function initBrokenImgGuardV50() {
  if (window.__bhV50ImgGuard) return;
  window.__bhV50ImgGuard = true;
  document.addEventListener("error", function (ev) {
    const img = ev.target;
    if (!img || img.tagName !== "IMG") return;
    if (img.dataset.bhFallbackDone) return;
    const card = img.closest("[data-id], .flat-card, .fc");
    const sid = card && (card.dataset.id || card.getAttribute("data-id"));
    let pool = [];
    if (sid && window.__bhById && window.__bhById.get) {
      const s = window.__bhById.get(sid);
      if (s && Array.isArray(s.photos)) pool = s.photos;
    }
    const tried = Number(img.dataset.bhTry || "0");
    const nextUrl = pool.find((u, idx) => idx > tried && u && u !== img.src);
    if (nextUrl) {
      img.dataset.bhTry = String(tried + 1);
      img.src = nextUrl;
      return;
    }
    img.dataset.bhFallbackDone = "1";
    img.style.opacity = "0";
    const parent = img.parentElement;
    if (parent && !parent.querySelector(".bh-img-ph")) {
      parent.classList.add("bh-img-missing");
    }
  }, true);
})();

/* === BH_V60_A11Y_AND_LINKS (debounced & scoped to cards/drawer - zero map-pan overhead) === */
(function initV60A11yAndLinkSafety() {
  if (window.__bhV60A11y) return;
  window.__bhV60A11y = true;
  const polish = (root) => {
    try {
      const scope = root && root.querySelectorAll ? root : document;
      scope.querySelectorAll('a[href^="http"]').forEach((a) => {
        if (!a.getAttribute("target")) a.setAttribute("target", "_blank");
        const rel = (a.getAttribute("rel") || "").toLowerCase();
        if (!rel.includes("noopener") || !rel.includes("noreferrer")) {
          a.setAttribute("rel", "noopener noreferrer");
        if (!a.getAttribute("referrerpolicy")) a.setAttribute("referrerpolicy", "no-referrer");
        }
      });
      scope.querySelectorAll("img").forEach((im) => {
        if (im.getAttribute("alt") && im.getAttribute("alt").trim().length > 1) return;
        const card = im.closest(".fc, #detailSheet, .bh-preview, .leaflet-popup");
        const title = card ? (card.querySelector(".fc-name, .fc-title, h2, h3, .d-title")?.textContent || "").trim() : "";
        const loc = card ? (card.querySelector(".fc-loc, .d-loc, .fc-sub")?.textContent || "").trim() : "";
        const desc = title ? (loc ? `${title}, ${loc}` : `${title} - Mumbai flat`) : "Bombay Homes Mumbai flat photo";
        im.setAttribute("alt", desc.slice(0, 95));
      });
    } catch {}
  };
  let _t = null;
  const schedule = (el) => {
    if (_t) return;
    _t = setTimeout(() => { _t = null; requestAnimationFrame(() => polish(el || document)); }, 80);
  };
  const attach = () => {
    const targets = ["cardList", "detailSheet", "mapPreview"].map((id) => document.getElementById(id)).filter(Boolean);
    if (!targets.length) { polish(document); return; }
    targets.forEach((el) => {
      polish(el);
      new MutationObserver(() => schedule(el)).observe(el, { childList: true, subtree: true });
    });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", attach);
  else attach();
})();

/* === BH_V62_MAP_LASSO: Freehand Map Lasso Area-Select (Desktop + Touch Mobile) === */
(function initMapLassoV62() {
  if (window.__bhV62Lasso) return;
  window.__bhV62Lasso = true;

  let drawing = false;
  let dragging = false;
  let pts = [];
  let polyLayer = null;
  let hintEl = null;

  const getApi = () => (typeof window.__bh === "function" ? window.__bh() : {});

  function showHint(text) {
    const pane = document.getElementById("mapPane");
    if (!pane) return;
    if (!hintEl) {
      hintEl = document.createElement("div");
      hintEl.id = "bhLassoHint";
      hintEl.className = "bh-lasso-hint";
      pane.appendChild(hintEl);
    }
    hintEl.textContent = text;
    hintEl.style.display = text ? "block" : "none";
  }

  function updateBtn() {
    const btn = document.getElementById("mapLassoBtn");
    const api = getApi();
    if (!btn) return;
    const hasLasso = !!(api.st && Array.isArray(api.st.lasso) && api.st.lasso.length >= 3);
    btn.classList.toggle("active", drawing || hasLasso);
    btn.classList.toggle("drawing", drawing);
    if (drawing) {
      btn.textContent = "Cancel draw";
      showHint("Drag on map to circle an area (Esc to cancel)");
    } else if (hasLasso) {
      const cnt = Array.isArray(api.filtered) ? api.filtered.length : 0;
      btn.textContent = "\u2715 Clear area" + (cnt ? " (" + cnt.toLocaleString("en-IN") + ")" : "");
      showHint("");
    } else {
      btn.textContent = "\u270E Draw area";
      showHint("");
    }
  }

  function stopDrawing(map) {
    drawing = false;
    dragging = false;
    if (map) {
      try { map.dragging.enable(); } catch {}
      const c = map.getContainer();
      if (c) c.classList.remove("bh-lasso-cursor");
    }
    updateBtn();
  }

  function clearLasso(silent) {
    const api = getApi();
    const map = api.map;
    if (polyLayer && map) {
      try { map.removeLayer(polyLayer); } catch {}
    }
    polyLayer = null;
    pts = [];
    if (api.st) api.st.lasso = null;
    stopDrawing(map);
    if (!silent && api.renderAll) api.renderAll();
    updateBtn();
  }
  window.__bhClearLasso = clearLasso;

  function renderPolygon(map, closed) {
    if (!map || !window.L) return;
    if (polyLayer) {
      try { map.removeLayer(polyLayer); } catch {}
    }
    if (!pts.length) return;
    polyLayer = closed
      ? window.L.polygon(pts, {
          color: "#1b4332",
          weight: 2.5,
          fillColor: "#2d6a4f",
          fillOpacity: 0.16,
          dashArray: null,
          interactive: false,
        }).addTo(map)
      : window.L.polyline(pts, {
          color: "#c49e5c",
          weight: 3,
          dashArray: "6,4",
          interactive: false,
        }).addTo(map);
  }

  function clientToLatLng(map, clientX, clientY) {
    const rect = map.getContainer().getBoundingClientRect();
    return map.containerPointToLatLng(window.L.point(clientX - rect.left, clientY - rect.top));
  }

  function attach() {
    const api = getApi();
    const map = api.map;
    const btn = document.getElementById("mapLassoBtn");
    if (!map || !btn) {
      setTimeout(attach, 300);
      return;
    }
    if (btn.dataset.bhLassoWired) return;
    btn.dataset.bhLassoWired = "1";

    const container = map.getContainer();

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const curApi = getApi();
      const hasLasso = !!(curApi.st && Array.isArray(curApi.st.lasso) && curApi.st.lasso.length >= 3);
      if (drawing || hasLasso) {
        clearLasso(false);
        return;
      }
      if (curApi.st && curApi.st.mapBounds) {
        curApi.st.mapBounds = false;
        const ab = document.getElementById("mapAreaBtn");
        if (ab) ab.classList.remove("active");
      }
      pts = [];
      if (polyLayer) { try { map.removeLayer(polyLayer); } catch {} polyLayer = null; }
      drawing = true;
      dragging = false;
      try { map.dragging.disable(); } catch {}
      container.classList.add("bh-lasso-cursor");
      updateBtn();
    });

    const onStart = (cx, cy, ev) => {
      if (!drawing) return;
      if (ev && ev.target && ev.target.closest(".map-left-ctl, .map-ctl, .leaflet-control")) return;
      if (ev) { ev.preventDefault(); ev.stopPropagation(); }
      dragging = true;
      const ll = clientToLatLng(map, cx, cy);
      pts = [[ll.lat, ll.lng]];
      renderPolygon(map, false);
    };

    const onMove = (cx, cy, ev) => {
      if (!drawing || !dragging) return;
      if (ev) { ev.preventDefault(); }
      const ll = clientToLatLng(map, cx, cy);
      const prev = pts[pts.length - 1];
      if (!prev || Math.hypot(ll.lat - prev[0], ll.lng - prev[1]) > 0.00025) {
        pts.push([ll.lat, ll.lng]);
        renderPolygon(map, false);
      }
    };

    const onEnd = () => {
      if (!drawing || !dragging) return;
      dragging = false;
      const curApi = getApi();
      if (pts.length < 3) {
        clearLasso(false);
        return;
      }
      let minLa = 999, maxLa = -999, minLn = 999, maxLn = -999;
      for (const p of pts) {
        if (p[0] < minLa) minLa = p[0];
        if (p[0] > maxLa) maxLa = p[0];
        if (p[1] < minLn) minLn = p[1];
        if (p[1] > maxLn) maxLn = p[1];
      }
      if ((maxLa - minLa) < 0.0006 && (maxLn - minLn) < 0.0006) {
        clearLasso(false);
        return;
      }
      renderPolygon(map, true);
      if (curApi.st) {
        curApi.st.lasso = pts.slice();
        curApi.st.page = 36;
      }
      stopDrawing(map);
      if (curApi.renderAll) curApi.renderAll();
      setTimeout(updateBtn, 60);
    };

    container.addEventListener("mousedown", (e) => { if (e.button === 0) onStart(e.clientX, e.clientY, e); }, { passive: false });
    window.addEventListener("mousemove", (e) => onMove(e.clientX, e.clientY, e), { passive: false });
    window.addEventListener("mouseup", onEnd);

    container.addEventListener("touchstart", (e) => {
      if (e.touches && e.touches.length === 1) onStart(e.touches[0].clientX, e.touches[0].clientY, e);
    }, { passive: false });
    window.addEventListener("touchmove", (e) => {
      if (drawing && dragging && e.touches && e.touches.length === 1) onMove(e.touches[0].clientX, e.touches[0].clientY, e);
    }, { passive: false });
    window.addEventListener("touchend", onEnd);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && drawing) clearLasso(false);
    });

    const rs = document.getElementById("resSum");
    if (rs) new MutationObserver(() => { if (!drawing) updateBtn(); }).observe(rs, { childList: true, characterData: true, subtree: true });

    const ab = document.getElementById("activeBar");
    if (ab) {
      ab.addEventListener("click", (e) => {
        const tag = e.target.closest("span, button, .atag");
        if (tag && /Drawn Area/i.test(tag.textContent || "")) clearLasso(false);
      });
    }
    updateBtn();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(attach, 350));
  else setTimeout(attach, 350);
})();

/* === BH_V62C_SS_DISMISS === */
document.addEventListener("pointerdown", (e) => {
  const ss = document.getElementById("searchSuggest");
  if (!ss || ss.style.display === "none") return;
  if (!e.target.closest(".search-wrap, #searchSuggest")) {
    ss.style.display = "none";
    ss.classList.remove("open", "show");
  }
}, true);
