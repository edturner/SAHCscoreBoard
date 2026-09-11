"""
Client for England Hockey's GMS data warehouse API.

This is the direct replacement for the gmsfeed.co.uk HTML scraping in gms_fetcher.py.
England Hockey retired the old warehouse host (eh-dw-prod.azurewebsites.net) in July 2026;
the current endpoint serves JSON and is authenticated with an x-api-key header.

Run standalone to produce data/scoreboard/weekend_fixtures.json:

    python scripts/eh_api.py weekend
    python scripts/eh_api.py weekend --weekend 2026-09-12 --output /tmp/compare.json

The key is read from the GMS_API_KEY environment variable and is never stored in the repo.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "scoreboard" / "weekend_fixtures.json"

EH_API_BASE = "https://ehdwapi.englandhockey.co.uk/api/"
API_KEY_ENV = "GMS_API_KEY"


class MissingApiKey(RuntimeError):
    pass


@dataclass
class EHApiClient:
    """Thin JSON client. Retries on 429 and 5xx with exponential backoff."""

    api_key: str = ""
    base_url: str = EH_API_BASE
    timeout: int = 30
    retry_limit: int = 6
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get(API_KEY_ENV, "")
        if not self.api_key:
            raise MissingApiKey(
                f"No API key. Set {API_KEY_ENV} in your environment "
                "(and as a GitHub Actions secret for CI)."
            )

    def get(self, path: str) -> Any:
        url = self.base_url + path.lstrip("/")
        headers = {"x-api-key": self.api_key, "Accept": "application/json"}
        last_error: Optional[str] = None
        for attempt in range(1, self.retry_limit + 1):
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            if response.status_code < 400:
                return response.json()
            if response.status_code in (401, 403):
                raise RuntimeError(
                    f"{response.status_code} from {url} - the API key was rejected."
                )
            if response.status_code == 404:
                return None
            last_error = f"{response.status_code} {response.reason}"
            if attempt < self.retry_limit:
                time.sleep(self._backoff(response, attempt))
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    @staticmethod
    def _backoff(response: requests.Response, attempt: int) -> float:
        """Seconds to wait before retrying.

        A 429 means the API is rate limiting us, so honour its Retry-After when it
        sends one and otherwise back off far harder than for a 5xx: a scorer run can
        make a few hundred requests, and short retries just hit the limit again.
        """
        retry_after = (response.headers.get("Retry-After") or "").strip()
        if retry_after.isdigit():
            return min(float(retry_after), 60.0)
        if response.status_code == 429:
            return min(5 * 2 ** attempt, 60)   # 10, 20, 40, 60, 60s
        return min(2 ** attempt, 10)

    # -- resources -------------------------------------------------------

    def get_seasons(self) -> List[Dict[str, Any]]:
        return self.get("seasons") or []

    def current_season(self, on: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """The season whose date range contains `on` (default: today)."""
        target = on or date.today()
        for season in self.get_seasons():
            try:
                start = datetime.fromisoformat(season["fromDate"]).date()
                end = datetime.fromisoformat(season["toDate"]).date()
            except (KeyError, TypeError, ValueError):
                continue
            if start <= target < end:
                return season
        return None

    def get_club_matchday(self, club_id: str, day: date) -> Optional[Dict[str, Any]]:
        """Every fixture the club plays on one date, across all competitions."""
        return self.get(f"clubs/{club_id}/matchdays/{day.isoformat()}")

    def get_club_teams(self, club_id: str) -> List[Dict[str, Any]]:
        return self.get(f"clubs/{club_id}/teams") or []


# -- config -------------------------------------------------------------


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_club_config() -> Dict[str, Any]:
    return load_json(CONFIG_DIR / "club.json")


def load_team_index() -> Dict[str, str]:
    """teamId -> configured display name, e.g. "St Albans 5 (M)"."""
    teams = load_json(CONFIG_DIR / "teamIDs.json")
    return {t["teamId"]: t.get("name", "") for t in teams if t.get("teamId")}


# -- normalisation ------------------------------------------------------


def strip_season_suffix(label: str) -> str:
    return re.sub(r"\s*\(\d{4}-\d{4}\)\s*$", "", label or "").strip()


def short_division(competition_name: str) -> str:
    """"East Open - Men's Division 2 South West" -> "Division 2 South West".

    Delegates to gms_fetcher so the API and gmsfeed paths label divisions identically.
    """
    from gms_fetcher import normalize_comp_label

    return normalize_comp_label(strip_season_suffix(competition_name)) or competition_name


def build_fixture_record(
    fixture: Dict[str, Any],
    competition_name: str,
    club_id: str,
    team_index: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Map one API fixture onto the scoreboard's record shape.

    Returns None for fixtures that don't involve a team listed in teamIDs.json,
    which filters out junior and non-league sides the club portal also returns.
    """
    home, away = fixture.get("homeTeam") or {}, fixture.get("awayTeam") or {}
    is_home = fixture.get("homeClubId") == club_id
    ours = home if is_home else away

    team_id = ours.get("id")
    if team_id not in team_index:
        return None

    played = bool(fixture.get("isResult"))
    return {
        "date": fixture.get("fixtureDate"),
        "team": team_index[team_id],
        "category": "men" if (ours.get("gender") or "").upper() == "M" else "women",
        "home_team": (home.get("teamName") or "").strip(),
        "away_team": (away.get("teamName") or "").strip(),
        "kickoff": fixture.get("fixtureTime"),
        "division": short_division(competition_name),
        "location": "Home" if is_home else "Away",
        "status": "Played" if played else "Scheduled",
        "fixtureId": fixture.get("id"),
        "home_score": fixture.get("homeTeamScoreAsInt") if played else None,
        "away_score": fixture.get("awayTeamScoreAsInt") if played else None,
        "_ha": "h" if is_home else "a",
    }


def _harvest(competitions, team_index, sink) -> None:
    """Collect (competition, fixture, is_home, team) tuples for our configured teams."""
    for competition in competitions or []:
        for fixture in competition.get("fixtures") or []:
            for is_home, side in ((True, "homeTeam"), (False, "awayTeam")):
                team = fixture.get(side) or {}
                team_id = team.get("id")
                if team_id in team_index:
                    sink.setdefault(team_id, []).append((competition, fixture, is_home, team))


def collect_season_fixtures(
    client: EHApiClient, team_index: Dict[str, str]
) -> Dict[str, List[tuple]]:
    """Every configured team's full season, one request per team.

    clubs/{id}/matchdays looks like a whole-season feed but only embeds fixtures for
    nextMatchDay - the remaining match days are empty date placeholders - so full
    season data has to come from the per-team endpoint.
    """
    by_team: Dict[str, List[tuple]] = {}
    for team_id in team_index:
        _harvest(client.get(f"teams/{team_id}/fixturesandresults"), team_index, by_team)
    return by_team


def collect_fixtures(
    client: EHApiClient, club_id: str, days: Iterable[date]
) -> List[Dict[str, Any]]:
    """Fixtures for the given days.

    One request per day covers every team in the club's *area* competitions. Teams in
    national leagues (the 1st XIs) never appear there, so any configured team missing
    from the day responses is then looked up individually.
    """
    team_index = load_team_index()
    days = list(days)
    wanted = {d.isoformat() for d in days}

    by_team: Dict[str, List[tuple]] = {}
    for day in days:
        _harvest(client.get_club_matchday(club_id, day), team_index, by_team)

    for team_id in team_index:
        if team_id not in by_team:
            _harvest(client.get(f"teams/{team_id}/fixturesandresults"), team_index, by_team)

    records: List[Dict[str, Any]] = []
    for entries in by_team.values():
        for competition, fixture, _is_home, _team in entries:
            if (fixture.get("fixtureDate") or "")[:10] not in wanted:
                continue
            record = build_fixture_record(
                fixture, competition.get("competitionName") or "", club_id, team_index
            )
            if record:
                records.append(record)
    return records


# -- output -------------------------------------------------------------


def build_payload(
    records: List[Dict[str, Any]], saturday: date, sunday: date
) -> Dict[str, Any]:
    unique: Dict[str, Dict[str, Any]] = {}
    for record in records:
        unique[record.get("fixtureId") or json.dumps(record, sort_keys=True)] = record

    ordered = sorted(unique.values(), key=lambda r: (r.get("date") or "", r.get("kickoff") or ""))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Which weekend this file covers, so the displays can title themselves
        # correctly even when there are no fixtures to read a date from.
        "weekend": {"saturday": saturday.isoformat(), "sunday": sunday.isoformat()},
        "home": [r for r in ordered if r["_ha"] == "h"],
        "away": [r for r in ordered if r["_ha"] == "a"],
    }


def write_fixture_csvs(records: List[Dict[str, Any]], output_dir: Path) -> List[Path]:
    """Companion CSVs for the social/media team, in the same shape gms_fetcher wrote."""
    written = []
    for category, filename in (("men", "mens_fixtures.csv"), ("women", "womens_fixtures.csv")):
        path = output_dir / filename
        rows = [r for r in records if r.get("category") == category]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Team", "Opponent", "Match_Time", "Location", "Division"])
            for r in rows:
                opponent = r["away_team"] if r["location"] == "Home" else r["home_team"]
                writer.writerow([r["team"], opponent, r["kickoff"], r["location"], r["division"]])
        written.append(path)
    return written


def command_weekend(weekend: Optional[str], output: Path, club_id: Optional[str]) -> int:
    from gms_fetcher import weekend_range  # single source of truth for "which weekend"

    saturday, sunday = weekend_range(weekend)
    club_id = club_id or load_club_config().get("club_id")
    if not club_id:
        print("No club id. Pass --club-id or add \"club_id\" to config/club.json.")
        return 2

    client = EHApiClient()
    records = collect_fixtures(client, club_id, (saturday, sunday))
    payload = build_payload(records, saturday, sunday)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    for path in write_fixture_csvs(payload["home"] + payload["away"], output.parent):
        print(f"Wrote {path}")

    print(
        f"{saturday} - {sunday}: {len(payload['home'])} home, "
        f"{len(payload['away'])} away -> {output}"
    )
    return 0


# -- league tables ------------------------------------------------------


def season_label(competition_name: str, season: Optional[str]) -> str:
    from gms_fetcher import normalize_comp_label

    label = normalize_comp_label(strip_season_suffix(competition_name)) or competition_name
    return f"{label} ({season})" if season else label


def get_group_tables(client: EHApiClient, group_id: str) -> List[Dict[str, Any]]:
    """All standings tables for a competition group, following pagination."""
    tables: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = client.get(f"competitiongroups/{group_id}/tables?pageNo={page}")
        if not payload:
            break
        tables.extend(payload.get("data") or [])
        if not payload.get("hasMoreData"):
            break
        page += 1
    return tables


def result_letter(fixture: Dict[str, Any], is_home: bool) -> Optional[str]:
    if not fixture.get("isResult"):
        return None
    ours = fixture.get("homeTeamScoreAsInt") if is_home else fixture.get("awayTeamScoreAsInt")
    theirs = fixture.get("awayTeamScoreAsInt") if is_home else fixture.get("homeTeamScoreAsInt")
    if ours is None or theirs is None:
        return None
    return "W" if ours > theirs else "L" if ours < theirs else "D"


def collect_league_records(client: EHApiClient, club_id: str) -> List[Dict[str, Any]]:
    """Build teamData.json records from each team's competition and its group table."""

    team_index = load_team_index()
    by_team = collect_season_fixtures(client, team_index)

    tables_by_group: Dict[str, List[Dict[str, Any]]] = {}
    records: List[Dict[str, Any]] = []

    for team_id, name in team_index.items():
        entries = by_team.get(team_id)
        if not entries:
            continue

        competition, sample_fixture, _, team = entries[0]
        group_id = competition.get("competitionGroupId")
        competition_id = competition.get("competitionId")

        if group_id and group_id not in tables_by_group:
            tables_by_group[group_id] = get_group_tables(client, group_id)

        row: Dict[str, Any] = {}
        for table in tables_by_group.get(group_id, []):
            if table.get("id") == competition_id:
                for candidate in table.get("table") or []:
                    if candidate.get("teamId") == team_id:
                        row = candidate
                        break

        # Newest first: the league page renders the first five badges.
        results = sorted(
            (
                (fixture.get("fixtureDate") or "", result_letter(fixture, is_home))
                for _, fixture, is_home, _ in entries
            ),
            key=lambda r: r[0],
            reverse=True,
        )
        form = [{"result": letter} for _, letter in results if letter][:5]

        played = row.get("gamesPlayed")
        points = row.get("totalPoints")
        as_text = lambda key: str(row[key]) if row.get(key) is not None else None

        records.append(
            {
                "name": name,
                "teamId": team_id,
                # GMS reports a club's 1st team without a squad number ("St Albans").
                # gms_fetcher means to add it but its check never matches, so the name
                # has always been published bare; kept as-is to avoid changing the board.
                "teamDisplay": (team.get("teamName") or "").strip(),
                "competition": {
                    "id": competition_id,
                    # gmsfeed's label carried the season, e.g. "Division 5 South West (2026-2027)";
                    # the API reports competition and season separately.
                    "label": season_label(
                        competition.get("competitionName") or "", sample_fixture.get("season")
                    ),
                },
                "stats": {
                    "played": as_text("gamesPlayed"),
                    "won": as_text("gamesWon"),
                    "drawn": as_text("gamesDrawn"),
                    "lost": as_text("gamesLost"),
                    "goalsFor": as_text("goalsFor"),
                    "goalsAgainst": as_text("goalsAgainst"),
                    "goalDiff": as_text("goalsDifference"),
                    "points": as_text("totalPoints"),
                    "ppg": f"{points / played:.2f}" if played else ("0.00" if row else None),
                },
                "form": form,
            }
        )
    return records


def command_league(output: Path, club_id: Optional[str], no_rotate: bool) -> int:
    from gms_fetcher import rotate_snapshots

    club_id = club_id or load_club_config().get("club_id")
    if not club_id:
        print('No club id. Pass --club-id or add "club_id" to config/club.json.')
        return 2

    client = EHApiClient()
    records = collect_league_records(client, club_id)

    expected = len(load_team_index())
    missing = expected - len(records)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_suffix(output.suffix + ".new")
    with staging.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")

    previous = output.with_suffix("")
    previous = previous.parent / (previous.name + ".prev" + output.suffix)

    if no_rotate or missing:
        # A partial snapshot must not become the "previous" one, or the league page's
        # movement arrows would compare against incomplete data.
        staging.replace(output)
        if missing:
            print(f"WARNING: {missing} of {expected} teams missing - wrote {output} without rotating.")
        else:
            print(f"{len(records)} team records -> {output} (rotation skipped)")
        return 0

    rotate_snapshots(staging, output, previous)
    print(f"{len(records)} team records -> {output} (previous -> {previous})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    weekend = sub.add_parser("weekend", help="Write weekend_fixtures.json from the API")
    weekend.add_argument("--weekend", help="Any date in the target weekend (YYYY-MM-DD)")
    weekend.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    weekend.add_argument("--club-id", help="Overrides club_id in config/club.json")

    league = sub.add_parser("league", help="Write teamData.json from the API")
    league.add_argument("--output", type=Path, default=REPO_ROOT / "data" / "league" / "teamData.json")
    league.add_argument("--club-id", help="Overrides club_id in config/club.json")
    league.add_argument("--no-rotate", action="store_true", help="Do not rotate teamData.prev.json")

    seasons = sub.add_parser("seasons", help="List seasons and show the current one")
    seasons.add_argument("--club-id", help=argparse.SUPPRESS)

    args = parser.parse_args()
    try:
        if args.command == "weekend":
            return command_weekend(args.weekend, args.output, args.club_id)
        if args.command == "league":
            return command_league(args.output, args.club_id, args.no_rotate)
        if args.command == "seasons":
            client = EHApiClient()
            current = client.current_season()
            for season in client.get_seasons():
                marker = "*" if current and season["id"] == current["id"] else " "
                print(f" {marker} {season['description']:12} {season['id']}")
            return 0
    except MissingApiKey as exc:
        print(exc)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
