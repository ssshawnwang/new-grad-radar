"""Markdown rendering for digest and alert issues."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from .models import Job

BUCKET_LABEL = {"sde": "Software engineering", "ml": "Machine learning / AI", "adjacent": "Adjacent roles", "other": "Other"}


def flags(job: Job) -> list[str]:
    c = job.classification or {}
    out = []
    if c.get("sponsorship") == "no":
        out.append("⚠️ no sponsorship")
    if c.get("citizenship_required"):
        out.append("⚠️ citizenship required")
    if c.get("requires_phd"):
        out.append("🎓 PhD")
    if c.get("start") == "2026":
        out.append("📅 2026 start")
    if (job.prefilter or {}).get("preferred"):
        out.append("📍 preferred location")
    if c.get("confidence") == "low":
        out.append("❔ judged from title only")
    return out


def job_line(job: Job) -> str:
    c = job.classification or {}
    locs = "; ".join(job.locations[:4]) + (" …" if len(job.locations) > 4 else "")
    head = f"- **{job.company}** — [{job.title}]({job.url})"
    bits = [b for b in [locs or None, f"posted {job.posted_at}" if job.posted_at else None] if b]
    if bits:
        head += " · " + " · ".join(bits)
    fl = flags(job)
    if fl:
        head += " · " + " · ".join(fl)
    if c and "fit" in c:
        head += f"\n  {c.get('resume', 'SDE')} resume · fit {c['fit']} · {c.get('reason', '').strip()}"
    return head


def _sort_key(job: Job):
    c = job.classification or {}
    return (
        0 if job.tier == 1 else 1,
        0 if (job.prefilter or {}).get("preferred") else 1,
        -int(c.get("fit", 0)),
        job.posted_at or "",
    )


def render_digest(jobs: list[Job], unclassified: list[Job], health: dict, date_label: str,
                  dashboard_url: str | None, max_items: int) -> tuple[str, str]:
    jobs = sorted(jobs, key=_sort_key)
    shown = jobs[:max_items]
    title = f"Digest {date_label}: {len(jobs)} new posting{'s' if len(jobs) != 1 else ''}"
    lines = [f"## New eligible postings since the last digest: {len(jobs)}"]
    if dashboard_url:
        lines.append(f"Dashboard: {dashboard_url}")
    lines.append("")

    tier1 = [j for j in shown if j.tier == 1]
    if tier1:
        lines.append(f"### Tier-1 companies ({len(tier1)})")
        lines.extend(job_line(j) for j in tier1)
        lines.append("")
    rest = [j for j in shown if j.tier != 1]
    for bucket in ("sde", "ml", "adjacent"):
        group = [j for j in rest if (j.classification or {}).get("bucket") == bucket]
        if group:
            lines.append(f"### {BUCKET_LABEL[bucket]} ({len(group)})")
            lines.extend(job_line(j) for j in group)
            lines.append("")
    if len(jobs) > max_items:
        lines.append(f"_{len(jobs) - max_items} more are on the dashboard._")
        lines.append("")
    if unclassified:
        lines.append(f"### Not yet classified ({len(unclassified)})")
        lines.append("_These passed the keyword screen but no model verdict is available yet (missing API key or rate limit)._")
        lines.extend(job_line(j) for j in unclassified[:40])
        if len(unclassified) > 40:
            lines.append(f"_… and {len(unclassified) - 40} more._")
        lines.append("")

    bad = {k: v for k, v in (health or {}).items() if not v.get("ok")}
    if bad:
        lines.append("### Source problems")
        for k, v in bad.items():
            lines.append(f"- `{k}`: {v.get('error', 'failed')}")
        lines.append("")
    if not jobs and not unclassified:
        lines.append("Nothing new. Quiet day.")
    return title, "\n".join(lines)


def render_alert(jobs: list[Job]) -> tuple[str, str]:
    jobs = sorted(jobs, key=_sort_key)
    if len(jobs) == 1:
        j = jobs[0]
        title = f"🚨 {j.company}: {j.title}"
    else:
        companies = Counter(j.company for j in jobs)
        top = ", ".join(c for c, _ in companies.most_common(3))
        title = f"🚨 {len(jobs)} new tier-1 postings: {top}"
    body = "\n".join(job_line(j) for j in jobs)
    return title, body


def summarize_counts(jobs: Iterable[Job]) -> dict:
    c = Counter()
    for j in jobs:
        c["active"] += j.active
        if j.prefilter and j.prefilter.get("passed"):
            c["screened_in"] += 1
        if j.classification and j.classification.get("eligible"):
            c["eligible"] += 1
    return dict(c)
