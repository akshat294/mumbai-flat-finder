import json
from collections import Counter
from pathlib import Path

d = json.loads(Path("web/public/data/mumbai-index.json").read_text(encoding="utf-8"))
socs = d.get("societies", [])

rent_socs = [s for s in socs if s.get("units_rent")]
buy_socs = [s for s in socs if s.get("units_buy")]
approx_pins = sum(1 for s in socs if s.get("coords_approx"))
exact_pins = len(socs) - approx_pins

r_units, r_img, r_zb, r_bldgs = Counter(), Counter(), Counter(), Counter()
b_units, b_img, b_rera, b_bldgs = Counter(), Counter(), Counter(), Counter()
r_lister = Counter()
loc_rent, loc_buy = Counter(), Counter()

for s in socs:
    loc = s.get("locality") or "Unknown"
    has_rera = bool(s.get("rera_ids"))
    seen_rs, seen_bs = set(), set()
    for u in (s.get("units_rent") or []):
        src = str(u.get("s") or "unknown").lower()
        r_units[src] += 1
        seen_rs.add(src)
        loc_rent[loc] += 1
        if u.get("img") or s.get("thumb"):
            r_img[src] += 1
        if u.get("zb"):
            r_zb[src] += 1
        lt = str(u.get("lt") or ("owner" if u.get("zb") else "broker")).lower()
        r_lister[lt] += 1
    for src in seen_rs:
        r_bldgs[src] += 1

    for u in (s.get("units_buy") or []):
        src = str(u.get("s") or "unknown").lower()
        b_units[src] += 1
        seen_bs.add(src)
        loc_buy[loc] += 1
        if u.get("img") or s.get("thumb"):
            b_img[src] += 1
        if has_rera:
            b_rera[src] += 1
    for src in seen_bs:
        b_bldgs[src] += 1

print("\n" + "=" * 68)
print("  BOMBAY HOMES - FULL INVENTORY REPORT")
print("=" * 68)
print(f"  Updated         : {d.get('generated_at', 'N/A')}")
print(f"  Total Buildings : {len(socs):,}  (Rent: {len(rent_socs):,} | Buy: {len(buy_socs):,})")
print(f"  Total Flats     : {sum(r_units.values()) + sum(b_units.values()):,}  (Rent: {sum(r_units.values()):,} | Buy: {sum(b_units.values()):,})")
print(f"  Map Pins        : {exact_pins:,} exact | {approx_pins:,} locality-fenced (0 > 3.8km off)")
print(f"  Rent Listers    : Broker={r_lister['broker']:,} | Owner={r_lister['owner']:,} | Shared={r_lister['shared']:,}")

print("\n  --- RENT BY SOURCE ---")
print(f"  {'Source':<15} {'Flats':>7} {'Bldgs':>7} {'With Photo':>11} {'Zero-Brok':>10}")
print("  " + "-" * 54)
for src, cnt in r_units.most_common():
    pct = int(round(100 * r_img[src] / cnt)) if cnt else 0
    print(f"  {src:<15} {cnt:>7,} {r_bldgs[src]:>7,} {r_img[src]:>6,} ({pct:>2}%) {r_zb[src]:>10,}")
print("  " + "-" * 54)
rt = sum(r_units.values())
ri = sum(r_img.values())
print(f"  {'TOTAL RENT':<15} {rt:>7,} {len(rent_socs):>7,} {ri:>6,} ({int(round(100*ri/rt)) if rt else 0:>2}%) {sum(r_zb.values()):>10,}")

print("\n  --- BUY BY SOURCE ---")
print(f"  {'Source':<15} {'Flats':>7} {'Bldgs':>7} {'With Photo':>11} {'RERA Tag':>10}")
print("  " + "-" * 54)
for src, cnt in b_units.most_common():
    pct = int(round(100 * b_img[src] / cnt)) if cnt else 0
    print(f"  {src:<15} {cnt:>7,} {b_bldgs[src]:>7,} {b_img[src]:>6,} ({pct:>2}%) {b_rera[src]:>10,}")
print("  " + "-" * 54)
bt = sum(b_units.values())
bi = sum(b_img.values())
print(f"  {'TOTAL BUY':<15} {bt:>7,} {len(buy_socs):>7,} {bi:>6,} ({int(round(100*bi/bt)) if bt else 0:>2}%) {sum(b_rera.values()):>10,}")

print("\n  --- TOP 12 LOCALITIES (RENT / BUY FLATS) ---")
all_locs = Counter({k: loc_rent[k] + loc_buy[k] for k in set(loc_rent) | set(loc_buy)})
for loc, tot in all_locs.most_common(12):
    print(f"  {loc:<22} Rent: {loc_rent[loc]:>4,}  |  Buy: {loc_buy[loc]:>4,}  |  Total: {tot:>4,}")
print("=" * 68 + "\n")
