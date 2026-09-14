"""Ashby public job board API."""
from __future__ import annotations

from ..models import Job
from ..util import get_json, iso_to_date

API = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def _board(s, token: str) -> list[dict]:
    data = get_json(s, API.format(token=token), timeout=60)
    return data.get("jobs", [])


def _to_job(j: dict, company_name: str, token: str) -> Job:
    locs = []
    if j.get("location"):
        locs.append(j["location"])
    for sec in j.get("secondaryLocations") or []:
        if sec.get("location") and sec["location"] not in locs:
            locs.append(sec["location"])
    country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
    if j.get("isRemote") and not any("remote" in l.lower() for l in locs):
        locs.append("Remote" + (f" in {country}" if country else ""))
    return Job.make(
        url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{token}/{j['id']}",
        company=company_name,
        title=j.get("title", ""),
        locations=locs,
        source=f"ashby:{token}",
        posted_at=iso_to_date(j.get("publishedAt")),
        meta={
            "department": j.get("department"), "team": j.get("team"),
            "employment_type": j.get("employmentType"), "country": country,
            "workplace": j.get("workplaceType"),
        },
        description=j.get("descriptionPlain"),
    )


def fetch(s, cfg, company) -> list[Job]:
    token = company["token"]
    return [_to_job(j, company["name"], token) for j in _board(s, token) if j.get("isListed", True)]


def fetch_description(s, token: str, ashby_id: str) -> str | None:
    for j in _board(s, token):
        if j.get("id") == ashby_id:
            return j.get("descriptionPlain")
    return None
