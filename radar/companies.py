"""Watchlist loading and company-name matching."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

_SUFFIXES = re.compile(r"\b(inc|llc|corp|corporation|co|ltd|limited|plc|technologies|technology|labs|group|holdings)\b\.?")


def normalize(name: str) -> str:
    t = (name or "").lower()
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = _SUFFIXES.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


class Watchlist:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self._exact: dict[str, dict] = {}
        for e in entries:
            for n in [e["name"], *(e.get("aliases") or [])]:
                self._exact[normalize(n)] = e

    @classmethod
    def load(cls, path: str | Path = "companies.yaml") -> "Watchlist":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        for e in data:
            e.setdefault("tier", 2)
            e.setdefault("ats", "none")
            e.setdefault("aliases", [])
        return cls(data)

    def match(self, company_name: str) -> Optional[dict]:
        n = normalize(company_name)
        if not n:
            return None
        if n in self._exact:
            return self._exact[n]
        # "google deepmind" -> google; "amazon web services aws" -> amazon
        for key, e in self._exact.items():
            if len(key) >= 4 and (n.startswith(key + " ") or n.endswith(" " + key)):
                return e
        return None

    def direct(self) -> list[dict]:
        return [e for e in self.entries if e.get("ats") and e["ats"] != "none"]

    def level_exception(self, company_name: str) -> bool:
        e = self.match(company_name)
        return bool(e and e.get("level_exception"))
