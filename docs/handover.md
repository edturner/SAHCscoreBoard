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

### The always-on machine (installed 12 September 2026)

The always-on home server now does the dispatching — a Proxmox host, reachable on the home LAN
and over Tailscale. **This repo is public, so its addresses and login details are deliberately
not written here**; they live in the private Obsidian vault at
`Resources/Home Server Documentation.md`.

The trigger runs on the Proxmox host itself rather than in the media LXC: it is a
dependency-free curl to `api.github.com`, and the host is up whenever the container is, so a
container restart or maintenance window cannot silently stop match-day updates.

| Path | What |
| --- | --- |
| `/usr/local/bin/sahc-trigger.sh` | copy of `scripts/trigger_update.sh` |
| `/usr/local/bin/sahc-cron.sh` | cron entry point: loads the token, logs every outcome |
| `/root/.sahc-token` | `export GITHUB_TOKEN=…`, mode 600. Not in the repo, not backed up |
| `/var/log/sahc-trigger.log` | one line per dispatch; logrotate monthly, 3 kept |

Root crontab, in **Europe/London** (the host's timezone, so these are local push-back times —
note `trigger_update.sh`'s own header comments are written in UTC and are an hour out in BST):

```
*/5  9-21 * * 6   fast      # Saturday, every 5 minutes
*/15 9-20 * * 0   fast      # Sunday, every 15 minutes
5    22   * * 6   all       # Saturday evening, league tables
5    21   * * 0   all       # Sunday evening, league tables
```

The `all` dispatches sit deliberately *after* the fast window: `fixtures.yml` sets
`cancel-in-progress: true`, so a league run fired mid-afternoon would just be killed by the next
`fast` five minutes later.

`sahc-cron.sh` exists because the obvious crontab line is wrong. In
`. /root/.sahc-token && sahc-trigger.sh fast >> log 2>&1` the redirect binds only to the trigger
script, so a missing or unreadable token file fails *silently* — no dispatch, nothing in the log.
The wrapper checks the token itself and logs the failure, so the trigger can never stop quietly.

Check it is alive with `tail /var/log/sahc-trigger.log` on the host; a healthy line reads
`dispatched fixtures.yml (fast) on edturner/SAHCscoreBoard`.

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

- **The trigger needs its token.** Everything above is installed on the home server and cron is
  firing on schedule, but `/root/.sahc-token` does not exist yet, so nothing is dispatched — the log says
  `ERROR: /root/.sahc-token missing or unreadable`. Create a fine-grained PAT scoped to this repo
  with **Actions: read and write**, write it to that file mode 600, and the trigger goes live.
  Until then GitHub's own best-effort schedules are still the only clock.
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
