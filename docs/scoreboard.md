## Scoreboard Workflow

This document captures the end-to-end flow for the home/away scoreboard displays: how data is fetched from the GMS API, filtered, stored, and rendered.

---

### Components
- `scripts/gms_fetcher.py` – Unified CLI tool. The `update-scoreboard` command fetches fixtures/results directly from GMS.
- `apps/scoreboard/` – `homeFixtures.html`, `awayFixtures.html`, and `fixtures.js` (front-end polling logic).
- `apps/shared/` – shared styles, fonts, and background imagery.
- `data/scoreboard/`
  - `weekend_fixtures.json` – authoritative payload consumed by the displays.
  - `mens_fixtures.csv` / `womens_fixtures.csv` – helpers for social/media teams.
  - `weekend_fixtures.json` (previous) – used for automatic rollback/merging if the API returns incomplete data during a game.

> **Note**: `main.py` and `filter.py` are deprecated legacy scripts. `gms_fetcher.py` replaces them entirely.

---

### Running the Pipeline Manually
To fetch the latest fixtures and update the JSON/CSV files:

```powershell
python scripts/gms_fetcher.py update-scoreboard --config config/teamCompIDs.json
```

**Optional arguments:**
- `--weekend YYYY-MM-DD`: Target a specific weekend (defaults to upcoming/current weekend).
- `--output-dir <path>`: Override output location (defaults to `data/scoreboard`).

The script will:
1. Load team configs from `config/teamCompIDs.json`.
2. Fetch results/fixtures for each team from GMS.
3. Filter for the relevant weekend.
4. Merge with previous data (rollback logic) to ensure in-progress or completed scores aren't lost if the API glitches.
5. Write `weekend_fixtures.json` and CSV exports.

---

### Exclusions & Rollback
- **Rollback**: The script automatically loads the *existing* `weekend_fixtures.json` before writing. If a fixture was previously "Played" but the new fetch says "Scheduled" (or missing scores), it preserves the "Played" state. This prevents scores from vanishing mid-game.
- **Exclusions**: Currently handled via code logic or config. (Note: The old `exclusions.json` file used by `filter.py` is not currently used by `gms_fetcher.py`. If specific fixtures need hiding, logic should be added to `gms_fetcher.py` or the specific team config).

---

### Automation (GitHub Actions)
- **`fixtures.yml`**
  - Runs `python scripts/gms_fetcher.py update-scoreboard`.
  - Scheduled:
    - Thu/Fri @ 03:00 UTC (Initial build).
    - Sat/Sun every 5 minutes (Live scores).
  - Commits changes to `data/scoreboard/` back to the repo.

---

### Troubleshooting
| Symptom | Checks |
|---------|--------|
| `weekend_fixtures.json` missing / empty | Run the script manually and check for API errors. Ensure `teamCompIDs.json` is populated (`scripts/gms_fetcher.py competitions`). |
| Teams missing | Check `config/teamCompIDs.json`. If a team isn't there, run `gms_fetcher.py competitions` to refresh the mappings. |
| Board not updating | Check browser console for `fetch` errors; confirm the HTML is served from repo root so `../../data/...` resolves correctly. |

---

### Deployment Tips
- Host the repo (or the `apps/` + `data/` subsets) on any static host.
- The `apps/scoreboard` HTML expects `data/scoreboard/weekend_fixtures.json` to be reachable via relative path.
