const VALID_REASONS = new Set(["rented", "wrong_pin", "fake_price", "broker_bait", "duplicate"]);

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allowed =
    !origin ||
    origin === "https://bombayhomes.pages.dev" ||
    /^https:\/\/[a-z0-9-]+\.bombayhomes\.pages\.dev$/i.test(origin) ||
    /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin);
  return {
    "Access-Control-Allow-Origin": allowed ? (origin || "https://bombayhomes.pages.dev") : "https://bombayhomes.pages.dev",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
    "X-Content-Type-Options": "nosniff",
  };
}

const jsonRes = (request, data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(request), ...extra },
  });

async function sha256Hex(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return [...new Uint8Array(buf)].slice(0, 12).map(b => b.toString(16).padStart(2, "0")).join("");
}

function cleanHttpUrl(raw) {
  if (!raw) return null;
  try {
    const u = new URL(String(raw).trim());
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    return u.toString().slice(0, 400);
  } catch {
    return null;
  }
}

async function ensureTable(db) {
  await db.prepare(
    `CREATE TABLE IF NOT EXISTS listing_flags (
      id TEXT PRIMARY KEY,
      society_id TEXT NOT NULL,
      unit_url TEXT,
      reason TEXT NOT NULL,
      note TEXT,
      ip_hash TEXT,
      created_at INTEGER NOT NULL
    )`
  ).run();
  try { await db.prepare("ALTER TABLE listing_flags ADD COLUMN ip_hash TEXT").run(); } catch {}
}

export async function onRequestOptions({ request }) {
  return new Response(null, { status: 204, headers: corsHeaders(request) });
}

export async function onRequestGet({ request, env }) {
  if (!env.DB) return jsonRes(request, { flags: {} }, 200, { "Cache-Control": "public, max-age=60" });
  try {
    await ensureTable(env.DB);
    const cutoff = Math.floor(Date.now() / 1000) - 21 * 86400;
    const { results } = await env.DB.prepare(
      `SELECT society_id, unit_url, reason, COUNT(DISTINCT COALESCE(ip_hash, id)) as cnt
       FROM listing_flags
       WHERE created_at > ?
       GROUP BY society_id, unit_url, reason`
    ).bind(cutoff).all();

    const byKey = {};
    for (const r of (results || [])) {
      const k = r.unit_url || r.society_id;
      if (!byKey[k]) byKey[k] = { total: 0, reasons: {} };
      const c = Number(r.cnt || 1);
      byKey[k].total += c;
      byKey[k].reasons[r.reason] = c;
    }
    return jsonRes(request, { flags: byKey }, 200, { "Cache-Control": "public, max-age=60" });
  } catch {
    return jsonRes(request, { flags: {} }, 200);
  }
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return jsonRes(request, { error: "Database not bound" }, 503);

  const origin = request.headers.get("Origin") || "";
  if (origin && !/^https:\/\/([a-z0-9-]+\.)?bombayhomes\.pages\.dev$/i.test(origin) && !/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)) {
    return jsonRes(request, { error: "Forbidden origin" }, 403);
  }

  let body;
  try { body = await request.json(); } catch { return jsonRes(request, { error: "Invalid JSON" }, 400); }

  const society_id = String(body.society_id || "").replace(/[^\w.-]/g, "").slice(0, 80);
  const unit_url = cleanHttpUrl(body.unit_url);
  const reason = VALID_REASONS.has(body.reason) ? body.reason : "rented";
  const note = body.note ? String(body.note).replace(/[<>]/g, "").trim().slice(0, 180) : null;
  if (!society_id) return jsonRes(request, { error: "society_id required" }, 400);

  const now = Math.floor(Date.now() / 1000);
  const ip = request.headers.get("CF-Connecting-IP") || "anon";
  const ip_hash = await sha256Hex("bh-flag:" + ip);

  try {
    await ensureTable(env.DB);
    const rl = await env.DB.prepare(
      "SELECT COUNT(*) as c FROM listing_flags WHERE ip_hash = ? AND created_at > ?"
    ).bind(ip_hash, now - 3600).first();
    if ((rl?.c || 0) >= 15) return jsonRes(request, { error: "Rate limit exceeded" }, 429);

    const dup = await env.DB.prepare(
      "SELECT id FROM listing_flags WHERE ip_hash = ? AND society_id = ? AND created_at > ? LIMIT 1"
    ).bind(ip_hash, society_id, now - 86400).first();
    if (dup) return jsonRes(request, { ok: true, id: dup.id, deduped: true }, 200);

    const id = "fl-" + now.toString(36) + "-" + Math.random().toString(36).slice(2, 6);
    await env.DB.prepare(
      `INSERT INTO listing_flags (id, society_id, unit_url, reason, note, ip_hash, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).bind(id, society_id, unit_url, reason, note, ip_hash, now).run();
    return jsonRes(request, { ok: true, id }, 201);
  } catch {
    return jsonRes(request, { error: "Failed to record flag" }, 500);
  }
}
