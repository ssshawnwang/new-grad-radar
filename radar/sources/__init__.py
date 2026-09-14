"""Source adapters. Each exposes fetch(session, cfg, company) -> list[Job].

Community sources (simplify, speedyapply_*) ignore `company`.
Direct sources take a companies.yaml entry.
"""
from __future__ import annotations

from . import simplify, speedyapply, greenhouse, ashby, lever, smartrecruiters, workday, amazon, apple, eightfold

COMMUNITY = {
    "simplify": simplify.fetch,
    "speedyapply_swe": speedyapply.fetch_swe,
    "speedyapply_ai": speedyapply.fetch_ai,
}

DIRECT = {
    "greenhouse": greenhouse.fetch,
    "ashby": ashby.fetch,
    "lever": lever.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workday": workday.fetch,
    "amazon": amazon.fetch,
    "apple": apple.fetch,
    "eightfold": eightfold.fetch,
}
