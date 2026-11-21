from __future__ import annotations
import argparse, hashlib, io, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
from PIL import Image

CACHE_PATH = Path("data/vision_tags_cache.json")
INDEX_PATH = Path("web/public/data/mumbai-index.json")
REPO_ID = "onnx-community/siglip2-base-patch16-224-ONNX"

PROMPTS: List[Tuple[str, str]] = [
    ("balcony",   "an apartment balcony or sit-out with a railing"),
    ("terrace",   "a spacious private rooftop terrace or wide open outdoor deck"),
    ("garden",    "a residential home with a private garden, lawn, or lush green park view"),
    ("sea_view",  "an ocean or sea view with water and coastline seen from an apartment window or balcony"),
    ("bright",    "a bright sunlit modern apartment living room with large windows and daylight"),
    ("neg_plan",  "an architectural 2D floor plan diagram or blueprint"),
    ("neg_ext",   "a tall residential apartment building exterior viewed from the road"),
]
THRESH = {"balcony": 0.065, "terrace": 0.055, "garden": 0.065, "sea_view": 0.055, "bright": 0.095}
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

def _download_one(item: Tuple[str, str, str]) -> Optional[Tuple[str, str, np.ndarray]]:
    h, u, name = item
    try:
        with httpx.Client(headers=UA, timeout=6.0, follow_redirects=True) as client:
            r = client.get(u)
            if r.status_code != 200 or len(r.content) < 2500: return None
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if im.width < 120 or im.height < 90: return None
            im = im.resize((224, 224), Image.BICUBIC)
            arr = (np.asarray(im, dtype=np.float32) / 255.0 - 0.5) / 0.5
            arr = np.transpose(arr, (2, 0, 1))
            return h, name, arr
    except Exception:
        return None

def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-x))

def _load_onnx_engine():
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    tok_path = hf_hub_download(repo_id=REPO_ID, filename="tokenizer.json")
    tok = Tokenizer.from_file(tok_path)
    tok.enable_truncation(max_length=64)
    tok.enable_padding(length=64, pad_id=0)

    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CPUExecutionProvider"]

    for fname in ("onnx/model_int8.onnx", "onnx/model_quantized.onnx", "onnx/model_uint8.onnx", "onnx/model_q4.onnx", "onnx/model.onnx"):
        try:
            mp = hf_hub_download(repo_id=REPO_ID, filename=fname)
            sess = ort.InferenceSession(mp, sess_options=sess_opts, providers=providers)
            print(f"[vision-onnx] Loaded combined model: {fname}", flush=True)
            return "combined", tok, sess, None
        except Exception:
            continue

    v_path = hf_hub_download(repo_id=REPO_ID, filename="onnx/vision_model_int8.onnx")
    t_path = hf_hub_download(repo_id=REPO_ID, filename="onnx/text_model_int8.onnx")
    v_sess = ort.InferenceSession(v_path, sess_options=sess_opts, providers=providers)
    t_sess = ort.InferenceSession(t_path, sess_options=sess_opts, providers=providers)
    print("[vision-onnx] Loaded split INT8 vision + text models!", flush=True)
    return "split", tok, v_sess, t_sess

def _encode_prompts(tok, texts: List[str]) -> np.ndarray:
    encs = tok.encode_batch([t.lower() for t in texts])
    return np.array([e.ids for e in encs], dtype=np.int64)

def _run_batch(mode: str, sess, t_emb: Optional[np.ndarray], input_ids: np.ndarray, pixels: np.ndarray) -> np.ndarray:
    if mode == "combined":
        in_names = {inp.name for inp in sess.get_inputs()}
        feed: Dict[str, Any] = {"input_ids": input_ids, "pixel_values": pixels}
        if "attention_mask" in in_names:
            feed["attention_mask"] = (input_ids != 0).astype(np.int64)
        out_names = [o.name for o in sess.get_outputs()]
        outs = sess.run(None, feed)
        by_name = dict(zip(out_names, outs))
        logits = by_name.get("logits_per_image")
        if logits is None: logits = outs[0]
        return _sigmoid(np.asarray(logits, dtype=np.float32))
    else:
        v_in = sess.get_inputs()[0].name
        v_outs = sess.run(None, {v_in: pixels})
        v_map = dict(zip([o.name for o in sess.get_outputs()], v_outs))
        v_emb = v_map.get("pooler_output")
        if v_emb is None: v_emb = v_outs[-1]
        v_emb = v_emb / np.maximum(np.linalg.norm(v_emb, axis=-1, keepdims=True), 1e-8)
        logits = (v_emb @ t_emb.T) * 112.6689 - 12.93
        return _sigmoid(logits.astype(np.float32))

def scan_photos(limit: int = 600, batch_size: int = 16, max_workers: int = 16, max_seconds: float = 240.0) -> Dict[str, Any]:
    if not INDEX_PATH.exists():
        print(f"[vision-onnx] Missing {INDEX_PATH}, skipping.", flush=True)
        return {"scanned": 0}

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

    print(f"[vision-onnx] Cached: {len(cache):,} | Queued this run: {len(todo):,}", flush=True)
    if not todo: return {"scanned": 0, "cached_total": len(cache)}

    mode, tok, sess, t_sess = _load_onnx_engine()
    prompt_keys = [k for k, _ in PROMPTS]
    prompt_texts = [t for _, t in PROMPTS]
    input_ids = _encode_prompts(tok, prompt_texts)

    t_emb = None
    if mode == "split" and t_sess is not None:
        t_in = t_sess.get_inputs()[0].name
        t_outs = t_sess.run(None, {t_in: input_ids})
        t_map = dict(zip([o.name for o in t_sess.get_outputs()], t_outs))
        t_emb = t_map.get("pooler_output")
        if t_emb is None: t_emb = t_outs[-1]
        t_emb = t_emb / np.maximum(np.linalg.norm(t_emb, axis=-1, keepdims=True), 1e-8)

    t0, scanned = time.monotonic(), 0
    hits = {"balcony": 0, "terrace": 0, "garden": 0, "sea_view": 0, "bright": 0}
    samples: List[str] = []

    chunk_sz = batch_size * 3
    for start in range(0, len(todo), chunk_sz):
        if (time.monotonic() - t0) > max_seconds:
            print(f"[vision-onnx] Reached {max_seconds:.0f}s cloud budget — saving progress.", flush=True)
            break
        chunk = todo[start:start + chunk_sz]
        downloaded: List[Tuple[str, str, np.ndarray]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for fut in as_completed([ex.submit(_download_one, it) for it in chunk]):
                res = fut.result()
                if res: downloaded.append(res)

        for bi in range(0, len(downloaded), batch_size):
            if (time.monotonic() - t0) > max_seconds: break
            batch = downloaded[bi:bi + batch_size]
            pixels = np.stack([x[2] for x in batch], axis=0).astype(np.float32)
            probs = _run_batch(mode, sess, t_emb, input_ids, pixels).tolist()

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
        print(f"[vision-onnx] {min(start + chunk_sz, len(todo)):,}/{len(todo):,} fetched | {scanned:,} scored ({rate:.1f} img/s) | hits={hits}", flush=True)

    if samples: print("[vision-onnx] Sample detections:\n" + "\n".join(samples), flush=True)
    return {"engine": f"onnx-{mode}", "scanned": scanned, "cached_total": len(cache), "hits": hits}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=600)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-seconds", type=float, default=240.0)
    args = ap.parse_args()
    print("[vision-onnx] DONE:", json.dumps(scan_photos(limit=args.limit, batch_size=args.batch_size, max_seconds=args.max_seconds)), flush=True)
