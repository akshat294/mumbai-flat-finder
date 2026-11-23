import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "web/public/data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
SHARDS_DIR = DATA_DIR / "shards"
LEGACY_INDEX = DATA_DIR / "mumbai-index.json"

def _merge_soc_pair(base, incoming):
    out = dict(base)
    for uk in ("units_rent", "units_buy"):
        a = out.get(uk) or []
        b = incoming.get(uk) or []
        if b:
            seen = {u.get("u") for u in a if isinstance(u, dict) and u.get("u")}
            merged = list(a)
            for u in b:
                uu = u.get("u") if isinstance(u, dict) else None
                if not uu or uu not in seen:
                    merged.append(u)
                    if uu:
                        seen.add(uu)
            out[uk] = merged
    p1 = dict(out.get("pricing") or {})
    p2 = incoming.get("pricing") or {}
    if isinstance(p2, dict):
        for k, v in p2.items():
            if v is not None and (k not in p1 or p1[k] is None):
                p1[k] = v
    if p1:
        out["pricing"] = p1
    for sk in ("sources", "sources_rent", "sources_buy"):
        if incoming.get(sk) and not out.get(sk):
            out[sk] = incoming[sk]
        elif isinstance(out.get(sk), dict) and isinstance(incoming.get(sk), dict):
            m = dict(out[sk])
            m.update(incoming[sk])
            out[sk] = m
    for k, v in incoming.items():
        if k in ("units_rent", "units_buy", "pricing", "sources", "sources_rent", "sources_buy"):
            continue
        if v is not None and (k not in out or out[k] in (None, "", [], {})):
            out[k] = v
    return out

def load_index():
    if MANIFEST_PATH.exists():
        man = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        by_id, order = {}, []
        for rel in list(man.get("rent_shards") or []) + list(man.get("buy_shards") or []):
            sp = DATA_DIR / rel
            if not sp.exists():
                continue
            chunk = json.loads(sp.read_text(encoding="utf-8"))
            rows = chunk if isinstance(chunk, list) else (chunk.get("societies") or [])
            for s in rows:
                sid = s.get("id")
                if not sid:
                    continue
                if sid in by_id:
                    by_id[sid] = _merge_soc_pair(by_id[sid], s)
                else:
                    by_id[sid] = s
                    order.append(sid)
        socs = [by_id[i] for i in order]
        return {
            "city": man.get("city", "Mumbai MMR"),
            "generated_at": man.get("generated_at", ""),
            "generated_ts": man.get("generated_ts", 0),
            "count": len(socs),
            "societies": socs,
        }
    if LEGACY_INDEX.exists():
        return json.loads(LEGACY_INDEX.read_text(encoding="utf-8"))
    return {"city": "Mumbai MMR", "generated_at": "", "generated_ts": 0, "count": 0, "societies": []}

def _slim_for_mode(soc, mode):
    s = dict(soc)
    if mode == "rent":
        s["units_buy"] = []
        s.pop("sources_buy", None)
        if isinstance(s.get("pricing"), dict):
            s["pricing"] = {k: v for k, v in s["pricing"].items() if not k.startswith("buy_")}
    else:
        s["units_rent"] = []
        s.pop("sources_rent", None)
        if isinstance(s.get("pricing"), dict):
            s["pricing"] = {k: v for k, v in s["pricing"].items() if not k.startswith("rent_")}
    return s

def _write_mode_shards(items, prefix, max_shard_bytes=3_800_000):
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    shards_rel, cur_batch, cur_bytes, idx = [], [], 2, 0

    def _flush():
        nonlocal idx, cur_batch, cur_bytes
        if not cur_batch:
            return
        fname = f"{prefix}_{idx}.json"
        (SHARDS_DIR / fname).write_text(json.dumps(cur_batch, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        shards_rel.append(f"shards/{fname}")
        idx += 1
        cur_batch, cur_bytes = [], 2

    for s in items:
        encoded = json.dumps(s, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if cur_batch and (cur_bytes + len(encoded) + 1) > max_shard_bytes:
            _flush()
        cur_batch.append(s)
        cur_bytes += len(encoded) + 1
    _flush()
    return shards_rel

def save_sharded_index(data, max_shard_bytes=3_800_000):
    socs = data.get("societies") or []
    rent_socs = [_slim_for_mode(s, "rent") for s in socs if (s.get("units_rent") or [])]
    buy_socs = [_slim_for_mode(s, "buy") for s in socs if (s.get("units_buy") or [])]

    SHARDS_DIR.mkdir(parents=True, exist_ok=True)
    for old_f in SHARDS_DIR.glob("*.json"):
        old_f.unlink()

    rent_shards = _write_mode_shards(rent_socs, "rent", max_shard_bytes=max_shard_bytes)
    buy_shards = _write_mode_shards(buy_socs, "buy", max_shard_bytes=max_shard_bytes)

    total_rent_units = sum(len(s.get("units_rent") or []) for s in rent_socs)
    total_buy_units = sum(len(s.get("units_buy") or []) for s in buy_socs)

    manifest = {
        "version": 28,
        "city": data.get("city", "Mumbai MMR"),
        "generated_at": data.get("generated_at", ""),
        "generated_ts": data.get("generated_ts", 0),
        "count": len(socs),
        "rent_buildings": len(rent_socs),
        "buy_buildings": len(buy_socs),
        "rent_flats": total_rent_units,
        "buy_flats": total_buy_units,
        "rent_shards": rent_shards,
        "buy_shards": buy_shards,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    if LEGACY_INDEX.exists():
        LEGACY_INDEX.unlink()

    total_bytes = sum((DATA_DIR / r).stat().st_size for r in rent_shards + buy_shards)
    max_mb = max(((DATA_DIR / r).stat().st_size for r in rent_shards + buy_shards), default=0) / (1024 * 1024)
    return {
        "rent_shards": len(rent_shards),
        "buy_shards": len(buy_shards),
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "max_shard_mb": round(max_mb, 2),
        "rent_flats": total_rent_units,
        "buy_flats": total_buy_units,
        "societies": len(socs),
    }
