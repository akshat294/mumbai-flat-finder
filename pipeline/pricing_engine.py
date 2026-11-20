from __future__ import annotations
import statistics
from typing import Any, Dict, List, Optional, Tuple

def filter_outliers(values: List[int]) -> Tuple[List[int], int]:
    clean = [v for v in values if v and v > 0]
    if len(clean) < 3:
        return clean, 0
    med = statistics.median(clean)
    kept = [v for v in clean if (0.4 * med) <= v <= (2.5 * med)]
    return kept or clean, len(clean) - len(kept)

def summarize_portal_prices(raw_by_source: Dict[str, List[Dict[str, Any]]], default_yield_pct: float = 3.1, carpet_sqft: Optional[float] = None) -> Dict[str, Any]:
    all_rents, all_buys, all_deps, by_portal = [], [], [], {}
    for portal in ("magicbricks", "99acres", "housing", "nobroker"):
        recs = raw_by_source.get(portal) or []
        rents, _ = filter_outliers([int(r["rent_inr"]) for r in recs if r.get("rent_inr")])
        buys, _ = filter_outliers([int(r["buy_inr"]) for r in recs if r.get("buy_inr")])
        deps = [int(r["deposit_inr"]) for r in recs if r.get("deposit_inr")]
        all_rents.extend(rents); all_buys.extend(buys); all_deps.extend(deps)
        if rents or buys:
            e: Dict[str, Any] = {"count": len(rents) + len(buys)}
            if rents: e["rent_median"] = int(statistics.median(rents))
            if buys: e["buy_median"] = int(statistics.median(buys))
            if deps: e["deposit_median"] = int(statistics.median(deps))
            if portal == "nobroker": e["zero_brokerage_count"] = len(rents)
            by_portal[portal] = e

    clean_rents, ro = filter_outliers(all_rents)
    clean_buys, bo = filter_outliers(all_buys)
    rent_med = int(statistics.median(clean_rents)) if clean_rents else None
    buy_med = int(statistics.median(clean_buys)) if clean_buys else None
    rent_est = buy_est = False
    if rent_med is None and buy_med is not None:
        rent_med, rent_est = int((buy_med * (default_yield_pct / 100.0)) / 12.0), True
    elif buy_med is None and rent_med is not None:
        buy_med, buy_est = int((rent_med * 12.0) / (default_yield_pct / 100.0)), True

    dep_med = int(statistics.median(all_deps)) if all_deps else (rent_med * 4 if rent_med else None)
    return {
        "rent_monthly_inr": {"median": rent_med, "count": len(clean_rents), "is_estimate": rent_est},
        "buy_inr": {"median": buy_med, "count": len(clean_buys), "is_estimate": buy_est},
        "deposit_inr_median": dep_med,
        "has_zero_brokerage": by_portal.get("nobroker", {}).get("zero_brokerage_count", 0) > 0,
        "move_in_cash_nobroker": (dep_med + rent_med) if (dep_med and rent_med) else None,
        "move_in_cash_broker": (dep_med + rent_med * 2) if (dep_med and rent_med) else None,
        "price_per_carpet_sqft": int(buy_med / carpet_sqft) if (buy_med and carpet_sqft and carpet_sqft > 100) else None,
        "rental_yield_pct": round(((rent_med * 12.0) / buy_med) * 100.0, 2) if (rent_med and buy_med) else None,
        "flagged_outliers_count": ro + bo,
        "by_portal": by_portal,
    }
