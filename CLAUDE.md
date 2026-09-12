# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```powershell
# Install dependencies
pip install requests

# The API key is read from the environment and is never committed
$env:GMS_API_KEY = "<key>"

# Serve frontend locally
python -m http.server 8000
# Then open: http://localhost:8000/apps/scoreboard/homeFixtures.html

# Fetch this weekend's fixtures (weekend_fixtures.json + mens/womens CSVs)
python scripts/eh_api.py weekend

# A specific weekend
python scripts/eh_api.py weekend --weekend 2026-09-19

# League standings (rotates teamData.json -> teamData.prev.json)
python scripts/eh_api.py league
python scripts/eh_api.py league --no-rotate     # leave the previous snapshot alone

# Seasons; the current one is marked with *
python scripts/eh_api.py seasons

# Top scorers (writes data/scorers/scorers.json and its fixture cache)
python scripts/top_scorers.py --print
```

### Legacy gmsfeed commands

`gms_fetcher.py` scrapes gmsfeed.co.uk and needs no API key. It is the fallback, not the
default -- it returns less complete data (see Pipeline 1 below).

```powershell
# Refresh competition IDs (only the legacy path uses teamCompIDs.json)
python scripts/gms_fetcher.py competitions --team-file config/teamIDs.json --output config/teamCompIDs.json

python scripts/gms_fetcher.py update-scoreboard --config config/teamCompIDs.json
python scripts/live_league_updater.py --once
python scripts/gms_fetcher.py team-summary --team-id <uuid> --comp-id <uuid>
```

There are no automated tests. Manual verification means loading the HTML pages in a browser and
checking the browser console for fetch errors. When changing a fetcher, run both implementations
to a scratch directory and diff the output — that is how the API migration was validated.

## Architecture

Two pipelines feed a static-file GitHub Pages site. Both have an API implementation
(`scripts/eh_api.py`, the default) and a legacy gmsfeed scraper (`scripts/gms_fetcher.py`).

### The API client — `scripts/eh_api.py`

Talks to England Hockey's GMS data warehouse at `https://ehdwapi.englandhockey.co.uk/api/`,
authenticated with an `x-api-key` header read from `GMS_API_KEY`. Paths are
`{resource}/{uuid}/{action}` and are keyed on the same team UUIDs already in `teamIDs.json`.

Two traps worth knowing, both handled in the code:

- `clubs/{clubId}/matchdays` looks like a whole-season feed but embeds fixtures for
  **nextMatchDay only**; the rest are empty date placeholders. Full-season data comes from
  `teams/{teamId}/fixturesandresults`, one call per team.
- That club endpoint covers only the club's **area** competitions. Teams in national leagues
  (the 1st XIs, in the EHL Conferences) never appear, so any configured team missing from a
  day's response is looked up individually.

League tables come from `competitiongroups/{competitionGroupId}/tables` — keyed on the
competition *group*, not the competition, and paginated. Rows carry `teamId`, so no name
matching. There is no PPG field; it is computed as `totalPoints / gamesPlayed`.

### Pipeline 1 — Scoreboard (Fixtures & Results)

`eh_api.py weekend` fetches `clubs/{clubId}/matchdays/{date}` for Saturday and Sunday, filters
to teams listed in `teamIDs.json`, and writes `data/scoreboard/weekend_fixtures.json` plus the
two CSVs. Home vs away is decided by comparing `homeClubId` to the configured `club_id`, and
men/women comes from the team object's `gender`.

The legacy `gms_fetcher.py update-scoreboard` instead scrapes each team's HTML, identifies the
club's team by name prefix, and merges against the existing JSON as a rollback guard (a fixture
that was `"Played"` is never downgraded to `"Scheduled"`). Because it matches on name, it
collapses teams that share a division: on 2026-09-19 it returned 13 of 17 teams, dropping the
6th and 7th XIs in both genders. The API path returned all 17.

The frontend (`apps/scoreboard/fixtures.js`) fetches `weekend_fixtures.json` and re-renders
every 5 minutes. `<body data-side="home|away">` picks the list, which is split into MEN and WOMEN
panels by `category` because GMS names two same-numbered squads identically; under a panel heading
our team is just "3s". A result that was not there at the previous refresh gets a brief highlight, tracked
in memory by `fixtureId`. Games on the weekend's second day (usually the 1st XIs, whose national
leagues often play on Sunday) get a small day tag over the kick-off time, and the pill shows both dates.

### Pipeline 2 — League of Leagues

`eh_api.py league` reads every team's season, looks each team up in its competition group's
table, derives form from played fixtures (newest first — the page renders the first five badges),
and writes `data/league/teamData.json`, rotating the old file to `teamData.prev.json`.

Rotation is **skipped** if any configured team is missing, so a partial snapshot can never become
the baseline the movement arrows compare against.

The frontend (`apps/league/league.js`) loads both files, sorts by PPG (ties: goal difference,
then squad number, so a pre-season table reads 1s, 2s, 3s) and compares ranks against the previous
snapshot for the up / down arrows; unchanged teams get no arrow. If `teamData.prev.json` is
missing it falls back to `teamData.lastGameweek.json`. Form is drawn oldest to newest left to
right, the reverse of the data's order.

### Pipeline 3 — Top Scorers

`scripts/top_scorers.py` reads every configured team's season (the same per-team feed as the
league), fetches `fixtures/{id}` for each played fixture and counts our team's FG / PC / PS events.
Coverage depends entirely on captains completing GMS team sheets. Players without GMS `consent` are
skipped, and member IDs are replaced by a truncated SHA-256, so nothing beyond the public display
name is committed. Detail for fixtures older than 14 days is reused from
`data/scorers/fixture_goals.json`. "On the day" is the latest weekend with results, Sunday included.
It runs in `fixtures.yml` on every slot, including the Saturday five-minute one, with
`continue-on-error` so a scorer failure never blocks the fixtures and league commit. Each run
re-reads only today's fixtures, plus any inside the 14-day window still missing a team sheet or
goals, so the steady-state cost is a handful of requests. `--last-season --output <file>` looks back at 2025-26 via the
competition IDs in git history.

### Match-day trigger

GitHub's scheduled runs are best-effort and on a busy Saturday have been over an hour apart, so
`scripts/trigger_update.sh` lets any always-on machine dispatch `fixtures.yml` on a cron instead;
the schedules stay as the fallback. Its `scope` input is `fast` (fixtures + scorers) or `all`
(those plus league tables), and the league step is skipped on a `fast` dispatch.

### Screens — shared frontend

All five screens share `apps/shared/styles.css` (one design system: Barlow for text, TT
Bluescreens for titles, flat navy panels, one accent colour: orange, or white on the away screen via `.board--away`) and `apps/shared/board.js` (fetching, text fitting,
squad labels, the 5-minute refresh). `board.js` also reads the footer's club name from
`config/club.json`. `topScorers.html` reads `data/scorers/scorers.json`, written by `scripts/top_scorers.py` (Pipeline 3).

### Config dependency

`config/club.json` holds the club's display name, `short_name` and `club_id`.

- `club_id` is the club's GMS UUID. The API path uses it for the match-day endpoint and to decide
  home vs away.
- `short_name` is the prefix GMS uses in fixture team names (e.g. `"St Albans"`). Only the legacy
  scraper depends on it. Note that `fetch_team_record`'s 1st-XI rename tests for `"st albans (m)"`
  but GMS returns `"St Albans"`, so **that branch has never fired** — the 1st XI has always been
  published without a squad number, and `eh_api.py` deliberately reproduces that.

`config/teamIDs.json` is the source of truth for team UUIDs and is all the API path needs.

`config/teamCompIDs.json` is **generated** from it and is used only by the legacy gmsfeed path.
The API path resolves competitions per team, so it needs no annual regeneration.

`GMS_API_KEY` must be set in the environment locally and as a GitHub Actions secret for CI.

### GitHub Pages path rewriting

The HTML/JS files use relative paths suited for the `apps/` directory structure (`../../data/`, `../../config/`, `../shared/styles.css`, `../shared/board.js`). `pages.yml` copies everything flat into `_site/` (plus `config/club.json`) and rewrites those paths with `sed` so the site works when served from the Pages root. If paths break on the live site, check the `sed` substitutions in `pages.yml`.

