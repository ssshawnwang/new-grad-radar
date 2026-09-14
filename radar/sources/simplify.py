"""SimplifyJobs/New-Grad-Positions machine-readable listings."""
from __future__ import annotations

from ..models import Job
from ..util import get_json, epoch_to_date

URL = "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json"
KEEP_CATEGORIES = {"Software", "Software Engineering", "AI/ML/Data", "Data Science, AI & Machine Learning", "Quant"}


def fetch(s, cfg, company=None) -> list[Job]:
    data = get_json(s, URL, timeout=60)
    out: list[Job] = []
    for j in data:
        if not (j.get("active") and j.get("is_visible", True)):
            continue
        if j.get("category") not in KEEP_CATEGORIES:
            continue
        url = j.get("url") or ""
        if not url.startswith("http"):
            continue
        out.append(Job.make(
            url=url,
            company=j.get("company_name", ""),
            title=j.get("title", ""),
            locations=j.get("locations") or [],
            source="simplify",
            posted_at=epoch_to_date(j.get("date_posted")),
            meta={
                "sponsorship": j.get("sponsorship"),
                "degrees": j.get("degrees") or [],
                "category": j.get("category"),
                "simplify_id": j.get("id"),
                "updated": epoch_to_date(j.get("date_updated")),
            },
        ))
    return out
