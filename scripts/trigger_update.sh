#!/usr/bin/env sh
# Ask GitHub to run the data workflow now.
#
# GitHub's scheduled workflows are best-effort: on a busy Saturday they can be an
# hour or more late, or skipped. A workflow you dispatch by hand starts straight
# away, so run this from any always-on machine (a NAS, a media server, a Pi) and
# GitHub's own schedule becomes the fallback rather than the main clock.
#
# crontab -e, on the always-on machine:
#   */5 8-21 * * 6   /path/to/trigger_update.sh fast   # Saturday, every 5 minutes
#   */15 9-19 * * 0  /path/to/trigger_update.sh fast   # Sunday
#
#   fast = fixtures and top scorers (what changes during a match day)
#   all  = those plus the league tables (slower, and the schedule covers it hourly)
#
# Needs a GitHub fine-grained token with "Actions: read and write" on the repo,
# in GITHUB_TOKEN. Keep it in a file only this user can read, e.g.:
#   echo 'export GITHUB_TOKEN=github_pat_...' > ~/.clubscript-token
#   chmod 600 ~/.clubscript-token
# and have cron run: . ~/.clubscript-token && /path/to/trigger_update.sh fast
set -eu

REPO="${CLUBSCRIPT_REPO:-edturner/SAHCscoreBoard}"
WORKFLOW="${CLUBSCRIPT_WORKFLOW:-fixtures.yml}"
BRANCH="${CLUBSCRIPT_BRANCH:-main}"
SCOPE="${1:-fast}"

: "${GITHUB_TOKEN:?set GITHUB_TOKEN to a token with Actions: read and write}"

response="$(mktemp)"
trap 'rm -f "$response"' EXIT

status="$(curl -sS -o "$response" -w '%{http_code}' \
    -X POST "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -d "{\"ref\":\"$BRANCH\",\"inputs\":{\"scope\":\"$SCOPE\"}}")"

if [ "$status" = "204" ]; then
    echo "$(date -u +%FT%TZ) dispatched $WORKFLOW ($SCOPE) on $REPO"
else
    echo "$(date -u +%FT%TZ) dispatch failed: HTTP $status $(cat "$response")" >&2
    exit 1
fi
