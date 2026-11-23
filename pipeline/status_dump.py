import sys; from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from pipeline.index_io import load_index
import json, os, urllib.request, urllib.parse
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "bombayhomes_status.txt"
lines = []
log = lambda s="": lines.append(str(s))

IST = timezone(timedelta(hours=5, minutes=30))
log("=" * 72)
log(f"BOMBAY HOMES - MASTER STATUS DUMP ({datetime.now(IST).strftime('%d %b %Y, %I:%M %p IST')})")
log("=" * 72)

# 1. APIFY CREDITS & RECENT RUN COSTS ($0 read-only calls)
log("\n[1] APIFY CREDITS & RECENT RUNS")
tok = os.environ.get("APIFY_TOKEN", "").strip()
if not tok:
    log("  APIFY_TOKEN is NOT set in this PowerShell window.")
else:
    try:
        req = urllib.request.Request(f"https://api.apify.com/v2/users/me/limits?token={urllib.parse.quote(tok)}")
        with urllib.request.urlopen(req, timeout=15) as r:
            lim = json.loads(r.read().decode("utf-8", errors="ignore")).get("data", {})
        used = float((lim.get("current") or {}).get("monthlyUsageUsd", 0))
        cap = float((lim.get("limits") or {}).get("maxMonthlyUsageUsd", 5))
        log(f"  Monthly Usage : ${used:.4f} / ${cap:.2f}")
        log(f"  Remaining USD : ${max(0.0, cap - used):.4f}")
        log(f"  Reset Cycle   : {lim.get('monthlyUsageCycle', {})}")
    except Exception as e:
        log(f"  Limits check error: {e}")

    try:
        req2 = urllib.request.Request(f"https://api.apify.com/v2/actor-runs?token={urllib.parse.quote(tok)}&desc=true&limit=6")
        with urllib.request.urlopen(req2, timeout=15) as r:
            runs = (json.loads(r.read().decode("utf-8", errors="ignore")).get("data") or {}).get("items") or []
        for r in runs:
            cost = r.get("usageTotalUsd")
            cost_s = f"${float(cost):.4f}" if cost is not None else "n/a"
            log(f"  Run {r.get('id')} | status={r.get('status')} | cost={cost_s} | started={str(r.get('startedAt',''))[:19]}")
    except Exception as e:
        log(f"  Recent runs check error: {e}")

# 2. DAILY AUTO-REFRESH WORKFLOW
log("\n[2] DAILY AUTO-REFRESH WORKFLOW (.github/workflows/daily-mmr-sync.yml)")
wf_p = ROOT / ".github/workflows/daily-mmr-sync.yml"
log(wf_p.read_text(encoding="utf-8").strip() if wf_p.exists() else "  NOT FOUND")

# 3. LIVE INVENTORY SUMMARY
log("\n[3] LIVE INVENTORY SUMMARY")
d = load_index()
socs = d.get("societies", [])
rent_socs = [s for s in socs if s.get("units_rent")]
buy_socs = [s for s in socs if s.get("units_buy")]
approx_pins = sum(1 for s in socs if s.get("coords_approx"))
multi_photo = sum(1 for s in socs if len(s.get("photos") or []) > 1)
rera_socs = sum(1 for s in socs if s.get("rera_ids"))

r_units, r_img, r_zb, b_units, b_img = Counter(), Counter(), Counter(), Counter(), Counter()
for s in socs:
    for u in (s.get("units_rent") or []):
        src = str(u.get("s") or "unknown").lower()
        r_units[src] += 1
        if u.get("img") or s.get("thumb"): r_img[src] += 1
        if u.get("zb"): r_zb[src] += 1
    for u in (s.get("units_buy") or []):
        src = str(u.get("s") or "unknown").lower()
        b_units[src] += 1
        if u.get("img") or s.get("thumb"): b_img[src] += 1

log(f"  Updated         : {d.get('generated_at', 'N/A')}")
log(f"  Total Buildings : {len(socs):,} (Rent: {len(rent_socs):,} | Buy: {len(buy_socs):,})")
log(f"  Total Flats     : {sum(r_units.values()) + sum(b_units.values()):,} (Rent: {sum(r_units.values()):,} | Buy: {sum(b_units.values()):,})")
log(f"  Map Pins        : {len(socs) - approx_pins:,} exact | {approx_pins:,} locality-fenced")
log(f"  Multi-Photo Bld : {multi_photo:,} | RERA Buildings: {rera_socs:,}")
log("  RENT : " + ", ".join(f"{k}={v} ({int(round(100*r_img[k]/v))}% img)" for k, v in r_units.most_common()))
log("  BUY  : " + ", ".join(f"{k}={v} ({int(round(100*b_img[k]/v))}% img)" for k, v in b_units.most_common()))

# 4. APIFY CACHE STATUS
log("\n[4] APIFY CACHE STATUS (data/apify_cache.json)")
cp = ROOT / "data/apify_cache.json"
if cp.exists():
    cb = json.loads(cp.read_text(encoding="utf-8"))
    recs = cb.get("records") or []
    log(f"  Total cached: {len(recs)} | breakdown: {dict(Counter((r.get('s'), r.get('mode')) for r in recs))}")
else:
    log("  No apify_cache.json yet")

OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

gi = ROOT / ".gitignore"
gi_txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
if "bombayhomes_status.txt" not in gi_txt:
    gi.write_text(gi_txt.rstrip() + "\nbombayhomes_status.txt\n", encoding="utf-8")

print(f"[DONE] Saved to {OUT_FILE}")
