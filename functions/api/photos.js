const ALLOWED_HOSTS = new Set([
  "www.magicbricks.com", "magicbricks.com",
  "www.nobroker.in", "nobroker.in",
  "www.squareyards.com", "squareyards.com",
  "www.makaan.com", "makaan.com",
  "www.commonfloor.com", "commonfloor.com",
  "www.99acres.com", "99acres.com",
  "housing.com", "www.housing.com",
]);

const BAD_IMG = /(floor[-_]?plan|master[-_]?plan|site[-_]?plan|unit[-_]?plan|location[-_]?map|3d[-_]?plan|3d[-_]?render|layout|blueprint|brochure|elevation|under_screening|fbshare|static\.99acres\.com|assets\.nobroker\.in|logo|icon|avatar|placeholder|default[-_]?img|spinner|loader|blank|pixel|badge|sprite|banner|ads|verified|watermark|qrcode|playstore|appstore|whatsapp|facebook|twitter|instagram|youtube|no[-_]?image|no[-_]?photo|agent|broker|owner[-_]?img|profile|user[-_]?pic|1x1|\.svg(?:\?|$)|\.gif(?:\?|$))/i;
const BAD_CAPTION = /(floor\s*plan|master\s*plan|site\s*plan|unit\s*plan|location\s*map|layout|brochure|blueprint|3d|elevation|amenity\s*map|route\s*map)/i;
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

function cleanUrl(raw) {
  if (!raw || typeof raw !== "string") return null;
  let u = raw.trim().replace(/\\u002F/gi, "/").replace(/\\\//g, "/").replace(/&/g, "&");
  if (u.startsWith("//")) u = "https:" + u;
  if (!/^https?:\/\//i.test(u)) return null;
  if (u.length < 24 || u.length > 520) return null;
  if (BAD_IMG.test(u)) return null;
  return u;
}

function imgMeta(u) {
  const clean = u.split("?")[0];
  const m99 = clean.match(/imagecdn\.99acres\.com\/.*\/(\d+)([A-Z])-\d+\./i);
  if (m99) {
    const code = m99[2].toUpperCase();
    const rank = code === "O" ? 5 : (code === "L" ? 4 : (code === "M" ? 3 : (code === "F" ? 2 : 1)));
    return { key: "99:" + m99[1], rank };
  }
  if (clean.includes("images.nobroker.in/images/")) {
    const k = clean.replace(/_(?:thumbnail|small|medium|large|original|enhance_large|enhance_medium)(?=\.[a-z]+$)/i, "").toLowerCase();
    const rank = /_original\./i.test(clean) ? 4 : (/_large\./i.test(clean) ? 3 : (/_medium\./i.test(clean) ? 2 : 1));
    return { key: "nb:" + k, rank };
  }
  if (clean.includes("housingcdn.com") || clean.includes("n7net.in")) {
    const mH = clean.match(/\/([a-f0-9]{16,40})\/v\d+\/([^/]+)\//i);
    if (mH) {
      const varName = mH[2].toLowerCase();
      const rank = varName === "fs" ? 4 : (varName.includes("large") ? 3 : (varName.includes("medium") ? 2 : 1));
      return { key: "hs:" + mH[1].toLowerCase(), rank };
    }
  }
  const dk = clean
    .replace(/\/(thumb|medium|small|large|original|cropped|resized|fs|fs_medium|version)\//gi, "/")
    .replace(/[_\-]\d+x\d+(?=\.[a-z]+$)/i, "")
    .replace(/[_\-](?:small|medium|large|thumb|thumbnail|original)(?=\.[a-z]+$)/i, "")
    .toLowerCase();
  return { key: dk, rank: 2 };
}

function upgradeRes(u) {
  if (u.includes("housingcdn.com/") || u.includes("housing-images.n7net.in/")) {
    return u.replace(/\/v(\d+)\/(?:version|fs_medium|medium|small|thumb)\//i, "/v$1/fs/");
  }
  if (u.includes("images.nobroker.in/images/")) {
    return u.replace(/_thumbnail\./i, "_large.").replace(/_small\./i, "_large.");
  }
  return u;
}

function extractMedia(html, host, targetUrl) {
  const byKey = new Map();
  const order = [];
  const add = (raw, boost = 0) => {
    const u = cleanUrl(raw);
    if (!u) return;
    const up = upgradeRes(u);
    const { key, rank } = imgMeta(up);
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, { url: up, rank: rank + boost });
      order.push(key);
    } else if (rank + boost > prev.rank) {
      byKey.set(key, { url: up, rank: rank + boost });
    }
  };

  const unesc = html.replace(/\\u002F/gi, "/").replace(/\\\//g, "/");

  if (host.includes("magicbricks")) {
    for (const m of unesc.matchAll(/https?:\/\/img\.staticmb\.com\/mbphoto\/property\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0], 1);
    for (const m of unesc.matchAll(/https?:\/\/img\.staticmb\.com\/mbimages\/project\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0], 0);
  }
  if (host.includes("nobroker")) {
    for (const m of unesc.matchAll(/https?:\/\/images\.nobroker\.in\/images\/[a-f0-9]{16,32}\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0], 1);
    const idM = targetUrl.match(/([a-f0-9]{24,32})/i) || unesc.match(/"propertyId"\s*:\s*"([a-f0-9]{20,32})"/i) || unesc.match(/"id"\s*:\s*"([a-f0-9]{24,32})"/i);
    if (idM) {
      const pid = idM[1];
      for (const m of unesc.matchAll(/"(?:original|large|medium)"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp))"/gi)) {
        const fn = m[1];
        add(fn.startsWith("http") ? fn : ("https:" + "//images.nobroker.in/images/" + pid + "/" + fn), 1);
      }
    }
  }
  if (host.includes("squareyards")) {
    for (const m of unesc.matchAll(/https?:\/\/(?:img|static)\.squareyards\.com\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) {
      if (/\/secondaryPortal\/|\/project\/|\/property\/|\/cdn-cgi\//i.test(m[0])) add(m[0]);
    }
  }
  if (host.includes("makaan") || host.includes("housing")) {
    for (const m of unesc.matchAll(/\{[^{}]{0,400}"(?:src|url|imageUrl)"\s*:\s*"(https?:\/\/(?:is1-\d+\.housingcdn\.com|housing-images\.n7net\.in|im\.proptiger\.com|c\.housingcdn\.com)\/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"[^{}]{0,300}\}/gi)) {
      if (BAD_CAPTION.test(m[0])) continue;
      add(m[1], 2);
    }
    for (const m of unesc.matchAll(/https?:\/\/(?:is1-\d+\.housingcdn\.com|housing-images\.n7net\.in|im\.proptiger\.com)\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) {
      add(m[0], 0);
    }
  }
  if (host.includes("commonfloor")) {
    for (const m of unesc.matchAll(/https?:\/\/[^\s"'<>\\]*commonfloor\.com\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0]);
  }
  if (host.includes("99acres")) {
    for (const m of unesc.matchAll(/https?:\/\/(?:imagecdn\.99acres\.com|mediacdn\.99acres\.com)\/[^\s"'<>\\]+\.(?:jpg|jpeg|png|webp)/gi)) add(m[0], 1);
  }

  for (const m of unesc.matchAll(/"(?:image|imageUrl|photoUrl|originalUrl)"\s*:\s*"(https?:\/\/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"/gi)) add(m[1]);
  for (const m of html.matchAll(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/gi)) add(m[1]);

  const videos = [];
  const seenVid = new Set();
  const addVid = (raw, kind) => {
    if (!raw || typeof raw !== "string") return;
    const u = raw.trim().replace(/&/g, "&");
    if (!u.startsWith("http") || u.length > 520) return;
    if (/(logo|intro|promo|ad_|brand|banner|spinner)/i.test(u)) return;
    const k = u.split("?")[0].toLowerCase();
    if (seenVid.has(k)) return;
    seenVid.add(k);
    videos.push({ url: u, kind });
  };

  for (const m of unesc.matchAll(/https?:\/\/[^\s"'<>\\]+?\.(?:mp4|webm|m3u8)(?:\?[^\s"'<>\\]*)?/gi)) {
    if (/(99acres|housingcdn|n7net|nobroker|staticmb|squareyards|cloudfront|amazonaws|vimeo|akamaized)/i.test(m[0])) {
      addVid(m[0], "video");
    }
  }
  for (const m of unesc.matchAll(/https?:\/\/(?:www\.)?(?:youtube\.com\/(?:embed|watch\?v=)|youtu\.be\/)([A-Za-z0-9_-]{11})/gi)) {
    addVid("https:" + "//www.youtube.com/embed/" + m[1], "youtube");
  }

  const photos = order.map(k => byKey.get(k).url).slice(0, 14);
  return { photos, videos: videos.slice(0, 4) };
}

export async function onRequestGet(context) {
  const reqUrl = new URL(context.request.url);
  const target = reqUrl.searchParams.get("url") || "";
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "public, max-age=43200",
    "access-control-allow-origin": "*",
  };

  let parsed;
  try { parsed = new URL(target); }
  catch { return new Response(JSON.stringify({ photos: [], videos: [], error: "invalid url" }), { status: 400, headers }); }

  if (!ALLOWED_HOSTS.has(parsed.hostname.toLowerCase())) {
    return new Response(JSON.stringify({ photos: [], videos: [], error: "host not allowed" }), { status: 403, headers });
  }

  const cache = caches.default;
  const cacheKey = new Request(reqUrl.toString() + "&v=40", { method: "GET" });
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
    if (!resp.ok) return new Response(JSON.stringify({ photos: [], videos: [], status: resp.status }), { status: 200, headers });
    const html = await resp.text();
    const { photos, videos } = extractMedia(html, parsed.hostname.toLowerCase(), parsed.toString());
    const outResp = new Response(JSON.stringify({ photos, videos }), { status: 200, headers });
    if (photos.length > 0 || videos.length > 0) context.waitUntil(cache.put(cacheKey, outResp.clone()));
    return outResp;
  } catch (err) {
    return new Response(JSON.stringify({ photos: [], videos: [], error: String(err) }), { status: 200, headers });
  }
}
