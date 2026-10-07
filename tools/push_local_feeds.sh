#!/usr/bin/env bash
# ADDED 2026-10-07: home-PC half of the "blocked from GitHub Actions" fix.
# Fetches the `fetch: local` feeds (sources.yml) and pushes
# data/local/latest.json; the daily Actions run merges it (radar/collect.py).
# Run by systemd user timer painradar-local-feeds (05:40 + 17:40 London).
# Commits ONLY data/local/latest.json. Safe to run by hand.
set -uo pipefail
cd "$(dirname "$0")/.."
echo "----- $(date '+%F %T %Z') -----"
git pull -q --rebase --autostash || { echo "git pull failed"; exit 1; }
python3 run.py collect-local || { echo "collect-local failed"; exit 1; }
git add data/local/latest.json
if git diff --cached --quiet; then echo "no change"; exit 0; fi
git commit -q -m "data: local feeds $(date -u '+%F %H:%MZ')" -- data/local/latest.json
# CI may have pushed a report meanwhile: one rebase + retry.
git push -q || { git pull -q --rebase --autostash && git push -q; } || { echo "git push failed"; exit 1; }
echo "pushed"
