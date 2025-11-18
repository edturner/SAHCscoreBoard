## Scoreboard Workflow

This document captures the end-to-end flow for the home/away scoreboard displays: how data is fetched, filtered, stored, and rendered.

---

### Components
- `scripts/main.py` – grabs raw HTML from `stalbanshc.co.uk/matches` and writes `data/raw/matches_data_<timestamp>.html`.
- `scripts/filter.py` – parses the freshest raw HTML, applies weekend/date filters, excludes unwanted fixtures, and emits all scoreboard outputs.
- `apps/scoreboard/` – `homeFixtures.html`, `awayFixtures.html`, and `fixtures.js` (front-end polling logic).
- `apps/shared/` – shared styles, fonts, and background imagery.
- `data/scoreboard/`
  - `weekend_fixtures.json` – authoritative payload consumed by the displays.
  - `full_json_data.json` – optional debug dump of the raw schedule JSON.
  - `mens_fixtures.csv` / `womens_fixtures.csv` – helpers for social/media teams.
  - `exclusions.json` – fixture IDs to omit permanently.

---

### Running the Pipeline Manually
1. **Fetch raw HTML**
   ```powershell
   python scripts/main.py
   ```
   - Creates `data/raw/matches_data_<timestamp>.html`.
   - Safe to run multiple times per day; the newest timestamp wins.

2. **Build fixtures JSON**
   ```powershell
   python scripts/filter.py --output data/scoreboard/weekend_fixtures.json
   ```
   Optional arguments:
   - `--start dd/mm/YYYY --end dd/mm/YYYY` – restrict to a custom range instead of “upcoming weekend”.
   - `--output <path>` – override the destination (defaults to `data/scoreboard/weekend_fixtures.json`).

3. **Review artefacts**
   - Open `apps/scoreboard/homeFixtures.html` / `awayFixtures.html` in a browser (from repo root) to confirm layout.
   - Inspect `data/scoreboard/mens_fixtures.csv` and `womens_fixtures.csv` if the comms team needs structured exports.

---

### Excluding Fixtures
- Edit `data/scoreboard/exclusions.json` and add the `fixtureId` you want to hide. Example:
  ```json
  {
    "fixtureIds": [
      "123456",
      "789012"
    ]
  }
  ```
- Re-run `python scripts/filter.py` to regenerate the outputs. The script accepts either a plain array or the object form above.

---

### Automation (GitHub Actions)
- **`fixtures.yml`** (Thu/Fri @ 03:00 UTC)
  1. Runs `python scripts/main.py`.
  2. Runs `python scripts/filter.py --output data/scoreboard/weekend_fixtures.json`.
  3. Commits/pushes the regenerated JSON if it changed.
- **`scores.yml`** (Sat/Sun every 5 minutes)
  - Same commands as above so boards receive live scores during the weekend.

Both workflows respect the new folder layout, so local runs and CI/CD stay aligned.

---

### Troubleshooting
| Symptom | Checks |
|---------|--------|
| `weekend_fixtures.json` missing / empty | Ensure a recent `matches_data_*.html` exists in `data/raw`. `scripts/main.py` might have hit a site outage—rerun it manually. |
| Kids fixtures sneaking in | Confirm `is_kids_fixture` rules fit the naming convention. Adjust `filter.py` or extend `exclusions.json`. |
| TBC games showing | `filter.py` already drops “TBC” kickoff entries. If they still appear, verify the source feed isn’t sending a different token. |
| Board not updating | Check browser console for `fetch` errors; confirm the HTML is served from repo root so `../../data/...` resolves correctly. |

---

### Deployment Tips
- Host the repo (or the `apps/` + `data/` subsets) on any static host. The only requirement is that `apps/scoreboard` can reach `data/scoreboard/weekend_fixtures.json` via the relative path.
- For kiosk PCs, a simple scheduled task can run `scripts/filter.py` locally and copy the JSON to the signage machine.
- Keep `data/raw/` under version control if you want historical debugging. Otherwise you can `.gitignore` old dumps once the JSON is confirmed.

The scoreboard code path is now isolated, documented, and aligned with automation so weekend updates are a single command—or entirely hands-off via Actions.

