#!/usr/bin/env bash
# One manual radar round on your Claude Code login (Pro/Max), no API key:
#   fetch -> screen -> classify with `claude -p` -> alert issues -> digest issue -> commit & push data/docs
#
#   ./round.sh               full round
#   ./round.sh --dry-run     classify, but post no issues and commit nothing
#   ./round.sh --limit 50    classify at most 50 postings this round
set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-.venv/bin/python}
[ -x "$PY" ] || PY=python3

DRY=0
for a in "$@"; do [ "$a" = "--dry-run" ] && DRY=1; done

# Never let a metered key shadow the subscription login for this round.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN

command -v claude >/dev/null || { echo "claude CLI not found; install Claude Code and run 'claude' once to log in" >&2; exit 1; }

"$PY" -m radar run --force --backend claude_code "$@"

if [ "$DRY" = 1 ]; then
  "$PY" -m radar digest --force --dry-run --skip-empty
  echo "dry run: nothing posted, nothing committed"
  exit 0
fi

"$PY" -m radar digest --force --skip-empty

git add data docs
if git diff --cached --quiet; then
  echo "no changes to commit"
  exit 0
fi
git commit -q -m "radar: $(date -u +%Y-%m-%dT%H:%MZ) (manual round)"
git pull -q --rebase --autostash origin main
git push -q origin main
echo "pushed; the dashboard updates within a minute"
