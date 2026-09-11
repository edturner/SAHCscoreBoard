# ClubScript

**Automated digital signage for hockey clubs — portrait fixture displays and a live League of Leagues table, powered by England Hockey's GMS.**

No server required. Data updates automatically via GitHub Actions and is served as a static site on GitHub Pages.

---

## What it shows

- **Home & Away Fixtures** — portrait 1080×1920 screens updated every 5 minutes on match days, showing kick-off times and live scores as they come in
- **League of Leagues** — weekly ranking of all your club's squads by points-per-game, with form badges and rank-change trend arrows
- **Top Scorers** — the season's leading scorers for men and women, plus the scorers from the latest match day

---

## Setup for a new club

### 1. Get your team IDs from England Hockey GMS

Each team registered with England Hockey has a UUID in the GMS system. Populate `config/teamIDs.json`:

```json
[
  { "name": "Anytown 1 (M)", "teamId": "your-uuid-here" },
  { "name": "Anytown 1 (F)", "teamId": "your-uuid-here" }
]
```

The `(M)` / `(F)` suffix is used to split the League of Leagues into men's and women's tables.

### 2. Set your club details

Edit `config/club.json`:

```json
{
  "name": "Anytown Hockey Club",
  "short_name": "Anytown",
  "club_id": "your-club-uuid"
}
```

`club_id` is your club's GMS UUID. It lets the fetcher pull a whole match day in one request and
identify home vs away by club ID rather than by name.

`short_name` is the prefix GMS uses for your team names (e.g. if GMS shows "Anytown 1", use
`"Anytown"`). Only the legacy gmsfeed path relies on it for home/away.

### 3. Set your API key

Data comes from England Hockey's GMS data warehouse, which requires a key. Request one from
`gms.support@englandhockey.co.uk`, then:

```bash
# locally
export GMS_API_KEY=your-key            # PowerShell: $env:GMS_API_KEY = "your-key"

# for CI
gh secret set GMS_API_KEY --body "your-key"
```

The scripts read `GMS_API_KEY` from the environment and never store it in the repo.

### 4. Set your club colours

Edit the `:root` block at the top of `apps/shared/styles.css`:

```css
:root {
    --panel: #1c1668;          /* Content panels */
    --ground: #140f52;         /* Page background */
    --ground-deep: #0e0a3d;    /* Text on the accent */
    --orange: #ff6600;         /* The one accent colour */
}
```

The club name in each screen's footer bar comes from `name` in `config/club.json`.
The away fixtures screen swaps the accent to white for the away kit: see `.board--away` in the same file.

### 5. Generate competition IDs *(legacy path only)*

The API fetcher resolves competitions itself, so this is only needed if you fall back to the
gmsfeed scraper in `gms_fetcher.py`. Run it once at the start of each season:

```bash
python scripts/gms_fetcher.py competitions \
    --team-file config/teamIDs.json \
    --output config/teamCompIDs.json
```

This generates `config/teamCompIDs.json`, which pairs each team with their current competition UUID. Commit this file.

### 6. Enable GitHub Pages

In your repo settings, enable GitHub Pages from the `gh-pages` environment (created automatically by the `pages.yml` workflow on first push).

### 7. Connect your screens

Point your display screens at the GitHub Pages URLs:

| Screen | URL |
|--------|-----|
| Home fixtures | `https://<your-org>.github.io/<repo>/homeFixtures.html` |
| Away fixtures | `https://<your-org>.github.io/<repo>/awayFixtures.html` |
| Men's league | `https://<your-org>.github.io/<repo>/leagueOfLeagues-men.html` |
| Women's league | `https://<your-org>.github.io/<repo>/leagueOfLeagues-women.html` |
| Top scorers | `https://<your-org>.github.io/<repo>/topScorers.html` |

---

## How data stays fresh

| What | How often | Workflow |
|------|-----------|----------|
| Initial fixture build | Thu & Fri at 03:00 UTC | `fixtures.yml` |
| Fixture scores | Every 5 min, Sat 08:00–21:59 UTC | `fixtures.yml` |
| Fixture scores | Hourly on Sunday | `fixtures.yml` |
| League of Leagues | Hourly, Sat & Sun at :37 | `fixtures.yml` |
| Top scorers | With the league updates | `fixtures.yml` |
| Weekly league snapshot | Monday 06:00 UTC | `league-gameweek.yml` |

League tables only move once results are entered, so they run on a slower cadence than live scores.

All workflows commit updated JSON back to the repo, which triggers a Pages redeploy. The displays poll for new data every 5 minutes.

---

## Running locally

```bash
pip install requests
python -m http.server 8000
# Open http://localhost:8000/apps/scoreboard/homeFixtures.html
```

## Manual data refresh

```bash
# Fetch this weekend's fixtures (writes weekend_fixtures.json + the CSVs)
python scripts/eh_api.py weekend

# A specific weekend
python scripts/eh_api.py weekend --weekend 2026-09-19

# Fetch league standings (rotates teamData.json -> teamData.prev.json)
python scripts/eh_api.py league

# List seasons; the current one is marked
python scripts/eh_api.py seasons

# Top scorers (writes data/scorers/scorers.json)
python scripts/top_scorers.py --print
```

<details>
<summary>Legacy gmsfeed commands</summary>

`gms_fetcher.py` scrapes gmsfeed.co.uk instead of calling the API. It needs no key but returns
less complete data, and depends on a third party's HTML.

```bash
python scripts/gms_fetcher.py update-scoreboard --config config/teamCompIDs.json
python scripts/live_league_updater.py --once
```
</details>

---

## Tech stack

- **Python 3.11+** — ETL scripts pulling from the England Hockey GMS data warehouse API
- **HTML / CSS / Vanilla JS** — static display pages, no framework
- **GitHub Actions** — automated data refresh and Pages deployment
