"""Greenhouse job board API (public, no auth)."""
from __future__ import annotations

from ..models import Job
from ..util import get_json, iso_to_date, strip_html

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(s, cfg, company) -> list[Job]:
    token = company["token"]
    data = get_json(s, API.format(token=token), timeout=60)
    out: list[Job] = []
    for j in data.get("jobs", []):
        locs = []
        if j.get("location", {}).get("name"):
            locs.append(j["location"]["name"])
        for o in j.get("offices") or []:
            if o.get("name") and o["name"] not in locs:
                locs.append(o["name"])
        out.append(Job.make(
            url=j.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{j['id']}",
            company=company["name"],
            title=j.get("title", ""),
            locations=locs,
            source=f"greenhouse:{token}",
            posted_at=iso_to_date(j.get("first_published") or j.get("updated_at")),
            meta={
                "fetch": {"kind": "greenhouse", "token": token, "id": j.get("id")},
                "departments": [d.get("name") for d in (j.get("departments") or []) if d.get("name")],
                "requisition_id": j.get("requisition_id"),
            },
        ))
    return out


def fetch_description(s, token: str, job_id) -> str | None:
    data = get_json(s, API.format(token=token) + f"/{job_id}", timeout=30)
    return strip_html(data.get("content")) or None
