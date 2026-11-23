from __future__ import annotations
import sys; from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from pipeline.index_io import load_index
import argparse, hashlib, io, json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
from PIL import Image

CACHE_PATH = Path("data/vision_tags_cache.json")
INDEX_PATH = Path("web/public/data/mumbai-index.json")
REPO_ID = "onnx-community/siglip2-base-patch16-224-ONNX"
CACHE_VER = 2

PROMPTS: List[Tuple[str, str]] = [
    ("balcony",   "this is a photo of an apartment balcony with a railing and outdoor view."),
    ("terrace",   "this is a photo of a spacious private rooftop terrace or outdoor patio deck."),
    ("garden",    "this is a photo of a residential apartment overlooking a green garden, park, or lawn."),
    ("sea_view",  "this is a photo of an ocean or sea view with water seen from an apartment window or balcony."),
    ("bright",    "this is a photo of a bright sunlit modern living room with large windows."),
    ("bg_room",   "this is a photo of an indoor apartment bedroom or empty living room."),
    ("bg_kb",     "this is a photo of an indoor kitchen or tiled bathroom."),
    ("bg_ext",    "this is a photo of a tall residential apartment building exterior from outside."),
    ("bg_plan",   "this is a photo of a 2d architectural floor plan blueprint diagram."),
]

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
            return h, name, np.transpose(arr, (2, 0, 1))
    except Exception:
        return None

def _encode_siglip2_ids(tok, texts: List[str], max_len: int = 64) -> np.ndarray:
    eos_id = tok.token_to_id("</s>") or tok.token_to_id("<eos>") or 1
    pad_id = tok.token_to_id("<pad>")
    if pad_id is None: pad_id = 0
    rows = []
    for t in texts:
        ids = tok.encode(t.lower()).ids
        if not ids or ids[-1] != eos_id:
            ids = ids[:max_len - 1] + [eos_id]
        else:
            ids = ids[:max_len]
        if len(ids) < max_len:
            ids = ids + [pad_id] * (max_len - len(ids))
        rows.append(ids)
    return np.array(rows, dtype=np.int64)

def _load_onnx_split():
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    hf_tok = os.environ.get("HF_TOKEN") or None
    tok_path = hf_hub_download(repo_id=REPO_ID, filename="tokenizer.json", token=hf_tok)
    tok = Tokenizer.from_file(tok_path)

    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_opts.intra_op_num_threads = max(1, (os.cpu_count() or 4))
    providers = ["CPUExecutionProvider"]

    t_sess = v_sess = None
    for tf in ("onnx/text_model.onnx", "onnx/text_model_fp16.onnx", "onnx/text_model_int8.onnx"):
        try:
            tp = hf_hub_download(repo_id=REPO_ID, filename=tf, token=hf_tok)
            t_sess = ort.InferenceSession(tp, sess_options=sess_opts, providers=providers)
            print(f"[vision-onnx] Text encoder: {tf}", flush=True)
            break
        except Exception:
            continue
    for vf in ("onnx/vision_model_uint8.onnx", "onnx/vision_model_int8.onnx", "onnx/vision_model_quantized.onnx", "onnx/vision_model.onnx"):
        try:
            vp = hf_hub_download(repo_id=REPO_ID, filename=vf, token=hf_tok)
            v_sess = ort.InferenceSession(vp, sess_options=sess_opts, providers=providers)
            print(f"[vision-onnx] Vision encoder: {vf}", flush=True)
            break
        except Exception:
            continue

    if t_sess is not None and v_sess is not None:
        return "split", tok, v_sess, t_sess

    for cf in ("onnx/model_quantized.onnx", "onnx/model_int8.onnx", "onnx/model.onnx"):
        try:
            cp = hf_hub_download(repo_id=REPO_ID, filename=cf, token=hf_tok)
            sess = ort.InferenceSession(cp, sess_options=sess_opts, providers=providers)
            print(f"[vision-onnx] Combined fallback: {cf}", flush=True)
            return "combined", tok, sess, None
        except Exception:
            continue
    raise RuntimeError("Could not download SigLIP2 ONNX files from Hugging Face Hub")

def _l2_norm(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)

def _get_pooler(sess, outs: List[np.ndarray]) -> np.ndarray:
    by_name = dict(zip([o.name for o in sess.get_outputs()], outs))
    for k in ("pooler_output", "image_embeds", "text_embeds"):
        if k in by_name: return np.asarray(by_name[k], dtype=np.float32)
    for arr in outs:
        a = np.asarray(arr, dtype=np.float32)
        if a.ndim == 2: return a
    return np.asarray(outs[-1], dtype=np.float32)

def scan_photos(limit: int = 800, batch_size: int = 16, max_workers: int = 16, max_seconds: float = 240.0) -> Dict[str, Any]:
    if False:
        print(f"[vision-onnx] Missing {INDEX_PATH}, skipping.", flush=True)
        return {"scanned": 0}

    socs = load_index().get("societies") or []
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
        if h in seen_h: continue
        if h in cache and int(cache[h].get("v", 1)) >= CACHE_VER: continue
        seen_h.add(h)
        todo.append((h, u, s.get("name") or ""))
    if limit > 0: todo = todo[:limit]

    already_v2 = sum(1 for v in cache.values() if isinstance(v, dict) and int(v.get("v", 1)) >= CACHE_VER)
    print(f"[vision-onnx] v2 Cached: {already_v2:,} | Queued this run: {len(todo):,}", flush=True)
    if not todo: return {"scanned": 0, "cached_total": len(cache)}

    mode, tok, v_sess, t_sess = _load_onnx_split()
    prompt_keys = [k for k, _ in PROMPTS]
    prompt_texts = [t for _, t in PROMPTS]
    input_ids = _encode_siglip2_ids(tok, prompt_texts)

    t_emb = None
    if mode == "split" and t_sess is not None:
        t_in = {inp.name for inp in t_sess.get_inputs()}
        t_feed: Dict[str, Any] = {"input_ids": input_ids}
        if "attention_mask" in t_in: t_feed["attention_mask"] = (input_ids != 0).astype(np.int64)
        t_emb = _l2_norm(_get_pooler(t_sess, t_sess.run(None, t_feed)))

    t0, scanned = time.monotonic(), 0
    hits = {"balcony": 0, "terrace": 0, "garden": 0, "sea_view": 0, "bright": 0}
    samples: List[str] = []

    chunk_sz = batch_size * 3
    for start in range(0, len(todo), chunk_sz):
        if (time.monotonic() - t0) > max_seconds:
            print(f"[vision-onnx] Reached {max_seconds:.0f}s budget — saving progress.", flush=True)
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

            if mode == "split":
                v_in = v_sess.get_inputs()[0].name
                v_emb = _l2_norm(_get_pooler(v_sess, v_sess.run(None, {v_in: pixels})))
                sims = (v_emb @ t_emb.T).tolist()
            else:
                in_names = {inp.name for inp in v_sess.get_inputs()}
                feed = {"input_ids": input_ids, "pixel_values": pixels}
                if "attention_mask" in in_names: feed["attention_mask"] = (input_ids != 0).astype(np.int64)
                outs = v_sess.run(None, feed)
                by_name = dict(zip([o.name for o in v_sess.get_outputs()], outs))
                if "image_embeds" in by_name and "text_embeds" in by_name:
                    sims = (_l2_norm(by_name["image_embeds"]) @ _l2_norm(by_name["text_embeds"]).T).tolist()
                else:
                    lg = np.asarray(by_name.get("logits_per_image", outs[0]), dtype=np.float32)
                    sims = ((lg + 14.0) / 112.0).tolist()

            for (h, name, _), row in zip(batch, sims):
                sc = dict(zip(prompt_keys, row))
                bg_max = max(sc["bg_room"], sc["bg_kb"], sc["bg_ext"], sc["bg_plan"])
                is_plan = sc["bg_plan"] >= max(sc["balcony"], sc["terrace"], sc["garden"], sc["sea_view"], sc["bg_room"]) + 0.015
                is_kb   = sc["bg_kb"] >= bg_max - 0.002 and sc["bg_kb"] > sc["balcony"] + 0.015

                tags = []
                if not is_plan and not is_kb:
                    if sc["balcony"] >= 0.095 and sc["balcony"] >= (bg_max - 0.012):
                        tags.append("balcony"); hits["balcony"] += 1
                    if sc["terrace"] >= 0.095 and sc["terrace"] >= (bg_max - 0.005):
                        tags.append("terrace"); hits["terrace"] += 1
                    if sc["garden"] >= 0.098 and sc["garden"] >= (bg_max - 0.008):
                        tags.append("garden"); hits["garden"] += 1
                    if sc["sea_view"] >= 0.095 and sc["sea_view"] >= (bg_max - 0.010):
                        tags.append("sea_view"); hits["sea_view"] += 1

                bright = (not is_plan) and (sc["bright"] >= 0.105) and (sc["bright"] >= sc["bg_ext"] + 0.005)
                if bright: hits["bright"] += 1

                cache[h] = {
                    "v": CACHE_VER, "tags": tags, "bright": bright,
                    "s": {k: round(sc[k], 3) for k in ("balcony","terrace","garden","sea_view","bg_room","bg_ext")},
                }
                scanned += 1
                if tags and len(samples) < 10:
                    samples.append(f"  - {name}: {tags} ({cache[h]['s']})")

        save_cache(cache)
        rate = scanned / max(time.monotonic() - t0, 0.1)
        print(f"[vision-onnx] {min(start + chunk_sz, len(todo)):,}/{len(todo):,} fetched | {scanned:,} scored ({rate:.1f} img/s) | hits={hits}", flush=True)

    if samples: print("[vision-onnx] Sample detections:\n" + "\n".join(samples), flush=True)
    return {"engine": f"onnx-{mode}-v2", "scanned": scanned, "cached_total": len(cache), "hits": hits}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=800)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-seconds", type=float, default=240.0)
    args = ap.parse_args()
    print("[vision-onnx] DONE:", json.dumps(scan_photos(limit=args.limit, batch_size=args.batch_size, max_seconds=args.max_seconds)), flush=True)
