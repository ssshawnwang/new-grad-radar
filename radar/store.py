"""JSONL state store, one job per line, sorted by id for stable git diffs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from .models import Job


class Store:
    def __init__(self, path: str | Path = "data/jobs.jsonl"):
        self.path = Path(path)
        self.jobs: dict[str, Job] = {}

    def load(self) -> "Store":
        self.jobs = {}
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    self.jobs[rec["id"]] = Job.from_record(rec)
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for jid in sorted(self.jobs):
                f.write(json.dumps(self.jobs[jid].to_record(), ensure_ascii=False, sort_keys=True) + "\n")
        tmp.replace(self.path)

    def get(self, jid: str) -> Optional[Job]:
        return self.jobs.get(jid)

    def put(self, job: Job) -> None:
        self.jobs[job.id] = job

    def active(self) -> Iterable[Job]:
        return (j for j in self.jobs.values() if j.active)

    def __len__(self) -> int:
        return len(self.jobs)
