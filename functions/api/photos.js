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
