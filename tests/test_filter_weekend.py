import re
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from pytz import UTC

# Import scripts/filter.py as a module via its file path so tests
# don't rely on the package name resolution.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FILTER_PATH = PROJECT_ROOT / "scripts" / "filter.py"

spec = importlib.util.spec_from_file_location("filter_script", FILTER_PATH)
assert spec and spec.loader, "Could not load scripts/filter.py"
filter_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(filter_script)  # type: ignore[arg-type]


def _run_with_fixed_now(now_iso: str):
    """
    Helper to run filter_weekend_fixtures with a fixed 'today' value.

    We monkeypatch scripts.filter.datetime.now so the weekend calculation
    uses a deterministic reference point, then capture the printed range.
    """
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            base = datetime.fromisoformat(now_iso)
            if tz is not None:
                return base.astimezone(tz)
            # default to UTC if no tz provided
            return base.replace(tzinfo=UTC)

    # Craft a single dummy fixture so the function runs its loop
    fixtures = [
        {
            "date": now_iso,
            "team": "Men's 1s",
            "competition": "Men",
            "division": "Prem",
            "home_team": "Men's 1s",
            "away_team": "Opposition",
            "kickoff": "12:00",
            "location": "Home",
            "ha": "h",
            "competitionId": "l",
            "status": "Scheduled",
            "fixtureId": "123",
        }
    ]

    original_datetime = filter_script.datetime
    try:
        # Patch the datetime class used in the module
        filter_script.datetime = FixedDateTime  # type: ignore[assignment]
        # Capture the printed range line
        captured = []

        def fake_print(msg):
            captured.append(str(msg))

        # run, with print monkeypatched
        filter_script.print = fake_print  # type: ignore[assignment]
        filter_script.filter_weekend_fixtures(fixtures)
    finally:
        filter_script.datetime = original_datetime  # type: ignore[assignment]
        # best effort: restore print; not critical in tests, but polite

    # Find the "Filtering for fixtures between ..." line
    for line in captured:
        if "Filtering for fixtures between" in line:
            return line
    raise AssertionError("Did not capture weekend range log line")


@pytest.mark.parametrize(
    "today_iso, expected_range_start_date",
    [
        # Saturday 2025-11-29 -> anchor Saturday is 29th, range_start is 28th 22:00 (logged as 2025-11-28)
        ("2025-11-29T10:00:00+00:00", "2025-11-28"),
        # Sunday 2025-11-30 -> anchor Saturday is 29th, same range_start date
        ("2025-11-30T10:00:00+00:00", "2025-11-28"),
        # Tuesday 2025-12-02 -> upcoming Saturday is 6th, range_start date is 5th
        ("2025-12-02T10:00:00+00:00", "2025-12-05"),
    ],
)
def test_filter_weekend_uses_current_weekend(today_iso, expected_range_start_date):
    """
    Ensure that the weekend range anchor behaves as expected:
    - Saturday: same-day Saturday
    - Sunday: previous-day Saturday (current weekend)
    - Weekday: upcoming Saturday
    """
    log_line = _run_with_fixed_now(today_iso)

    # Extract the first datetime from the log line
    m = re.search(r"between ([^ ]+)", log_line)
    assert m, f"Could not parse range from: {log_line}"
    start_str = m.group(1)

    # The logged value is the date part of range_start, which is always
    # two hours before the anchor Saturday (i.e. usually the Friday date).
    assert start_str == expected_range_start_date, (
        f"For today={today_iso}, expected logged range_start date "
        f"{expected_range_start_date}, got {start_str}"
    )


