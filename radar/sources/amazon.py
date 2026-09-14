"""amazon.jobs search JSON."""
from __future__ import annotations

from ..models import Job
from ..util import get_json, long_date_to_date, strip_html

API = "https://www.amazon.jobs/en/search.json"
TERMS = [
    "software development engineer 2027",
    "software development engineer I",
    "software dev engineer I",
    "applied scientist I",
    "early career software",
    "university software development engineer",
]


def fetch(s, cfg, company) -> list[Job]:
    seen: dict[str, Job] = {}
    for term in TERMS:
        params = {"base_query": term, "country[]": "USA", "result_limit": 100, "offset": 0, "sort": "recent"}
        data = get_json(s, API, params=params, timeout=60)
        for j in data.get("jobs", []):
            path = j.get("job_path")
            if not path or path in seen:
                continue
            desc = "\n\n".join(p for p in [
                strip_html(j.get("description_short")),
                "Basic qualifications:\n" + strip_html(j.get("basic_qualifications")) if j.get("basic_qualifications") else "",
                "Preferred qualifications:\n" + strip_html(j.get("preferred_qualifications")) if j.get("preferred_qualifications") else "",
            ] if p)
            seen[path] = Job.make(
                url="https://www.amazon.jobs" + path,
                company="Amazon",
                title=j.get("title", ""),
                locations=[j.get("normalized_location")] if j.get("normalized_location") else [],
                source="amazon",
                posted_at=long_date_to_date(j.get("posted_date")),
                meta={
                    "job_family": j.get("job_family"), "job_category": j.get("job_category"),
                    "university_job": str(j.get("university_job")) not in ("None", "False", "", "0"),
                    "amazon_id": j.get("id_icims") or j.get("id"),
                    "fetch": {"kind": "amazon", "path": path},
                },
                description=desc or None,
            )
    return list(seen.values())
