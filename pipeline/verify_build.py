import json, sys
from pathlib import Path

DATA_DIR = Path("web/public/data")
MAN = DATA_DIR / "manifest.json"
LEGACY = DATA_DIR / "mumbai-index.json"

if LEGACY.exists() and LEGACY.stat().st_size > 20 * 1024 * 1024:
    sys.exit(f"ERROR: Legacy monolithic {LEGACY} ({LEGACY.stat().st_size/1048576:.2f} MB) would break Cloudflare 25 MiB limit!")

if not MAN.exists():
    sys.exit("ERROR: web/public/data/manifest.json missing")

m = json.loads(MAN.read_text(encoding="utf-8"))
all_shards = list(m.get("rent_shards") or []) + list(m.get("buy_shards") or [])
if not all_shards:
    sys.exit("ERROR: manifest.json lists 0 shards")

total_b, max_mb = 0, 0.0
for rel in all_shards:
    sp = DATA_DIR / rel
    if not sp.exists():
        sys.exit(f"ERROR: Missing shard {sp}")
    sz = sp.stat().st_size
    mb = sz / (1024 * 1024)
    total_b += sz
    max_mb = max(max_mb, mb)
    if mb > 15.0:
        sys.exit(f"ERROR: Shard {rel} is {mb:.2f} MB (> 15 MB limit)")

n = m.get("count", 0)
print(
    f"[verify_build] Societies: {n:,} | Rent Flats: {m.get('rent_flats',0):,} | Buy Flats: {m.get('buy_flats',0):,} | "
    f"Shards: {len(m.get('rent_shards',[]))}R + {len(m.get('buy_shards',[]))}B | "
    f"Total: {total_b/1048576:.2f} MB (max shard: {max_mb:.2f} MB) | Updated: {m.get('generated_at')}"
)
if n < 25:
    sys.exit("ERROR: Too few societies (<25). Aborting deploy.")
print("[verify_build] PASSED.")
# === QUALITY_GATE_V44: Hard non-regression checks ===
def _run_v44_quality_gate():
    import json as _j
    from collections import Counter as _C
    from pathlib import Path as _P
    root = _P(__file__).resolve().parent.parent
    man = _j.loads((root / "web/public/data/manifest.json").read_text(encoding="utf-8-sig"))
    r_socs, b_socs = [], []
    for sf in (man.get("rent_shards") or []):
        r_socs.extend(_j.loads((root / "web/public/data" / sf).read_text(encoding="utf-8-sig")))
    for sf in (man.get("buy_shards") or []):
        b_socs.extend(_j.loads((root / "web/public/data" / sf).read_text(encoding="utf-8-sig")))
    r_units = sum(len(s.get("units_rent") or []) for s in r_socs)
    b_units = sum(len(s.get("units_buy") or []) for s in b_socs)
    tiny_mb = sum(
        1 for s in (r_socs + b_socs)
        for p in ([s.get("thumb")] + (s.get("photos") or []))
        if isinstance(p, str) and "Photo_h180_w240" in p
    )
    coords = _C((round(float(s["lat"]), 5), round(float(s["lng"]), 5)) for s in r_socs if s.get("lat") and s.get("lng"))
    stacked = sum(1 for v in coords.values() if v >= 3)
    print(f"[QUALITY GATE] Rent={len(r_socs):,} soc/{r_units:,} flats | Buy={len(b_socs):,} soc/{b_units:,} flats | tiny_mb={tiny_mb} | stacked_pins={stacked}")
    assert r_units >= 12000, f"Rent flat floor breached: {r_units}"
    assert b_units >= 8000, f"Buy flat floor breached: {b_units}"
    assert tiny_mb == 0, f"Tiny MagicBricks 180x240 thumbnails leaked: {tiny_mb}"
    assert stacked == 0, f"Stacked pin collisions leaked: {stacked}"

if __name__ == "__main__":
    _run_v44_quality_gate()
