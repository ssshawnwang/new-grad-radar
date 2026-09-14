"""Fetch a job description for classification, using the ATS API when the URL reveals one."""
from __future__ import annotations

import re
from typing import Optional

from .models import Job
from .sources import greenhouse, ashby, lever, smartrecruiters, workday, apple, eightfold
from .util import strip_html, log

_GH = re.compile(r"greenhouse\.io/(?:embed/job_app\?.*?token=|)([a-z0-9_-]+)/jobs/(\d+)", re.I)
_GH_JID = re.compile(r"[?&]gh_jid=(\d+)")
_LEVER = re.compile(r"jobs\.lever\.co/([a-z0-9_-]+)/([0-9a-f-]{36})", re.I)
_ASHBY = re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_.-]+)/([0-9a-f-]{36})", re.I)
_WD = re.compile(r"https://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)(/job/.+)$", re.I)


def fetch_description(s, job: Job, max_chars: int) -> Optional[str]:
    text = _fetch(s, job)
    if text:
        text = text.strip()
        return text[:max_chars]
    return None


def _fetch(s, job: Job) -> Optional[str]:
    if job.description:
        return job.description
    f = (job.meta or {}).get("fetch") or {}
    try:
        kind = f.get("kind")
        if kind == "greenhouse":
            return greenhouse.fetch_description(s, f["token"], f["id"])
        if kind == "workday":
            d = workday.fetch_detail(s, f["host"], f["tenant"], f["site"], f["path"])
            if d.get("posted_at"):
                job.posted_at = d["posted_at"]
            if d.get("locations"):
                job.locations = d["locations"]
            return d.get("description")
        if kind == "smartrecruiters":
            return smartrecruiters.fetch_description(s, f["ref"])
        if kind == "apple":
            return apple.fetch_description(s, f["pid"])
        if kind == "eightfold":
            return eightfold.fetch_description(s, f["host"], f["domain"], f["variant"], f["id"])
    except Exception as e:  # noqa: BLE001
        log.info("description via API failed for %s: %s", job.url, e)

    url = job.url
    try:
        m = _GH.search(url)
        if m:
            return greenhouse.fetch_description(s, m.group(1), m.group(2))
        m = _GH_JID.search(url)
        if m:
            # e.g. stripe.com/jobs/search?gh_jid=123 -> board token unknown; try the company name slug.
            token = re.sub(r"[^a-z0-9]", "", job.company.lower())
            return greenhouse.fetch_description(s, token, m.group(1))
        m = _LEVER.search(url)
        if m:
            return lever.fetch_description(s, m.group(1), m.group(2))
        m = _ASHBY.search(url)
        if m:
            return ashby.fetch_description(s, m.group(1), m.group(2))
        m = _WD.search(url)
        if m:
            tenant, wd, site, path = m.group(1), m.group(2), m.group(3), m.group(4)
            d = workday.fetch_detail(s, f"{tenant}.{wd}.myworkdayjobs.com", tenant, site, path)
            if d.get("posted_at"):
                job.posted_at = d["posted_at"]
            return d.get("description")
    except Exception as e:  # noqa: BLE001
        log.info("description via URL pattern failed for %s: %s", url, e)

    # Generic HTML fallback (best effort; many sites render client-side).
    try:
        r = s.get(url, timeout=12, headers={"Accept": "text/html"})
        if r.ok and "text/html" in r.headers.get("content-type", ""):
            text = strip_html(r.text)
            return text if len(text) > 400 else None
    except Exception as e:  # noqa: BLE001
        log.debug("generic fetch failed for %s: %s", url, e)
    return None
