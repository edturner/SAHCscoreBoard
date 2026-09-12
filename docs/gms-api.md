# England Hockey GMS API — field notes

Everything worked out by trial and error against the live API in September 2026. The
client is `scripts/eh_api.py`; this is the reference behind it.

## Host and auth

| | |
| --- | --- |
| Base URL | `https://ehdwapi.englandhockey.co.uk/api/` |
| Auth header | `x-api-key: <key>` |
| Key | `GMS_API_KEY` env var locally, GitHub Actions secret in CI. Never committed. |

The old warehouse host `eh-dw-prod.azurewebsites.net` was retired around 18 July 2026 and
answers `403 "This web app is stopped"`. It took gmsfeed.co.uk and England Hockey's own
WordPress plugin down nationally for about seven weeks, which is what originally broke this
project — nothing in this repo was at fault.

The old host used `x-functions-key`. That header returns **401** on the new host; it must be
`x-api-key`.

A club key can be requested from `gms.support@englandhockey.co.uk`.

## Conventions

- Paths are `{resource}/{uuid}/{action}`, and the UUIDs are the same team IDs already in
  `config/teamIDs.json`.
- Responses are JSON, and resources carry HATEOAS `links` with `rel` / `href`.
- **404 means "nothing there", not an error.** The client returns `None`.
- **Some endpoints return a bare list, some an object.** `fixtures/{id}` has been seen both
  ways; `clubs/{id}/matchdays/{date}` returns a bare competitions list. Handle both.
- **Rate limiting is real.** A few hundred requests in quick succession returns
  `429 Too Many Requests`. Honour `Retry-After` when present and back off hard; pace bulk
  loops (`top_scorers.py` sleeps 0.3s between match-detail calls).

## Endpoints in use

| Endpoint | What it gives |
| --- | --- |
| `seasons` | `id`, `description`, `fromDate`, `toDate`. The current season is the one whose range contains today. |
| `clubs/{clubId}/teams` | Every team the club has registered. |
| `clubs/{clubId}/matchdays` | **Trap.** Looks like a whole-season feed, but only `nextMatchDay` has fixtures embedded; the rest are empty date placeholders. |
| `clubs/{clubId}/matchdays/{yyyy-mm-dd}` | One date's fixtures across the club's **area** competitions. |
| `teams/{teamId}/fixturesandresults` | One team's full season: a list of competitions, each with `fixtures[]`. The reliable source for whole-season data. |
| `competitiongroups/{groupId}/tables?pageNo=N` | League standings. Keyed on the competition **group**, not the competition. Paginated: `data[]` plus `hasMoreData`. |
| `competitions/{compId}/matchdays` and `.../matchdays/{date}` | Fixtures by competition. Used to look back at past seasons, since the team feed only covers the current one. |
| `fixtures/{fixtureId}` | Match detail: team sheets and events. See below. |

### The two traps that cost the most time

1. `clubs/{clubId}/matchdays` embeds fixtures for `nextMatchDay` only. Reading it as a season
   feed silently returns one match day out of thirty-six.
2. The club match-day endpoint covers only **area** competitions. Teams in national leagues —
   for St Albans, both 1st XIs in the EHL Conferences — never appear in it. Any configured team
   missing from a day's response has to be looked up individually via its own team feed.

## Fixture fields

```
id                     fixture UUID
fixtureDate            "2026-09-12T10:15:00"
fixtureTime            "10:15"
isResult               false until the result is submitted
fixtureStatus          "Active" before, "Result" after
homeTeam / awayTeam    { id, teamName, gender: "M" | "F" }
homeClubId             compare with your club_id to decide home or away
homeTeamScoreAsInt     null until isResult
awayTeamScoreAsInt
season                 "2026-2027"
```

On the competition wrapper: `competitionName`, `competitionId`, `competitionGroupId`.

League table rows carry `teamId` (so no name matching), plus `gamesPlayed`, `gamesWon`,
`gamesDrawn`, `gamesLost`, `goalsFor`, `goalsAgainst`, `goalsDifference`, `totalPoints`.
**There is no points-per-game field** — compute `totalPoints / gamesPlayed`.

## Match detail: team sheets and goals

`fixtures/{fixtureId}` returns:

- `allPlayers[]` — the team sheet, each entry carrying `teamId`. Only teams whose captain has
  completed the sheet appear. It is common to see the opposition's sheet and not your own.
- `fixtureEvents[]` — each with `teamId`, `eventType`, `memberId`, `displayName`, `consent`.

Event types: **`FG`** field goal, **`PC`** penalty corner, **`PS`** penalty stroke are goals.
`GC` / `YC` / `RC` are cards, not goals.

**Consent:** England Hockey gates name display on each player's own consent flag. When
`consent` is false the `displayName` comes back as `"Name Withheld"`. Those goals are excluded
here, as they are on England Hockey's own site. On 12 Sep 2026 that hid two of the women's 8s'
four goals.

**Team sheets are the real coverage limit.** Goals only exist once a captain fills the sheet in,
often days later, sometimes never. A low total means "not recorded", never "did not score".

## Naming and data-quality traps

- **The men's 1st XI has no squad number.** GMS publishes it as `"St Albans"`, not
  `"St Albans 1"`. Anything parsing a number off the end must default to 1.
- **Two squads with the same number are indistinguishable by name.** On 12 Sep 2026 there were
  two "St Albans 3" home fixtures, one men's and one women's. Use the team's `gender`, or the
  `category` we store on each fixture record.
- **Division labels carry a season suffix** in some paths: `"Division 2 South West (2026-2027)"`,
  and sometimes an area prefix: `"East Open - Men's Division 2 South West"`.
- **Doubled spaces appear in names** (`"Edward  Burns"`). Collapse whitespace before display.
- **One person can have several GMS member records.** Ed Turner has two accounts, and last
  season's 3s list shows "Edward Turner" (2 goals) and "Ed Turner" (1) separately. Aggregating
  by member ID is correct but will split them. The fix is merging the records in GMS; a local
  alias map would only paper over it, and it matters for any future appearance or subs tracking.

## Privacy

Member IDs are never written into this repo. `top_scorers.py` groups players by a truncated
SHA-256 of the member ID, which keeps two people with the same name apart without publishing
anything identifying beyond the display name GMS already shows publicly.

## How this was verified

- **Diff two implementations.** The API migration was validated by running the API path and the
  old gmsfeed scraper into a scratch directory and comparing field by field: league 0 differences
  across 17 teams, scoreboard 0 differences on 12 Sep, and the API found 4 fixtures gmsfeed had
  missed (it matched teams by name prefix and collapsed squads sharing a division).
- **Check against a known answer.** The scorer generator was checked against last season's men's
  3s, worked out by hand first: 22 results, 21 team sheets, 71 goals, 18 scorers — exact match.
- **Fake the client.** `EHApiClient` is a plain object with a `get(path)` method, so tests pass a
  stub and assert on the output without touching the network.
