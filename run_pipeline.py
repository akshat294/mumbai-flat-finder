from __future__ import annotations
import argparse, json, signal, sys
from pathlib import Path
from pipeline.build_city import build_mumbai
from pipeline.connectors.reddit import RedditRentalsConnector
from pipeline.connectors.ghosla import GhoslaConnector
from pipeline.connectors.browser_portals import Browser99AcresConnector, BrowserHousingConnector
from pipeline.connectors.free_sources import SquareYardsConnector, CommonFloorConnector, MakaanConnector, NoBrokerageConnector, CommunityFlatmatesConnector
from pipeline.connectors.portals import NoBrokerConnector, MagicBricksConnector, NinetyNineAcresConnector
from pipeline.core.checkpoint import CheckpointDB

CONNECTORS = {"magicbricks": MagicBricksConnector, "nobroker": NoBrokerConnector, "99acres": NinetyNineAcresConnector, "reddit": RedditRentalsConnector, "squareyards": SquareYardsConnector, "commonfloor": CommonFloorConnector, "makaan": MakaanConnector, "nobrokerage": NoBrokerageConnector, "community": CommunityFlatmatesConnector, "ghosla": GhoslaConnector, "99acres_pw": Browser99AcresConnector, "housing": BrowserHousingConnector}

def _sig(signum, frame):
    print(f"\n[run_pipeline] Caught signal {signum} - SQLite WAL safe. Exiting."); sys.exit(0)

def main():
    sys.stdout.reconfigure(line_buffering=True)
    signal.signal(signal.SIGINT, _sig); signal.signal(signal.SIGTERM, _sig)
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-mmr", action="store_true")
    ap.add_argument("--localities", default="Bandra West,Powai")
    ap.add_argument("--sources", default="magicbricks,nobroker,99acres")
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--fresh-hours", type=float, default=20.0)
    ap.add_argument("--max-google-calls", type=int, default=25)
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()

    zones = json.loads(Path("data/cities.json").read_text(encoding="utf-8-sig"))["mumbai"]["zones"]
    loc_meta = [{"locality": l, "zone": z, "city": zi["city"]} for z, zi in zones.items() for l in zi["localities"]] if args.all_mmr else [{"locality": x.strip(), "zone": "Mumbai", "city": "Mumbai"} for x in args.localities.split(",") if x.strip()]
    db = CheckpointDB()
    if not args.build_only:
        if hasattr(db, "reset_stale_jobs"): db.reset_stale_jobs(fresh_hours=args.fresh_hours)
        for src in [s.strip().lower() for s in args.sources.split(",") if s.strip()]:
            if src in CONNECTORS:
                print(f"[pipeline] Syncing {src} across {len(loc_meta)} localities...")
                n = CONNECTORS[src](db).run_localities(loc_meta, limit_per_locality=args.limit, fresh_hours=args.fresh_hours)
                print(f"[pipeline] {src}: saved {n} records")
    print("[pipeline] Compiling web/public/data/mumbai-index.json...")
    print("[pipeline] DONE:", json.dumps(build_mumbai(max_google_calls=args.max_google_calls, max_osm_calls=0 if args.build_only else 60), indent=2))

if __name__ == "__main__": main()
