from __future__ import annotations
import re
from typing import Any, Dict, List
from urllib.parse import quote_plus
import httpx
from pipeline.connectors.base import BaseConnector

MAHARERA_URL = "https://maharera.maharashtra.gov.in/projects-search-result"
RERA_RE = re.compile(r"P51[789]\d{8}")

class MahaRERAConnector(BaseConnector):
    source_name = "maharera"

    def run_localities(self, localities: List[str], limit_per_locality: int = 30, max_ram_mb: int = 600) -> int:
        self.db.register_jobs(self.source_name, localities)
        pending = [j for j in self.db.next_pending_jobs(self.source_name) if j["locality"] in localities]
        saved = 0
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}
        with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
            for job in pending:
                loc = job["locality"]
                self.db.mark_job(job["job_key"], "in_progress")
                try:
                    cached = self.read_cache(f"rera:{loc}")
                    if cached is None:
                        resp = client.get(f"{MAHARERA_URL}?project_name={quote_plus(loc)}&project_state=27")
                        resp.raise_for_status()
                        html = resp.text
                        cached, seen = [], set()
                        for m in RERA_RE.finditer(html):
                            rid = m.group(0)
                            if rid in seen:
                                continue
                            seen.add(rid)
                            win = html[max(0, m.start() - 450): min(len(html), m.end() + 700)]
                            tm = re.search(r"<h[345][^>]*>\s*([^<]{3,120})\s*</h[345]>", win, re.I)
                            name = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else f"Project {rid}"
                            cached.append({
                                "rera_id": rid, "name": name, "locality": loc,
                                "url": f"{MAHARERA_URL}?project_name={quote_plus(rid)}",
                            })
                            if len(cached) >= limit_per_locality:
                                break
                        self.write_cache(f"rera:{loc}", cached)
                    for proj in cached[:limit_per_locality]:
                        self.db.upsert_raw_record(
                            self.source_name, proj["rera_id"], proj["name"], proj,
                            locality=loc, rera_id=proj["rera_id"], source_url=proj["url"]
                        )
                        saved += 1
                    self.db.mark_job(job["job_key"], "done")
                    self.polite_sleep()
                except Exception as exc:
                    self.db.mark_job(job["job_key"], "failed", str(exc)[:300])
        return saved
