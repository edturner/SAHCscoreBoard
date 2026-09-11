"""
Top goalscorers for the Top Scorers screen, from GMS match detail.

    python scripts/top_scorers.py                  # current season -> data/scorers/scorers.json
    python scripts/top_scorers.py --print          # ...and print the tables
    python scripts/top_scorers.py --last-season --print --output scratch.json

Reads GMS_API_KEY from the environment.

Goals are the field goal, penalty corner and penalty stroke events on each played
fixture's detail, so they only exist once a captain completes the GMS team sheet. A
squad whose captain never does will score nothing here: treat a low total as "not
recorded", never as "did not score".

Players who have not given GMS consent are left out entirely, as England Hockey's own
site does. Member IDs are never written out: players are grouped by a one-way hash of
the ID, so two people with the same name stay separate without their IDs being
published.

Match detail for fixtures more than REFRESH_DAYS old is reused from
data/scorers/fixture_goals.json, so a run late in the season does not re-request every
game. Recent fixtures are always re-read, because team sheets are often completed days
after the match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eh_api import (  # noqa: E402
    REPO_ROOT,
    EHApiClient,
    MissingApiKey,
    collect_season_fixtures,
    load_team_index,
)

OUTPUT = REPO_ROOT / "data" / "scorers" / "scorers.json"
CACHE = REPO_ROOT / "data" / "scorers" / "fixture_goals.json"

# Field goal, penalty corner, penalty stroke. Cards (GC/YC/RC) are not goals.
GOAL_EVENTS = {"FG", "PC", "PS"}

REFRESH_DAYS = 14
PACE_SECONDS = 0.3  # between match-detail requests, to stay under the API's rate limit
SEASON_TOP = 10     # the screen shows 7; a little spare for ties
DAY_TOP = 8         # the screen shows 4

# Last commit before the 2026-27 competition IDs were generated.
LAST_SEASON_REF = "667f5274:config/teamCompIDs.json"


@dataclass(frozen=True)
class Result:
    """One of our teams in one played fixture. A club derby is two Results."""

    fixture_id: str
    day: str            # YYYY-MM-DD
    team_id: str
    season: str = ""    # "2026-2027", when the feed says


# -- labels ---------------------------------------------------------------


def player_key(member_id: Any) -> str:
    return hashlib.sha256(str(member_id).encode("utf-8")).hexdigest()[:12]


def squad_label(team_name: str) -> str:
    """"St Albans 3 (M)" -> "3s". GMS gives the men's 1st XI no number."""
    match = re.search(r"(\d+)\s*(?:\([^)]*\))?\s*$", team_name or "")
    return f"{match.group(1) if match else 1}s"


def gender_of(team_name: str) -> str:
    match = re.search(r"\((M|F)\)\s*$", team_name or "")
    return match.group(1) if match else ""


def day_label(days: List[str]) -> str:
    """["2026-09-12"] -> "Saturday 12 September"; both days -> "Sat 12 & Sun 13 September"."""
    dates = [date.fromisoformat(d) for d in days]
    if len(dates) == 1:
        d = dates[0]
        return f"{d:%A} {d.day} {d:%B}"
    first, last = dates[0], dates[-1]
    first_text = f"{first:%a} {first.day}" + ("" if first.month == last.month else f" {first:%B}")
    return f"{first_text} & {last:%a} {last.day} {last:%B}"


def season_label(results: Iterable[Result], today: date) -> str:
    for result in results:
        match = re.match(r"(\d{4})\s*-\s*\d{2}(\d{2})$", result.season or "")
        if match:
            return f"{match.group(1)}/{match.group(2)} season"
    start = today.year if today.month >= 8 else today.year - 1
    return f"{start}/{str(start + 1)[2:]} season"


# -- which fixtures -------------------------------------------------------


def current_results(client: EHApiClient, team_index: Dict[str, str]) -> List[Result]:
    """Every played fixture this season, from each team's own feed (as the league uses)."""
    results = set()
    for team_id, entries in collect_season_fixtures(client, team_index).items():
        for _competition, fixture, _is_home, _team in entries:
            if fixture.get("isResult") and fixture.get("id"):
                results.add(Result(
                    fixture["id"],
                    (fixture.get("fixtureDate") or "")[:10],
                    team_id,
                    fixture.get("season") or "",
                ))
    return sorted(results, key=lambda r: (r.day, r.fixture_id, r.team_id))


def last_season_results(
    client: EHApiClient, team_index: Dict[str, str]
) -> Tuple[List[Result], Dict[str, str]]:
    """2025-26, via the competition IDs committed before this season's were generated.

    The team feeds only cover the current season, so looking back needs the old
    competitions. Returns the results and a team index that includes last season's
    names.
    """
    raw = subprocess.check_output(["git", "show", LAST_SEASON_REF], text=True, cwd=REPO_ROOT)
    names = dict(team_index)
    results = set()
    for entry in json.loads(raw):
        comp, team_id = entry.get("compId"), entry.get("teamId")
        if not comp or not team_id:
            continue
        names.setdefault(team_id, entry.get("name") or "")
        listing = client.get(f"competitions/{comp}/matchdays")
        days = listing.get("matchDays") if isinstance(listing, dict) else (listing or [])
        for day in days:
            day_iso = (day.get("matchDay") or "")[:10]
            for fixture in client.get(f"competitions/{comp}/matchdays/{day_iso}") or []:
                if not fixture.get("isResult") or not fixture.get("id"):
                    continue
                if team_id in (fixture.get("homeTeamId"), fixture.get("awayTeamId")):
                    results.add(Result(fixture["id"], day_iso, team_id, "2025-2026"))
    return sorted(results, key=lambda r: (r.day, r.fixture_id, r.team_id)), names


# -- goals ----------------------------------------------------------------


def fetch_goals(client: EHApiClient, fixture_id: str, team_ids: Iterable[str]) -> Dict[str, Any]:
    """Per team of ours: whether it has a team sheet, and its consenting scorers."""
    detail = client.get(f"fixtures/{fixture_id}")
    if isinstance(detail, list):
        detail = detail[0] if detail else None
    detail = detail or {}

    with_sheet = {player.get("teamId") for player in detail.get("allPlayers") or []}
    events = detail.get("fixtureEvents") or []

    teams: Dict[str, Any] = {}
    for team_id in team_ids:
        tally: Counter = Counter()
        names: Dict[str, str] = {}
        for event in events:
            if event.get("teamId") != team_id or event.get("eventType") not in GOAL_EVENTS:
                continue
            # England Hockey gates name display on the player's own consent.
            if not event.get("consent") or not event.get("memberId"):
                continue
            key = player_key(event["memberId"])
            tally[key] += 1
            # GMS sometimes has doubled spaces ("Edward  Burns").
            names[key] = " ".join((event.get("displayName") or "").split()) or "Unknown"
        teams[team_id] = {
            "sheet": team_id in with_sheet,
            "scorers": [{"player": k, "name": names[k], "goals": n} for k, n in tally.most_common()],
        }
    return teams


def gather(
    client: EHApiClient, results: List[Result], cache: Dict[str, Any], today: date
) -> Dict[str, Any]:
    """fixture id -> {day, teams}, reusing cached detail for fixtures past REFRESH_DAYS."""
    by_fixture: Dict[str, List[Result]] = defaultdict(list)
    for result in results:
        by_fixture[result.fixture_id].append(result)

    cutoff = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    goals: Dict[str, Any] = {}
    fetched = reused = stale = 0
    for fixture_id, rows in by_fixture.items():
        team_ids = sorted({row.team_id for row in rows})
        cached = cache.get(fixture_id)
        if cached and rows[0].day < cutoff and all(t in cached.get("teams", {}) for t in team_ids):
            goals[fixture_id] = cached
            reused += 1
            continue
        try:
            teams = fetch_goals(client, fixture_id, team_ids)
        except RuntimeError:
            # Without this fixture the totals would come out short, and a short
            # table is worse than a slightly old one. Fall back to the cached
            # copy if there is one; otherwise stop before anything is written,
            # so the last good scorers.json stays on the screen.
            if not cached:
                raise
            print(f"  {fixture_id}: fetch failed, using cached detail", file=sys.stderr)
            goals[fixture_id] = cached
            stale += 1
            continue
        goals[fixture_id] = {"day": rows[0].day, "teams": teams}
        fetched += 1
        time.sleep(PACE_SECONDS)
    print(
        f"match detail: {fetched} fetched, {reused} from cache"
        + (f", {stale} stale after a failed fetch" if stale else ""),
        file=sys.stderr,
    )
    return goals


# -- output ---------------------------------------------------------------


def aggregate(
    results: List[Result],
    goals: Dict[str, Any],
    team_index: Dict[str, str],
    days: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Per gender, best first: [{name, goals, squad}]. `days` limits to those dates.

    A player's squad is the one they scored most for, since players move between
    squads during a season.
    """
    totals: Dict[str, Counter] = {"M": Counter(), "F": Counter()}
    names: Dict[str, str] = {}
    squads: Dict[str, Counter] = defaultdict(Counter)

    for result in results:
        if days is not None and result.day not in days:
            continue
        team_name = team_index.get(result.team_id, "")
        gender = gender_of(team_name)
        if gender not in totals:
            continue
        team = goals.get(result.fixture_id, {}).get("teams", {}).get(result.team_id, {})
        for scorer in team.get("scorers", []):
            totals[gender][scorer["player"]] += scorer["goals"]
            names[scorer["player"]] = scorer["name"]
            squads[scorer["player"]][squad_label(team_name)] += scorer["goals"]

    ranked: Dict[str, List[Dict[str, Any]]] = {}
    for gender, tally in totals.items():
        order = sorted(tally.items(), key=lambda item: (-item[1], names[item[0]]))
        ranked[gender] = [
            {"name": names[p], "goals": g, "squad": squads[p].most_common(1)[0][0]}
            for p, g in order
        ]
    return ranked


def latest_weekend(results: List[Result]) -> List[str]:
    """The dates of the most recent weekend with results (Sunday included: the 1st XIs'
    national leagues often play then). A midweek fixture stands alone."""
    days = sorted({r.day for r in results if r.day})
    if not days:
        return []
    last = date.fromisoformat(days[-1])
    if last.weekday() == 6:
        saturday = last - timedelta(days=1)
    elif last.weekday() == 5:
        saturday = last
    else:
        return [days[-1]]
    weekend = [saturday.isoformat(), (saturday + timedelta(days=1)).isoformat()]
    return [d for d in weekend if d in days]


def build_payload(
    results: List[Result], goals: Dict[str, Any], team_index: Dict[str, str], today: date
) -> Dict[str, Any]:
    weekend = latest_weekend(results)
    season = aggregate(results, goals, team_index)
    match_day = aggregate(results, goals, team_index, days=weekend) if weekend else {"M": [], "F": []}
    sheets = sum(
        1 for r in results
        if goals.get(r.fixture_id, {}).get("teams", {}).get(r.team_id, {}).get("sheet")
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season_label": season_label(results, today),
        "match_day": {"date": weekend[0], "label": day_label(weekend)} if weekend else None,
        "season": {g: rows[:SEASON_TOP] for g, rows in season.items()},
        "match_day_scorers": {g: rows[:DAY_TOP] for g, rows in match_day.items()},
        "coverage": {"results": len(results), "with_team_sheet": sheets},
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".new")
    with staging.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    staging.replace(path)


def load_cache() -> Dict[str, Any]:
    try:
        with CACHE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def print_tables(payload: Dict[str, Any]) -> None:
    for heading, section in (("SEASON", "season"), ("LATEST WEEKEND", "match_day_scorers")):
        for gender, label in (("M", "MEN"), ("F", "WOMEN")):
            print(f"\n=== {heading} - {label} ===")
            for row in payload[section][gender]:
                print(f"  {row['goals']:>3}  {row['name']:<28} {row['squad']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--last-season", action="store_true",
                        help="2025-26 via the competition IDs in git history (no cache)")
    parser.add_argument("--print", dest="show", action="store_true", help="Print the tables")
    args = parser.parse_args()

    if args.last_season and args.output.resolve() == OUTPUT.resolve():
        print("--last-season needs --output: it must not replace the live screen's data.")
        return 2

    try:
        client = EHApiClient()
    except MissingApiKey as exc:
        print(exc)
        return 2

    today = date.today()
    team_index = load_team_index()
    if args.last_season:
        results, team_index = last_season_results(client, team_index)
        goals = gather(client, results, {}, today)
    else:
        results = current_results(client, team_index)
        goals = gather(client, results, load_cache(), today)
        # Only this season's fixtures, so the cache never outgrows the season.
        write_json(CACHE, goals)

    payload = build_payload(results, goals, team_index, today)
    write_json(args.output, payload)

    scored = sum(r["goals"] for rows in payload["season"].values() for r in rows)
    coverage = payload["coverage"]
    print(
        f"{coverage['results']} results ({coverage['with_team_sheet']} with a team sheet); "
        f"top-{SEASON_TOP} scorers account for {scored} goals -> {args.output}"
    )
    if args.show:
        print_tables(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
