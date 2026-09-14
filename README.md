# new-grad-radar

Watches US tech career sites for **new-grad software and machine-learning postings**, asks Claude whether each one fits a specific candidate, and delivers the results three ways:

- **Daily digest** at 9am Eastern, posted as a GitHub Issue (GitHub emails it to whoever watches the repo).
- **Instant alerts** for tier-1 companies, also as Issues, within an hour of the posting appearing.
- **Dashboard** at `https://<owner>.github.io/<repo>/` listing every open eligible posting with filters.

No servers, no email credentials. Everything runs on GitHub Actions; the only secret is an Anthropic API key.

## How it works

```
community lists ──┐
  Simplify JSON   │
  speedyapply MD  │      keyword screen         Claude verdict            outputs
                  ├──► (title, level, US,  ──► (eligible? SDE/ML?  ──► digest issue
direct polling ───┘     PhD-only, location)     sponsorship? fit)       alert issue
  Greenhouse · Ashby · Lever · SmartRecruiters                          docs/jobs.json
  Workday · Amazon · Apple · Eightfold (Microsoft, Netflix)
```

1. **Collect.** Two community-maintained new-grad lists (SimplifyJobs/New-Grad-Positions and speedyapply's SWE and AI lists) plus direct polling of every company in `companies.yaml` whose hiring platform exposes a public JSON endpoint. Google, Meta, Uber and TikTok have no such endpoint and arrive through the community lists.
2. **Screen.** Cheap regex rules drop senior, intern, PhD-only, non-US and mid-level titles (`config.yaml` → `roles`). Nothing is sent to the model until it passes.
3. **Classify.** Claude reads the job description once per new posting and returns a structured verdict: eligible or not, SDE / ML / adjacent, which resume to send, sponsorship language, start year, and a fit score. Only new postings cost anything; unchanged postings are never re-sent.
4. **Deliver.** Eligible tier-1 postings that are less than a week old trigger an alert issue immediately. Everything else waits for the morning digest. The dashboard is a static page reading `docs/jobs.json`.

State lives in `data/jobs.jsonl` (one posting per line, committed after every run), so the repository is its own database.

## Use it for yourself

1. **Fork** this repository. Keep it public if you want the free GitHub Pages dashboard.
2. **Settings → Secrets and variables → Actions**: add `ANTHROPIC_API_KEY`. Consider a dedicated Anthropic workspace with a monthly spend cap.
3. **Settings → Pages**: source "Deploy from a branch", branch `main`, folder `/docs`.
4. **Settings → Actions → General**: workflow permissions "Read and write".
5. Describe yourself **privately**. Copy the `candidate` and `locations` blocks from `config.yaml` into a new `config.private.yaml` (gitignored) with your real degree, timing, skills, visa situation and preferred cities. Then store it as a second secret so Actions can use it:
   ```bash
   base64 < config.private.yaml | tr -d '\n' | gh secret set RADAR_PRIVATE_CONFIG_B64
   ```
   The public `config.yaml` keeps only generic defaults and the screening rules; edit it for digest hour, timezone and keyword rules. Edit `companies.yaml` to change the watchlist and tiers.
6. **Watch** the repository (or subscribe to issues) so GitHub emails you the digests and alerts. Anyone else who wants the emails watches the repo too.
7. Run the `radar` workflow once by hand from the Actions tab to fill the dashboard.

### Add a company

```bash
python -m radar add-company "Figma" --tier 1
```

This probes Greenhouse, Ashby, Lever and SmartRecruiters for a public board under that name and appends the entry to `companies.yaml`. If nothing is found the company is still tracked through the community lists; you can also fill in `ats`, `token`, `workday` or `eightfold` fields by hand (see the comments at the top of `companies.yaml`).

### Run locally

```bash
uv venv --python 3.12 && uv pip install -r requirements.txt   # or python -m venv + pip
export ANTHROPIC_API_KEY=...                                    # optional; skip to only screen
python -m radar run --force --dry-run       # fetch, screen, classify; no issues created
python -m radar digest --force --dry-run    # print what the digest would say
python -m radar fetch Stripe                # debug one source
python -m radar stats
```

Without an API key the pipeline still fetches, screens and fills the dashboard; postings simply show as "unclassified" until a key is present.

## Schedule and cost

- `radar.yml` runs hourly. During peak season (until `schedule.peak_until` in `config.yaml`) every run does work; afterwards only every `offpeak_every_hours`.
- `digest.yml` runs at 13:05 and 14:05 UTC and posts only when it is 9am in the configured timezone.
- Model cost is per new posting, roughly 2,500 input and a few hundred output tokens each. At the default `claude-opus-5` that is about one to two cents per posting; a season of daily new-grad postings runs on the order of a hundred dollars, the first backlog pass about twenty. Set `classify.model` to `claude-haiku-4-5` for roughly a fifth of that.
- GitHub Actions, Pages and Issues are free for public repositories.

## Safety notes

- The API key is only ever read from the environment; it is never written to the repo or the logs.
- Workflows request only `contents: write` and `issues: write`, and do not run on pull requests, so forks cannot read the secret.
- Only public job data is stored. Nothing about applications, contacts or personal status is in the repo; the candidate profile lives in a gitignored file and a secret, and the model is instructed to describe postings, never the person, in the published verdicts.
- Sources that break (a company changes platform, a runner IP gets blocked) are reported in `data/health.json`, on the dashboard footer, and in the digest, without failing the run.

## Layout

```
config.yaml           candidate profile, screening rules, schedule
companies.yaml        watchlist with platform ids and tiers
radar/sources/        one adapter per platform
radar/prefilter.py    keyword screen
radar/classify.py     Claude call with a JSON schema
radar/pipeline.py     run / digest orchestration
radar/render.py       issue markdown
docs/                 dashboard (index.html + generated jobs.json)
data/                 jobs.jsonl state + health.json
.github/workflows/    radar.yml (hourly) · digest.yml (daily)
```

## License

MIT
