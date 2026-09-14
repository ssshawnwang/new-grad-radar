"""Orchestration: run (fetch → screen → classify → alert → dashboard) and digest."""
from __future__ import annotations

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import yaml

from . import dashboard, sources
from .classify import Classifier
from .companies import Watchlist
from .descriptions import fetch_description
from .github import GitHub, resolve_token
from .models import Job
from .prefilter import screen, COMMUNITY_SOURCES
from .render import render_alert, render_digest, summarize_counts
from .store import Store
from .util import session, iso_now, now_utc, days_since, log

HEALTH_PATH = Path("data/health.json")


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str = "config.yaml") -> dict:
    """Public defaults from config.yaml, overlaid with private values.

    Private values come from config.private.yaml (gitignored, for local runs) and/or the
    RADAR_PRIVATE_CONFIG_B64 environment variable (base64 of the same YAML, stored as a
    GitHub Actions secret). Both are optional; the later one wins.
    """
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    private_path = Path("config.private.yaml")
    if private_path.exists():
        with open(private_path, "r", encoding="utf-8") as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})
        log.info("loaded config.private.yaml")
    b64 = os.environ.get("RADAR_PRIVATE_CONFIG_B64", "").strip()
    if b64:
        try:
            cfg = _deep_merge(cfg, yaml.safe_load(base64.b64decode(b64).decode("utf-8")) or {})
            log.info("loaded private config from environment")
        except Exception as e:  # noqa: BLE001
            log.error("RADAR_PRIVATE_CONFIG_B64 could not be decoded: %s", e)
    return cfg


def repo_name(cfg: dict) -> str | None:
    return os.environ.get("GITHUB_REPOSITORY") or (cfg.get("github") or {}).get("repo")


def dashboard_url(cfg: dict) -> str | None:
    repo = repo_name(cfg)
    if not repo or "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


def in_schedule(cfg: dict, force: bool = False) -> bool:
    """Hourly during peak season, every N hours after."""
    if force:
        return True
    sch = cfg.get("schedule") or {}
    tz = ZoneInfo(sch.get("timezone", "America/New_York"))
    now = datetime.now(tz)
    peak_until = sch.get("peak_until")
    if peak_until and now.date() <= datetime.strptime(str(peak_until), "%Y-%m-%d").date():
        return True
    every = int(sch.get("offpeak_every_hours", 6))
    return now.hour % every == 0


def _fetch_all(cfg: dict, watchlist: Watchlist) -> tuple[list[Job], dict]:
    s = session()
    fetched: list[Job] = []
    health: dict[str, dict] = {}
    enabled = cfg.get("sources") or {}

    for name, fn in sources.COMMUNITY.items():
        if not enabled.get(name, True):
            continue
        try:
            jobs = fn(s, cfg, None)
            for j in jobs:
                j.meta["community"] = True
            fetched.extend(jobs)
            health[name] = {"ok": True, "count": len(jobs), "at": iso_now()}
            log.info("%s: %d postings", name, len(jobs))
        except Exception as e:  # noqa: BLE001
            health[name] = {"ok": False, "error": str(e)[:300], "at": iso_now()}
            log.warning("%s failed: %s", name, e)

    if enabled.get("direct", True):
        for company in watchlist.direct():
            fn = sources.DIRECT.get(company["ats"])
            if not fn:
                continue
            key = f"{company['ats']}:{company['name']}"
            try:
                jobs = fn(s, cfg, company)
                fetched.extend(jobs)
                health[key] = {"ok": True, "count": len(jobs), "at": iso_now()}
                log.info("%s: %d postings", key, len(jobs))
            except Exception as e:  # noqa: BLE001
                health[key] = {"ok": False, "error": str(e)[:300], "at": iso_now()}
                log.warning("%s failed: %s", key, e)
    return fetched, health


def _merge(store: Store, fetched: list[Job], health: dict, watchlist: Watchlist) -> tuple[list[Job], set[str]]:
    now = iso_now()
    seen_ids: set[str] = set()
    new_jobs: list[Job] = []
    for job in fetched:
        seen_ids.add(job.id)
        match = watchlist.match(job.company)
        if match:
            job.tier = match["tier"]
            job.watch_company = match["name"]
        existing = store.get(job.id)
        if existing is None:
            job.first_seen = now
            job.last_seen = now
            store.put(job)
            new_jobs.append(job)
            continue
        # Prefer direct-source metadata over community-list metadata. Community lists spell the
        # same title differently, so only a direct source may overwrite an established title,
        # and only a materially different title invalidates an existing verdict.
        direct_new = job.source not in COMMUNITY_SOURCES
        direct_old = existing.source not in COMMUNITY_SOURCES
        title_changed = direct_new and _norm_title(existing.title) != _norm_title(job.title)
        if direct_new or (not direct_old and not existing.classification):
            existing.title = job.title
            existing.locations = job.locations or existing.locations
            existing.source = job.source
        if job.posted_at and (not existing.posted_at or direct_new):
            existing.posted_at = job.posted_at
        merged_meta = dict(existing.meta or {})
        merged_meta.update({k: v for k, v in job.meta.items() if v not in (None, "", [])})
        srcs = set(merged_meta.get("sources") or [existing.source])
        srcs.add(job.source)
        merged_meta["sources"] = sorted(srcs)
        existing.meta = merged_meta
        existing.description = job.description or existing.description
        existing.last_seen = now
        existing.active = True
        if match:
            existing.tier = match["tier"]
            existing.watch_company = match["name"]
        if title_changed:
            existing.prefilter = None
            existing.classification = None
    # Deactivate jobs whose source was fetched fine but no longer lists them.
    for job in store.jobs.values():
        if job.id in seen_ids or not job.active:
            continue
        key = job.source if job.source in COMMUNITY_SOURCES else None
        if key is None:
            # direct sources are keyed "ats:Company" in health; find by prefix
            ats = job.source.split(":")[0]
            key = next((k for k in health if k.startswith(ats + ":") and (job.watch_company or "") in k), None)
        if key and health.get(key, {}).get("ok"):
            job.active = False
    return new_jobs, seen_ids


def _classify(store: Store, cfg: dict, watchlist: Watchlist, limit: int | None) -> dict:
    stats = {"attempted": 0, "classified": 0, "skipped_no_key": False}
    candidates = [j for j in store.active() if (j.prefilter or {}).get("passed") and not j.classification]
    candidates.sort(key=lambda j: (0 if j.tier == 1 else 1, -(int((j.posted_at or "0000").replace("-", "")) if j.posted_at else 0)))
    cap = limit if limit is not None else int(cfg["classify"].get("max_per_run", 400))
    candidates = candidates[:cap]
    stats["pending"] = len(candidates)
    if not candidates:
        return stats
    if not Classifier.available():
        log.warning("ANTHROPIC_API_KEY not set; skipping classification of %d postings", len(candidates))
        stats["skipped_no_key"] = True
        return stats
    clf = Classifier(cfg)
    max_chars = int(cfg["classify"].get("description_max_chars", 12000))
    workers = max(1, int(cfg["classify"].get("workers", 4)))
    auth_failed = False

    def work(job: Job):
        s = session()
        desc = fetch_description(s, job, max_chars)
        return job, clf.classify(job, desc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, job) for job in candidates]
        for fut in as_completed(futures):
            stats["attempted"] += 1
            try:
                job, result = fut.result()
            except anthropic.AuthenticationError:
                if not auth_failed:
                    log.error("ANTHROPIC_API_KEY was rejected (401); skipping classification this run")
                auth_failed = True
                stats["auth_failed"] = True
                continue
            except Exception as e:  # noqa: BLE001
                log.warning("classification worker failed: %s", e)
                continue
            if result is None:
                continue
            job.classification = result
            stats["classified"] += 1
    stats["calls"] = clf.calls
    stats["input_tokens"] = clf.input_tokens
    stats["output_tokens"] = clf.output_tokens
    log.info("classified %d/%d (tokens in=%d out=%d)", stats["classified"], stats["attempted"], clf.input_tokens, clf.output_tokens)
    return stats


def _alerts(store: Store, cfg: dict, gh: GitHub | None, dry_run: bool) -> int:
    acfg = cfg.get("alerts") or {}
    if not acfg.get("enabled", True):
        return 0
    max_age = int(acfg.get("max_posting_age_days", 7))
    due = []
    for j in store.active():
        c = j.classification or {}
        if j.tier != 1 or j.alerted_at or not c.get("eligible"):
            continue
        if c.get("bucket") not in ("sde", "ml"):
            continue
        age = days_since(j.posted_at)
        if age is not None and age > max_age:
            j.alerted_at = "skipped:stale"
            continue
        due.append(j)
    if not due:
        return 0
    title, body = render_alert(due)
    if dry_run or gh is None:
        log.info("ALERT (not sent): %s\n%s", title, body)
        return len(due)
    label = (cfg.get("github") or {}).get("labels", {}).get("alert", "alert")
    gh.ensure_label(label, "d73a4a", "Instant alert for a tier-1 posting")
    issue = gh.create_issue(title, body, [label])
    log.info("alert issue #%s: %s", issue.get("number"), title)
    stamp = iso_now()
    for j in due:
        j.alerted_at = stamp
    return len(due)


def run(*, force: bool = False, no_classify: bool = False, no_alerts: bool = False,
        limit: int | None = None, dry_run: bool = False) -> dict:
    cfg = load_config()
    if not in_schedule(cfg, force):
        log.info("outside schedule window; nothing to do")
        return {"skipped": "schedule"}
    watchlist = Watchlist.load()
    store = Store().load()

    fetched, health = _fetch_all(cfg, watchlist)
    new_jobs, _ = _merge(store, fetched, health, watchlist)
    for j in store.active():
        if j.prefilter is None or j.prefilter.get("title") != j.title:
            j.prefilter = screen(j, cfg, watchlist)
    # Screening is deterministic and cheap, so rejected postings with no history are not kept.
    for jid in [k for k, j in store.jobs.items()
                if not (j.prefilter or {}).get("passed") and not j.classification and not j.alerted_at and not j.digested_at]:
        del store.jobs[jid]

    cls_stats = {} if no_classify else _classify(store, cfg, watchlist, limit)

    gh = None
    repo = repo_name(cfg)
    token = resolve_token()
    if repo and token and not dry_run:
        gh = GitHub(repo, token)
    alerted = 0 if no_alerts else _alerts(store, cfg, gh, dry_run)

    counts = summarize_counts(store.jobs.values())
    new_kept = sum(1 for j in new_jobs if j.id in store.jobs)
    counts.update({"new_this_run": new_kept, "fetched": len(fetched), "alerted": alerted, "classify": cls_stats})
    dashboard.export(list(store.jobs.values()), health, counts)
    store.save()
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps({"at": iso_now(), "sources": health, "stats": counts}, indent=1), encoding="utf-8")
    log.info("run complete: %s", json.dumps(counts))
    return counts


def digest(*, force: bool = False, dry_run: bool = False) -> dict:
    cfg = load_config()
    dcfg = cfg.get("digest") or {}
    tz = ZoneInfo(dcfg.get("timezone", "America/New_York"))
    now_local = datetime.now(tz)
    if not force and now_local.hour != int(dcfg.get("hour", 9)):
        log.info("not digest hour in %s (now %s); skipping", tz, now_local.strftime("%H:%M"))
        return {"skipped": "hour"}
    store = Store().load()
    eligible, unclassified = [], []
    for j in store.active():
        if not (j.prefilter or {}).get("passed") or j.digested_at:
            continue
        c = j.classification
        if c and "error" not in c:
            if c.get("eligible") and c.get("bucket") in ("sde", "ml", "adjacent"):
                eligible.append(j)
            else:
                j.digested_at = "skipped:not_eligible"
        else:
            unclassified.append(j)
    health = {}
    if HEALTH_PATH.exists():
        health = json.loads(HEALTH_PATH.read_text(encoding="utf-8")).get("sources", {})
    title, body = render_digest(eligible, unclassified, health, now_local.strftime("%Y-%m-%d"),
                                dashboard_url(cfg), int(dcfg.get("max_items", 150)))
    if dry_run:
        print(f"# {title}\n\n{body}")
        return {"eligible": len(eligible), "unclassified": len(unclassified), "dry_run": True}
    repo, token = repo_name(cfg), resolve_token()
    if not (repo and token):
        raise SystemExit("digest needs a GitHub repo and token (GITHUB_TOKEN or `gh auth login`)")
    gh = GitHub(repo, token)
    label = (cfg.get("github") or {}).get("labels", {}).get("digest", "digest")
    gh.ensure_label(label, "0e8a16", "Daily digest of new eligible postings")
    issue = gh.create_issue(title, body, [label])
    log.info("digest issue #%s: %s", issue.get("number"), title)
    stamp = iso_now()
    for j in eligible:
        j.digested_at = stamp
    # Keep the issue list tidy.
    keep_days = int(dcfg.get("close_after_days", 7))
    for old in gh.list_open_issues(label):
        if old.get("number") == issue.get("number"):
            continue
        created = old.get("created_at", "")
        if created and days_since(created[:10]) is not None and days_since(created[:10]) >= keep_days:
            gh.close_issue(old["number"])
    store.save()
    return {"eligible": len(eligible), "unclassified": len(unclassified), "issue": issue.get("html_url")}
