# ClubScript

**Automated digital signage for hockey clubs — portrait fixture displays and a live League of Leagues table, powered by England Hockey's GMS.**

No server required. Data updates automatically via GitHub Actions and is served as a static site on GitHub Pages.

---

## What it shows

- **Home & Away Fixtures** — portrait 1080×1920 screens updated every 5 minutes on match days, showing kick-off times and live scores as they come in
- **League of Leagues** — weekly ranking of all your club's squads by points-per-game, with form badges and rank-change trend arrows

---

## Setup for a new club

### 1. Get your team IDs from England Hockey GMS

Each team registered with England Hockey has a UUID in the GMS system. Find them at `gmsfeed.co.uk` and populate `config/teamIDs.json`:

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
  "short_name": "Anytown"
}
```

`short_name` must match the prefix GMS uses for your team names (e.g. if GMS shows "Anytown 1", use `"Anytown"`). This is used to determine home vs away for each fixture.

### 3. Set your club colours

Edit the `:root` block at the top of `apps/shared/styles.css`:

```css
:root {
    --color-primary: #ff6600;       /* Main accent colour */
    --color-primary-dark: #a64a0d;  /* Darker accent */
    --color-background: #1a1464;    /* Screen background */
    --color-surface: #2f3a73;       /* Content card background */
}
```

### 4. Generate competition IDs

Run once at the start of each season (or when a team changes division):

```bash
python scripts/gms_fetcher.py competitions \
    --team-file config/teamIDs.json \
    --output config/teamCompIDs.json
```

This generates `config/teamCompIDs.json`, which pairs each team with their current competition UUID. Commit this file.

### 5. Enable GitHub Pages

In your repo settings, enable GitHub Pages from the `gh-pages` environment (created automatically by the `pages.yml` workflow on first push).

### 6. Connect your screens

Point your display screens at the GitHub Pages URLs:

| Screen | URL |
|--------|-----|
| Home fixtures | `https://<your-org>.github.io/<repo>/homeFixtures.html` |
| Away fixtures | `https://<your-org>.github.io/<repo>/awayFixtures.html` |
| Men's league | `https://<your-org>.github.io/<repo>/leagueOfLeagues-men.html` |
| Women's league | `https://<your-org>.github.io/<repo>/leagueOfLeagues-women.html` |

---

## How data stays fresh

| What | How often | Workflow |
|------|-----------|----------|
| Fixture scores (match days) | Every 5 min, Sat–Sun | `fixtures.yml` |
| Initial fixture build | Thu & Fri at 03:00 UTC | `fixtures.yml` |
| League of Leagues | Every 5 min (live updater) | `fixtures.yml` |
| Weekly league snapshot | Monday 06:00 UTC | `league-gameweek.yml` |

All workflows commit updated JSON back to the repo, which triggers a Pages redeploy. The displays poll for new data every 5 minutes.

---

## Running locally

```bash
pip install requests beautifulsoup4 pytz
python -m http.server 8000
# Open http://localhost:8000/apps/scoreboard/homeFixtures.html
```

## Manual data refresh

```bash
# Fetch this weekend's fixtures
python scripts/gms_fetcher.py update-scoreboard --config config/teamCompIDs.json

# Fetch league standings
python scripts/live_league_updater.py --once
```

---

## Tech stack

- **Python 3.11+** — ETL scripts pulling from the England Hockey GMS API
- **HTML / CSS / Vanilla JS** — static display pages, no framework
- **GitHub Actions** — automated data refresh and Pages deployment
