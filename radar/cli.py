from __future__ import annotations

import argparse
import json
import logging
import re
import sys

from .util import session, log


def _cmd_run(args):
    from .pipeline import run
    out = run(force=args.force, no_classify=args.no_classify, no_alerts=args.no_alerts,
              limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(out, indent=1))


def _cmd_digest(args):
    from .pipeline import digest
    out = digest(force=args.force, dry_run=args.dry_run)
    print(json.dumps(out, indent=1))


def _cmd_stats(args):
    from .store import Store
    from .render import summarize_counts
    store = Store().load()
    print(json.dumps(summarize_counts(store.jobs.values()), indent=1))
    by_src = {}
    for j in store.active():
        by_src[j.source.split(":")[0]] = by_src.get(j.source.split(":")[0], 0) + 1
    print(json.dumps(by_src, indent=1))


def _cmd_fetch(args):
    from . import sources
    from .companies import Watchlist
    from .pipeline import load_config
    cfg = load_config()
    s = session()
    if args.source in sources.COMMUNITY:
        jobs = sources.COMMUNITY[args.source](s, cfg, None)
    else:
        wl = Watchlist.load()
        entry = next((e for e in wl.entries if e["name"].lower() == args.source.lower()), None)
        if not entry or entry.get("ats", "none") == "none":
            sys.exit(f"unknown source or company without a pollable platform: {args.source}")
        jobs = sources.DIRECT[entry["ats"]](s, cfg, entry)
    print(f"{len(jobs)} postings")
    for j in jobs[: args.limit]:
        print(f"- {j.company} | {j.title} | {'; '.join(j.locations)} | {j.posted_at} | {j.url}")


def _probe(s, name: str) -> dict | None:
    slugs = []
    base = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    slugs.append(base.replace(" ", ""))
    slugs.append(base.replace(" ", "-"))
    seen = set()
    for slug in [x for x in slugs if not (x in seen or seen.add(x))]:
        probes = [
            ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", lambda d: d.get("jobs")),
            ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}", lambda d: d.get("jobs")),
            ("lever", f"https://api.lever.co/v0/postings/{slug}?mode=json", lambda d: d if isinstance(d, list) else None),
            ("smartrecruiters", f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", lambda d: d.get("content") if d.get("totalFound") else None),
        ]
        for ats, url, pick in probes:
            try:
                r = s.get(url, timeout=15)
                if r.status_code != 200:
                    continue
                items = pick(r.json())
                if items:
                    return {"ats": ats, "token": slug, "count": len(items)}
            except Exception:  # noqa: BLE001
                continue
    return None


def _cmd_add_company(args):
    s = session()
    found = _probe(s, args.name)
    block = [f"\n- name: {args.name}", f"  tier: {args.tier}"]
    if found:
        block += [f"  ats: {found['ats']}", f"  token: {found['token']}"]
        print(f"found {found['ats']} board '{found['token']}' with {found['count']} postings")
    else:
        block += ["  ats: none  # no public board found; covered via community lists"]
        print("no Greenhouse/Ashby/Lever/SmartRecruiters board found under that name; added with ats: none")
    with open("companies.yaml", "a", encoding="utf-8") as f:
        f.write("\n".join(block) + "\n")
    print("appended to companies.yaml")


def main(argv=None):
    p = argparse.ArgumentParser(prog="radar", description="new-grad job posting radar")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="fetch, screen, classify, alert, export dashboard")
    r.add_argument("--force", action="store_true", help="ignore the peak/off-peak schedule gate")
    r.add_argument("--no-classify", action="store_true")
    r.add_argument("--no-alerts", action="store_true")
    r.add_argument("--limit", type=int, default=None, help="max postings to classify this run")
    r.add_argument("--dry-run", action="store_true", help="do not create GitHub issues")
    r.set_defaults(fn=_cmd_run)

    d = sub.add_parser("digest", help="post the daily digest issue")
    d.add_argument("--force", action="store_true", help="ignore the digest hour")
    d.add_argument("--dry-run", action="store_true", help="print instead of posting")
    d.set_defaults(fn=_cmd_digest)

    st = sub.add_parser("stats", help="print store statistics")
    st.set_defaults(fn=_cmd_stats)

    f = sub.add_parser("fetch", help="fetch one source and print postings (debug)")
    f.add_argument("source", help="simplify | speedyapply_swe | speedyapply_ai | <Company name from companies.yaml>")
    f.add_argument("--limit", type=int, default=30)
    f.set_defaults(fn=_cmd_fetch)

    a = sub.add_parser("add-company", help="probe public job boards and append a company to companies.yaml")
    a.add_argument("name")
    a.add_argument("--tier", type=int, default=2)
    a.set_defaults(fn=_cmd_add_company)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.fn(args)


if __name__ == "__main__":
    main()
