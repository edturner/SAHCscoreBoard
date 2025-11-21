"""
Live League of Leagues Updater

Continuously fetches team data snapshots every 5 minutes to keep the League of Leagues
display up-to-date. Can run as a standalone service or be called periodically.

Usage:
    # Run continuously (every 5 minutes)
    python scripts/live_league_updater.py

    # Run once and exit
    python scripts/live_league_updater.py --once

    # Custom interval (in minutes)
    python scripts/live_league_updater.py --interval 10

    # Run with validation
    python scripts/live_league_updater.py --validate --expect-count 26
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"
LEAGUE_DATA_DIR = REPO_ROOT / "data" / "league"
GMS_FETCHER = REPO_ROOT / "scripts" / "gms_fetcher.py"
DEFAULT_CONFIG = CONFIG_DIR / "teamCompIDs.json"
DEFAULT_OUTPUT = LEAGUE_DATA_DIR / "teamData.json"
DEFAULT_PREVIOUS = LEAGUE_DATA_DIR / "teamData.prev.json"
DEFAULT_INTERVAL_MINUTES = 5


def run_fetch(validate: bool = False, expect_count: int | None = None) -> bool:
    """
    Run a single fetch cycle using gms_fetcher.py.

    Returns:
        True if successful, False otherwise
    """
    if not GMS_FETCHER.exists():
        print(f"ERROR: gms_fetcher.py not found at {GMS_FETCHER}", file=sys.stderr)
        return False

    if not DEFAULT_CONFIG.exists():
        print(
            f"ERROR: Config file not found at {DEFAULT_CONFIG}. Run 'gms_fetcher.py competitions' first.",
            file=sys.stderr,
        )
        return False

    # Generate snapshot date timestamp
    snapshot_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build the command
    cmd = [
        sys.executable,
        str(GMS_FETCHER),
        "bulk-team-data",
        "--config",
        str(DEFAULT_CONFIG),
        "--output",
        str(DEFAULT_OUTPUT),
        "--publish-path",
        str(DEFAULT_OUTPUT),
        "--previous-path",
        str(DEFAULT_PREVIOUS),
        "--rotate-snapshots",
        "--snapshot-date",
        snapshot_date,
    ]

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching team data...")
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print(f"ERROR: Fetch failed with return code {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False

        # Print output from gms_fetcher
        if result.stdout:
            print(result.stdout)

        # Run validation if requested
        if validate:
            validate_cmd = [
                sys.executable,
                str(GMS_FETCHER),
                "validate-snapshots",
                "--current",
                str(DEFAULT_OUTPUT),
                "--previous",
                str(DEFAULT_PREVIOUS),
            ]
            if expect_count:
                validate_cmd.extend(["--expect-count", str(expect_count)])

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Validating snapshots...")
            validate_result = subprocess.run(
                validate_cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            if validate_result.returncode != 0:
                print("ERROR: Validation failed", file=sys.stderr)
                if validate_result.stderr:
                    print(validate_result.stderr, file=sys.stderr)
                return False

            if validate_result.stdout:
                print(validate_result.stdout)

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetch completed successfully")
        return True

    except Exception as exc:
        print(f"ERROR: Exception during fetch: {exc}", file=sys.stderr)
        return False


def run_continuous(interval_minutes: int, validate: bool, expect_count: int | None):
    """Run fetch cycles continuously with the specified interval."""
    interval_seconds = interval_minutes * 60
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
        f"Starting live updater (interval: {interval_minutes} minutes)"
    )
    print("Press Ctrl+C to stop")

    try:
        while True:
            success = run_fetch(validate=validate, expect_count=expect_count)
            if not success:
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                    "Fetch failed, will retry at next interval"
                )

            # Wait for next interval
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Next fetch in {interval_minutes} minutes..."
            )
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Stopping updater")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Live League of Leagues updater - fetches team data snapshots periodically"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (useful for cron/scheduled tasks)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_MINUTES,
        help=f"Interval between fetches in minutes (default: {DEFAULT_INTERVAL_MINUTES})",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validation after each fetch",
    )
    parser.add_argument(
        "--expect-count",
        type=int,
        help="Expected number of teams for validation",
    )

    args = parser.parse_args()

    if args.once:
        success = run_fetch(validate=args.validate, expect_count=args.expect_count)
        sys.exit(0 if success else 1)
    else:
        run_continuous(
            interval_minutes=args.interval,
            validate=args.validate,
            expect_count=args.expect_count,
        )


if __name__ == "__main__":
    main()

