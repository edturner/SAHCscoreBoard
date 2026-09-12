# Where things stand

Written 12 September 2026, the first match day of the season. Companion to `CLAUDE.md`
(architecture) and `docs/gms-api.md` (the API itself).

## What's live

Five portrait 1080x1920 screens on GitHub Pages at
`https://edturner.github.io/SAHCscoreBoard/`:

| Screen | URL |
| --- | --- |
| Home fixtures | `homeFixtures.html` |
| Away fixtures | `awayFixtures.html` |
| Men's league | `leagueOfLeagues-men.html` |
| Women's league | `leagueOfLeagues-women.html` |
| Top scorers | `topScorers.html` |

They share one design system (`apps/shared/styles.css`) and one helper script
(`apps/shared/board.js`), and re-read their data every 60 seconds.

## How data reaches a screen

```
GMS API  ->  scripts/*.py in GitHub Actions  ->  commit to main
         ->  pages.yml deploys (~25s)        ->  screen polls (<=60s)
```

`fixtures.yml` runs the three data steps; `pages.yml` redeploys on every push and after each
data run.

**GitHub's scheduled runs are the weak link.** They are best-effort: on Saturday 12 September
the every-5-minutes cron actually fired at 09:33, 11:50, 13:07 and 14:24 UTC — roughly every 75
minutes. `scripts/trigger_update.sh` exists for that: any always-on machine can dispatch the
workflow on a cron, and dispatched runs start immediately. The schedules stay as a fallback.
A `fast` dispatch runs fixtures and scorers but skips the league tables.

## Decisions worth not re-litigating

- **Readability beat cleverness on the screens.** Two earlier designs were rejected: one looked
  "vibe coded" (glass panels, gradient text, glow), the next used a condensed all-caps font that
  was hard to read across a room. What stuck: normal-width Barlow in Title Case for names, the
  club's TT Bluescreens for titles only, flat panels, one accent colour.
- **The away screen is white, not orange** (`.board--away`), because the club plays away in white.
- **Squads are shown as "3s" under a MEN or WOMEN panel heading,** never "St Albans 3". GMS names
  two same-numbered squads identically, which the old boards could not tell apart.
- **Only one thing animates:** a result that arrived since the last refresh glows briefly. Rows
  settle in once on load. Nothing loops — it sits on a wall all day.
- **Scorers exclude players without GMS consent** and never publish member IDs (hashed instead).
- **The scorer cache re-reads today's fixtures every run,** keeps anything older than 14 days
  from cache, and in between only re-reads fixtures still missing a team sheet or goals.
- **A failed fetch with no cached copy aborts the scorer run** rather than publishing a short
  table. The last good file stays on screen.

## Open items

- **Sunday cadence.** Sunday score checks are hourly. The 1st XIs' national leagues often play
  Sunday, so their results can be an hour stale. A one-line cron change if it annoys.
- **The GMS API key is England Hockey's own website key.** Still worth requesting a club key from
  `gms.support@englandhockey.co.uk`; they could rotate theirs at any time.
- **Duplicate member records.** Ed Turner has two GMS accounts, so his goals split across both.
  Merging them in GMS is the only real fix, and it matters for any appearances work.
- **Team sheet coverage is the limit on scorer data,** not the code. On 12 Sep the men's 6s won
  3-1 with no sheet filled in at all, so none of it was recorded.
- **Appearances / subs tracking** was designed but never built: a private CSV of who actually
  played, for whoever handles membership. Same data source (`allPlayers` on each fixture), but it
  must never be published, and duplicate accounts would understate appearances.
- **The open day posters** (`apps/statics/`) still use the old look and no longer match the other
  screens in rotation.
- **Fonts load from Google Fonts.** If the clubhouse loses internet the screens fall back to a
  plainer font. Self-hosting Barlow would remove that.

## Working on it

- **Preview locally:** `python -m http.server 8000`, then
  `http://localhost:8000/apps/scoreboard/homeFixtures.html`. The browser pane shrinks a
  1080x1920 page a lot, so for anything visual render it properly instead (below).
- **True-size renders:** headless Chrome, as `apps/statics/render.bat` already does:
  `chrome --headless=new --window-size=1080,1920 --virtual-time-budget=8000 --screenshot=out.png <url>`.
  This is the only reliable way to judge type sizes for a 65" TV.
- **Preview harnesses:** to see a state the live data can't show (results mid-afternoon, a
  week-five league table, a Sunday 1st XI game), put a temporary page at the repo root that loads
  the real screen in an iframe and calls its `render(...)` with doctored data. Delete it after.
  Note `Board` is a top-level `const`, so it is *not* on the iframe's `window`; patch it via
  `frame.contentWindow.eval(...)`.
- **Test the Python offline** by passing a stub client with a `get(path)` method. That covers
  consent, cards, the fail-safe and the cache rules without touching the network.
- **Python on this machine is `py -3`.** Plain `python` is the Microsoft Store stub and fails.
- **Check the live site after pushing:** `gh run watch <id>`, then fetch the deployed file, e.g.
  `curl -s https://edturner.github.io/SAHCscoreBoard/data/scorers/scorers.json`.
