"""Ask Claude whether a posting fits the candidate. One structured call per new posting.

Two interchangeable backends produce the same verdict dict:
  Classifier           Anthropic API via the SDK (metered by an API key).
  ClaudeCodeClassifier `claude -p`, Claude Code headless mode, on the Claude Code login
                       (Pro/Max subscription or CLAUDE_CODE_OAUTH_TOKEN). No per-token bill.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional

import anthropic

from .models import Job
from .util import iso_now, log

SCHEMA = {
    "type": "object",
    "properties": {
        "eligible": {"type": "boolean",
                     "description": "True if the candidate described in the system prompt can realistically apply: entry-level or new-grad scope, not PhD-only, not an internship, degree timing compatible."},
        "seniority": {"type": "string", "enum": ["new_grad", "early_career", "mid", "senior", "intern", "unclear"]},
        "bucket": {"type": "string", "enum": ["sde", "ml", "adjacent", "other"],
                   "description": "sde = software engineering; ml = machine learning / applied science / research engineering / AI engineering; adjacent = data scientist, data engineer, forward deployed, quant dev, solutions/ML platform roles worth a look; other = not relevant."},
        "resume": {"type": "string", "enum": ["SDE", "MLE"], "description": "Which resume variant to send."},
        "requires_phd": {"type": "boolean"},
        "sponsorship": {"type": "string", "enum": ["offers", "no", "unclear"],
                        "description": "'no' only if the posting says it will not sponsor or requires citizenship/permanent residency."},
        "citizenship_required": {"type": "boolean"},
        "start": {"type": "string", "enum": ["2027", "2026", "rolling", "unclear"],
                  "description": "Program start year if stated; 'rolling' for ordinary open reqs."},
        "us": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "fit": {"type": "integer",
                "description": "Overall fit for this candidate from 0 to 100, considering role, seniority, skills, and location preferences."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"],
                       "description": "Low when no description was available."},
        "reason": {"type": "string", "description": "One sentence, at most 200 characters, in plain words."},
    },
    "required": ["eligible", "seniority", "bucket", "resume", "requires_phd", "sponsorship",
                 "citizenship_required", "start", "us", "fit", "confidence", "reason"],
    "additionalProperties": False,
}


def _system_prompt(cfg: dict) -> str:
    c = cfg["candidate"]
    loc = cfg["locations"]
    return (
        "You screen job postings for one specific job seeker and return a structured verdict.\n\n"
        f"Candidate: {c['summary'].strip()}\n"
        f"Graduation: {c['graduation']}. Earliest start: {c['earliest_start']}. "
        f"Needs visa sponsorship: {'yes' if c.get('needs_sponsorship') else 'no'}.\n"
        f"Location preferences: United States only. {loc.get('preferred_summary') or ('Prefers ' + ', '.join(loc.get('preferred', [])[:8]))} "
        f"Will not take a role that is only in {', '.join(loc.get('exclude_only', []))}.\n\n"
        "Rules of thumb:\n"
        "- 'New grad', 'university grad', 'early career', 'entry level', '2027 start', 'campus', level I/1, "
        "'Level 3' at Snap, 'Software Engineer II' at Walmart, 'AMTS' at Salesforce, 'Analyst' at banks are entry-level.\n"
        "- 'Software Engineer II' elsewhere, L4+, Senior, Staff, and anything asking for 3+ years of experience is not.\n"
        "- A posting that lists a PhD as required is not eligible; 'MS or PhD' or 'advanced degree' is eligible.\n"
        "- Postings labelled '2026 start' may still accept December 2026 graduates; mark start='2026' and judge eligibility normally.\n"
        "- Applied Scientist I at Amazon and Data & Applied Sciences at Microsoft accept MS candidates.\n"
        "- If no description is given, judge from the title, company and metadata and set confidence='low'.\n"
        "- bucket 'ml' covers machine learning engineer, applied scientist, research engineer, AI engineer, "
        "deep learning, ML infrastructure/platform, LLM roles. 'sde' covers general software, backend, infrastructure, "
        "full stack, systems, distributed systems. 'adjacent' covers data scientist, data engineer, forward deployed "
        "engineer, quant developer, solutions engineer with heavy coding. Everything else is 'other'.\n"
        "- resume='MLE' for bucket ml and for data-science-flavoured adjacent roles; otherwise 'SDE'.\n"
        "- fit: weigh seniority match, bucket, skills overlap with the candidate's background, preferred locations, "
        "and sponsorship. Non-eligible postings should score under 30.\n"
        "- The 'reason' field is published on a public page. Describe only the posting itself: its level, "
        "requirements, location, and what kind of background it suits. Never mention the candidate's degree, "
        "graduation date, citizenship, visa or sponsorship situation, or any other personal attribute. "
        "Write 'requires US citizenship', not 'the candidate is not a citizen'.\n"
        "Respond with JSON only, matching the provided schema."
    )


def _user_content(job: Job, description: Optional[str]) -> str:
    meta = job.meta or {}
    hints = []
    if meta.get("sponsorship") and meta["sponsorship"] != "Other":
        hints.append(f"Listed sponsorship note: {meta['sponsorship']}")
    if meta.get("degrees"):
        hints.append(f"Listed degrees: {', '.join(meta['degrees'])}")
    if meta.get("salary"):
        hints.append(f"Listed salary: {meta['salary']}")
    if job.tier:
        hints.append(f"Watchlist tier: {job.tier}")
    if meta.get("university_job"):
        hints.append("Amazon flags this as a university job")
    body = description.strip() if description else "(no description available)"
    return (
        f"Company: {job.company}\n"
        f"Title: {job.title}\n"
        f"Locations: {'; '.join(job.locations) or 'unknown'}\n"
        f"Posted: {job.posted_at or 'unknown'}\n"
        f"Source: {job.source}\n"
        + ("\n".join(hints) + "\n" if hints else "")
        + f"\nDescription:\n{body}"
    )


class Classifier:
    def __init__(self, cfg: dict):
        self.cfg = cfg["classify"]
        self.model = self.cfg.get("model", "claude-opus-5")
        self.effort = self.cfg.get("effort", "medium")
        self.use_fallback = bool(self.cfg.get("server_side_fallback", True))
        self.system = [{"type": "text", "text": _system_prompt(cfg), "cache_control": {"type": "ephemeral"}}]
        self.client = anthropic.Anthropic(max_retries=3)
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def _request(self, messages: list[dict], with_fallback: bool):
        kwargs = dict(
            model=self.model,
            max_tokens=4096,
            system=self.system,
            messages=messages,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if with_fallback:
            return self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        return self.client.messages.create(**kwargs)

    def classify(self, job: Job, description: Optional[str]) -> Optional[dict]:
        messages = [{"role": "user", "content": _user_content(job, description)}]
        try:
            try:
                resp = self._request(messages, self.use_fallback)
            except anthropic.BadRequestError as e:
                if self.use_fallback and ("fallback" in str(e).lower() or "beta" in str(e).lower()):
                    log.warning("server-side fallback rejected; retrying without it (%s)", e.message)
                    self.use_fallback = False
                    resp = self._request(messages, False)
                else:
                    raise
        except anthropic.AuthenticationError:
            raise
        except anthropic.RateLimitError as e:
            log.warning("rate limited: %s", e)
            return None
        except anthropic.APIStatusError as e:
            log.warning("API error %s for %s: %s", e.status_code, job.url, e.message)
            return None
        except anthropic.APIConnectionError as e:
            log.warning("network error for %s: %s", job.url, e)
            return None

        self.calls += 1
        usage = getattr(resp, "usage", None)
        if usage:
            self.input_tokens += (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
                + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
            self.output_tokens += usage.output_tokens or 0

        if resp.stop_reason == "refusal":
            return {"error": "refusal", "model": resp.model, "classified_at": iso_now()}
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("unparseable classification for %s: %r", job.url, text[:200])
            return None
        data["model"] = resp.model
        data["classified_at"] = iso_now()
        data["had_description"] = bool(description)
        return data


class ClassifierAuthError(RuntimeError):
    """The classification backend has no usable credentials."""


class ClassifierRateLimited(RuntimeError):
    """The backend's usage limit was reached; remaining postings stay pending for the next round."""


CLAUDE_BIN = os.environ.get("RADAR_CLAUDE_BIN", "claude")
_METERED_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class ClaudeCodeClassifier:
    """Same verdicts as Classifier, but every call is one `claude -p` subprocess.

    Anthropic allows subscription (claude.ai) credentials only inside Claude Code itself, not
    with the SDK, so this shells out to the CLI instead of reusing the client above. The
    child runs with no tools, no MCP servers, no settings files and no session persistence,
    and with ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN removed so the CLI cannot quietly fall
    back to a metered key. Structured output comes from --json-schema.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg["classify"]
        self.model = self.cfg.get("model", "claude-opus-5")
        self.effort = self.cfg.get("effort", "medium")
        self.timeout = int(self.cfg.get("claude_code_timeout", 180))
        self.system = _system_prompt(cfg)
        self.schema = json.dumps(SCHEMA)
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.halted = False

    @staticmethod
    def available() -> bool:
        return shutil.which(CLAUDE_BIN) is not None

    def _command(self) -> list[str]:
        return [
            CLAUDE_BIN, "-p",
            "--model", self.model,
            "--effort", self.effort,
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--no-session-persistence",
            "--output-format", "json",
            "--json-schema", self.schema,
            "--system-prompt", self.system,
        ]

    def _check_fatal(self, msg: str) -> None:
        low = msg.lower()
        if "not logged in" in low or "/login" in low or "invalid api key" in low or "authentication" in low:
            raise ClassifierAuthError(msg[:300])
        if "limit" in low and any(w in low for w in ("usage", "rate", "reached", "hit", "exceed", "resets")):
            self.halted = True
            raise ClassifierRateLimited(msg[:300])

    def classify(self, job: Job, description: Optional[str]) -> Optional[dict]:
        if self.halted:
            return None
        env = {k: v for k, v in os.environ.items() if k not in _METERED_KEYS}
        try:
            proc = subprocess.run(self._command(), input=_user_content(job, description), capture_output=True,
                                  text=True, timeout=self.timeout, env=env)
        except subprocess.TimeoutExpired:
            log.warning("claude -p timed out after %ss for %s", self.timeout, job.url)
            return None
        except OSError as e:
            raise ClassifierAuthError(f"cannot run {CLAUDE_BIN}: {e}") from e
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            msg = (proc.stderr or proc.stdout or "").strip()
            self._check_fatal(msg)
            log.warning("claude -p returned no JSON for %s (exit %s): %s", job.url, proc.returncode, msg[:300])
            return None
        if out.get("is_error") or out.get("subtype") != "success":
            msg = str(out.get("result") or out.get("error") or out.get("subtype") or "unknown error")
            self._check_fatal(msg)
            log.warning("claude -p failed for %s: %s", job.url, msg[:300])
            return None

        self.calls += 1
        u = out.get("usage") or {}
        self.input_tokens += (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) \
            + (u.get("cache_creation_input_tokens") or 0)
        self.output_tokens += u.get("output_tokens") or 0
        used = list((out.get("modelUsage") or {}).keys())
        model = used[0] if used else self.model

        verdict = out.get("structured_output")
        if not isinstance(verdict, dict) or "eligible" not in verdict:
            # Finished without a schema-shaped answer (e.g. a refusal). Record it so the
            # posting is listed as unclassified rather than retried every round.
            log.warning("no structured verdict for %s: %r", job.url, str(out.get("result"))[:200])
            return {"error": "no_verdict", "model": model, "classified_at": iso_now()}
        data = dict(verdict)
        data["model"] = model
        data["classified_at"] = iso_now()
        data["had_description"] = bool(description)
        return data


BACKENDS = ("auto", "api", "claude_code")


def pick_backend(cfg: dict, override: Optional[str] = None) -> Optional[str]:
    """Resolve classify.backend (or a CLI override) to a usable backend name, or None."""
    want = (override or cfg["classify"].get("backend") or "auto").lower()
    if want not in BACKENDS:
        raise ValueError(f"unknown classify backend {want!r}; expected one of {BACKENDS}")
    if want == "api":
        return "api" if Classifier.available() else None
    if want == "claude_code":
        return "claude_code" if ClaudeCodeClassifier.available() else None
    if Classifier.available():
        return "api"
    if ClaudeCodeClassifier.available():
        return "claude_code"
    return None


def make_classifier(cfg: dict, backend: str):
    return Classifier(cfg) if backend == "api" else ClaudeCodeClassifier(cfg)
