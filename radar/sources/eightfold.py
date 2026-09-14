"""Eightfold-hosted career sites (Microsoft 'pcsx' variant, Netflix 'apply_v2' variant)."""
from __future__ import annotations

import ast

from ..models import Job
from ..util import get_json, epoch_to_date, strip_html, log

NUM = 50


def _locations(p: dict) -> list[str]:
    locs = p.get("standardizedLocations") or p.get("locations") or []
    if isinstance(locs, str):
        try:
            locs = ast.literal_eval(locs)
        except (ValueError, SyntaxError):
            locs = [locs]
    if not locs and p.get("location"):
        locs = [p["location"]]
    return [str(l) for l in locs if l]


def fetch(s, cfg, company) -> list[Job]:
    ef = company["eightfold"]
    host, domain, variant = ef["host"], ef["domain"], ef.get("variant", "apply_v2")
    seen: dict[str, Job] = {}
    for term in cfg.get("search_terms", ["new grad"]):
        params = {"domain": domain, "query": term, "start": 0, "num": NUM, "sort_by": "timestamp"}
        if variant == "pcsx":
            data = get_json(s, f"https://{host}/api/pcsx/search", params=params, timeout=30)
            positions = (data.get("data") or {}).get("positions") or []
        else:
            data = get_json(s, f"https://{host}/api/apply/v2/jobs", params=params, timeout=30)
            positions = data.get("positions") or []
        for p in positions:
            pid = str(p.get("id"))
            if not pid or pid in seen:
                continue
            if variant == "pcsx":
                display = p.get("displayJobId") or p.get("atsJobId") or pid
                url = f"https://jobs.careers.microsoft.com/global/en/job/{display}" if "microsoft" in domain \
                    else f"https://{host}{p.get('positionUrl', '/careers/job/' + pid)}"
                posted = epoch_to_date(p.get("postedTs") or p.get("creationTs"))
            else:
                url = p.get("canonicalPositionUrl") or f"https://{host}/careers/job/{pid}"
                posted = epoch_to_date(p.get("t_create") or p.get("t_update"))
            seen[pid] = Job.make(
                url=url,
                company=company["name"],
                title=p.get("name") or p.get("posting_name") or "",
                locations=_locations(p),
                source=f"eightfold:{domain}",
                posted_at=posted,
                meta={"department": p.get("department"),
                      "fetch": {"kind": "eightfold", "host": host, "domain": domain, "variant": variant, "id": pid}},
                description=strip_html(p.get("job_description")) or None,
            )
    return list(seen.values())


def fetch_description(s, host: str, domain: str, variant: str, pid: str) -> str | None:
    try:
        if variant == "pcsx":
            d = get_json(s, f"https://{host}/api/pcsx/job/{pid}", params={"domain": domain}, timeout=20, retries=0)
            data = d.get("data") or d
            return strip_html(data.get("job_description") or data.get("description")) or None
        d = get_json(s, f"https://{host}/api/apply/v2/jobs/{pid}", params={"domain": domain}, timeout=20, retries=0)
        return strip_html(d.get("job_description") or (d.get("data") or {}).get("job_description")) or None
    except Exception as e:  # noqa: BLE001
        log.debug("eightfold detail failed for %s: %s", pid, e)
        return None
