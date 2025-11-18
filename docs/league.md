## League of Leagues Quick Start

Use this checklist to refresh the combined league table every week. For the deep-dive (API behaviour, retry logic, parser internals) see `docs/league-data-workflow.md`.

---

### 1. Prepare Config (when divisions change)
```powershell
python scripts/gms_fetcher.py competitions `
    --team-file config/teamIDs.json `
    --output config/teamCompIDs.json
```
- `teamIDs.json` stores each club team + GMS team UUID.
- The command scrapes the current competition UUIDs (`compId`) and writes the merged mapping.

---

### 2. Fetch Weekly Snapshot
```powershell
python scripts/gms_fetcher.py bulk-team-data `
    --config config/teamCompIDs.json `
    --output data/league/teamData.new.json `
    --publish-path data/league/teamData.json `
    --rotate-snapshots `
    --snapshot-date 2025-11-19
```
- `--rotate-snapshots` automatically moves the previous `teamData.json` to `teamData.prev.json` before promoting the new export.
- If any teams fail after retries, rotation is skipped to protect the current snapshot.

---

### 3. Validate Before Publishing
```powershell
python scripts/gms_fetcher.py validate-snapshots `
    --current data/league/teamData.json `
    --previous data/league/teamData.prev.json `
    --expect-count 26
```
- Fails fast if counts differ, PPG is missing, or the team list drifted unexpectedly.
- Run this whenever you manually edit snapshots or after automation completes.

---

### 4. Deploy Static Assets
- Upload `data/league/teamData.json` and `teamData.prev.json` wherever the HTML is hosted (static site, CDN, CMS).
- Serve `apps/league/leagueOfLeagues.html` (and the shared `apps/shared` folder) from the repo root so relative paths resolve.

---

### 5. Front-End Notes
- `league.js` fetches both snapshots from `../../data/league/`.
- The `data-gender` attribute on `<body>` controls which teams render; duplicate the HTML and switch to `data-gender="F"` for a women-only view.
- Missing `teamData.prev.json` simply results in neutral arrows (“steady”).

---

### Automation Ideas
- Schedule `scripts/gms_fetcher.py bulk-team-data --rotate-snapshots` midweek via cron or GitHub Actions.
- Optionally push snapshots to object storage (S3/Azure) to keep the repo lightweight; just update `apps/league/league.js` to point at the hosted URLs.

---

### Troubleshooting Cheatsheet
| Issue | Fix |
|-------|-----|
| `requests` errors / 429 rate limits | Re-run later or lower the rate limit in `GMSClient`. |
| Snapshot stuck on “fallback” entries | Check console output for offending team IDs, update `config/teamCompIDs.json`, rerun. |
| Trend arrows look wrong | Ensure `teamData.prev.json` truly is last week’s file; delete and rerun rotation if someone overwrote it manually. |

For everything else (parser internals, fallback metadata, API schemas), refer to `docs/league-data-workflow.md`.

