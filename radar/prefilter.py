"""Cheap, deterministic screening before any model call."""
from __future__ import annotations

import re

from .companies import Watchlist
from .locations import us_status, only_in, any_preferred
from .models import Job
from .util import days_since

COMMUNITY_SOURCES = {"simplify", "speedyapply_swe", "speedyapply_ai"}
_PHD = re.compile(r"\bph\.?\s?d\b", re.I)
_NOT_PHD_ONLY = re.compile(r"\b(ms|m\.s\.|master|masters|master's|bs|b\.s\.|bachelor|bachelor's|advanced degree|bs/ms|ms/phd)\b", re.I)
_INTERN = re.compile(r"\b(intern(ship)?s?|co-?ops?)\b", re.I)


def _rx(cfg: dict, key: str) -> re.Pattern:
    return re.compile(cfg["roles"][key], re.I)


def screen(job: Job, cfg: dict, watchlist: Watchlist) -> dict:
    title = job.title or ""
    reasons: list[str] = []

    if not _rx(cfg, "include_title").search(title):
        reasons.append("role_mismatch")
    if _rx(cfg, "exclude_title").search(title) or _INTERN.search(title):
        reasons.append("excluded_title")
    if cfg["roles"].get("exclude_phd_only", True) and _PHD.search(title) and not _NOT_PHD_ONLY.search(title):
        reasons.append("phd_only")
    degrees = set((job.meta or {}).get("degrees") or [])
    if degrees and degrees == {"PhD"}:
        reasons.append("phd_only")
    if not watchlist.level_exception(job.company) and _rx(cfg, "exclude_level").search(title):
        reasons.append("level_not_entry")

    community = job.source in COMMUNITY_SOURCES or (job.meta or {}).get("community")
    if not community and not _rx(cfg, "newgrad_title").search(title):
        reasons.append("no_newgrad_signal")
    # Community lists keep postings "active" for months; skip the very old ones.
    # Direct sources are exempt because Lever/Greenhouse dates reflect evergreen reqs.
    max_age = cfg["roles"].get("max_age_days_community")
    if community and max_age:
        age = days_since(job.posted_at)
        if age is not None and age > int(max_age):
            reasons.append("stale")

    us = us_status(job.locations)
    if us is False:
        reasons.append("not_us")
    exclude_only = cfg["locations"].get("exclude_only") or []
    if exclude_only and only_in(job.locations, exclude_only):
        reasons.append("excluded_location_only")
    preferred = any_preferred(job.locations, cfg["locations"].get("preferred") or [])

    # Dedupe reasons, keep order.
    seen = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    return {"passed": not reasons, "reasons": reasons, "us": us, "preferred": preferred, "title": title}
