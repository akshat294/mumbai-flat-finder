// Cloudflare Pages Function: POST /api/ask
// AI Concierge for BombayHomes ("Ask the Map")
// Engine priority:
//   1. GEMINI_API_KEY (optional Cloudflare Pages env secret -> Gemini 2.5 Flash)
//   2. Cloudflare Workers AI binding (env.AI via wrangler.toml [ai] -> Llama 3.1 8B Instruct)
//   3. Built-in Mumbai real-estate fallback (always succeeds, 0 external calls)

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const prod = "https:" + "//bombayhomes.pages.dev";
  const allowed =
    !origin ||
    origin === prod ||
    /^https:\/\/([a-z0-9-]+\.)?(bombayhomes|thikana[a-z0-9-]*)\.pages\.dev$/i.test(origin) || /^https:\/\/(www\.)?thikana\.(in|com|homes)$/i.test(origin) ||
    /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin);
  return {
    "Access-Control-Allow-Origin": allowed ? (origin || prod) : prod,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
    "X-Content-Type-Options": "nosniff",
  };
}

const jsonRes = (request, data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(request) },
  });

export async function onRequestOptions({ request }) {
  return new Response(null, { status: 204, headers: corsHeaders(request) });
}

function extractJsonObject(rawText) {
  if (!rawText) return null;
  if (typeof rawText === "object") return rawText;
  const s = String(rawText).trim();
  const fenced = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const cand = fenced ? fenced[1].trim() : s;
  const i0 = cand.indexOf("{");
  const i1 = cand.lastIndexOf("}");
  if (i0 === -1 || i1 <= i0) return null;
  try {
    return JSON.parse(cand.slice(i0, i1 + 1));
  } catch {
    return null;
  }
}

const GEMINI_MODELS = ["gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"];

async function callGemini(apiKey, systemPrompt, userPrompt, expectJson) {
  let lastErr = "no_models";
  for (const model of GEMINI_MODELS) {
    const endpoint =
      "https:" +
      "//generativelanguage.googleapis.com/v1beta/models/" +
      model +
      ":generateContent?key=" +
      encodeURIComponent(apiKey);
    const body = {
      systemInstruction: { parts: [{ text: systemPrompt }] },
      contents: [{ role: "user", parts: [{ text: userPrompt }] }],
      generationConfig: {
        temperature: expectJson ? 0.1 : 0.35,
        maxOutputTokens: expectJson ? 380 : 280,
        ...(expectJson ? { responseMimeType: "application/json" } : {}),
      },
    };
    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const et = await r.text().catch(() => "");
      lastErr = model + " HTTP " + r.status + " " + et.slice(0, 80);
      if (r.status === 404 || r.status === 400) continue;
      throw new Error(lastErr);
    }
    const d = await r.json();
    const txt = d?.candidates?.[0]?.content?.parts?.[0]?.text || "";
    if (txt) return txt;
    lastErr = model + " empty";
  }
  throw new Error(lastErr);
}

function localParseQuery(query, knownLocalities, currentMode) {
  const q = String(query || "").toLowerCase();
  const out = {};
  if (/\b(buy|purchase|sale|resale|cr|crore)\b/.test(q)) out.mode = "buy";
  else if (/\b(rent|lease|pg|flatmate|sharing|\/mo)\b/.test(q)) out.mode = "rent";
  else if (currentMode === "buy" || currentMode === "rent") out.mode = currentMode;

  const bhks = [];
  if (/\b(1\s*rk|studio)\b/.test(q)) bhks.push(0);
  for (const m of q.matchAll(/\b([1-4])\s*\+?\s*bhk\b/g)) bhks.push(Number(m[1]));
  if (bhks.length) out.bhks = [...new Set(bhks)];

  const parseAmt = (numStr, unit) => {
    let n = parseFloat(numStr);
    if (!Number.isFinite(n)) return 0;
    const u = (unit || "").toLowerCase();
    if (u.startsWith("cr")) n *= 1e7;
    else if (u === "l" || u.startsWith("lac") || u.startsWith("lakh")) n *= 1e5;
    else if (u === "k") n *= 1e3;
    else if (n < 500) n *= (out.mode === "buy" ? 1e5 : 1e3);
    return Math.round(n);
  };
  const maxM = q.match(/(?:under|below|max|upto|up to|within|less than|<|<=)\s*(?:rs\.?|inr|\u20b9)?\s*(\d+(?:\.\d+)?)\s*(k|l|lac|lakh|cr|crore)?\b/);
  if (maxM) { const v = parseAmt(maxM[1], maxM[2]); if (v >= 5000) out.maxPrice = v; }
  const minM = q.match(/(?:above|over|min|at least|more than|>|>=)\s*(?:rs\.?|inr|\u20b9)?\s*(\d+(?:\.\d+)?)\s*(k|l|lac|lakh|cr|crore)?\b/);
  if (minM) { const v = parseAmt(minM[1], minM[2]); if (v >= 5000) out.minPrice = v; }

  const locs = [];
  for (const loc of (knownLocalities || [])) {
    const ll = String(loc || "").toLowerCase();
    if (ll.length >= 3 && q.includes(ll) && !locs.includes(loc)) locs.push(loc);
    if (locs.length >= 5) break;
  }
  if (locs.length) out.localities = locs;

  if (/\b(zero\s*brok|no\s*brok|direct\s*owner|owner\s*only)\b/.test(q)) out.zero = true;
  if (/\b(flatmate|sharing|pg|shared)\b/.test(q)) out.lister = "shared";
  else if (/\bowner\b/.test(q)) out.lister = "owner";
  if (/\bsemi[\s-]*furn/.test(q)) out.furn = "Semi-Furnished";
  else if (/\bunfurn/.test(q)) out.furn = "Unfurnished";
  else if (/\bfurnish/.test(q)) out.furn = "Furnished";
  if (/\b(sunlit|bright|modern|airy|good interior)\b/.test(q)) out.brightOnly = true;
  if (/\bbalcony\b/.test(q)) out.balcony = true;
  if (/\bsea\s*view\b/.test(q)) out.seaview = true;
  if (/\bterrace\b/.test(q)) out.terrace = true;
  if (/\b(flood\s*safe|monsoon\s*safe|low\s*flood)\b/.test(q)) out.floodSafe = true;
  if (/\brera\b/.test(q)) out.reraOnly = true;
  if (/\b(near\s*metro|walk\s*to\s*metro|aqua\s*line)\b/.test(q)) out.maxMetroWalk = 15;
  if (/\bbkc\b/.test(q)) out.hub = "bkc";
  if (/\b(cheapest|lowest|budget)\b/.test(q)) out.sort = "p_asc";
  else if (/\b(best\s*deal|great\s*value|bargain)\b/.test(q)) out.sort = "deal";
  return out;
}


async function callWorkersAI(aiBinding, systemPrompt, userPrompt, expectJson) {
  const res = await aiBinding.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
    ],
    temperature: expectJson ? 0.1 : 0.35,
    max_tokens: expectJson ? 360 : 300,
  });
  const txt = typeof res === "string" ? res : (res?.response || res?.result?.response || "");
  if (!txt) throw new Error("Workers AI empty response");
  return txt;
}

async function runLLM(env, systemPrompt, userPrompt, expectJson) {
  let diag = "no_key";
  const gemKey = (env?.GEMINI_API_KEY || "").trim();
  if (gemKey) {
    try {
      const txt = await callGemini(gemKey, systemPrompt, userPrompt, expectJson);
      return { engine: "gemini", text: txt, diag: "ok" };
    } catch (e) {
      diag = String(e?.message || e).slice(0, 140);
      console.error("[ask] Gemini error:", diag);
    }
  }
  if (env?.AI && typeof env.AI.run === "function") {
    try {
      const txt = await callWorkersAI(env.AI, systemPrompt, userPrompt, expectJson);
      return { engine: "workers-ai", text: txt };
    } catch (e) {
      console.error("[ask] Workers AI error:", e?.message || e);
    }
  }
  return { engine: "local-nlp", text: "", diag };
}

function sanitizeParsedFilters(raw, knownLocalities) {
  const out = {};
  if (!raw || typeof raw !== "object") return out;

  if (raw.mode === "rent" || raw.mode === "buy") out.mode = raw.mode;
  if (Array.isArray(raw.bhks)) {
    const cleanB = [...new Set(raw.bhks.map(Number).filter(n => Number.isFinite(n) && n >= 0 && n <= 4))];
    if (cleanB.length) out.bhks = cleanB;
  }
  if (Number.isFinite(Number(raw.minPrice)) && Number(raw.minPrice) >= 5000) out.minPrice = Math.round(Number(raw.minPrice));
  if (Number.isFinite(Number(raw.maxPrice)) && Number(raw.maxPrice) >= 5000) out.maxPrice = Math.round(Number(raw.maxPrice));

  if (Array.isArray(raw.localities) && raw.localities.length) {
    const knownMap = new Map((knownLocalities || []).map(l => [String(l).toLowerCase(), String(l)]));
    const matched = [];
    for (const loc of raw.localities) {
      const s = String(loc || "").trim();
      if (!s) continue;
      const exact = knownMap.get(s.toLowerCase());
      if (exact && !matched.includes(exact)) {
        matched.push(exact);
      } else {
        for (const [kl, orig] of knownMap.entries()) {
          if ((kl.includes(s.toLowerCase()) || s.toLowerCase().includes(kl)) && !matched.includes(orig)) {
            matched.push(orig);
            break;
          }
        }
      }
      if (matched.length >= 5) break;
    }
    if (matched.length) out.localities = matched;
  }

  for (const bk of ["zero", "balcony", "seaview", "terrace", "drop", "floodSafe", "brightOnly", "reraOnly"]) {
    if (raw[bk] === true) out[bk] = true;
  }
  if (["owner", "shared", "broker"].includes(raw.lister)) out.lister = raw.lister;
  if (["Furnished", "Semi-Furnished", "Unfurnished"].includes(raw.furn)) out.furn = raw.furn;
  if (Number.isFinite(Number(raw.maxMetroWalk)) && Number(raw.maxMetroWalk) > 0 && Number(raw.maxMetroWalk) <= 45) {
    out.maxMetroWalk = Math.round(Number(raw.maxMetroWalk));
  }
  if (["bkc", "lower_parel", "andheri_seepz", "powai", "goregaon_nesco", "nariman_point"].includes(raw.hub)) {
    out.hub = raw.hub;
  }
  if (Number.isFinite(Number(raw.maxHubMin)) && Number(raw.maxHubMin) >= 5 && Number(raw.maxHubMin) <= 90) {
    out.maxHubMin = Math.round(Number(raw.maxHubMin));
  }
  if (["rec", "p_asc", "p_desc", "deal", "metro", "rate"].includes(raw.sort)) out.sort = raw.sort;
  if (typeof raw.keywords === "string" && raw.keywords.trim().length >= 2 && raw.keywords.trim().length <= 40) {
    out.keywords = raw.keywords.trim();
  }
  return out;
}

function buildFallbackSummary(query, totalBuildings, totalFlats, topMatches, mode) {
  if (!topMatches || !topMatches.length) {
    return "No exact matches in the live Mumbai registry for that combination. Try broadening the budget, adding adjacent localities, or relaxing Bright & Modern / Zero Brokerage.";
  }
  const fmtP = (v) => {
    if (!v) return "On request";
    if (mode === "buy") return v >= 1e7 ? ("\u20b9" + (v / 1e7).toFixed(2) + " Cr") : ("\u20b9" + (v / 1e5).toFixed(1) + " L");
    return v >= 1e5 ? ("\u20b9" + (v / 1e5).toFixed(2) + "L/mo") : ("\u20b9" + Math.round(v / 1000) + "k/mo");
  };
  const top3 = topMatches.slice(0, 3).map(m => {
    const bits = [fmtP(m.p)];
    if (m.metroWalk) bits.push(m.metroWalk + "m to metro");
    if (m.zb) bits.push("Zero Brokerage");
    if (m.vs >= 76 && !m.vr) bits.push("Sunlit");
    return `${m.name} (${m.locality}: ${bits.join(", ")})`;
  });
  return `Matched ${totalFlats.toLocaleString("en-IN")} live flats across ${totalBuildings.toLocaleString("en-IN")} buildings. Standout picks: ${top3.join(" | ")}. Click any society chip below to jump straight to it on the map.`;
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonRes(request, { ok: false, error: "Invalid JSON body" }, 400);
  }

  const action = String(body?.action || "parse").trim().toLowerCase();
  const query = String(body?.query || "").trim().slice(0, 260);
  if (!query) return jsonRes(request, { ok: false, error: "Empty query" }, 400);

  if (action === "parse") {
    const knownLocalities = Array.isArray(body?.knownLocalities) ? body.knownLocalities.slice(0, 120) : [];
    const currentMode = body?.currentMode === "buy" ? "buy" : "rent";

    const sysPrompt =
      "You are the Mumbai real-estate query parser for BombayHomes. " +
      "Convert the user's natural-language flat search into a STRICT JSON object with ONLY the keys that apply. " +
      "Valid keys: " +
      'mode ("rent"|"buy"), bhks (array of ints: 0=1RK/Studio, 1=1BHK, 2=2BHK, 3=3BHK, 4=4+BHK), ' +
      "minPrice (INR int), maxPrice (INR int; 80k=80000, 1.2L=120000, 3cr=30000000), " +
      "localities (array of up to 5 exact names chosen from the provided Known Localities list), " +
      "zero (boolean, true for no broker/owner/direct), lister ('owner'|'shared'|'broker'; use 'shared' for flatmate/sharing/PG), " +
      "furn ('Furnished'|'Semi-Furnished'|'Unfurnished'), balcony (boolean), seaview (boolean), terrace (boolean), " +
      "drop (boolean, price drop/discount), floodSafe (boolean, low flood risk/monsoon safe), " +
      "brightOnly (boolean, sunlit/bright/modern/good interiors/no 3D renders), reraOnly (boolean, MahaRERA verified), " +
      "maxMetroWalk (int minutes 5-30 when near metro/Aqua Line mentioned), " +
      "hub ('bkc'|'lower_parel'|'andheri_seepz'|'powai'|'goregaon_nesco'|'nariman_point'), maxHubMin (int minutes), " +
      "sort ('rec'|'p_asc'|'p_desc'|'deal'|'metro'|'rate'), keywords (optional specific society name ONLY if user named a building). " +
      "Mumbai shortcuts: SoBo -> Worli, Lower Parel, Prabhadevi, Colaba, Malabar Hill; " +
      "near BKC -> Bandra East, Bandra West, Santacruz East, Chembur + hub='bkc'; " +
      "Aqua Line -> Worli, Lower Parel, Dadar West, Bandra East, Santacruz East + maxMetroWalk=15; " +
      "cheapest/budget -> sort='p_asc'; best deal/value -> sort='deal'. " +
      "Output ONLY valid JSON, no prose or markdown.";

    const userPrompt =
      `Current mode: ${currentMode}\n` +
      `Known Localities: ${knownLocalities.join(", ")}\n` +
      `User query: "${query}"`;

    const llm = await runLLM(env, sysPrompt, userPrompt, true);
    const rawParsed = extractJsonObject(llm.text) || localParseQuery(query, knownLocalities, currentMode);
    const parsed = sanitizeParsedFilters(rawParsed, knownLocalities);
    return jsonRes(request, { ok: true, engine: llm.engine, diag: llm.diag || "", filters: parsed });
  }

  if (action === "summarize") {
    const mode = body?.mode === "buy" ? "buy" : "rent";
    const totalBuildings = Number(body?.totalBuildings || 0);
    const totalFlats = Number(body?.totalFlats || 0);
    const appliedLabels = Array.isArray(body?.appliedLabels) ? body.appliedLabels.slice(0, 12) : [];
    const topMatches = Array.isArray(body?.topMatches) ? body.topMatches.slice(0, 12) : [];

    if (!topMatches.length) {
      return jsonRes(request, {
        ok: true,
        engine: "local-nlp",
        summary: buildFallbackSummary(query, totalBuildings, totalFlats, topMatches, mode),
      });
    }

    const sysPrompt =
      "You are BombayHomes' grounded Mumbai flat-finder assistant. " +
      "Write a crisp, helpful 2 to 3 sentence answer summarizing the BEST matches from the REAL registry data provided below. " +
      "STRICT RULES: " +
      "1) ONLY mention societies, prices, localities, walk times, and tags that appear verbatim in Top Matches. NEVER invent buildings or numbers. " +
      "2) Highlight 2-3 standout societies by exact name and why they fit (price in INR k/L/Cr, metro walk time, zero brokerage, sunlit vibe, price drop, or RERA). " +
      "3) Keep it under 75 words, plain natural text (no markdown headers or bullet lists).";

    const compactMatches = topMatches.map((m, i) => ({
      rank: i + 1,
      name: m.name,
      locality: m.locality,
      price_inr: m.p,
      bhks: m.bhks,
      flats: m.units,
      zero_brokerage: !!m.zb,
      sunlit_vibe_score: m.vs,
      is_3d_render: !!m.vr,
      metro: m.metro || null,
      metro_walk_min: m.metroWalk || null,
      flood_risk: m.flood || null,
      price_drop: !!m.drop,
      rera: !!m.rera,
      google_rating: m.rating || null,
    }));

    const userPrompt =
      `User asked: "${query}"\n` +
      `Mode: ${mode} | Applied filters: ${appliedLabels.join(", ") || "All"}\n` +
      `Total live matches in Mumbai registry: ${totalFlats} flats across ${totalBuildings} buildings\n` +
      `Top Matches JSON:\n${JSON.stringify(compactMatches)}`;

    const llm = await runLLM(env, sysPrompt, userPrompt, false);
    const cleanText = (llm.text || "").replace(/\s+/g, " ").trim();
    return jsonRes(request, {
      ok: true,
      engine: cleanText ? llm.engine : "local-nlp",
      summary: cleanText || buildFallbackSummary(query, totalBuildings, totalFlats, topMatches, mode),
    });
  }

  return jsonRes(request, { ok: false, error: "Unknown action" }, 400);
}
