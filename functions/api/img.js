// Cloudflare Pages Function: Strict SquareYards Image Proxy with Buffered Edge Cache (v63)
const ALLOWED_HOSTS = new Set(["static.squareyards.com"]);

export async function onRequestGet({ request }) {
  try {
    const reqUrl = new URL(request.url);
    const target = reqUrl.searchParams.get("u") || "";
    if (!target) return new Response("Missing u", { status: 400 });

    let parsed;
    try {
      parsed = new URL(target);
    } catch {
      return new Response("Invalid URL", { status: 400 });
    }
    if (parsed.protocol !== "https:" || !ALLOWED_HOSTS.has(parsed.hostname)) {
      return new Response("Host not allowed", { status: 403 });
    }

    const cache = typeof caches !== "undefined" ? caches.default : null;
    const cacheKey = new Request(reqUrl.origin + "/__cache/img?u=" + encodeURIComponent(parsed.toString()), { method: "GET" });
    if (cache) {
      const hit = await cache.match(cacheKey);
      if (hit) {
        const h = new Headers(hit.headers);
        h.set("X-Edge-Cache", "HIT");
        return new Response(hit.body, { status: hit.status, headers: h });
      }
    }

    const upstream = await fetch(parsed.toString(), {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https:" + "//www.squareyards.com/",
        "Accept": "image/webp,image/jpeg,image/png,image/*;q=0.8",
      },
      cf: { cacheTtl: 604800, cacheEverything: true },
    });

    const ct = (upstream.headers.get("content-type") || "").toLowerCase();
    if (!upstream.ok || !ct.startsWith("image/")) {
      return new Response("Upstream image unavailable", {
        status: 404,
        headers: { "Cache-Control": "public, max-age=300", "Cross-Origin-Resource-Policy": "cross-origin" },
      });
    }

    const bytes = await upstream.arrayBuffer();
    const headers = {
      "Content-Type": ct,
      "Cache-Control": "public, max-age=604800, immutable",
      "Cross-Origin-Resource-Policy": "cross-origin",
      "Access-Control-Allow-Origin": "*",
      "X-Content-Type-Options": "nosniff",
      "X-Edge-Cache": "MISS",
    };
    if (cache) {
      try { await cache.put(cacheKey, new Response(bytes.slice(0), { status: 200, headers })); } catch {}
    }
    return new Response(bytes, { status: 200, headers });
  } catch {
    return new Response("Proxy error", { status: 502 });
  }
}
