# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```powershell
# Install dependencies
pip install requests beautifulsoup4 pytz

# Serve frontend locally
python -m http.server 8000
# Then open: http://localhost:8000/apps/scoreboard/homeFixtures.html

# Refresh competition IDs (run pre-season when divisions change)
python scripts/gms_fetcher.py competitions --team-file config/teamIDs.json --output config/teamCompIDs.json

# Fetch this weekend's fixtures and update scoreboard JSON/CSV
python scripts/gms_fetcher.py update-scoreboard --config config/teamCompIDs.json

# Fetch for a specific weekend
python scripts/gms_fetcher.py update-scoreboard --config config/teamCompIDs.json --weekend 2026-03-07

# Fetch a full league snapshot and rotate snapshots
python scripts/gms_fetcher.py bulk-team-data `
    --config config/teamCompIDs.json `
    --output data/league/teamData.json `
    --publish-path data/league/teamData.json `
    --rotate-snapshots `
    --snapshot-date 2026-03-07

# Validate current and previous league snapshots
python scripts/gms_fetcher.py validate-snapshots `
    --current data/league/teamData.json `
    --previous data/league/teamData.prev.json `
    --expect-count 17

# Run league updater once (same as what CI does)
python scripts/live_league_updater.py --once

# Debug a single team's data
python scripts/gms_fetcher.py team-summary --team-id <uuid> --comp-id <uuid>
```

There are no automated tests. Manual verification means loading the HTML pages in a browser and checking the browser console for fetch errors.

## Architecture

Two independent pipelines share the same API client and both feed into a static-file GitHub Pages site.

### Pipeline 1 — Scoreboard (Fixtures & Results)

`gms_fetcher.py update-scoreboard` iterates every team in `config/teamCompIDs.json`, calls `show=results+fixtures` on the GMS API for each, filters to the relevant weekend, then merges results against the **existing** `data/scoreboard/weekend_fixtures.json` before overwriting it. The merge step is the rollback guard: if a fixture was `"Played"` in the previous file but the new API response says `"Scheduled"` (or omits it), the old result is kept. Deduplication keys on `(date, time, home_team, away_team)` because multiple teams can return overlapping fixtures.

The frontend (`apps/scoreboard/fixtures.js`) fetches `weekend_fixtures.json` with no-cache headers and re-renders on a 5-minute timer.

### Pipeline 2 — League of Leagues

`gms_fetcher.py bulk-team-data` calls `show=league` for each team, collecting points/PPG/form. On success it rotates the files: `teamData.json` → `teamData.prev.json`, new data → `teamData.json`. Rotation is **skipped entirely** if any team still failed after retries; a fallback copy of the team's previous record (tagged `meta.source: "fallback"`) is inserted instead.

`live_league_updater.py` is a thin wrapper that shells out to `gms_fetcher.py bulk-team-data` with the correct arguments. It exists purely so CI can call one simple script.

The frontend (`apps/league/league.js`) loads both `teamData.json` (current) and `teamData.prev.json` (previous), sorts by PPG, and compares ranks/PPG values to show `movement-up` / `movement-down` / `movement-steady` badges. If `teamData.prev.json` is missing it silently defaults to steady arrows.

### Config dependency

`config/teamIDs.json` is the source of truth for team UUIDs. `config/teamCompIDs.json` is **generated** from it — it pairs each team with its current competition UUID and must be regenerated at the start of each season via the `competitions` command. Both pipelines read `teamCompIDs.json` at runtime.

### GitHub Pages path rewriting

The HTML/JS files use relative paths suited for the `apps/` directory structure (`../../data/`, `../shared/styles.css`). `pages.yml` copies everything flat into `_site/` and rewrites those paths with `sed` so the site works when served from the Pages root. If paths break on the live site, check the `sed` substitutions in `pages.yml`.

