from pipeline.index_io import load_index, save_sharded_index
from pipeline.quality_filter import filter_and_track_societies

def compact_societies_for_pages(socs, **kwargs):
    cleaned, stats = filter_and_track_societies(socs)
    socs[:] = cleaned
    return stats.get("dropped_clones", 0)

def save_compacted_index(idx_path, data, max_bytes=None):
    cleaned, stats = filter_and_track_societies(data.get("societies") or [])
    data["societies"] = cleaned
    data["count"] = len(cleaned)
    res = save_sharded_index(data, max_shard_bytes=3_800_000)
    return stats.get("dropped_clones", 0), int(res["total_mb"] * 1024 * 1024)
