# SAHC ScoreBoard

![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

**Unified data pipeline, automation, and static assets for St Albans Hockey Club’s digital displays.**

---

## 🚀 About

SAHC ScoreBoard is a robust system designed to power the digital experience at St Albans Hockey Club. It seamlessly aggregates fixture data, league standings, and results to drive dynamic displays and web views (like the "League of Leagues").

## ✨ Features

*   **Scoreboard Fixtures**: Portrait layouts (1080×1920) for home and away screens that automatically refresh every five minutes.
*   **League of Leagues**: A combined men’s and women’s league table tracking weekly performance and ranking shifts.
*   **Automated Data Collection**: Python utilities and GitHub Actions keep JSON snapshots fresh without manual intervention.

## 🛠 Tech Stack

*   **Core**: Python 3.11+
*   **Frontend**: HTML5, CSS3, Vanilla JavaScript
*   **Automation**: GitHub Actions

---

## 🏁 Getting Started

### Prerequisites

*   Python 3.11 or higher

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/edturner/SAHCscoreBoard.git
    cd SAHCscoreBoard
    ```
2.  Install dependencies:
    ```bash
    pip install requests beautifulsoup4 pytz
    ```

### Running Locally

HTML files can be served via any static web server. For local development:

```bash
# Serve from the root directory
python -m http.server 8000
```
Visit `http://localhost:8000/apps/scoreboard/home.html` to view the displays.

> **Note**: When testing scripts locally, prefer using the existing `data/` directories to keep automation and manual runs aligned.

---

## 📂 Project Architecture

```
apps/
  scoreboard/        # Home/Away displays & fixture logic
  league/            # League of Leagues views & logic
  shared/            # Shared styles, fonts, and assets
config/              # Team and Competition IDs (GMS)
data/
  scoreboard/        # Generated fixture data, exclusions, and CSV exports
  league/            # League snapshots (current & previous)
  raw/               # Raw HTML dumps for debugging
docs/                # Detailed technical documentation
scripts/             # Core Python ETL scripts
.github/workflows/   # CI/CD Automation pipelines (Fixtures, Scores, League)
```

## 🔄 Pipelines

### Scoreboard (Fixtures & Results)
The scoreboard pipeline fetches data directly from the GMS API, filters it based on exclusions, and generates JSON for the frontend.
*   **Source**: England Hockey GMS API.
*   **Update Frequency**: Every 5 minutes (Sat/Sun) via `.github/workflows/fixtures.yml`.
*   **Core Script**: `scripts/gms_fetcher.py update-scoreboard`.

### League of Leagues
Weekly aggregation of team performance across all leagues, highlighting movement and stats.
*   **Source**: GMS (Game Management System) API.
*   **Update Frequency**: Weekly + Live updates during match days via `.github/workflows/league-live.yml`.
*   **Core Script**: `scripts/gms_fetcher.py`.

---

## 📚 Documentation
For deeper dives into specific components, check out the `docs/` directory:
*   [Scoreboard Workflow](docs/scoreboard.md) – Ingestion, exclusion rules, and manual overrides.
*   [League Pipeline](docs/league.md) – Weekly checklist for the League of Leagues.
*   [Data Workflow & Retries](docs/league-data-workflow.md) – API behavior and retry strategies.

---

## 🤝 Contributing
Contributions are welcome! Please ensure you test local scripts before submitting a PR.
