import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.compact_index import save_compacted_index

CACHE_PATH = ROOT / "data/vibe_scores_cache.json"
VISION_CACHE = ROOT / "data/vision_tags_cache.json"

RENDER_RE = re.compile(r"(?:render|elevation|brochure|floorplan|masterplan|artist|3d|project-img|amenities)", re.I)
MODERN_KW = ("sea_view", "balcony", "terrace", "modern", "pool", "gym", "clubhouse", "high_rise", "luxury", "furnished", "modular")
BRIGHT_KW = ("sunlit", "bright", "daylight", "balcony", "sea_view", "terrace", "open_view", "greenery", "park")

def _load_json(p, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def score_societies(run_onnx=False, onnx_limit=200):
    idx_p = ROOT / "web/public/data/mumbai-index.json"
    data = json.loads(idx_p.read_text(encoding="utf-8"))
    socs = data.get("societies", [])

    vtags = _load_json(VISION_CACHE, {})
    vibe_cache = _load_json(CACHE_PATH, {})
    bright_modern_cnt, render_cnt = 0, 0

    for s in socs:
        sid = s.get("id") or ""
        thumb = str(s.get("thumb") or "")
        photos = s.get("photos") or []
        feats = [str(f).lower() for f in (s.get("features") or [])]
        furn = str(s.get("furnishing") or "").lower()

        cached_v = vtags.get(thumb) or vtags.get(sid) or {}
        if isinstance(cached_v, dict):
            for k, v in cached_v.items():
                if v and str(k).lower() not in feats:
                    feats.append(str(k).lower())

        if sid in vibe_cache and isinstance(vibe_cache[sid], dict):
            score = int(vibe_cache[sid].get("vs", 50))
            is_render = bool(vibe_cache[sid].get("vr", False))
        else:
            score = 48
            n_photos = (1 if thumb else 0) + len(photos)
            if n_photos >= 4: score += 16
            elif n_photos >= 2: score += 10
            elif n_photos == 0: score -= 20

            if any(k in feats for k in BRIGHT_KW): score += 14
            if any(k in feats for k in MODERN_KW): score += 10
            if "furnished" in furn and "unfurn" not in furn: score += 8
            elif "semi" in furn: score += 4

            g = s.get("google") or {}
            if isinstance(g, dict) and float(g.get("rating") or 0) >= 4.2:
                score += 8
            if s.get("rera_ids"):
                score += 6

            is_render = bool(thumb and RENDER_RE.search(thumb) and not s.get("units_rent"))
            if is_render:
                score -= 12
            score = max(10, min(99, score))

        s["vs"] = score
        if is_render:
            s["vr"] = 1
            render_cnt += 1
        else:
            s.pop("vr", None)

        if score >= 74 and not is_render:
            bright_modern_cnt += 1

    _, size_b = save_compacted_index(idx_p, data)
    print(f"[v25 VIBE] Scored {len(socs):,} buildings | Bright & Modern (>=74): {bright_modern_cnt:,} | 3D Renders: {render_cnt:,} | Index: {size_b/1048576:.2f} MiB")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    score_societies(run_onnx=args.onnx, onnx_limit=args.limit)
