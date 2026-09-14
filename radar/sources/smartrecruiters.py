"""SmartRecruiters public postings API."""
from __future__ import annotations

from ..models import Job
from ..util import get_json, iso_to_date, strip_html

API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"


def fetch(s, cfg, company) -> list[Job]:
    token = company["token"]
    out: list[Job] = []
    offset = 0
    while True:
        data = get_json(s, API.format(token=token), params={"limit": 100, "offset": offset}, timeout=60)
        items = data.get("content", [])
        for j in items:
            loc = j.get("location") or {}
            loc_str = ", ".join(p for p in [loc.get("city"), loc.get("region"), loc.get("country")] if p)
            if loc.get("remote"):
                loc_str = (loc_str + " (Remote)").strip()
            out.append(Job.make(
                url=f"https://jobs.smartrecruiters.com/{token}/{j['id']}",
                company=company["name"],
                title=j.get("name", ""),
                locations=[loc_str] if loc_str else [],
                source=f"smartrecruiters:{token}",
                posted_at=iso_to_date(j.get("releasedDate")),
                meta={"fetch": {"kind": "smartrecruiters", "ref": j.get("ref")},
                      "department": (j.get("department") or {}).get("label"),
                      "experience_level": (j.get("experienceLevel") or {}).get("label")},
            ))
        offset += len(items)
        if not items or offset >= int(data.get("totalFound", 0)) or offset > 2000:
            break
    return out


def fetch_description(s, ref: str) -> str | None:
    data = get_json(s, ref, timeout=30)
    sections = (data.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
        sec = sections.get(key) or {}
        if sec.get("text"):
            parts.append((sec.get("title") or key) + "\n" + strip_html(sec["text"]))
    return "\n\n".join(parts) or None
