"""jobs.apple.com search API. The `format` key in the body is mandatory."""
from __future__ import annotations

from ..models import Job
from ..util import post_json, get_json, iso_to_date, strip_html, log

API = "https://jobs.apple.com/api/v1/search"
DETAIL = "https://jobs.apple.com/api/role/detail/{pid}?languageCd=en-us"
TERMS = ["early career", "new grad", "software engineer early career", "machine learning engineer"]
MAX_PAGES_PER_TERM = 3


def _body(term: str, page: int) -> dict:
    return {
        "query": term,
        "filters": {"postingpostLocation": ["postLocation-USA"], "locations": ["postLocation-USA"]},
        "page": page,
        "locale": "en-us",
        "sort": "newest",
        "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"},
    }


def fetch(s, cfg, company) -> list[Job]:
    seen: dict[str, Job] = {}
    for term in TERMS:
        for page in range(1, MAX_PAGES_PER_TERM + 1):
            data = post_json(s, API, _body(term, page), timeout=30)
            res = data.get("res") or {}
            results = res.get("searchResults") or []
            for j in results:
                pid = j.get("positionId")
                if not pid or pid in seen:
                    continue
                locs = j.get("locations") or []
                us = [l for l in locs if (l.get("countryID") == "iso-country-USA" or l.get("countryName") == "United States")]
                if locs and not us:
                    continue
                names = [l.get("name") for l in (us or locs) if l.get("name")]
                slug = j.get("transformedPostingTitle") or ""
                seen[pid] = Job.make(
                    url=f"https://jobs.apple.com/en-us/details/{pid}/{slug}".rstrip("/"),
                    company="Apple",
                    title=j.get("postingTitle", ""),
                    locations=[n if n != "United States" else "United States (multiple)" for n in names],
                    source="apple",
                    posted_at=iso_to_date(j.get("postDateInGMT")),
                    meta={"team": (j.get("team") or {}).get("teamName"), "req_id": j.get("reqId"),
                          "fetch": {"kind": "apple", "pid": pid}},
                    description=j.get("jobSummary"),
                )
            if len(results) < 20:
                break
    return list(seen.values())


def fetch_description(s, pid: str) -> str | None:
    try:
        d = get_json(s, DETAIL.format(pid=pid), timeout=20, retries=0)
    except Exception as e:  # noqa: BLE001
        log.debug("apple detail failed for %s: %s", pid, e)
        return None
    parts = []
    for key in ("jobSummary", "description", "keyQualifications", "education", "additionalRequirements", "preferredQualifications"):
        v = d.get(key)
        if isinstance(v, list):
            v = "\n".join(str(x.get("description", x)) if isinstance(x, dict) else str(x) for x in v)
        if v:
            parts.append(f"{key}:\n{strip_html(str(v))}")
    return "\n\n".join(parts) or None
