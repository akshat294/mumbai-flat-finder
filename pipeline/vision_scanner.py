from __future__ import annotations
import argparse, hashlib, io, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx
from PIL import Image

CACHE_PATH = Path("data/vision_tags_cache.json")
INDEX_PATH = Path("web/public/data/mumbai-index.json")

PROMPTS: List[Tuple[str, str]] = [
    ("balcony",   "an apartment balcony or sit-out with a railing"),
    ("terrace",   "a spacious private rooftop terrace or wide open outdoor deck"),
    ("garden",    "a residential home with a private garden, lawn, or lush green park view"),
    ("sea_view",  "an ocean or sea view with water and coastline seen from an apartment window or balcony"),
    ("bright",    "a bright sunlit modern apartment living room with large windows and daylight"),
    ("neg_plan",  "an architectural 2D floor plan diagram or blueprint"),
    ("neg_ext",   "a tall residential apartment building exterior viewed from the road"),
]
THRESH = {"balcony": 0.075, "terrace": 0.065, "garden": 0.075, "sea_view": 0.060, "bright": 0.100}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}

def url_hash(u: str) -> str:
    return hashlib.sha1(u.strip().encode("utf-8")).hexdigest()[:16]

def load_cache() -> Dict[str, Dict[str, Any]]:
    if not CACHE_PATH.exists(): return {}
    try: return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}

def save_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")

def _download_one(item: Tuple[str, str, str]) -> Optional[Tuple[str, str, Image.Image]]:
    h, u, name = item
    try:
        with httpx.Client(headers=UA, timeout=6.0, follow_redirects=True) as client:
            r = client.get(u)
            if r.status_code != 200 or len(r.content) < 2500: return None
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if im.width < 120 or im.height < 90: return None
            return h, name, im
    except Exception:
        return None

def load_siglip_model(device: str):
    import torch
    from transformers import AutoModel, AutoProcessor
    for model_id in ("google/siglip2-base-patch16-384", "google/siglip-base-patch16-384"):
        try:
            print(f"[vision] Loading {model_id} on {device}...", flush=True)
            proc = AutoProcessor.from_pretrained(model_id)
            dtype = torch.float16 if device == "cuda" else torch.float32
            mdl = AutoModel.from_pretrained(model_id, torch_dtype=dtype).to(device)
            mdl.eval()
            print(f"[vision] Loaded {model_id} cleanly!", flush=True)
            return model_id, proc, mdl
        except Exception as exc:
            print(f"[vision] {model_id} unavailable ({str(exc)[:80]}), trying fallback...", flush=True)
    raise RuntimeError("Install vision deps first: pip install transformers pillow")

def scan_photos(limit: int = 0, batch_size: int = 32, max_workers: int = 16) -> Dict[str, Any]:
    import torch
    if not INDEX_PATH.exists(): raise FileNotFoundError(f"Missing {INDEX_PATH}")
    socs = json.loads(INDEX_PATH.read_text(encoding="utf-8")).get("societies") or []
    cache = load_cache()

    todo: List[Tuple[str, str, str]] = []
    seen_h = set()
    ordered = sorted(socs, key=lambda s: (
        0 if (s.get("features") or {}).get("dist_sea_km", 99) <= 2.0 else 1,
        0 if not s.get("coords_approx") else 1,
        -(len(s.get("units_rent") or []) + len(s.get("units_buy") or [])),
    ))
    for s in ordered:
        u = s.get("thumb")
        if not u or not isinstance(u, str) or not u.startswith("http"): continue
        h = url_hash(u)
        if h in cache or h in seen_h: continue
        seen_h.add(h)
        todo.append((h, u, s.get("name") or ""))
    if limit > 0: todo = todo[:limit]

    print(f"[vision] Cached: {len(cache):,} | To scan now: {len(todo):,}", flush=True)
    if not todo: return {"scanned": 0, "cached_total": len(cache)}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_id, proc, mdl = load_siglip_model(device)
    prompt_keys = [k for k, _ in PROMPTS]
    prompt_texts = [t for _, t in PROMPTS]

    t0, scanned = time.monotonic(), 0
    hits = {"balcony": 0, "terrace": 0, "garden": 0, "sea_view": 0, "bright": 0}
    samples: List[str] = []

    chunk_sz = batch_size * 4
    for start in range(0, len(todo), chunk_sz):
        chunk = todo[start:start + chunk_sz]
        downloaded: List[Tuple[str, str, Image.Image]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for fut in as_completed([ex.submit(_download_one, it) for it in chunk]):
                res = fut.result()
                if res: downloaded.append(res)

        for bi in range(0, len(downloaded), batch_size):
            batch = downloaded[bi:bi + batch_size]
            imgs = [x[2] for x in batch]
            inputs = proc(text=prompt_texts, images=imgs, padding="max_length", truncation=True, return_tensors="pt")
            inputs = {k: (v.to(device, dtype=torch.float16) if (device == "cuda" and v.is_floating_point()) else v.to(device)) for k, v in inputs.items()}
            with torch.no_grad():
                probs = torch.sigmoid(mdl(**inputs).logits_per_image).float().cpu().tolist()

            for (h, name, _), row in zip(batch, probs):
                scores = dict(zip(prompt_keys, row))
                is_plan = scores["neg_plan"] > 0.18
                is_ext  = scores["neg_ext"] > 0.25 and scores["balcony"] < 0.15
                tags = []
                if not is_plan:
                    for tag in ("balcony","terrace","garden","sea_view"):
                        if scores[tag] >= THRESH[tag] and not (is_ext and tag in ("balcony","terrace")):
                            tags.append(tag); hits[tag] += 1
                bright = (not is_plan) and (not is_ext) and (scores["bright"] >= THRESH["bright"])
                if bright: hits["bright"] += 1
                cache[h] = {"tags": tags, "bright": bright, "s": {k: round(scores[k], 3) for k in ("balcony","terrace","garden","sea_view")}}
                scanned += 1
                if tags and len(samples) < 8:
                    samples.append(f"  - {name}: {tags} ({cache[h]['s']})")

        save_cache(cache)
        rate = scanned / max(time.monotonic() - t0, 0.1)
        print(f"[vision] {min(start + chunk_sz, len(todo)):,}/{len(todo):,} fetched | {scanned:,} scored ({rate:.1f} img/s) | hits={hits}", flush=True)

    if samples: print("[vision] Sample detections:\n" + "\n".join(samples), flush=True)
    return {"model": model_id, "device": device, "scanned": scanned, "cached_total": len(cache), "hits": hits}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()
    print("[vision] DONE:", json.dumps(scan_photos(limit=args.limit, batch_size=args.batch_size)), flush=True)
