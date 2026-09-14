"""Export docs/jobs.json for the static dashboard in docs/index.html."""
from __future__ import annotations

import json
from pathlib import Path

from .models import Job
from .util import iso_now


def _compact(j: Job) -> dict:
    c = j.classification or {}
    return {
        "id": j.id,
        "company": j.company,
        "title": j.title,
        "url": j.url,
        "locations": j.locations,
        "posted": j.posted_at,
        "first_seen": (j.first_seen or "")[:10],
        "tier": j.tier,
        "source": j.source.split(":")[0],
        "preferred": bool((j.prefilter or {}).get("preferred")),
        "eligible": c.get("eligible"),
        "bucket": c.get("bucket"),
        "seniority": c.get("seniority"),
        "resume": c.get("resume"),
        "fit": c.get("fit"),
        "sponsorship": c.get("sponsorship"),
        "citizenship": c.get("citizenship_required"),
        "phd": c.get("requires_phd"),
        "start": c.get("start"),
        "confidence": c.get("confidence"),
        "reason": c.get("reason"),
        "classified": bool(c) and "error" not in c,
    }


def export(jobs: list[Job], health: dict, stats: dict, out_dir: str | Path = "docs") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    visible = [j for j in jobs if j.active and (j.prefilter or {}).get("passed")]
    visible.sort(key=lambda j: (j.first_seen or "", j.posted_at or ""), reverse=True)
    head = {"generated_at": iso_now(), "stats": stats, "health": health}
    # One job per line so hourly commits diff by line instead of rewriting one giant line.
    lines = [json.dumps(_compact(j), ensure_ascii=False, separators=(",", ":")) for j in visible]
    text = "{" + ",".join(f"\"{k}\":{json.dumps(v, ensure_ascii=False, separators=(',', ':'))}" for k, v in head.items()) \
        + ",\n\"jobs\":[\n" + ",\n".join(lines) + "\n]}\n"
    path = out / "jobs.json"
    path.write_text(text, encoding="utf-8")
    return path
