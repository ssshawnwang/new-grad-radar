from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "lever-source", "source", "src", "ref", "referrer", "ashby_jid_src",
    "embed", "mobile", "needsRedirect", "icims",
}


def canonical_url(url: str) -> str:
    """Strip tracking params and normalise so the same posting hashes identically."""
    url = (url or "").strip()
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
    path = parts.path.rstrip("/") or "/"
    # Apply-page variants (Amazon /apply, Ashby /application, Lever /apply) point at the same req.
    path = re.sub(r"/(apply|application)$", "", path)
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), path, urlencode(query), ""))


def job_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


@dataclass
class Job:
    id: str
    url: str
    company: str
    title: str
    locations: list[str]
    source: str
    posted_at: Optional[str] = None          # ISO date "YYYY-MM-DD" when known
    meta: dict[str, Any] = field(default_factory=dict)
    first_seen: Optional[str] = None         # ISO datetime UTC
    last_seen: Optional[str] = None
    active: bool = True
    tier: Optional[int] = None               # from companies.yaml, when matched
    watch_company: Optional[str] = None      # canonical company name from companies.yaml
    prefilter: Optional[dict[str, Any]] = None
    classification: Optional[dict[str, Any]] = None
    alerted_at: Optional[str] = None
    digested_at: Optional[str] = None
    # Transient: description text fetched this run, never persisted in full.
    description: Optional[str] = None

    @classmethod
    def make(cls, *, url: str, company: str, title: str, locations: list[str], source: str,
             posted_at: Optional[str] = None, meta: Optional[dict] = None,
             description: Optional[str] = None) -> "Job":
        return cls(
            id=job_id(url),
            url=url.strip(),
            company=(company or "").strip(),
            title=re.sub(r"\s+", " ", (title or "")).strip(),
            locations=[re.sub(r"\s+", " ", l).strip() for l in (locations or []) if l and l.strip()],
            source=source,
            posted_at=posted_at,
            meta=meta or {},
            description=description,
        )

    def to_record(self) -> dict[str, Any]:
        d = asdict(self)
        desc = d.pop("description", None)
        if desc and "description_excerpt" not in d["meta"]:
            d["meta"]["description_excerpt"] = desc[:300]
        return d

    @classmethod
    def from_record(cls, d: dict[str, Any]) -> "Job":
        d = dict(d)
        d.pop("description", None)
        return cls(**d)
