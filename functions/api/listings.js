const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Ingest-Key",
};
const jsonRes = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...CORS } });

const OUTER_CITY_RE = /\b(kalyan|dombivli|dombivali|badlapur|ambernath|ulhasnagar|vasai|virar|nallasopara|nalasopara|naigaon|bhiwandi|boisar|karjat|khopoli|palghar|titwala|shahad|dahanu)\b/i;

function parseBhk(raw) {
  if (raw === undefined || raw === null || raw === "") return null;
  const s = String(raw).trim().toLowerCase();
  if (s.includes("rk") || s.includes("studio")) return 0;
  const f = parseFloat(s);
  if (!Number.isFinite(f) || f < 0 || f > 6.5) return null;
  return Math.round(f * 2) / 2;
}

function normalizeListing(body) {
  const name = String(body.name || "").trim().slice(0, 90);
  const locality = String(body.locality || "Mumbai").trim().slice(0, 50);
  const zone = String(body.zone || "Mumbai").trim().slice(0, 40);
  const mode = body.mode === "buy" ? "buy" : "rent";
  const price = parseInt(body.price_inr || body.price || 0, 10);
  if (!name || !price || price < 5000) return null;
  if (mode === "rent" && price > 600000) return null;
  if (mode === "buy" && price < 1500000) return null;

  const url = body.url && String(body.url).startsWith("http") ? String(body.url).trim().slice(0, 400) : null;
  const chkTxt = `${name} ${url || ""}`;
  const om = chkTxt.replace(/-/g, " ").match(OUTER_CITY_RE);
  if (om && !locality.toLowerCase().includes(om[1].toLowerCase())) return null;

  const bhk = parseBhk(body.bhk);
  const sqft = body.carpet_sqft ? parseInt(body.carpet_sqft, 10) : null;
  const furn = body.furnishing ? String(body.furnishing).slice(0, 24) : null;
  const source = String(body.source || "owner").toLowerCase().slice(0, 24);
  const zb = body.zero_brokerage === false ? 0 : (source === "99acres" || source === "housing" ? (body.zero_brokerage ? 1 : 0) : 1);
  const contact = body.contact ? String(body.contact).trim().slice(0, 80) : null;
  const lat = Number.isFinite(Number(body.lat)) ? Number(body.lat) : null;
  const lng = Number.isFinite(Number(body.lng)) ? Number(body.lng) : null;

  return { name, locality, zone, mode, bhk, price, sqft, furn, zb, contact, url, lat, lng, source };
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestGet({ env }) {
  if (!env.DB) return jsonRes({ listings: [], note: "D1 not bound yet" });
  const now = Math.floor(Date.now() / 1000);
  try {
    const { results } = await env.DB.prepare(
      "SELECT * FROM direct_listings WHERE expires_at > ? ORDER BY created_at DESC LIMIT 500"
    ).bind(now).all();
    return jsonRes({ listings: results || [] });
  } catch (err) {
    return jsonRes({ listings: [], error: err.message }, 500);
  }
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return jsonRes({ error: "D1 database (DB) not bound in Cloudflare Pages" }, 503);
  let raw;
  try { raw = await request.json(); } catch { return jsonRes({ error: "Invalid JSON" }, 400); }

  const isBatch = Array.isArray(raw?.listings);
  const items = isBatch ? raw.listings.slice(0, 60) : [raw];
  const now = Math.floor(Date.now() / 1000);
  const expires = now + 28 * 86400;

  let inserted = 0, updated = 0, skipped = 0;
  let lastId = null;

  try {
    for (const item of items) {
      const rec = normalizeListing(item || {});
      if (!rec) { skipped++; continue; }

      if (rec.url) {
        const existing = await env.DB.prepare(
          "SELECT id FROM direct_listings WHERE url = ? LIMIT 1"
        ).bind(rec.url).first();
        if (existing?.id) {
          await env.DB.prepare(
            "UPDATE direct_listings SET price_inr = ?, bhk = COALESCE(?, bhk), carpet_sqft = COALESCE(?, carpet_sqft), expires_at = ? WHERE id = ?"
          ).bind(rec.price, rec.bhk, rec.sqft, expires, existing.id).run();
          updated++; lastId = existing.id;
          continue;
        }
      }

      const id = "bh-" + now.toString(36) + "-" + Math.random().toString(36).slice(2, 6);
      await env.DB.prepare(
        `INSERT INTO direct_listings (id, name, locality, zone, mode, bhk, price_inr, carpet_sqft, furnishing, zero_brokerage, contact, url, lat, lng, source, created_at, expires_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        id, rec.name, rec.locality, rec.zone, rec.mode, rec.bhk, rec.price, rec.sqft,
        rec.furn, rec.zb, rec.contact, rec.url, rec.lat, rec.lng, rec.source, now, expires
      ).run();
      inserted++; lastId = id;
    }

    if (!isBatch && inserted === 0 && updated === 0) {
      return jsonRes({ error: "Name and valid price required" }, 400);
    }
    return jsonRes({ ok: true, id: lastId, inserted, updated, skipped }, 201);
  } catch (err) {
    return jsonRes({ error: err.message }, 500);
  }
}
