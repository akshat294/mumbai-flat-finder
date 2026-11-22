const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const SUBS = [
  { name: "FlatmatesinMumbai", alwaysHousing: true },
  { name: "MumbaiRealEstate", alwaysHousing: true },
  { name: "mumbai", alwaysHousing: false },
];

const HOUSING_RE = /\b(bhk|1rk|1\s*rk|flatmate|flatmates|roommate|rent|rental|occupancy|brokerage|pg\b|studio|apartment|vacancy|looking for a flat|available for rent|replacement)\b/i;
const LOC_NAMES = [
  "Bandra West", "Bandra East", "Bandra", "Pali Hill", "Khar West", "Khar", "Santacruz West", "Santacruz East", "Santacruz",
  "Vile Parle", "Juhu", "Versova", "Lokhandwala", "Andheri West", "Andheri East", "Andheri", "Jogeshwari",
  "Goregaon West", "Goregaon East", "Goregaon", "Malad West", "Malad East", "Malad", "Kandivali", "Borivali",
  "Colaba", "Cuffe Parade", "Malabar Hill", "Worli", "Lower Parel", "Prabhadevi", "Dadar", "Mahim", "Matunga",
  "Sion", "Byculla", "Parel", "Tardeo", "Wadala", "Powai", "Chandivali", "Ghatkopar", "Vikhroli", "Kanjurmarg",
  "Bhandup", "Mulund", "Chembur", "Kurla", "BKC", "Thane", "Vashi", "Nerul", "Seawoods", "Kharghar", "Belapur", "Airoli", "Navi Mumbai"
];

function extractPrice(txt) {
  const m = txt.match(/(?:\u20B9|rs\.?|inr|rent[:\s]+)\s*([\d,.]+)\s*(cr|crore|l|lac|lakh|k)?/i) ||
            txt.match(/\b(\d{2,3})\s*k\b/i);
  if (!m) return null;
  let val = parseFloat(m[1].replace(/,/g, ""));
  if (!isFinite(val) || val <= 0) return null;
  const u = (m[2] || (m[0].toLowerCase().includes("k") ? "k" : "")).toLowerCase();
  if (u.startsWith("cr")) val *= 1e7;
  else if (u.startsWith("l")) val *= 1e5;
  else if (u === "k") val *= 1e3;
  val = Math.round(val);
  return val >= 5000 ? val : null;
}

function detectAreas(txt) {
  const low = txt.toLowerCase();
  const hit = [];
  for (const l of LOC_NAMES) if (low.includes(l.toLowerCase())) hit.push(l);
  return [...new Set(hit)].slice(0, 3);
}

function detectBhk(txt) {
  if (/\b1\s*rk\b|\bstudio\b/i.test(txt)) return "1 RK";
  const m = txt.match(/\b([1-5](?:\.5)?)\s*[-]?\s*bhk\b/i);
  return m ? `${m[1]} BHK` : null;
}

function detectType(txt) {
  const low = txt.toLowerCase();
  if (/\b(flatmate|roommate|sharing|single occupancy|double occupancy|replacement|male flatmate|female flatmate)\b/i.test(low)) return "Shared / Flatmate";
  if (/\b(looking for|searching for|need a|wanted|anyone know|suggestions|recommend)\b/i.test(low)) return "Seeker";
  if (/\b(no brokerage|zero brokerage|owner|direct)\b/i.test(low)) return "No Brokerage";
  return "Listing";
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestGet(context) {
  const reqUrl = new URL(context.request.url);
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "public, max-age=900",
    ...CORS,
  };

  const cache = caches.default;
  const cacheKey = new Request(reqUrl.origin + "/api/community", { method: "GET" });
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const posts = [];
  const seen = new Set();

  await Promise.all(SUBS.map(async sub => {
    try {
      const r = await fetch(`https://www.reddit.com/r/${sub.name}/new.json?limit=35`, {
        headers: {
          "user-agent": "web:bombayhomes:v17 (Mumbai community housing feed)",
          "accept": "application/json",
        },
      });
      if (!r.ok) return;
      const d = await r.json();
      for (const ch of (d?.data?.children || [])) {
        const p = ch?.data;
        if (!p || p.stickied || p.over_18) continue;
        const title = String(p.title || "").trim();
        const body = String(p.selftext || "").trim();
        const full = `${title} ${body}`;
        if (!sub.alwaysHousing && !HOUSING_RE.test(full)) continue;
        const perm = `https://www.reddit.com${p.permalink}`;
        if (seen.has(perm)) continue;
        seen.add(perm);

        let img = null;
        if (p.preview?.images?.[0]?.source?.url) img = p.preview.images[0].source.url.replace(/&/g, "&");
        else if (p.thumbnail && p.thumbnail.startsWith("http")) img = p.thumbnail;

        posts.push({
          id: p.id,
          source: `r/${sub.name}`,
          title: title.slice(0, 140),
          snippet: body.replace(/\s+/g, " ").slice(0, 220),
          url: perm,
          created: Number(p.created_utc || 0),
          areas: detectAreas(full),
          price: extractPrice(full),
          bhk: detectBhk(full),
          kind: detectType(full),
          img,
          comments: Number(p.num_comments || 0),
        });
      }
    } catch {}
  }));

  posts.sort((a, b) => b.created - a.created);
  const outResp = new Response(JSON.stringify({ posts: posts.slice(0, 80), updated: Math.floor(Date.now() / 1000) }), { status: 200, headers });
  if (posts.length > 0) context.waitUntil(cache.put(cacheKey, outResp.clone()));
  return outResp;
}
