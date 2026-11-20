import json, sys
from pathlib import Path
p = Path("web/public/data/mumbai-index.json")
if not p.exists(): sys.exit("ERROR: mumbai-index.json missing")
mb = p.stat().st_size / (1024 * 1024)
d = json.loads(p.read_text(encoding="utf-8"))
n = d.get("count", 0)
print(f"[verify_build] Societies: {n} | Size: {mb:.2f} MB | Updated: {d.get('generated_at')}")
if n < 25: sys.exit("ERROR: Too few societies (<25). Aborting deploy to protect live site.")
if mb > 22.0: sys.exit("ERROR: Exceeds safe 22 MB file limit.")
print("[verify_build] PASSED.")
