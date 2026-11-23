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
