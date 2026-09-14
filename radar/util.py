from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import requests

log = logging.getLogger("radar")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 new-grad-radar/0.1"
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"})
    return s


def get_json(s: requests.Session, url: str, *, params: Optional[dict] = None, timeout: int = 30,
             retries: int = 2) -> Any:
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = s.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def post_json(s: requests.Session, url: str, body: dict, *, timeout: int = 30, retries: int = 2,
              headers: Optional[dict] = None) -> Any:
    last: Optional[Exception] = None
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        h.update(headers)
    for attempt in range(retries + 1):
        try:
            r = s.post(url, json=body, headers=h, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"POST {url} failed: {last}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def epoch_to_date(v: Any) -> Optional[str]:
    """Epoch seconds or milliseconds -> YYYY-MM-DD."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n > 1e11:  # milliseconds
        n /= 1000.0
    return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%d")


def iso_to_date(s: Optional[str]) -> Optional[str]:
    dt = parse_iso(s)
    return dt.strftime("%Y-%m-%d") if dt else None


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def long_date_to_date(s: Optional[str]) -> Optional[str]:
    """'September 11, 2026' or 'Sep 11, 2026' -> '2026-09-11'."""
    if not s:
        return None
    m = re.match(r"\s*([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4})", s)
    if not m:
        return None
    mon = m.group(1).lower()
    month = _MONTHS.get(mon) or _MONTHS.get(next((k for k in _MONTHS if k.startswith(mon[:3])), ""), None)
    if not month:
        return None
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"


def relative_age_to_date(s: Optional[str]) -> Optional[str]:
    """'3d', '2w', '1mo', 'Posted 3 Days Ago', 'Posted Today' -> YYYY-MM-DD (approx)."""
    if not s:
        return None
    t = s.strip().lower()
    if "today" in t or t in ("0d", "<1d"):
        return now_utc().strftime("%Y-%m-%d")
    if "yesterday" in t:
        return (now_utc() - timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\+?\s*(h|hour|d|day|w|week|mo|month|y|year)", t)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)[0:2]
    days = {"h": 0, "ho": 0, "d": n, "da": n, "w": n * 7, "we": n * 7, "mo": n * 30, "y": n * 365, "ye": n * 365}
    delta = days.get(unit, n)
    return (now_utc() - timedelta(days=delta)).strftime("%Y-%m-%d")


def days_since(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (now_utc() - d).days


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


def strip_html(s: Optional[str]) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h[1-6]>|</tr>", "\n", s)
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = _WS_RE.sub(" ", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    return _NL_RE.sub("\n\n", s).strip()
