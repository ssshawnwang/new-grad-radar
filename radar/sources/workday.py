"""Workday career sites via the undocumented /wday/cxs JSON endpoint.

Works from home networks; GitHub Actions runners are sometimes blocked (403).
Failures are reported in health and never abort the run.
"""
from __future__ import annotations

from ..models import Job
from ..util import post_json, get_json, relative_age_to_date, strip_html, log

PAGE = 20
MAX_PAGES_PER_TERM = 5


def _search_url(wd: dict) -> str:
    return f"https://{wd['host']}/wday/cxs/{wd['tenant']}/{wd['site']}/jobs"


def fetch(s, cfg, company) -> list[Job]:
    wd = company["workday"]
    seen: dict[str, Job] = {}
    for term in cfg.get("search_terms", ["new grad"]):
        for page in range(MAX_PAGES_PER_TERM):
            body = {"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": term}
            data = post_json(s, _search_url(wd), body, timeout=30)
            postings = data.get("jobPostings", [])
            for p in postings:
                path = p.get("externalPath")
                if not path or path in seen:
                    continue
                url = f"https://{wd['host']}/en-US/{wd['site']}{path}"
                seen[path] = Job.make(
                    url=url,
                    company=company["name"],
                    title=p.get("title", ""),
                    locations=[p.get("locationsText")] if p.get("locationsText") else [],
                    source=f"workday:{wd['tenant']}",
                    posted_at=relative_age_to_date(p.get("postedOn")),
                    meta={
                        "fetch": {"kind": "workday", "host": wd["host"], "tenant": wd["tenant"],
                                  "site": wd["site"], "path": path},
                        "req_id": (p.get("bulletFields") or [None])[0],
                        "posted_on_text": p.get("postedOn"),
                    },
                )
            if len(postings) < PAGE or (page + 1) * PAGE >= int(data.get("total", 0)):
                break
    return list(seen.values())


def fetch_detail(s, host: str, tenant: str, site: str, path: str) -> dict:
    url = f"https://{host}/wday/cxs/{tenant}/{site}{path}"
    data = get_json(s, url, timeout=30)
    info = data.get("jobPostingInfo") or {}
    locs = [info.get("location")] if info.get("location") else []
    for extra in info.get("additionalLocations") or []:
        if extra not in locs:
            locs.append(extra)
    return {
        "description": strip_html(info.get("jobDescription")) or None,
        "posted_at": (info.get("startDate") or "")[:10] or None,
        "locations": locs,
        "time_type": info.get("timeType"),
    }
