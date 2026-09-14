"""Minimal GitHub Issues client. Uses GITHUB_TOKEN (Actions) or `gh auth token` locally."""
from __future__ import annotations

import os
import subprocess
from typing import Optional

import requests

from .util import log

API = "https://api.github.com"
MAX_BODY = 60000


def resolve_token() -> Optional[str]:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


class GitHub:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "new-grad-radar",
        })

    def _url(self, path: str) -> str:
        return f"{API}/repos/{self.repo}{path}"

    def ensure_label(self, name: str, color: str, description: str) -> None:
        r = self.s.get(self._url(f"/labels/{name}"), timeout=20)
        if r.status_code == 200:
            return
        r = self.s.post(self._url("/labels"), json={"name": name, "color": color, "description": description}, timeout=20)
        if r.status_code not in (200, 201, 422):
            log.warning("could not create label %s: %s %s", name, r.status_code, r.text[:200])

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        if len(body) > MAX_BODY:
            body = body[:MAX_BODY - 200] + "\n\n_(truncated; the full list is on the dashboard)_"
        r = self.s.post(self._url("/issues"), json={"title": title, "body": body, "labels": labels}, timeout=30)
        r.raise_for_status()
        return r.json()

    def list_open_issues(self, label: str) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            r = self.s.get(self._url("/issues"), params={"labels": label, "state": "open", "per_page": 100, "page": page}, timeout=30)
            r.raise_for_status()
            items = [i for i in r.json() if "pull_request" not in i]
            out.extend(items)
            if len(items) < 100:
                break
            page += 1
        return out

    def close_issue(self, number: int) -> None:
        r = self.s.patch(self._url(f"/issues/{number}"), json={"state": "closed", "state_reason": "completed"}, timeout=30)
        if not r.ok:
            log.warning("could not close issue #%s: %s", number, r.status_code)
