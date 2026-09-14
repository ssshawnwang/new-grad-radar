"""Lever public postings API."""
from __future__ import annotations

from ..models import Job
from ..util import get_json, epoch_to_date, strip_html

API = "https://api.lever.co/v0/postings/{token}"


def _description(j: dict) -> str:
    parts = [j.get("descriptionPlain") or "", j.get("descriptionBodyPlain") or ""]
    for lst in j.get("lists") or []:
        parts.append((lst.get("text") or "") + "\n" + strip_html(lst.get("content")))
    parts.append(j.get("additionalPlain") or "")
    return "\n\n".join(p for p in parts if p.strip())


def _to_job(j: dict, company_name: str, token: str) -> Job:
    cats = j.get("categories") or {}
    locs = list(cats.get("allLocations") or []) or ([cats["location"]] if cats.get("location") else [])
    return Job.make(
        url=j.get("hostedUrl") or f"https://jobs.lever.co/{token}/{j['id']}",
        company=company_name,
        title=j.get("text", ""),
        locations=locs,
        source=f"lever:{token}",
        posted_at=epoch_to_date(j.get("createdAt")),
        meta={"team": cats.get("team"), "commitment": cats.get("commitment"),
              "country": j.get("country"), "workplace": j.get("workplaceType")},
        description=_description(j),
    )


def fetch(s, cfg, company) -> list[Job]:
    token = company["token"]
    data = get_json(s, API.format(token=token), params={"mode": "json"}, timeout=60)
    return [_to_job(j, company["name"], token) for j in data]


def fetch_description(s, token: str, posting_id: str) -> str | None:
    data = get_json(s, API.format(token=token) + f"/{posting_id}", timeout=30)
    return _description(data) or None
