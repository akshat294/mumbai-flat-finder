const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const jsonRes = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...CORS } });

const VALID_REASONS = new Set(["rented", "wrong_pin", "fake_price", "broker_bait", "duplicate"]);

async function ensureTable(db) {
  await db.prepare(
    `CREATE TABLE IF NOT EXISTS listing_flags (
      id TEXT PRIMARY KEY,
      society_id TEXT NOT NULL,
      unit_url TEXT,
      reason TEXT NOT NULL,
      note TEXT,
      created_at INTEGER NOT NULL
    )`
  ).run();
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestGet({ env }) {
  if (!env.DB) return jsonRes({ flags: {} });
  try {
    await ensureTable(env.DB);
    const cutoff = Math.floor(Date.now() / 1000) - 21 * 86400;
    const { results } = await env.DB.prepare(
      `SELECT society_id, unit_url, reason, COUNT(*) as cnt
       FROM listing_flags
       WHERE created_at > ?
       GROUP BY society_id, unit_url, reason`
    ).bind(cutoff).all();

    const byKey = {};
    for (const r of (results || [])) {
      const k = r.unit_url || r.society_id;
      if (!byKey[k]) byKey[k] = { total: 0, reasons: {} };
      byKey[k].total += Number(r.cnt || 1);
      byKey[k].reasons[r.reason] = Number(r.cnt || 1);
    }
    return jsonRes({ flags: byKey });
  } catch (err) {
    return jsonRes({ flags: {}, error: err.message }, 200);
  }
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return jsonRes({ error: "D1 database (DB) not bound" }, 503);
  let body;
  try { body = await request.json(); } catch { return jsonRes({ error: "Invalid JSON" }, 400); }

  const society_id = String(body.society_id || "").trim().slice(0, 80);
  const unit_url = body.unit_url ? String(body.unit_url).trim().slice(0, 400) : null;
  const reason = VALID_REASONS.has(body.reason) ? body.reason : "rented";
  const note = body.note ? String(body.note).trim().slice(0, 180) : null;
  if (!society_id) return jsonRes({ error: "society_id required" }, 400);

  const now = Math.floor(Date.now() / 1000);
  const id = "fl-" + now.toString(36) + "-" + Math.random().toString(36).slice(2, 6);

  try {
    await ensureTable(env.DB);
    await env.DB.prepare(
      `INSERT INTO listing_flags (id, society_id, unit_url, reason, note, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(id, society_id, unit_url, reason, note, now).run();
    return jsonRes({ ok: true, id }, 201);
  } catch (err) {
    return jsonRes({ error: err.message }, 500);
  }
}
