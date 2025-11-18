## SAHC ScoreBoard

Unified data pipeline, automation, and static assets for St Albans Hockey Club’s digital displays:

- **Scoreboard fixtures** – 1080×1920 portrait layouts for home/away boards that refresh every five minutes.
- **League of Leagues** – combined men’s/women’s league table that highlights movement week-to-week.
- **Data collectors** – Python utilities and GitHub Actions that keep JSON snapshots fresh.

---

### Directory Layout

```
apps/
  scoreboard/        # home/away HTML + fixtures.js
  league/            # leagueOfLeagues.html + league.js
  shared/            # styles.css, fonts/, images/ shared by both apps
config/              # teamIDs.json + teamCompIDs.json (GMS config)
data/
  scoreboard/        # weekend_fixtures.json + csv exports + exclusions.json
  league/            # teamData.json + teamData.prev.json snapshots
  raw/               # matches_data_*.html (source dumps from stalbanshc.co.uk)
docs/                # deep dives (see docs/scoreboard.md & docs/league.md)
scripts/             # main.py (HTML fetcher), filter.py (fixtures builder), gms_fetcher.py
.github/workflows/   # fixtures.yml + scores.yml automation
```

Static assets live under `apps/`; data and configs stay under `data/` and `config/` so they can be synced or deployed independently.

---

### Pipelines at a Glance

#### Scoreboard (fixtures/results)
1. `python scripts/main.py` – pulls the latest `/matches` page HTML into `data/raw/matches_data_<timestamp>.html`.
2. `python scripts/filter.py [--start dd/mm/YYYY --end dd/mm/YYYY]` – parses the freshest raw HTML, filters out kids/TBC fixtures, applies exclusions from `data/scoreboard/exclusions.json`, then exports:
   - `data/scoreboard/weekend_fixtures.json` (consumed by `fixtures.js`)
   - `data/scoreboard/mens_fixtures.csv` / `womens_fixtures.csv` (optional reference)
   - `data/scoreboard/full_json_data.json` (debug snapshot)
3. `apps/scoreboard/*.html` + `fixtures.js` load `../../data/scoreboard/weekend_fixtures.json` and refresh every five minutes.
4. GitHub Actions (`.github/workflows/fixtures.yml` and `scores.yml`) run the same scripts on a schedule so the JSON stays current without manual pushes.

Detailed operator notes live in `docs/scoreboard.md`.

#### League of Leagues
1. `python scripts/gms_fetcher.py competitions --team-file config/teamIDs.json` (pre-season) produces `config/teamCompIDs.json`.
2. `python scripts/gms_fetcher.py bulk-team-data --config config/teamCompIDs.json --output data/league/teamData.new.json --publish-path data/league/teamData.json --rotate-snapshots` refreshes weekly stats and automatically rolls `teamData.prev.json`.
3. `python scripts/gms_fetcher.py validate-snapshots --current data/league/teamData.json --previous data/league/teamData.prev.json --expect-count <N>` ensures both snapshots look sane before publishing.
4. `apps/league/league.js` fetches `../../data/league/teamData.json` (+ `.prev`) to build the combined table, flagging rank/PPG deltas.

Deep dive (API behaviour, retries, trend logic) remains in `docs/league-data-workflow.md`, with a shorter quick-start in `docs/league.md`.

---

### Local Development
- Use Python 3.11+ (Actions run on `python-version: "3.x"`). Install dependencies from `requirements.txt` if present, otherwise `pip install requests beautifulsoup4 pytz`.
- Serve the HTML files via any static server (or open directly) from the repo root so relative paths to `apps/shared` and `data/...` resolve correctly.
- When testing scripts locally, prefer the existing directories (`data/raw`, `data/scoreboard`, `data/league`) to keep automation and manual runs aligned.
- Need to hide a rogue fixture? Add its `fixtureId` to `data/scoreboard/exclusions.json` before rerunning `filter.py`.

---

### Documentation
- `docs/scoreboard.md` – Scoreboard ingestion + display workflow, exclusion rules, manual overrides.
- `docs/league.md` – Concise weekly checklist for the League of Leagues pipeline.
- `docs/league-data-workflow.md` – Original long-form reference (API breakdown, retry/fallback strategy).

Each doc links the relevant scripts, cron jobs, and troubleshooting tips so new contributors can ramp quickly.

---

### Automation Reference
- `.github/workflows/fixtures.yml` – Thu/Fri overnight build; runs `scripts/main.py` and `scripts/filter.py` to refresh structure ahead of the weekend.
- `.github/workflows/scores.yml` – Every 5 minutes on Sat/Sun; re-runs the same scripts to capture score updates mid-weekend.
- Both workflows commit only `data/scoreboard/weekend_fixtures.json` to keep history clean.

---

Questions, ideas, or new display requirements? Add them under `docs/` (or open a ticket) so the pipeline stays transparent and maintainable.

