// Cloudflare Pages Function: Strict SquareYards Image Proxy (fixes Chromium ERR_BLOCKED_BY_ORB)
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

    const upstream = await fetch(parsed.toString(), {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https:" + "//www.squareyards.com/",
        "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/*,*/*;q=0.8",
      },
      cf: { cacheTtl: 86400, cacheEverything: true },
    });

    const ct = (upstream.headers.get("content-type") || "").toLowerCase();
    if (!upstream.ok || !ct.startsWith("image/")) {
      return new Response("Upstream image unavailable", {
        status: 404,
        headers: { "Cache-Control": "public, max-age=300", "Cross-Origin-Resource-Policy": "cross-origin" },
      });
    }

    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": ct,
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Access-Control-Allow-Origin": "*",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response("Proxy error", { status: 502 });
  }
}
