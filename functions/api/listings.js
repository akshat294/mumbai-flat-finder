const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const jsonRes = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...CORS } });

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestGet({ env }) {
  if (!env.DB) return jsonRes({ listings: [], note: "D1 not bound yet" });
  const now = Math.floor(Date.now() / 1000);
  try {
    const { results } = await env.DB.prepare(
      "SELECT * FROM direct_listings WHERE expires_at > ? ORDER BY created_at DESC LIMIT 200"
    ).bind(now).all();
    return jsonRes({ listings: results || [] });
  } catch (err) {
    return jsonRes({ listings: [], error: err.message }, 500);
  }
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return jsonRes({ error: "D1 database (DB) not bound in Cloudflare Pages" }, 503);
  let body;
  try { body = await request.json(); } catch { return jsonRes({ error: "Invalid JSON" }, 400); }

  const name = String(body.name || "").trim().slice(0, 90);
  const locality = String(body.locality || "Mumbai").trim().slice(0, 50);
  const zone = String(body.zone || "Mumbai").trim().slice(0, 40);
  const mode = body.mode === "buy" ? "buy" : "rent";
  const price = parseInt(body.price_inr || body.price || 0, 10);
  if (!name || !price || price < 5000) return jsonRes({ error: "Name and valid price required" }, 400);

  const bhk = body.bhk !== undefined && body.bhk !== "" && body.bhk !== null ? parseInt(body.bhk, 10) : null;
  const sqft = body.carpet_sqft ? parseInt(body.carpet_sqft, 10) : null;
  const furn = body.furnishing ? String(body.furnishing).slice(0, 24) : null;
  const zb = body.zero_brokerage === false ? 0 : 1;
  const contact = body.contact ? String(body.contact).trim().slice(0, 80) : null;
  const url = body.url && String(body.url).startsWith("http") ? String(body.url).trim().slice(0, 400) : null;
  const source = String(body.source || "owner").slice(0, 24);
  const lat = Number.isFinite(Number(body.lat)) ? Number(body.lat) : null;
  const lng = Number.isFinite(Number(body.lng)) ? Number(body.lng) : null;

  const now = Math.floor(Date.now() / 1000);
  const expires = now + 14 * 86400;
  const id = "bh-" + now.toString(36) + "-" + Math.random().toString(36).slice(2, 6);

  try {
    await env.DB.prepare(
      `INSERT INTO direct_listings (id, name, locality, zone, mode, bhk, price_inr, carpet_sqft, furnishing, zero_brokerage, contact, url, lat, lng, source, created_at, expires_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(id, name, locality, zone, mode, bhk, price, sqft, furn, zb, contact, url, lat, lng, source, now, expires).run();
    return jsonRes({ ok: true, id }, 201);
  } catch (err) {
    return jsonRes({ error: err.message }, 500);
  }
}
