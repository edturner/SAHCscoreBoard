import json
from datetime import datetime, timedelta
import argparse
from bs4 import BeautifulSoup
from pytz import UTC 
import csv
from typing import Set

def extract_json_from_html(html_file):
    """
    Extract JSON data from an HTML file.
    
    Args:
        html_file (str): Path to the HTML file containing the JSON data
    
    Returns:
        dict: Parsed JSON data
    """
    try:
        # Open and read the HTML file
        with open(html_file, 'r') as file:
            soup = BeautifulSoup(file, 'html.parser')

        # Find the <script> tag with the id "__NEXT_DATA__"
        script_tag = soup.find('script', id='__NEXT_DATA__', type='application/json')

        if not script_tag:
            print("Error: JSON data not found in HTML")
            return {}

        # Parse the JSON data from the script tag's content
        json_data = json.loads(script_tag.string)
        return json_data
    except Exception as e:
        print(f"Error reading HTML or extracting JSON: {str(e)}")
        return {}

def save_json_to_file(json_data, file_name):
    """
    Save JSON data to a file for inspection.
    
    Args:
        json_data (dict): JSON data to save
        file_name (str): The name of the file to save the data to
    """
    try:
        with open(file_name, 'w') as f:
            json.dump(json_data, f, indent=4)
        print(f"JSON data saved to {file_name}")
    except Exception as e:
        print(f"Error saving JSON to file: {str(e)}")

def extract_fixtures(json_data):
    """
    Extract fixture information from the provided JSON data.
    
    Args:
        json_data (dict): Dictionary containing fixture data
    
    Returns:
        list: List of dictionaries containing relevant fixture information
    """
    try:
        fixtures = []
        
        # Debug: save the full JSON structure to a file for inspection
        save_json_to_file(json_data, 'full_json_data.json')

        # Access the relevant section of the JSON
        currently_loaded = json_data.get('props', {}).get('initialReduxState', {}).get('calendar', {}).get('currentlyLoaded', {})

        # Iterate through each key in currentlyLoaded (each fixture identifier)
        for key, value in currently_loaded.items():
            # For each item in 'days', check if it contains fixtures
            for day in value.get('days', []):
                # Extract fixtures if present
                for fixture in day.get('fixtures', []):
                    # Safely parse score values coming from the feed (often strings)
                    def _parse_score(raw_score):
                        try:
                            return int(raw_score)
                        except (TypeError, ValueError):
                            return None

                    fixture_info = {
                        'date': fixture.get('dateTime'),
                        'team': fixture.get('teamName'),
                        'competition': fixture.get('type'),
                        'division': fixture.get('division'),
                        'home_team': fixture.get('homeSide', {}).get('name'),
                        'away_team': fixture.get('awaySide', {}).get('name'),
                        'kickoff': fixture.get('kickoff'),
                        'location': fixture.get('location'),
                        'ha': fixture.get('ha'),
                        'competitionId': fixture.get('competitionId'),
                        'status': 'Cancelled/Postponed' if fixture.get('isCancelledOrPostponed') else 'Scheduled',
                        'fixtureId': fixture.get('id'),
                        'home_score': _parse_score(fixture.get('homeSide', {}).get('score')),
                        'away_score': _parse_score(fixture.get('awaySide', {}).get('score'))
                    }
                    fixtures.append(fixture_info)

        return fixtures
    except Exception as e:
        print(f"Error processing data: {str(e)}")
        return []


def is_kids_fixture(fixture):
    """
    Determine whether a fixture should be considered a kids fixture.

    Rules:
    - division is None
    - either home or away team name contains 'u18' or 'u16' (case-insensitive)
    """
    division_is_null = fixture.get('division') is None

    home = (fixture.get('home_team') or '').lower()
    away = (fixture.get('away_team') or '').lower()

    contains_age_band = ('u18' in home) or ('u16' in home) or ('u18' in away) or ('u16' in away)

    return division_is_null or contains_age_band


def has_tbc_kickoff(fixture):
    """Return True if kickoff is 'TBC' (case-insensitive)."""
    kickoff = fixture.get('kickoff')
    if kickoff is None:
        return False
    return str(kickoff).strip().lower() == 'tbc'


def filter_weekend_fixtures(fixtures):
    """
    Filter fixtures to include only those on Saturday and Sunday of this week.
    """
    from datetime import timezone

    weekend_fixtures = []
    today = datetime.now(UTC)

    # Calculate the Saturday of the relevant weekend in UTC
    # On Sunday, still use the current weekend (yesterday's Saturday)
    if today.weekday() == 6:  # Sunday
        saturday_utc = (today - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif today.weekday() == 5:  # Saturday
        saturday_utc = today.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Monday-Friday: find the upcoming Saturday of this week
        days_ahead = (5 - today.weekday()) % 7
        saturday_utc = (today + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

    monday_utc = saturday_utc + timedelta(days=2)

    # Adjust for BST/GMT - extend range to catch fixtures in local time
    range_start = saturday_utc - timedelta(hours=2)  # Covers BST (UTC+1) and future UTC+2
    range_end = monday_utc + timedelta(hours=2)

    print(f"Filtering for fixtures between {range_start} and {range_end}")

    for fixture in fixtures:
        # Exclude kids fixtures
        if is_kids_fixture(fixture):
            continue
        # Exclude fixtures with TBC kickoff
        if has_tbc_kickoff(fixture):
            continue
        fixture_datetime = datetime.fromisoformat(fixture['date']).astimezone(UTC)
        if range_start <= fixture_datetime < range_end:
            weekend_fixtures.append(fixture)

    return weekend_fixtures

def load_exclusions(exclusions_path: str = 'exclusions.json') -> Set[str]:
    """Load a set of fixture IDs to exclude from output. Supports either a JSON array of IDs
    or an object with key "fixtureIds": [ ... ]. Missing file -> empty set.
    """
    try:
        with open(exclusions_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(x) for x in data}
        if isinstance(data, dict) and 'fixtureIds' in data and isinstance(data['fixtureIds'], list):
            return {str(x) for x in data['fixtureIds']}
    except FileNotFoundError:
        return set()
    except Exception:
        return set()

def apply_exclusions(fixtures, excluded_ids: Set[str]):
    """Return fixtures excluding any whose fixtureId is in excluded_ids."""
    if not excluded_ids:
        return fixtures
    filtered = []
    for fixture in fixtures:
        fixture_id = fixture.get('fixtureId')
        if fixture_id is None:
            filtered.append(fixture)
            continue
        if str(fixture_id) in excluded_ids:
            continue
        filtered.append(fixture)
    return filtered
def print_fixtures(fixtures):
    """
    Print fixture information in a readable format.
    
    Args:
        fixtures (list): List of fixture dictionaries
    """
    if not fixtures:
        print("No fixtures found")
        return
        
    for fixture in fixtures:
        print("\n=== Fixture Details ===")
        print(f"Date: {fixture['date']}")
        print(f"Team: {fixture['team']}")
        print(f"Competition: {fixture['competition']}")
        print(f"Division: {fixture['division']}")
        print(f"Match: {fixture['home_team']} vs {fixture['away_team']}")
        print(f"Kickoff: {fixture['kickoff']}")
        print(f"Location: {fixture['location'] or 'TBC'}")
        print(f"ha: {fixture['ha']}")
        print(f"CompetitionID: {fixture['competitionId']}")
        print(f"Status: {fixture['status']}")
        # Optional score and fixture id
        if fixture.get('home_score') is not None or fixture.get('away_score') is not None:
            print(f"Score: {fixture.get('home_score') if fixture.get('home_score') is not None else '-'} - {fixture.get('away_score') if fixture.get('away_score') is not None else '-'}")
        if fixture.get('fixtureId'):
            print(f"FixtureID: {fixture.get('fixtureId')}")


def process_fixtures(fixtures):
    # Separate men's and women's fixtures based on competition name
    mens_fixtures = []
    womens_fixtures = []

    for fixture in fixtures:
        competition = fixture['competition'].lower() if fixture['competition'] else ''

        # Check competition name to determine gender
        if "women" in competition:
            womens_fixtures.append(fixture)
        elif "men" in competition:
            mens_fixtures.append(fixture)
        else:
            # If unclear, check team name as fallback
            team_name = fixture['team']
            if team_name.startswith("Men's"):
                mens_fixtures.append(fixture)
            elif team_name.startswith("Women's"):
                womens_fixtures.append(fixture)
            else:
                # Default to men's if still unclear
                mens_fixtures.append(fixture)

    # Sort fixtures by team number
    def get_team_number(fixture):
        try:
            return int(''.join(filter(str.isdigit, fixture['team'])))
        except ValueError:
            return float('inf')

    mens_fixtures.sort(key=get_team_number)
    womens_fixtures.sort(key=get_team_number)

    # Write to CSV files
    def write_to_csv(fixtures, filename):
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Team', 'Opponent', 'Match_Time', 'Location', 'Division'])

            for fixture in fixtures:
                team_name = fixture['team']
                opponent = fixture['away_team'] if fixture['ha'] == 'h' else fixture['home_team']
                location = 'Home' if fixture['ha'] == 'h' else 'Away'
                division = 'Friendly' if fixture['competitionId'] == 'f' else fixture['division']

                writer.writerow([
                    team_name,
                    opponent,
                    fixture['kickoff'],
                    location,
                    division
                ])

    write_to_csv(mens_fixtures, 'mens_fixtures.csv')
    write_to_csv(womens_fixtures, 'womens_fixtures.csv')
    print(f"Created mens_fixtures.csv with {len(mens_fixtures)} fixtures")
    print(f"Created womens_fixtures.csv with {len(womens_fixtures)} fixtures")


    def get_team_number(fixture):
        try:
            return int(''.join(filter(str.isdigit, fixture['team'])))
        except ValueError:
            return float('inf')

    mens_fixtures.sort(key=get_team_number)
    womens_fixtures.sort(key=get_team_number)


def generate_json_output(fixtures, output_filename='weekend_fixtures.json'):
    """
    Generate JSON output with fixtures separated into home and away categories.

    Args:
        fixtures (list): List of fixture dictionaries
        output_filename (str): Name of the JSON file to create
    """
    home_fixtures = []
    away_fixtures = []

    for fixture in fixtures:
        competition = fixture['competition'].lower() if fixture['competition'] else ''

        # Determine category (men/women)
        if "women" in competition or "girls" in competition:
            category = "women"
        elif "men" in competition or "boys" in competition:
            category = "men"
        else:
            category = "men"  # default

        # Create fixture object
        fixture_obj = {
            "date": fixture['date'],
            "team": fixture['team'],
            "category": category,
            "home_team": fixture['home_team'],
            "away_team": fixture['away_team'],
            "kickoff": fixture['kickoff'],
            "division": fixture['division'] if fixture['division'] else "Friendly",
            "location": "Home" if fixture['ha'] == 'h' else "Away",
            "status": fixture['status'],
            "fixtureId": fixture.get('fixtureId'),
            "home_score": fixture.get('home_score'),
            "away_score": fixture.get('away_score')
        }

        # Add to home or away list
        if fixture['ha'] == 'h':
            home_fixtures.append(fixture_obj)
        else:
            away_fixtures.append(fixture_obj)

    # Create final JSON structure
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "home": home_fixtures,
        "away": away_fixtures
    }

    # Write to file
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Created {output_filename} with {len(home_fixtures)} home and {len(away_fixtures)} away fixtures")


def filter_by_date_range(fixtures, start_date_str, end_date_str):
    """
    Filter fixtures by a provided inclusive date range (local UK weekend style input dd/mm/YYYY).
    We expand the range by +/-2 hours in UTC to account for BST/GMT offsets in source times.
    """
    try:
        start_date = datetime.strptime(start_date_str, "%d/%m/%Y").date()
        end_date = datetime.strptime(end_date_str, "%d/%m/%Y").date()
    except ValueError:
        print("Invalid date format. Please use dd/mm/YYYY.")
        return []

    # Inclusive end: move to next day 00:00 then extend by +2h
    range_start = datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC) - timedelta(hours=2)
    range_end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC) + timedelta(days=1, hours=2)

    print(f"Filtering for fixtures between {range_start} and {range_end} (by date range)")

    filtered = []
    for fixture in fixtures:
        # Exclude kids fixtures
        if is_kids_fixture(fixture):
            continue
        # Exclude fixtures with TBC kickoff
        if has_tbc_kickoff(fixture):
            continue
        try:
            fixture_datetime = datetime.fromisoformat(fixture['date']).astimezone(UTC)
        except Exception:
            continue
        if range_start <= fixture_datetime < range_end:
            filtered.append(fixture)
    return filtered

if __name__ == "__main__":
    import os

    parser = argparse.ArgumentParser(description="Extract and filter fixtures (weekend or date range)")
    parser.add_argument("--start", type=str, help="Start date dd/mm/YYYY", required=False)
    parser.add_argument("--end", type=str, help="End date dd/mm/YYYY", required=False)
    parser.add_argument("--output", type=str, help="Output JSON filename", default='weekend_fixtures.json')
    args = parser.parse_args()

    # Find the most recent matches_data file
    matches_files = [f for f in os.listdir('.') if f.startswith('matches_data_') and f.endswith('.html')]

    if not matches_files:
        html_file = 'matches_data.html'
    else:
        html_file = max(matches_files, key=os.path.getctime)

    print(f"Using file: {html_file}")

    # Extract the JSON data from the HTML file
    json_data = extract_json_from_html(html_file)

    # If valid JSON data is extracted, process and print fixtures
    if json_data:
        fixtures = extract_fixtures(json_data)
        if args.start and args.end:
            selected = filter_by_date_range(fixtures, args.start, args.end)
        else:
            selected = filter_weekend_fixtures(fixtures)
        # Apply persistent exclusions (by fixtureId) if present
        excluded_ids = load_exclusions()
        if excluded_ids:
            selected = apply_exclusions(selected, excluded_ids)
        print_fixtures(selected)
        process_fixtures(selected)
        generate_json_output(selected, output_filename=args.output)