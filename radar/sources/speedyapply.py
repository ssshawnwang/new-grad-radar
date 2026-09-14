"""speedyapply 2027 new-grad markdown tables (SWE and AI lists)."""
from __future__ import annotations

import re

from ..models import Job
from ..util import strip_html, relative_age_to_date

SWE_URL = "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_USA.md"
AI_URL = "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main/NEW_GRAD_USA.md"

_HREF = re.compile(r'href="([^"]+)"')
_SECTION = re.compile(r"^###\s+(.*)$")


def _parse(md: str, source: str) -> list[Job]:
    out: list[Job] = []
    section = ""
    for line in md.splitlines():
        m = _SECTION.match(line.strip())
        if m:
            section = m.group(1).strip()
            continue
        if not line.startswith("| <a") and not line.startswith("| **"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) < 6:
            continue
        company = strip_html(cells[0]).strip("* ")
        title = strip_html(cells[1])
        location = strip_html(cells[2])
        salary = strip_html(cells[3])
        m2 = _HREF.search(cells[4])
        if not m2:
            continue
        url = m2.group(1)
        age = strip_html(cells[5])
        locations = [l.strip() for l in re.split(r"\s*(?:;|/|\|)\s*", location) if l.strip()] or [location]
        out.append(Job.make(
            url=url, company=company, title=title, locations=locations, source=source,
            posted_at=relative_age_to_date(age),
            meta={"salary": salary or None, "section": section, "age": age},
        ))
    return out


def _fetch(s, url: str, source: str) -> list[Job]:
    r = s.get(url, timeout=60)
    r.raise_for_status()
    return _parse(r.text, source)


def fetch_swe(s, cfg, company=None) -> list[Job]:
    return _fetch(s, SWE_URL, "speedyapply_swe")


def fetch_ai(s, cfg, company=None) -> list[Job]:
    return _fetch(s, AI_URL, "speedyapply_ai")
