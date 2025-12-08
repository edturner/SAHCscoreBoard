"""
Utility functions for working with England Hockey's GMS API.

Features
--------
1. Competition lookup: read `teamIDs.json`, fetch current competition IDs
   for each team (useful pre-season when divisions may change) and persist
   the results to a config JSON.
2. Team data fetch: retrieve the latest league table row for a specific
   team, given its team UUID and competition UUID.
3. Bulk team data fetch: read the saved config (team + comp IDs) and fetch
   every team’s latest row, writing them to a JSON export.
4. Summary & fixtures helpers: pull team summary tables and recent
   weekend fixtures/results for dashboards.

Usage
-----
python gms_fetcher.py competitions --team-file teamIDs.json --output teamCompIDs.json
python gms_fetcher.py team-data --team-id <uuid> --comp-id <uuid>
python gms_fetcher.py team-summary --team-id <uuid> [--comp-id <uuid>]
python gms_fetcher.py bulk-team-data --config teamCompIDs.json --output teamData.json
python gms_fetcher.py recent-results --team-id <uuid> --comp-id <uuid> --weekend 2025-11-15
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode

import requests

GMS_REFRESH_BASE = "https://gmsfeed.co.uk/api/show/refresh"
GMS_COMPETITIONS_URL = "https://gmsfeed.co.uk/api/competitions?team={team_id}"
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"
LEAGUE_DATA_DIR = REPO_ROOT / "data" / "league"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LEAGUE_DATA_DIR.mkdir(parents=True, exist_ok=True)


def resolve_repo_path(path: Path) -> Path:
    """
    Resolve a provided path relative to the repository root if it is not
    already absolute. This lets callers pass paths from anywhere (e.g. running
    scripts from the scripts/ directory) without hitting FileNotFoundError.
    """
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path

def build_show_url(show: str, team_id: str, comp_id: Optional[str] = None, **extra) -> str:
    params = {
        "method": "api",
        "show": show,
        "team": team_id.strip(),
        "sort_by": "fixtureTime",
    }
    if comp_id:
        params["comp_id"] = comp_id.strip()
    params.update({k: v for k, v in extra.items() if v is not None})
    return f"{GMS_REFRESH_BASE}?{urlencode(params)}"

DEFAULT_TEAM_FILE = CONFIG_DIR / "teamIDs.json"
DEFAULT_COMP_OUTPUT = CONFIG_DIR / "teamCompIDs.json"
DEFAULT_TEAM_DATA_OUTPUT = LEAGUE_DATA_DIR / "teamData.json"
DEFAULT_TEAM_DATA_PREVIOUS = LEAGUE_DATA_DIR / "teamData.prev.json"
VALIDATION_MAX_RETRIES = 2
VALIDATION_BACKOFF_SECONDS = 4


def qualified_snapshot_path(base: Path, qualifier: str) -> Path:
    base = Path(base)
    return base.with_name(f"{base.stem}.{qualifier}{base.suffix}")


class CompetitionHTMLParser(HTMLParser):
    """Extracts competition options from the GMS competitions dropdown HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._in_select = False
        self._current_option: Optional[Dict[str, str]] = None
        self.options: List[Dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "select" and attrs_dict.get("name") == "comp_id":
            self._in_select = True
        elif self._in_select and tag == "option":
            value = (attrs_dict.get("value") or "").strip()
            if value:
                self._current_option = {
                    "compId": value,
                    "label": "",
                    "selected": "selected" in attrs_dict or attrs_dict.get("selected") is not None,
                }

    def handle_data(self, data):
        if self._current_option is not None:
            self._current_option["label"] += data

    def handle_endtag(self, tag):
        if tag == "select" and self._in_select:
            self._in_select = False
        elif tag == "option" and self._current_option is not None:
            self._current_option["label"] = self._current_option["label"].strip()
            self.options.append(self._current_option)
            self._current_option = None


class LeagueRowParser(HTMLParser):
    """Parses the league table HTML chunk to extract stats for a single team."""

    def __init__(self, team_id: str) -> None:
        super().__init__()
        self.target_team = team_id.lower()
        self.in_target_row = False
        self.in_cell = False
        self.current_cell_text = ""
        self.cells: List[str] = []
        self.league_name_chunks: List[str] = []
        self.capture_league_name = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "tr":
            classes = (attrs_dict.get("class") or "").split()
            data_team = (attrs_dict.get("data-team") or "").lower()
            self.in_target_row = (
                "gms-clubteam" in classes and data_team == self.target_team
            )
            if self.in_target_row:
                self.cells.clear()

        if self.in_target_row and tag == "td":
            self.in_cell = True
            self.current_cell_text = ""

        if tag in {"div", "p", "span"}:
            classes = (attrs_dict.get("class") or "").split()
            if "gms-footnote" in classes:
                self.capture_league_name = True

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell_text += data
        if self.capture_league_name:
            self.league_name_chunks.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.cells.append(self.current_cell_text.strip())
            self.in_cell = False
        if tag == "tr" and self.in_target_row:
            self.in_target_row = False
        if tag in {"div", "p", "span"} and self.capture_league_name:
            self.capture_league_name = False


def parse_league_table(html: str, team_id: str) -> Optional[Dict[str, str]]:
    parser = LeagueRowParser(team_id)
    parser.feed(html or "")
    if not parser.cells:
        return None

    def safe_get(index: int, default: str = "") -> str:
        return parser.cells[index] if index < len(parser.cells) else default

    league_name = "Unknown League"
    if parser.league_name_chunks:
        footnote_text = "".join(parser.league_name_chunks)
        league_name = footnote_text.strip() or league_name

    return {
        "position": safe_get(0),
        "teamName": safe_get(1),
        "played": safe_get(2, "0"),
        "won": safe_get(3, "0"),
        "drawn": safe_get(4, "0"),
        "lost": safe_get(5, "0"),
        "goalsFor": safe_get(6, "0"),
        "goalsAgainst": safe_get(7, "0"),
        "goalDiff": safe_get(8, "0"),
        "points": safe_get(9, "0"),
        "leagueName": league_name,
    }


def parse_competitions(html: str) -> List[Dict[str, str]]:
    parser = CompetitionHTMLParser()
    parser.feed(html or "")
    return parser.options


class TeamSummaryParser(HTMLParser):
    def __init__(self, team_id: str) -> None:
        super().__init__()
        self.target_team = team_id.lower()
        self.in_target_row = False
        self.in_cell = False
        self.current_text = ""
        self.cells: List[Dict[str, Optional[str]]] = []
        self.row_cells: List[Dict[str, Optional[str]]] = []
        self.form_entries: List[Dict[str, str]] = []
        self.current_forms: List[Dict[str, str]] = []
        self.in_form_span = False
        self.form_span_class = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "tr":
            data_team = (attrs_dict.get("data-team") or "").lower()
            self.in_target_row = data_team == self.target_team or (self.target_team == "" and "data-team" not in attrs_dict)
            if self.in_target_row:
                self.row_cells = []
        elif tag == "td" and self.in_target_row:
            self.in_cell = True
            self.current_text = ""
            self.current_forms = []
        elif tag == "span" and self.in_cell:
            classes = (attrs_dict.get("class") or "").split()
            if "gms-form" in classes:
                self.in_form_span = True
                self.form_span_class = " ".join(classes)

    def handle_data(self, data):
        if self.in_cell:
            self.current_text += data
        if self.in_form_span:
            result = data.strip()
            if result:
                self.current_forms.append({"result": result})

    def handle_endtag(self, tag):
        if tag == "span" and self.in_form_span:
            self.in_form_span = False
            self.form_span_class = ""
        elif tag == "td" and self.in_cell:
            cell_data = {"text": self.current_text.strip()}
            if self.current_forms:
                cell_data["forms"] = list(self.current_forms)
                self.form_entries = list(self.current_forms)
            self.row_cells.append(cell_data)
            self.in_cell = False
        elif tag == "tr" and self.in_target_row:
            self.cells = self.row_cells
            self.in_target_row = False


def parse_team_summary(html: str, team_id: str) -> Optional[Dict[str, Optional[str]]]:
    parser = TeamSummaryParser(team_id)
    parser.feed(html or "")
    if not parser.cells:
        return None

    def cell_text(index: int) -> str:
        return parser.cells[index].get("text", "") if index < len(parser.cells) else ""

    return {
        "teamName": cell_text(0),
        "played": cell_text(1),
        "won": cell_text(2),
        "drawn": cell_text(3),
        "lost": cell_text(4),
        "goalsFor": cell_text(5),
        "goalsAgainst": cell_text(6),
        "goalDiff": cell_text(7),
        "points": cell_text(8),
        "ppg": cell_text(9),
        "form": parser.form_entries,
    }


def select_competition(options: Sequence[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if not options:
        return None
    for option in options:
        if option.get("selected"):
            return option
    return options[0]


def save_json(payload, path: Path):
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def rotate_snapshots(
    new_snapshot: Path, current_snapshot: Path, previous_snapshot: Path
):
    new_snapshot = Path(new_snapshot)
    current_snapshot = Path(current_snapshot)
    previous_snapshot = Path(previous_snapshot)

    if not new_snapshot.exists():
        raise FileNotFoundError(f"New snapshot {new_snapshot} does not exist.")

    if current_snapshot.exists():
        previous_snapshot.parent.mkdir(parents=True, exist_ok=True)
        current_snapshot.replace(previous_snapshot)

    current_snapshot.parent.mkdir(parents=True, exist_ok=True)
    new_snapshot.replace(current_snapshot)


def make_entry_key(entry: Dict[str, str], index: int) -> str:
    team_id = entry.get("teamId") or f"team-{index}"
    comp_id = entry.get("compId") or f"comp-{index}"
    return f"{team_id}::{comp_id}"


def build_error_record(entry: Dict[str, str], message: str) -> Dict[str, str]:
    return {
        "name": entry.get("name") or "Unknown Team",
        "teamId": entry.get("teamId") or "",
        "compId": entry.get("compId") or "",
        "error": message,
    }


def build_team_record(entry: Dict[str, str], summary: Dict[str, Optional[str]]) -> Dict:
    name = entry.get("name") or summary.get("teamName") or "Unknown Team"
    team_id = entry.get("teamId")
    comp_id = entry.get("compId")
    record = {
        "name": name,
        "teamId": team_id,
        "teamDisplay": summary.get("teamName") or name,
        "competition": {
            "id": comp_id,
            "label": entry.get("compLabel"),
        },
        "stats": {
            "played": summary.get("played"),
            "won": summary.get("won"),
            "drawn": summary.get("drawn"),
            "lost": summary.get("lost"),
            "goalsFor": summary.get("goalsFor"),
            "goalsAgainst": summary.get("goalsAgainst"),
            "goalDiff": summary.get("goalDiff"),
            "points": summary.get("points"),
            "ppg": summary.get("ppg"),
        },
        "form": summary.get("form", []),
    }
    if entry.get("compLabel"):
        record["competition"]["label"] = entry["compLabel"]
    return record


def fetch_team_record(client: GMSClient, entry: Dict[str, str], index: int):
    name = entry.get("name") or f"Team {index}"
    team_id = entry.get("teamId")
    comp_id = entry.get("compId")

    if not team_id or not comp_id:
        return False, "Missing teamId or compId"

    try:
        summary = client.get_team_summary(team_id)
        team_name = (summary.get("teamName") or "").strip()
        if team_name.lower() == "st albans (m)":
            summary["teamName"] = "St Albans 1"
        record = build_team_record(entry, summary)
        return True, record
    except Exception as exc:  # pragma: no cover - diagnostic
        return False, f"{name}: {exc}"


def deep_copy_record(record: Dict) -> Dict:
    return json.loads(json.dumps(record))


def attach_snapshot_meta(record: Dict, snapshot_date: Optional[str]):
    if snapshot_date:
        record.setdefault("meta", {})
        record["meta"]["snapshotDate"] = snapshot_date


def load_fallback_map(path: Path) -> Dict[str, Dict]:
    if not Path(path).exists():
        return {}
    try:
        with Path(path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    fallback = {}
    for item in data:
        team_id = item.get("teamId")
        if team_id:
            fallback[team_id] = item
    return fallback


def read_snapshot(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Snapshot not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Snapshot {path} must contain a list of team records.")
    return data


def analyze_snapshot(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    team_ids = [record.get("teamId") for record in records if record.get("teamId")]
    error_entries = [record for record in records if record.get("error")]
    missing_ppg = [
        record
        for record in records
        if not (record.get("stats") or {}).get("ppg") and not record.get("error")
    ]
    return {
        "count": len(records),
        "team_ids": set(team_ids),
        "errors": error_entries,
        "missing_ppg": missing_ppg,
    }


def command_validate_snapshots(
    current_path: Path, previous_path: Optional[Path], expected_count: Optional[int]
):
    current_records = read_snapshot(current_path)
    current_stats = analyze_snapshot(current_records)

    issues: List[str] = []
    if expected_count and current_stats["count"] != expected_count:
        issues.append(
            f"Current snapshot count {current_stats['count']} != expected {expected_count}"
        )
    if current_stats["errors"]:
        problem_names = ", ".join(
            (entry.get("name") or entry.get("teamId") or "Unknown")
            for entry in current_stats["errors"][:5]
        )
        issues.append(
            f"Current snapshot has {len(current_stats['errors'])} error entrie(s): {problem_names}"
        )
    if current_stats["missing_ppg"]:
        problem_names = ", ".join(
            (entry.get("name") or entry.get("teamId") or "Unknown")
            for entry in current_stats["missing_ppg"][:5]
        )
        issues.append(
            f"Current snapshot missing PPG for {len(current_stats['missing_ppg'])} team(s): {problem_names}"
        )

    previous_stats = None
    if previous_path and Path(previous_path).exists():
        previous_records = read_snapshot(previous_path)
        previous_stats = analyze_snapshot(previous_records)
        if expected_count and previous_stats["count"] != expected_count:
            issues.append(
                f"Previous snapshot count {previous_stats['count']} != expected {expected_count}"
            )
        missing_from_current = previous_stats["team_ids"] - current_stats["team_ids"]
        missing_from_previous = current_stats["team_ids"] - previous_stats["team_ids"]
        if missing_from_current:
            issues.append(
                f"Current snapshot missing {len(missing_from_current)} teamId(s) found in previous snapshot: "
                f"{', '.join(sorted(list(missing_from_current))[:5])}"
            )
        if missing_from_previous:
            issues.append(
                f"Previous snapshot missing {len(missing_from_previous)} teamId(s) present now: "
                f"{', '.join(sorted(list(missing_from_previous))[:5])}"
            )
    elif previous_path:
        issues.append(f"Previous snapshot not found at {previous_path}")

    if issues:
        print("Snapshot validation failed:")
        for issue in issues:
            print(f" - {issue}")
        raise SystemExit(1)

    print(
        f"Snapshot validation passed for {current_path} "
        f"({current_stats['count']} teams)."
    )
    if previous_stats:
        print(
            f"Previous snapshot {previous_path} looks consistent "
            f"({previous_stats['count']} teams)."
        )


class FixturesTableParser(HTMLParser):
    columns = ["date", "time", "homeTeam", "score", "awayTeam", "venue"]

    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_cells: List[Dict[str, Optional[str]]] = []
        self.current_text = ""
        self.current_class = ""
        self.current_href: Optional[str] = None
        self.rows: List[List[Dict[str, Optional[str]]]] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            classes = (attrs_dict.get("class") or "").split()
            self.in_table = "gms-table-results" in classes
        elif tag == "tbody" and self.in_table:
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_cells = []
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_text = ""
            self.current_class = attrs_dict.get("class", "")
            self.current_href = None
        elif tag == "a" and self.in_td:
            self.current_href = attrs_dict.get("href")

    def handle_data(self, data):
        if self.in_td:
            self.current_text += data

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            self.current_cells.append(
                {
                    "text": self.current_text.strip(),
                    "class": self.current_class,
                    "href": self.current_href,
                }
            )
            self.in_td = False
        elif tag == "tr" and self.in_tr:
            if self.current_cells:
                self.rows.append(self.current_cells)
            self.in_tr = False
        elif tag == "tbody" and self.in_tbody:
            self.in_tbody = False
        elif tag == "table" and self.in_table:
            self.in_table = False


def parse_results_and_fixtures(html: str) -> List[Dict[str, Optional[str]]]:
    parser = FixturesTableParser()
    parser.feed(html or "")
    fixtures = []

    for row_cells in parser.rows:
        row = {}
        for col_name, cell in zip(FixturesTableParser.columns, row_cells):
            row[col_name] = cell.get("text", "")
            if col_name == "score":
                row["scoreClass"] = cell.get("class", "")
            if col_name == "venue":
                row["venueLink"] = cell.get("href")
        fixtures.append(row)

    for fixture in fixtures:
        date_text = fixture.get("date", "")
        time_text = fixture.get("time", "")
        try:
            fixture_date = datetime.strptime(date_text, "%d %b %Y").date()
        except ValueError:
            fixture_date = None
        fixture["dateObj"] = fixture_date
        fixture["dateIso"] = fixture_date.isoformat() if fixture_date else None

        if fixture_date and time_text:
            try:
                fixture_dt = datetime.strptime(
                    f"{date_text} {time_text}", "%d %b %Y %H:%M"
                )
            except ValueError:
                fixture_dt = None
        else:
            fixture_dt = None
        fixture["dateTime"] = fixture_dt.isoformat() if fixture_dt else None

        score_class = fixture.get("scoreClass") or ""
        score_text = (fixture.get("score") or "").strip()
        if "gms-win" in score_class:
            status = "win"
        elif "gms-loss" in score_class:
            status = "loss"
        elif "gms-draw" in score_class:
            status = "draw"
        elif score_text:
            status = "result"
        else:
            status = "pending"
        fixture["status"] = status
        fixture["completed"] = status in {"win", "loss", "draw", "result"}

    return fixtures


def weekend_range(reference: Optional[str] = None) -> Tuple[date, date]:
    if reference:
        saturday = datetime.strptime(reference, "%Y-%m-%d").date()
    else:
        today = date.today()
        days_since_saturday = (today.weekday() - 5) % 7
        saturday = today - timedelta(days=days_since_saturday if days_since_saturday != 0 else 7)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday


@dataclass
class GMSClient:
    rate_limit_ms: int = 1200
    retry_limit: int = 4
    session: requests.Session = requests.Session()

    def __post_init__(self):
        self._next_allowed = 0.0

    def _respect_rate_limit(self):
        now = time.time()
        if now < self._next_allowed:
            sleep_for = self._next_allowed - now
            time.sleep(sleep_for)

    def _schedule_next_window(self, delay_ms: int):
        self._next_allowed = time.time() + delay_ms / 1000.0

    def _get(self, url: str) -> requests.Response:
        for attempt in range(1, self.retry_limit + 1):
            self._respect_rate_limit()
            response = self.session.get(url, timeout=20)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = int(retry_after) * 1000
                else:
                    delay = self.rate_limit_ms * (2 ** attempt)
                self._schedule_next_window(delay)
                if attempt == self.retry_limit:
                    response.raise_for_status()
                time.sleep(delay / 1000.0)
                continue

            response.raise_for_status()
            self._schedule_next_window(self.rate_limit_ms)
            return response
        raise RuntimeError("Failed to fetch after retries")

    def get_competitions_for_team(self, team_id: str) -> List[Dict[str, str]]:
        url = GMS_COMPETITIONS_URL.format(team_id=team_id.strip())
        data = self._get(url).json()
        return parse_competitions(data.get("html", ""))

    def get_team_row(self, team_id: str, comp_id: str) -> Dict[str, str]:
        url = build_show_url("league", team_id, comp_id)
        data = self._get(url).json()
        parsed = parse_league_table(data.get("html", ""), team_id)
        if not parsed:
            raise ValueError(f"Team {team_id} not found in competition {comp_id}")
        return parsed

    def get_team_summary(
        self, team_id: str, comp_id: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        url = build_show_url("league", team_id, comp_id)
        data = self._get(url).json()
        parsed = parse_team_summary(data.get("html", ""), team_id)
        if not parsed:
            raise ValueError("Unable to parse team summary table")
        if comp_id:
            parsed["compId"] = comp_id
        return parsed

    def get_results_and_fixtures(
        self, team_id: str, comp_id: str
    ) -> List[Dict[str, Optional[str]]]:
        url = build_show_url("results+fixtures", team_id, comp_id)
        data = self._get(url).json()
        return parse_results_and_fixtures(data.get("html", ""))


def load_team_file(team_file: Path) -> List[Dict[str, str]]:
    team_file = resolve_repo_path(team_file)
    with team_file.open("r", encoding="utf-8") as fh:
        teams = json.load(fh)
        if not isinstance(teams, list):
            raise ValueError("teamIDs.json must contain a list of objects")
        return teams


def command_competitions(team_file: Path, output_file: Path):
    client = GMSClient()
    teams = load_team_file(team_file)
    output = []

    for idx, entry in enumerate(teams, start=1):
        team_id = entry.get("teamId")
        name = entry.get("name") or f"Team {idx}"

        if not team_id:
            output.append({"name": name, "error": "Missing teamId"})
            continue

        try:
            competitions = client.get_competitions_for_team(team_id)
            selected = select_competition(competitions)
            record = {
                "name": name,
                "teamId": team_id,
                "competitions": competitions,
            }
            if selected:
                record["compId"] = selected["compId"]
                record["compLabel"] = selected["label"]
            output.append(record)
        except Exception as exc:  # pragma: no cover - diagnostic
            output.append({"name": name, "teamId": team_id, "error": str(exc)})

    save_json(output, output_file)
    print(json.dumps(output, indent=2))
    print(f"\nSaved {len(output)} entries to {output_file.resolve()}")


def command_team_data(team_id: str, comp_id: str):
    client = GMSClient()
    data = client.get_team_row(team_id, comp_id)
    print(json.dumps(data, indent=2))


def command_team_summary(
    team_id: str, comp_id: Optional[str], output_file: Optional[Path]
):
    client = GMSClient()
    data = client.get_team_summary(team_id, comp_id)
    print(json.dumps(data, indent=2))
    if output_file:
        save_json(data, output_file)
        print(f"\nSaved team summary to {output_file.resolve()}")


def weekend_fixtures(fixtures: List[Dict[str, Optional[str]]], start: date, end: date):
    return [
        fixture
        for fixture in fixtures
        if fixture.get("dateObj") and start <= fixture["dateObj"] <= end
    ]


def serialize_fixtures(fixtures: List[Dict[str, Optional[str]]]):
    serializable = []
    for fixture in fixtures:
        copy_fixture = dict(fixture)
        copy_fixture.pop("dateObj", None)
        serializable.append(copy_fixture)
    return serializable


def command_recent_results(
    team_id: str, comp_id: str, weekend_str: Optional[str], output_file: Optional[Path]
):
    client = GMSClient()
    fixtures = client.get_results_and_fixtures(team_id, comp_id)
    start, end = weekend_range(weekend_str)
    selected = weekend_fixtures(fixtures, start, end)

    payload = {
        "teamId": team_id,
        "compId": comp_id,
        "weekend": {"start": start.isoformat(), "end": end.isoformat()},
        "fixtures": serialize_fixtures(selected),
    }

    print(json.dumps(payload, indent=2))
    if output_file:
        save_json(payload, output_file)
        print(f"\nSaved weekend results to {output_file.resolve()}")


def command_bulk_team_data(
    config_file: Path,
    output_file: Path,
    publish_path: Optional[Path] = None,
    previous_path: Optional[Path] = None,
    rotate: bool = False,
    snapshot_date: Optional[str] = None,
):
    config_file = resolve_repo_path(config_file)
    output_file = resolve_repo_path(output_file)
    publish_path = resolve_repo_path(publish_path) if publish_path else Path(output_file)
    if previous_path:
        previous_path = resolve_repo_path(previous_path)
    else:
        previous_path = qualified_snapshot_path(publish_path, "prev")

    target_output = Path(output_file)
    auto_snapshot = False
    if rotate and target_output == publish_path:
        target_output = qualified_snapshot_path(publish_path, "new")
        auto_snapshot = True

    client = GMSClient()
    teams = load_team_file(config_file)

    ordered_entries = []
    records_by_key: Dict[str, Dict] = {}
    errors_by_key: Dict[str, Dict] = {}

    for idx, entry in enumerate(teams, start=1):
        key = make_entry_key(entry, idx)
        ordered_entries.append({"key": key, "entry": entry, "index": idx})
        success, payload = fetch_team_record(client, entry, idx)
        if success:
            attach_snapshot_meta(payload, snapshot_date)
            records_by_key[key] = payload
        else:
            errors_by_key[key] = {"entry": entry, "index": idx, "message": payload}

    if errors_by_key:
        print(f"Initial fetch missing {len(errors_by_key)} teams, retrying...")
    for attempt in range(1, VALIDATION_MAX_RETRIES + 1):
        if not errors_by_key:
            break
        time.sleep(VALIDATION_BACKOFF_SECONDS * attempt)
        pending_keys = list(errors_by_key.keys())
        for key in pending_keys:
            context = errors_by_key[key]
            success, payload = fetch_team_record(
                client, context["entry"], context["index"]
            )
            if success:
                attach_snapshot_meta(payload, snapshot_date)
                records_by_key[key] = payload
                del errors_by_key[key]
            else:
                errors_by_key[key]["message"] = payload

    fallback_used: List[str] = []
    if errors_by_key and publish_path.exists():
        fallback_map = load_fallback_map(publish_path)
        if fallback_map:
            for key in list(errors_by_key.keys()):
                entry = errors_by_key[key]["entry"]
                team_id = entry.get("teamId")
                if not team_id:
                    continue
                fallback_record = fallback_map.get(team_id)
                if fallback_record:
                    record_copy = deep_copy_record(fallback_record)
                    meta = record_copy.setdefault("meta", {})
                    meta["source"] = "fallback"
                    meta["fallbackSnapshot"] = str(publish_path)
                    meta["fallbackAppliedAt"] = datetime.utcnow().isoformat()
                    attach_snapshot_meta(record_copy, snapshot_date)
                    records_by_key[key] = record_copy
                    fallback_used.append(entry.get("name") or team_id)
                    del errors_by_key[key]

    results = []
    for item in ordered_entries:
        key = item["key"]
        entry = item["entry"]
        if key in records_by_key:
            results.append(records_by_key[key])
        else:
            message = errors_by_key.get(key, {}).get("message", "Unknown error")
            results.append(build_error_record(entry, message))

    save_json(results, target_output)
    print(json.dumps(results, indent=2))
    print(f"\nSaved {len(results)} team records to {target_output.resolve()}")

    if fallback_used:
        print(
            f"Used {len(fallback_used)} fallback record(s) from {publish_path} "
            f"for: {', '.join(fallback_used)}"
        )

    if rotate:
        if errors_by_key:
            print(
                "Skipping snapshot rotation because some teams could not be fetched: "
                f"{len(errors_by_key)} remaining."
            )
        else:
            rotate_snapshots(target_output, publish_path, previous_path)
            print(
                "Snapshot rotation complete:\n"
                f"  current → previous: {publish_path.name} → {previous_path.name}\n"
                f"  new → current: {target_output.name} → {publish_path.name}"
            )
            if auto_snapshot:
                print(
                    f"(Auto-created {target_output.name} as staging snapshot before rotation.)"
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Work with England Hockey GMS data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    comp_parser = subparsers.add_parser("competitions", help="Fetch comp IDs for every team")
    comp_parser.add_argument(
        "--team-file",
        type=Path,
        default=DEFAULT_TEAM_FILE,
        help=f"Path to teamIDs.json (default: {DEFAULT_TEAM_FILE})",
    )
    comp_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_COMP_OUTPUT,
        help=f"Where to save the merged team/competition JSON (default: {DEFAULT_COMP_OUTPUT})",
    )

    data_parser = subparsers.add_parser("team-data", help="Fetch league stats for a team")
    data_parser.add_argument("--team-id", required=True, help="Team UUID")
    data_parser.add_argument("--comp-id", required=True, help="Competition UUID")

    summary_parser = subparsers.add_parser(
        "team-summary", help="Fetch the summary league table for a team"
    )
    summary_parser.add_argument("--team-id", required=True, help="Team UUID")
    summary_parser.add_argument(
        "--comp-id",
        help="Optional competition UUID (omit to pull cross-competition summary)",
    )
    summary_parser.add_argument(
        "--output", type=Path, help="Optional file to save the summary JSON"
    )

    bulk_parser = subparsers.add_parser(
        "bulk-team-data", help="Fetch league stats for every team in the saved config"
    )
    bulk_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_COMP_OUTPUT,
        help=f"Path to the team/competition config JSON (default: {DEFAULT_COMP_OUTPUT})",
    )
    bulk_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_TEAM_DATA_OUTPUT,
        help=f"Where to write the freshly fetched JSON (default: {DEFAULT_TEAM_DATA_OUTPUT})",
    )
    bulk_parser.add_argument(
        "--publish-path",
        type=Path,
        help="Where to publish the rotated snapshot (defaults to --output).",
    )
    bulk_parser.add_argument(
        "--previous-path",
        type=Path,
        help="Where to archive the previous snapshot (defaults to <publish>.prev.json).",
    )
    bulk_parser.add_argument(
        "--rotate-snapshots",
        action="store_true",
        help=(
            "After successful fetch, move the existing publish file to the previous "
            "path and promote the new output to the publish path."
        ),
    )
    bulk_parser.add_argument(
        "--snapshot-date",
        help="Optional ISO date/tag to store inside each exported record's metadata.",
    )

    recent_parser = subparsers.add_parser(
        "recent-results",
        help="Fetch most recent weekend fixture(s) for a given team",
    )
    recent_parser.add_argument("--team-id", required=True, help="Team UUID")
    recent_parser.add_argument("--comp-id", required=True, help="Competition UUID")
    recent_parser.add_argument(
        "--weekend",
        help="Weekend reference date (YYYY-MM-DD, Saturday). Defaults to last weekend.",
    )
    recent_parser.add_argument(
        "--output",
        type=Path,
        help="Optional file to save the weekend fixtures JSON",
    )

    validate_parser = subparsers.add_parser(
        "validate-snapshots", help="Validate snapshot files before publishing"
    )
    validate_parser.add_argument(
        "--current",
        type=Path,
        default=DEFAULT_TEAM_DATA_OUTPUT,
        help=f"Path to the current snapshot JSON (default: {DEFAULT_TEAM_DATA_OUTPUT})",
    )
    validate_parser.add_argument(
        "--previous",
        type=Path,
        default=DEFAULT_TEAM_DATA_PREVIOUS,
        help=f"Optional path to the previous snapshot JSON (default: {DEFAULT_TEAM_DATA_PREVIOUS})",
    )
    validate_parser.add_argument(
        "--expect-count",
        type=int,
        help="Expected number of team entries; validation fails if counts differ.",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "competitions":
        command_competitions(args.team_file, args.output)
    elif args.command == "team-data":
        command_team_data(args.team_id, args.comp_id)
    elif args.command == "team-summary":
        command_team_summary(args.team_id, args.comp_id, args.output)
    elif args.command == "bulk-team-data":
        command_bulk_team_data(
            args.config,
            args.output,
            args.publish_path,
            args.previous_path,
            args.rotate_snapshots,
            args.snapshot_date,
        )
    elif args.command == "recent-results":
        command_recent_results(args.team_id, args.comp_id, args.weekend, args.output)
    elif args.command == "validate-snapshots":
        command_validate_snapshots(args.current, args.previous, args.expect_count)


if __name__ == "__main__":
    main()


